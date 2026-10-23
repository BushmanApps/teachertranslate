// EscapeBase44: one worker per actor NAME — the isolate your actor's code
// runs in. It is spawned by host.ts with NO access to the environment and
// no file access beyond the actor's own folder and the module cache, so an
// actor here sees exactly what it sees on Base44: Web APIs, its own
// imports, and the members of the `Actor` base class. Every room of this
// actor is one instance in this worker; the host owns the sockets, the
// storage and the timers and talks to this worker over messages.

import { bindActorContext, type Actor, type ActorContext, type Conn, type ConnIdentity } from "./runtime.ts";
import { createClient } from "@base44/sdk";
import axios from "axios";

type HostMessage =
  | { kind: "init"; actorName: string; entryUrl: string; appId: string; backendUrl: string; idleTtlMs: number; serviceToken: string; serviceTokenExpiresAt: number }
  | { kind: "connect"; room: string; conn: { id: string; identity: ConnIdentity } }
  | { kind: "message"; room: string; connId: string; data: unknown }
  | { kind: "close"; room: string; connId: string }
  | { kind: "wake"; room: string; key: string }
  | { kind: "storage-result"; id: number; value?: unknown; error?: string }
  | { kind: "service-token"; serviceToken: string; serviceTokenExpiresAt: number };

type WorkerMessage =
  | { kind: "ready" }
  | { kind: "send"; room: string; connId: string; data: unknown }
  | { kind: "broadcast"; room: string; data: unknown }
  | { kind: "reject"; room: string; connId: string; code: number; reason: string }
  | { kind: "storage"; id: number; room: string; op: "get" | "put" | "delete" | "deleteAll"; key?: string; value?: unknown }
  | { kind: "schedule"; room: string; key: string; at: number | null }
  | { kind: "room-idle"; room: string }
  | { kind: "need-service-token" }
  | { kind: "log"; level: "log" | "error"; text: string };

const post = (m: WorkerMessage) => (self as unknown as Worker).postMessage(m);
const log = (text: string) => post({ kind: "log", level: "log", text });
const logError = (text: string) => post({ kind: "log", level: "error", text });

// Base44 evicts an empty room within ~90 s and re-runs `handleStart` on the
// next connect (measured 2026-09-18). Same here: a room with no connection
// and no armed tick is dropped after this long (the host sets it).
let emptyRoomTtlMs = 60_000;

// The SDK's HTTP transport pinned onto fetch — the same pin every migrated
// backend function carries (`_eb44_http_compat.ts`): node:http never enters
// the request path, so every method + body combination behaves alike.
axios.defaults.adapter = "fetch";

let ActorClass: new () => Actor;
let actorName = "";
let appId = "";
let backendUrl = "";
let serviceToken = "";
let serviceTokenExpiresAt = 0;

// Storage + schedule calls are answered by the host; each call waits for
// its own reply.
let nextStorageId = 1;
const pendingStorage = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
function storageCall(room: string, op: "get" | "put" | "delete" | "deleteAll", key?: string, value?: unknown): Promise<unknown> {
  const id = nextStorageId++;
  return new Promise((resolve, reject) => {
    pendingStorage.set(id, { resolve, reject });
    post({ kind: "storage", id, room, op, key, value });
  });
}

// The `conn` an actor sees: a plain object with exactly Base44's own keys in
// its order (`id, identity, send, reject` — measured), nothing of the
// platform's on it. A rejected connection stays in the room until the host
// reports the socket closed — Base44 runs `handleClose` for a rejected
// connection too — but can no longer be sent to.
function makeConn(room: Room, id: string, identity: ConnIdentity): Conn {
  let rejected = false;
  return {
    id,
    identity,
    send(data: unknown): void {
      if (rejected || !room.conns.has(id)) throw new TypeError("Can't call WebSocket send() after close().");
      post({ kind: "send", room: room.id, connId: id, data });
    },
    reject(code: number, reason: string): void {
      rejected = true;
      post({ kind: "reject", room: room.id, connId: id, code, reason });
    },
  };
}

class Room {
  readonly conns = new Map<string, Conn>();
  instance: Actor;
  // Every handler of a room runs in order, one at a time (Base44's chain).
  private chain: Promise<void> = Promise.resolve();
  private started: Promise<void>;
  private ticker: number | null = null;
  private idleTimer: number | null = null;
  private client: unknown = null;
  private clientToken = "";

  constructor(readonly id: string) {
    this.instance = new ActorClass();
    const room = this;
    const ctx: ActorContext = {
      instanceId: id,
      storage: {
        get: <T,>(key: string) => storageCall(id, "get", key) as Promise<T | undefined>,
        put: (key, value) => storageCall(id, "put", key, value) as Promise<void>,
        delete: (key) => storageCall(id, "delete", key) as Promise<boolean>,
        deleteAll: () => storageCall(id, "deleteAll") as Promise<void>,
      },
      connections: () => [...room.conns.values()],
      broadcast: (data) => post({ kind: "broadcast", room: id, data }),
      schedule: async (key, at) => { post({ kind: "schedule", room: id, key, at }); },
      cancelSchedule: async (key) => { post({ kind: "schedule", room: id, key, at: null }); },
      client: () => room.getClient(),
      tickerChanged: () => room.evaluateTicker(),
    };
    bindActorContext(this.instance, ctx);
    this.started = this.run("handleStart", () => this.instance.handleStart());
  }

  // The instance's Base44 client: anonymous calls plus `asServiceRole` on a
  // service token the host mints; rebuilt when the token nears expiry.
  private getClient(): unknown {
    if (serviceTokenExpiresAt - Date.now() < 5 * 60_000) post({ kind: "need-service-token" });
    if (!this.client || this.clientToken !== serviceToken) {
      this.client = createClient({ appId, serverUrl: backendUrl, serviceToken });
      this.clientToken = serviceToken;
    }
    return this.client;
  }

  private run(what: string, fn: () => void | Promise<void>, onError?: (err: unknown) => void): Promise<void> {
    const step = this.chain.then(async () => {
      try {
        await fn();
      } catch (err) {
        logError(`[${actorName}/${this.id}] ${what} threw: ${err instanceof Error ? `${err.name}: ${err.message}` : String(err)}`);
        onError?.(err);
      }
      this.evaluateTicker();
    });
    this.chain = step;
    return step;
  }

  connect(connId: string, identity: ConnIdentity): void {
    this.clearIdle();
    const conn = makeConn(this, connId, identity);
    this.conns.set(connId, conn);
    // Base44 reports a throw in handleConnect to that socket as
    // `{error: "..."}` (measured); the socket stays open.
    this.started.then(() =>
      this.run("handleConnect", () => this.instance.handleConnect(conn), (err) => {
        if (this.conns.has(connId)) post({ kind: "send", room: this.id, connId, data: { error: err instanceof Error ? `${err.name}: ${err.message}` : String(err) } });
      }),
    );
  }

  message(connId: string, data: unknown): void {
    const conn = this.conns.get(connId);
    if (!conn) return;
    this.started.then(() => this.run("handleMessage", () => this.instance.handleMessage(conn, data)));
  }

  close(connId: string): void {
    const conn = this.conns.get(connId);
    if (!conn) return;
    this.conns.delete(connId);
    this.started.then(() => this.run("handleClose", () => this.instance.handleClose(conn)));
    this.armIdle();
  }

  wake(key: string): void {
    this.clearIdle();
    this.started.then(() => this.run("handleWake", () => this.instance.handleWake(key)));
    this.armIdle();
  }

  // The managed ticker: re-evaluated after every connect / message / close
  // and on every tick, like Base44's — a cheap, pure `shouldTick()` decides.
  evaluateTicker(): void {
    let wants = false;
    try {
      wants = typeof this.instance.shouldTick === "function" ? this.instance.shouldTick() === true : false;
    } catch (err) {
      logError(`[${actorName}/${this.id}] shouldTick threw: ${String(err)}`);
    }
    if (wants && this.ticker === null) {
      const period = Math.max(10, Number(this.instance.tickIntervalMs) || 100);
      this.clearIdle();
      this.ticker = setInterval(() => this.run("handleTick", () => this.instance.handleTick()), period);
    } else if (!wants && this.ticker !== null) {
      clearInterval(this.ticker);
      this.ticker = null;
      this.armIdle();
    }
  }

  private armIdle(): void {
    if (this.conns.size > 0 || this.ticker !== null) return;
    this.clearIdle();
    this.idleTimer = setTimeout(() => {
      if (this.conns.size === 0 && this.ticker === null) post({ kind: "room-idle", room: this.id });
    }, emptyRoomTtlMs);
  }

  private clearIdle(): void {
    if (this.idleTimer !== null) { clearTimeout(this.idleTimer); this.idleTimer = null; }
  }

  dispose(): void {
    this.clearIdle();
    if (this.ticker !== null) clearInterval(this.ticker);
  }
}

const rooms = new Map<string, Room>();
const roomFor = (id: string): Room => {
  let room = rooms.get(id);
  if (!room) { room = new Room(id); rooms.set(id, room); }
  return room;
};

(self as unknown as Worker).onmessage = async (ev: MessageEvent<HostMessage>) => {
  const m = ev.data;
  switch (m.kind) {
    case "init": {
      actorName = m.actorName; appId = m.appId; backendUrl = m.backendUrl; emptyRoomTtlMs = m.idleTtlMs;
      serviceToken = m.serviceToken; serviceTokenExpiresAt = m.serviceTokenExpiresAt;
      const mod = await import(m.entryUrl);
      const exported = mod.default;
      if (typeof exported !== "function") throw new Error(`${m.entryUrl} has no default-exported Actor class`);
      ActorClass = exported;
      post({ kind: "ready" });
      return;
    }
    case "connect": roomFor(m.room).connect(m.conn.id, m.conn.identity); return;
    case "message": rooms.get(m.room)?.message(m.connId, m.data); return;
    case "close": rooms.get(m.room)?.close(m.connId); return;
    case "wake": roomFor(m.room).wake(m.key); return;
    case "storage-result": {
      const pending = pendingStorage.get(m.id);
      if (!pending) return;
      pendingStorage.delete(m.id);
      if (m.error !== undefined) pending.reject(new Error(m.error)); else pending.resolve(m.value);
      return;
    }
    case "service-token": serviceToken = m.serviceToken; serviceTokenExpiresAt = m.serviceTokenExpiresAt; return;
  }
};

// The host confirms an idle room may go (nothing arrived for it meanwhile).
(self as unknown as Worker).addEventListener("message", (ev: MessageEvent) => {
  const m = ev.data as { kind: string; room?: string };
  if (m.kind === "evict" && m.room) {
    const room = rooms.get(m.room);
    if (room && room.conns.size === 0) { room.dispose(); rooms.delete(m.room); log(`[${actorName}/${m.room}] evicted (idle)`); }
  }
});
