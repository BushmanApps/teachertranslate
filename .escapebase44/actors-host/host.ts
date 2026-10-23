// EscapeBase44: the host that runs your Base44 Actors (realtime rooms) on
// your own server — the `actors` service in docker-compose.yml, and the
// same file `npm run dev` starts on a laptop or in the builder's sandbox.
//
// What it does, and what Base44's platform did in its place:
//   - accepts the WebSocket the SDK opens at /parties/<Actor>/<room>?_pk=…,
//     binds it to the principal the backend put in the connection token it
//     minted (POST /api/apps/<id>/actors/<Actor>/connection-token), or —
//     on the SDK's proxy-shaped URL — to the app user whose token rides
//     `token=`, else to an anonymous visitor
//   - runs each actor's code in its own isolate (worker.ts: no environment,
//     no files beyond its folder) and relays messages both ways; answers
//     the SDK's `__ping` heartbeat itself
//   - keeps every room's storage and armed schedules in the app's own
//     database (`_actor_storage`, `_actor_schedules`) and fires due
//     schedules, waking an evicted room
//   - mints the service token the actor's `this.client.asServiceRole` uses
//
// Env (the backend's own .env in production; `.env.local` in dev): APP_ID,
// MONGO_URL, MONGO_DB, SERVICE_JWT_SECRET, APP_JWT_SECRET,
// SERVICE_PRINCIPAL_ID; EB44_ACTORS_DIR (default base44/actors),
// EB44_ACTORS_PORT (default 9100), EB44_BACKEND_URL (default
// http://localhost:8000). Run with: deno run --allow-all
// --unstable-worker-options host.ts. Logs: `docker logs eb44-actors`.

import { MongoClient, type Collection } from "mongodb";
import { SignJWT, jwtVerify, decodeJwt } from "jose";
import type { ConnIdentity } from "./runtime.ts";

const env = (name: string, fallback?: string): string => {
  const v = Deno.env.get(name) ?? fallback;
  if (v === undefined) throw new Error(`${name} is not set`);
  return v;
};

// The actors folder may not exist yet (an app without actors still runs the
// host in dev); it is then served empty.
const ACTORS_DIR = (() => { const p = env("EB44_ACTORS_DIR", "base44/actors"); try { return Deno.realPathSync(p); } catch { return new URL(p, `file://${Deno.cwd()}/`).pathname; } })();
const PORT = Number(env("EB44_ACTORS_PORT", "9100"));
const BACKEND_URL = env("EB44_BACKEND_URL", "http://localhost:8000").replace(/\/$/, "");
const APP_ID = env("APP_ID");
const MONGO_URL = env("MONGO_URL");
const MONGO_DB = env("MONGO_DB");
const SERVICE_JWT_SECRET = env("SERVICE_JWT_SECRET");
const APP_JWT_SECRET = env("APP_JWT_SECRET");
const SERVICE_PRINCIPAL_ID = env("SERVICE_PRINCIPAL_ID");
const HOST_DIR = new URL(".", import.meta.url).pathname;
const DENO_DIR = env("DENO_DIR", `${env("HOME", "/root")}/.cache/deno`);
const CONNECTION_TOKEN_AUDIENCE = "eb44-actor-connect";
// A socket that has said nothing for this long is stale: a reconnect with
// its id supersedes it (Base44: ~6 s quiet → superseded, live → refused).
const LIVE_WINDOW_MS = 10_000;
const SERVICE_TOKEN_TTL_S = 3600;
// An empty room (no connection, no armed tick) is dropped after this long;
// the next connect is a cold start (`handleStart` again). Base44 evicts
// within ~90 s.
const IDLE_ROOM_TTL_MS = Number(env("EB44_ACTORS_IDLE_TTL_MS", "60000"));
const ACTOR_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

// Everything above is read; now the environment is scrubbed so the workers
// (which need environment access — the SDK's own dependencies enumerate it
// at import) inherit nothing of the app's secrets. Only what a runtime
// needs to find itself stays. The fork does the same to `os.environ` for
// its workflows engine.
const ENV_KEPT = new Set(["PATH", "HOME", "DENO_DIR", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "TZ", "NODE_ENV", "HOSTNAME"]);
for (const name of Object.keys(Deno.env.toObject())) if (!ENV_KEPT.has(name)) Deno.env.delete(name);
Deno.env.set("DENO_DIR", DENO_DIR);

// ── the actors on disk ──────────────────────────────────────────────────

interface ActorDef { name: string; entry: string; dir: string }

function discoverActors(): ActorDef[] {
  const found: ActorDef[] = [];
  let entries: Deno.DirEntry[] = [];
  try { entries = [...Deno.readDirSync(ACTORS_DIR)]; } catch { return found; }
  for (const e of entries) {
    if (!e.isDirectory || !ACTOR_NAME.test(e.name)) continue;
    const dir = `${ACTORS_DIR}/${e.name}`;
    const entry = ["entry.ts", "entry.js"].find((f) => { try { return Deno.statSync(`${dir}/${f}`).isFile; } catch { return false; } });
    if (entry) found.push({ name: e.name, entry, dir });
  }
  return found.sort((a, b) => a.name.localeCompare(b.name));
}

const actors = new Map(discoverActors().map((a) => [a.name, a]));

// The module cache is populated here, once, with the host's own rights —
// the worker runs with a read-only cache and no network to registries.
for (const a of actors.values()) {
  const cache = new Deno.Command(Deno.execPath(), {
    args: ["cache", "--config", `${HOST_DIR}deno.json`, `${a.dir}/${a.entry}`],
    stdout: "inherit", stderr: "inherit",
  }).outputSync();
  if (!cache.success) console.error(`[actors] ${a.name}: caching its imports failed (exit ${cache.code}) — it will fail to load`);
}

// ── storage + schedules in the app's own database ──────────────────────

const mongo = new MongoClient(MONGO_URL);
await mongo.connect();
const db = mongo.db(MONGO_DB);
type StorageDoc = { _id: string; actor: string; room: string; key: string; value: string };
type ScheduleDoc = { _id: string; actor: string; room: string; key: string; at: Date };
const storage: Collection<StorageDoc> = db.collection("_actor_storage");
const schedules: Collection<ScheduleDoc> = db.collection("_actor_schedules");
await schedules.createIndex({ at: 1 });
await storage.createIndex({ actor: 1, room: 1 });
const users = db.collection<{ _id: unknown; email?: string }>("User");

const storageKey = (actor: string, room: string, key: string) => `${actor}/${room}/${key}`;

// ── tokens ──────────────────────────────────────────────────────────────

const serviceKey = new TextEncoder().encode(SERVICE_JWT_SECRET);
const appKey = new TextEncoder().encode(APP_JWT_SECRET);

// The service token the actor's `asServiceRole` client sends — the shape
// the backend accepts from an automation fire (app/core/functions/
// service_token.py `mint_for_automation`).
async function mintServiceToken(): Promise<{ serviceToken: string; serviceTokenExpiresAt: number }> {
  const now = Math.floor(Date.now() / 1000);
  const token = await new SignJWT({
    sub: SERVICE_PRINCIPAL_ID, client_id: SERVICE_PRINCIPAL_ID, app_id: APP_ID, aud: "base44_api", scope: "app.access",
    exp: now + SERVICE_TOKEN_TTL_S, iat: now,
  }).setProtectedHeader({ alg: "HS256" }).sign(serviceKey);
  return { serviceToken: token, serviceTokenExpiresAt: (now + SERVICE_TOKEN_TTL_S) * 1000 };
}

type Principal = { identity: ConnIdentity } | { refuse: Response };

// Who is behind an upgrade request. Three token shapes, all measured on
// Base44 (2026-09-18): the backend's connection token (bound to this actor,
// room and connection id — anything else is 401), the SDK's proxy-path
// user token (the app user's own JWT → authenticated), and no/garbage
// token on the proxy path (anonymous, id = the connection id). No token on
// a mint-shaped request is 404 with Base44's own body.
async function principalFor(actorName: string, room: string, connId: string, token: string | null): Promise<Principal> {
  if (token) {
    try {
      const { payload } = await jwtVerify(token, serviceKey, { audience: CONNECTION_TOKEN_AUDIENCE });
      if (payload.app_id === APP_ID && payload.actor_name === actorName && payload.room === room && payload.connection_id === connId && payload.principal) {
        return { identity: payload.principal as ConnIdentity };
      }
      return { refuse: new Response("Unauthorized", { status: 401 }) };
    } catch {
      // Not our connection token: a mint-shaped token that fails is a
      // forgery/mismatch; anything else is a proxy-path credential.
      let mintShaped = false;
      try { mintShaped = decodeJwt(token).purpose === "actor-connect"; } catch { /* not a JWT at all */ }
      if (mintShaped) return { refuse: new Response("Unauthorized", { status: 401 }) };
    }
    try {
      const { payload } = await jwtVerify(token, appKey);
      const email = typeof payload.sub === "string" ? payload.sub : null;
      const user = email ? await users.findOne({ email }) : null;
      if (user) return { identity: { type: "authenticated", userId: String(user._id) } };
    } catch { /* garbage on the proxy path → anonymous, like Base44 */ }
  }
  return { identity: { type: "anonymous", anonymousId: connId } };
}

// ── workers (one per actor) ─────────────────────────────────────────────

interface Socket { ws: WebSocket; lastSeen: number; superseded: boolean }
interface RoomState { sockets: Map<string, Socket> }
interface ActorRuntime { worker: Worker; ready: Promise<void>; rooms: Map<string, RoomState> }

const runtimes = new Map<string, ActorRuntime>();

function roomOf(rt: ActorRuntime, room: string): RoomState {
  let state = rt.rooms.get(room);
  if (!state) { state = { sockets: new Map() }; rt.rooms.set(room, state); }
  return state;
}

async function runtimeFor(def: ActorDef): Promise<ActorRuntime> {
  const existing = runtimes.get(def.name);
  if (existing) return existing;
  const worker = new Worker(new URL("./worker.ts", import.meta.url).href, {
    type: "module",
    name: def.name,
    deno: {
      permissions: {
        // The environment is already scrubbed of every secret (above); the
        // SDK's dependencies read it at import, so it stays readable.
        env: true, run: false, write: false, ffi: false, sys: false,
        read: [ACTORS_DIR, HOST_DIR, DENO_DIR],
        net: [new URL(BACKEND_URL).host],
      },
    },
  });
  const rt: ActorRuntime = { worker, ready: Promise.resolve(), rooms: new Map() };
  rt.ready = new Promise<void>((resolve, reject) => {
    worker.onmessage = (ev: MessageEvent) => {
      const m = ev.data;
      if (m.kind === "ready") { resolve(); return; }
      handleWorkerMessage(def.name, rt, m).catch((err) => console.error(`[actors] ${def.name}: ${String(err)}`));
    };
    worker.onerror = (e) => {
      console.error(`[actors] ${def.name}: worker error: ${e.message}`);
      e.preventDefault();
      reject(new Error(e.message));
      // Every socket of every room of this actor is dropped; the next
      // connect spawns a fresh worker (a cold start, like an eviction).
      for (const [, state] of rt.rooms) for (const [, s] of state.sockets) try { s.ws.close(1011, "actor restarted"); } catch { /* closed */ }
      worker.terminate();
      runtimes.delete(def.name);
    };
  });
  runtimes.set(def.name, rt);
  const tok = await mintServiceToken();
  worker.postMessage({ kind: "init", actorName: def.name, entryUrl: `file://${def.dir}/${def.entry}`, appId: APP_ID, backendUrl: BACKEND_URL, idleTtlMs: IDLE_ROOM_TTL_MS, ...tok });
  return rt;
}

async function handleWorkerMessage(actorName: string, rt: ActorRuntime, m: Record<string, unknown>): Promise<void> {
  switch (m.kind) {
    case "send": {
      const s = rt.rooms.get(m.room as string)?.sockets.get(m.connId as string);
      if (s && s.ws.readyState === WebSocket.OPEN) s.ws.send(JSON.stringify(m.data));
      return;
    }
    case "broadcast": {
      const text = JSON.stringify(m.data);
      for (const [, s] of rt.rooms.get(m.room as string)?.sockets ?? []) if (s.ws.readyState === WebSocket.OPEN) s.ws.send(text);
      return;
    }
    case "reject": {
      const state = rt.rooms.get(m.room as string);
      const s = state?.sockets.get(m.connId as string);
      if (s) { try { s.ws.close(m.code as number, m.reason as string); } catch { /* closed */ } }
      return;
    }
    case "storage": {
      const room = m.room as string, key = m.key as string | undefined, id = m.id as number;
      try {
        let value: unknown;
        switch (m.op) {
          case "get": {
            const doc = key === undefined ? null : await storage.findOne({ _id: storageKey(actorName, room, key) });
            value = doc ? JSON.parse(doc.value) : undefined;
            break;
          }
          case "put": {
            if (key === undefined) throw new Error("put needs a key");
            const value_ = JSON.stringify(m.value === undefined ? null : m.value);
            await storage.updateOne({ _id: storageKey(actorName, room, key) }, { $set: { actor: actorName, room, key, value: value_ } }, { upsert: true });
            break;
          }
          case "delete": {
            const r = key === undefined ? { deletedCount: 0 } : await storage.deleteOne({ _id: storageKey(actorName, room, key) });
            value = r.deletedCount === 1;
            break;
          }
          case "deleteAll": await storage.deleteMany({ actor: actorName, room }); break;
        }
        rt.worker.postMessage({ kind: "storage-result", id, value });
      } catch (err) {
        rt.worker.postMessage({ kind: "storage-result", id, error: err instanceof Error ? err.message : String(err) });
      }
      return;
    }
    case "schedule": {
      const room = m.room as string, key = m.key as string, at = m.at as number | null;
      const _id = storageKey(actorName, room, key);
      if (at === null) await schedules.deleteOne({ _id });
      else await schedules.updateOne({ _id }, { $set: { actor: actorName, room, key, at: new Date(at) } }, { upsert: true });
      return;
    }
    case "room-idle": {
      const state = rt.rooms.get(m.room as string);
      if (!state || state.sockets.size === 0) { rt.rooms.delete(m.room as string); rt.worker.postMessage({ kind: "evict", room: m.room }); }
      return;
    }
    case "need-service-token": rt.worker.postMessage({ kind: "service-token", ...(await mintServiceToken()) }); return;
    case "log": (m.level === "error" ? console.error : console.log)(String(m.text)); return;
  }
}

// Due schedules fire once, room asleep or not (a wake instantiates it).
setInterval(async () => {
  try {
    const due = await schedules.find({ at: { $lte: new Date() } }).toArray();
    for (const s of due) {
      const gone = await schedules.deleteOne({ _id: s._id, at: s.at });
      if (gone.deletedCount !== 1) continue;
      const def = actors.get(s.actor);
      if (!def) continue;
      const rt = await runtimeFor(def);
      await rt.ready;
      rt.worker.postMessage({ kind: "wake", room: s.room, key: s.key });
    }
  } catch (err) {
    console.error(`[actors] schedule scan: ${String(err)}`);
  }
}, 1000);

// ── the socket route ─────────────────────────────────────────────────────

const NOT_FOUND = () => Response.json({ error: "not-found", detail: "invalid Actor WebSocket request" }, { status: 404 });

async function handleUpgrade(req: Request, actorName: string, room: string): Promise<Response> {
  const url = new URL(req.url);
  const connId = url.searchParams.get("_pk");
  const token = url.searchParams.get("token");
  if (!connId || connId.length > 64 || room.length === 0 || room.length > 256) return NOT_FOUND();
  const def = actors.get(actorName);
  const proxyShaped = url.searchParams.has("handler");
  if (!def && !proxyShaped) return NOT_FOUND();
  const who = await principalFor(actorName, room, connId, token);
  if ("refuse" in who) return who.refuse;
  if (!token && !proxyShaped) return NOT_FOUND();

  if (!def) {
    // The proxy path accepts the upgrade and closes with Base44's own
    // code + reason.
    const { socket, response } = Deno.upgradeWebSocket(req);
    socket.onopen = () => socket.close(1008, `Actor '${actorName}' has not been published`);
    return response;
  }

  const rt = await runtimeFor(def);
  try { await rt.ready; } catch { return new Response("actor failed to load", { status: 503 }); }
  const state = roomOf(rt, room);
  const holder = state.sockets.get(connId);
  if (holder) {
    if (Date.now() - holder.lastSeen < LIVE_WINDOW_MS) return new Response("Connection id in use", { status: 409 });
    // Stale: the newcomer takes the seat; the old socket goes without a
    // handleClose (Base44's 4408).
    holder.superseded = true;
    try { holder.ws.close(4408, "Superseded by reconnect"); } catch { /* closed */ }
    state.sockets.delete(connId);
  }

  const { socket, response } = Deno.upgradeWebSocket(req);
  const entry: Socket = { ws: socket, lastSeen: Date.now(), superseded: false };
  socket.onopen = () => {
    state.sockets.set(connId, entry);
    rt.worker.postMessage({ kind: "connect", room, conn: { id: connId, identity: who.identity } });
  };
  socket.onmessage = (ev) => {
    entry.lastSeen = Date.now();
    if (typeof ev.data !== "string") return;
    let data: unknown;
    try { data = JSON.parse(ev.data); } catch { return; }
    const type = data && typeof data === "object" ? (data as { type?: unknown }).type : undefined;
    if (type === "__ping") { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "__pong" })); return; }
    if (typeof type === "string" && type.startsWith("__")) return;
    rt.worker.postMessage({ kind: "message", room, connId, data });
  };
  socket.onclose = () => {
    if (entry.superseded) return;
    if (state.sockets.get(connId) === entry) state.sockets.delete(connId);
    rt.worker.postMessage({ kind: "close", room, connId });
  };
  socket.onerror = () => { /* onclose follows */ };
  return response;
}

const PARTIES = /^\/parties\/([^/]+)\/([^/]+)$/;

Deno.serve({ port: PORT, hostname: "0.0.0.0" }, async (req) => {
  const url = new URL(req.url);
  if (url.pathname === "/_internal/health") return Response.json({ ok: true, actors: [...actors.keys()] });
  const m = PARTIES.exec(url.pathname);
  if (!m) return NOT_FOUND();
  if (req.headers.get("upgrade")?.toLowerCase() !== "websocket") return NOT_FOUND();
  return handleUpgrade(req, decodeURIComponent(m[1]), decodeURIComponent(m[2]));
});

console.log(`[actors] serving ${actors.size} actor(s) on :${PORT} — ${[...actors.keys()].join(", ") || "(none)"}; backend ${BACKEND_URL}`);
