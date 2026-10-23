// Dev edge-function supervisor. Runs alongside uvicorn during `npm run dev`.
// The backend forwards `/functions/{name}` requests here (via the
// `VIBECODER_DEV_FUNCTIONS_BASE_URL` env hook in
// `app/modules/functions/proxy.py`), and we lazy-spawn one Deno process per
// function on first hit. Reads the same `.env.local` that uvicorn does, so
// functions and the backend share the env-var surface in dev.
//
// The functions are the project's own tree — `base44/functions/<name>/` and
// `base44/shared/` — found by the same rules the deploy uses
// (`./function-bundle.ts`, Base44's own): a folder with an `entry.ts` (or a
// `function.jsonc`) is a function, and a function added while this runs is
// found on its first request. Each one runs from the repo, where its
// relative imports resolve; the runtime files the deploy generates for it
// (the `base44:runtime` module, the import map, the serving entry) are
// generated here too, into a temp dir.
//
// Per-function isolation: each spawned process has its own runtime, its
// own env (filtered from `.env.local` when an allowlist is set), and its
// own file-watch reload loop. The supervisor itself sits in front purely
// to give callers a single stable URL.
//
// This file is committed to the repo and you own it — edit freely.
// Production functions are deployed by the deploy workflow (to the app's
// Supabase project, or to the `functions` container on the app's own
// server) and don't go through this supervisor.

import { join, resolve, toFileUrl } from "https://deno.land/std@0.224.0/path/mod.ts";
import {
  DEFAULT_FUNCTIONS_DIR,
  FUNCTION_IMPORT_MAP_FILE,
  discoverFunctions,
  runtimeSupport,
  sharedDirOf,
  type RepoFunction,
} from "./function-bundle.ts";

const SUPERVISOR_PORT = parseInt(Deno.env.get("ESCAPEBASE44_SUPERVISOR_PORT") ?? "8002", 10);
const REPO_ROOT = resolve(".");
const CONFIG_FILE = ".escapebase44/config.json";
const FUNCTION_ENV_FILE = resolve(Deno.env.get("ESCAPEBASE44_FUNCTION_ENV_FILE") ?? ".env.local");
// Optional comma-separated allowlist of env-var names to forward to each
// spawned function process. When unset (the local-dev default), the full
// env from `.env.local` is forwarded. When set (the vibecoder sandbox
// sets this), it mirrors the production function-env scope.
const FUNCTION_ENV_ALLOWLIST = (Deno.env.get("ESCAPEBASE44_FUNCTION_ENV_ALLOWLIST") ?? "")
  .split(",")
  .map((s) => s.trim())
  .filter((s) => s.length > 0);
const WRAPPER_DIR = "/tmp/escapebase44-fn-wrappers";
const SPAWN_READY_TIMEOUT_MS = 15_000;

interface FunctionProcess {
  port: number;
  ready: Promise<void>;
  child: Deno.ChildProcess;
}

const processes = new Map<string, Promise<FunctionProcess>>();
// Every function process alive, held as it is spawned: what the shutdown
// below stops. (Until 2026-10-20 the shutdown walked the promises above and
// queued its kills in their `.then` — which never ran, because `Deno.exit`
// came first; every stop of this supervisor left its functions running.)
const children = new Set<Deno.ChildProcess>();

// A port nobody holds, asked of the OS. (Until 2026-09-27 functions took
// 8003, 8004, … in order — and 8004 is the actors host's: the second
// function a dev session called was handed a port that was taken, never
// came up, and its requests were forwarded to the actors host.)
function freePort(): number {
  const listener = Deno.listen({ hostname: "127.0.0.1", port: 0 });
  const { port } = listener.addr as Deno.NetAddr;
  listener.close();
  return port;
}

// Where the functions live: the fact the deploy reads
// (`.escapebase44/config.json`), overridable for a one-off run.
async function functionsDir(): Promise<string> {
  const override = Deno.env.get("ESCAPEBASE44_FUNCTIONS_DIR");
  if (override) return override;
  try {
    const config = JSON.parse(await Deno.readTextFile(CONFIG_FILE)) as { functionsDir?: string };
    if (config.functionsDir) return config.functionsDir;
  } catch (err) {
    if (!(err instanceof Deno.errors.NotFound)) throw err;
  }
  return DEFAULT_FUNCTIONS_DIR;
}

// Every file under `dir`, repo-relative; hidden folders are not walked.
async function listFiles(dir: string): Promise<string[]> {
  const out: string[] = [];
  const walk = async (rel: string) => {
    let entries: AsyncIterable<Deno.DirEntry>;
    try {
      entries = Deno.readDir(join(REPO_ROOT, rel));
    } catch (err) {
      if (err instanceof Deno.errors.NotFound) return;
      throw err;
    }
    try {
      for await (const entry of entries) {
        if (entry.name.startsWith(".")) continue;
        const child = `${rel}/${entry.name}`;
        if (entry.isDirectory) await walk(child);
        else out.push(child);
      }
    } catch (err) {
      if (err instanceof Deno.errors.NotFound) return;
      throw err;
    }
  };
  await walk(dir.replace(/\/+$/, ""));
  return out;
}

// The repo's functions, by name. No functions folder = the app has none —
// the supervisor stays up so /api/functions hits don't fail-fast on
// connection-refused, and serves nothing. A `function.jsonc` that does not
// parse, or names an entry that is not there, is reported and the rest are
// served: one broken function must not take the others down in dev (the
// deploy refuses such a tree outright).
async function loadFunctions(): Promise<Map<string, RepoFunction>> {
  const dir = await functionsDir();
  const paths = [...await listFiles(dir), ...await listFiles(sharedDirOf(dir))];
  const configs = new Map<string, string>();
  for (const path of paths) {
    if (/(^|\/)function\.jsonc?$/.test(path)) configs.set(path, await Deno.readTextFile(join(REPO_ROOT, path)));
  }
  const { functions, problems } = discoverFunctions({
    paths,
    functionsDir: dir,
    readText: (path) => configs.get(path) ?? "",
  });
  for (const problem of problems) console.warn(`[supervisor] ${problem}`);
  const byName = new Map<string, RepoFunction>();
  for (const fn of functions) if (!byName.has(fn.name)) byName.set(fn.name, fn);
  return byName;
}

// Parses dotenv-style files. Tolerates `KEY=value` and `KEY="value"` with
// `\\`, `\"`, `\n` escapes inside the quotes, plus `#` comment lines.
async function loadFunctionEnv(): Promise<Record<string, string>> {
  let text: string;
  try {
    text = await Deno.readTextFile(FUNCTION_ENV_FILE);
  } catch (err) {
    console.warn(`[supervisor] missing ${FUNCTION_ENV_FILE}: ${(err as Error).message}`);
    return {};
  }
  const env: Record<string, string> = {};
  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 0) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (value.startsWith(`"`) && value.endsWith(`"`)) {
      value = value
        .slice(1, -1)
        .replace(/\\\\/g, "\\")
        .replace(/\\"/g, `"`)
        .replace(/\\n/g, "\n");
    }
    env[key] = value;
  }
  if (FUNCTION_ENV_ALLOWLIST.length === 0) return env;
  const filtered: Record<string, string> = {};
  for (const key of FUNCTION_ENV_ALLOWLIST) {
    if (key in env) filtered[key] = env[key];
  }
  return filtered;
}

// The runtime files of one function (the `base44:runtime` module, the HTTP
// compat module, the import map, the serving entry), generated into the
// function's own temp dir exactly as the deploy generates them into its
// bundle — naming the function's files by their address in the repo.
// Returns the module to boot and the import map to run it with.
async function writeRuntimeFiles(fn: RepoFunction): Promise<{ boot: string; config: string }> {
  const dir = join(WRAPPER_DIR, fn.name.replaceAll("/", "__"));
  await Deno.mkdir(dir, { recursive: true });
  const repo = toFileUrl(REPO_ROOT + "/").href;
  const entryPath = `${fn.dir}/${fn.entry}`;
  let ownImportMap: { dir: string; content: string } | null = null;
  try {
    ownImportMap = { dir: fn.dir, content: await Deno.readTextFile(join(REPO_ROOT, fn.dir, FUNCTION_IMPORT_MAP_FILE)) };
  } catch (err) {
    if (!(err instanceof Deno.errors.NotFound)) throw err;
  }
  const support = runtimeSupport({
    entryPath,
    entrySource: await Deno.readTextFile(join(REPO_ROOT, entryPath)),
    importMap: ownImportMap,
    root: repo,
  });
  for (const file of support.files) await Deno.writeTextFile(join(dir, file.path), file.content);
  return {
    // A module that neither serves nor default-exports a handler runs as it
    // is (it is not invocable on Base44 either).
    boot: support.entry === entryPath ? `${repo}${entryPath}` : toFileUrl(join(dir, support.entry)).href,
    config: join(dir, FUNCTION_IMPORT_MAP_FILE),
  };
}

async function writeWrapper(funcName: string, boot: string): Promise<string> {
  // The wrapper overrides Deno.serve to force the chosen port. The user's
  // function code stays untouched — it still calls Deno.serve(handler)
  // exactly as in production.
  // _wrap rebuilds req.url from the forwarded Host header so the handler sees
  // the real public URL (preview origin) instead of the localhost listener.
  const wrapper = `const _orig = Deno.serve.bind(Deno);
const PORT = parseInt(Deno.env.get("ESCAPEBASE44_FUNCTION_PORT"));
const _wrap = (h) => (req, info) => {
  const host = req.headers.get("host");
  if (host) {
    const u = new URL(req.url);
    req = new Request(\`https://\${host}\${u.pathname}\${u.search}\`, req);
  }
  return h(req, info);
};
Deno.serve = (a, b) => {
  if (typeof a === "function") return _orig({ handler: _wrap(a), port: PORT });
  const opts = { ...a, port: PORT };
  if (typeof opts.handler === "function") opts.handler = _wrap(opts.handler);
  return _orig(opts, typeof b === "function" ? _wrap(b) : b);
};
await import(${JSON.stringify(boot)});
`;
  const wrapperPath = join(WRAPPER_DIR, `${funcName.replaceAll("/", "__")}.ts`);
  await Deno.writeTextFile(wrapperPath, wrapper);
  return wrapperPath;
}

async function waitForPort(port: number): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < SPAWN_READY_TIMEOUT_MS) {
    try {
      const conn = await Deno.connect({ port });
      conn.close();
      return;
    } catch {
      await new Promise((r) => setTimeout(r, 100));
    }
  }
  throw new Error(`Function on port ${port} did not become ready within ${SPAWN_READY_TIMEOUT_MS}ms`);
}

async function spawnFunction(
  fn: RepoFunction,
  functionEnv: Record<string, string>,
): Promise<FunctionProcess> {
  const { boot, config } = await writeRuntimeFiles(fn);
  const wrapperPath = await writeWrapper(fn.name, boot);
  const port = freePort();

  // The import map maps `base44:runtime` to its local shim (the same module
  // the deployed runtime uses). It lives outside the function's folder, so
  // Deno's config auto-discovery never finds it — pass it explicitly.
  const child = new Deno.Command("deno", {
    args: ["run", "--allow-net", "--allow-env", "--allow-read", "--config", config, "--watch", wrapperPath],
    env: { ...functionEnv, ESCAPEBASE44_FUNCTION_PORT: String(port) },
    stdout: "inherit",
    stderr: "inherit",
  }).spawn();
  children.add(child);
  child.status.then(() => children.delete(child));

  return { port, ready: waitForPort(port), child };
}

function getOrSpawn(
  fn: RepoFunction,
  functionEnv: Record<string, string>,
): Promise<FunctionProcess> {
  const existing = processes.get(fn.name);
  if (existing) return existing;

  // Store the promise (not the resolved process) so concurrent first-requests
  // share one spawn. Drop on spawn failure or child exit so the next request
  // respawns instead of forwarding to a dead port.
  const promise = spawnFunction(fn, functionEnv);
  processes.set(fn.name, promise);
  promise.then(
    (proc) => {
      proc.child.status.then(() => {
        if (processes.get(fn.name) === promise) processes.delete(fn.name);
      });
    },
    () => {
      if (processes.get(fn.name) === promise) processes.delete(fn.name);
    },
  );
  return promise;
}

// The function a request path names — longest name first, so a nested name
// (`email/send`) beats its prefix (`email`).
function match(path: string, functions: Map<string, RepoFunction>): RepoFunction | undefined {
  const names = [...functions.keys()].sort((a, b) => b.length - a.length);
  const name = names.find((n) => path === n || path.startsWith(n + "/"));
  return name === undefined ? undefined : functions.get(name);
}

async function handle(
  req: Request,
  info: Deno.ServeHandlerInfo,
  functionEnv: Record<string, string>,
): Promise<Response> {
  const url = new URL(req.url);
  const path = decodeURIComponent(url.pathname).replace(/^\/+/, "").replace(/\/+$/, "");
  if (!path) return new Response("Missing function name", { status: 400 });
  let fn = match(path, functions);
  if (!fn) {
    // Not one we know: a function written since the last look.
    functions = await loadFunctions();
    fn = match(path, functions);
  }
  if (!fn) return new Response(`Unknown function: ${path}`, { status: 404 });
  const funcName = fn.name;

  const proc = await getOrSpawn(fn, functionEnv);
  await proc.ready;

  const suffix = "/" + path.slice(funcName.length).replace(/^\/+/, "");
  const upstreamUrl = new URL(suffix, `http://localhost:${proc.port}`);
  upstreamUrl.search = url.search;

  const upstreamHeaders = new Headers(req.headers);
  if (!upstreamHeaders.has("x-forwarded-host")) {
    const host = upstreamHeaders.get("host");
    if (host) upstreamHeaders.set("x-forwarded-host", host);
  }
  if (!upstreamHeaders.has("x-forwarded-proto")) {
    upstreamHeaders.set("x-forwarded-proto", "https");
  }
  if (!upstreamHeaders.has("x-forwarded-for")) {
    const addr = info.remoteAddr;
    if (addr && "hostname" in addr) upstreamHeaders.set("x-forwarded-for", addr.hostname);
  }

  const upstream = await fetch(upstreamUrl, {
    method: req.method,
    headers: upstreamHeaders,
    body: req.body,
    // @ts-expect-error — Deno's fetch accepts duplex for streaming bodies
    duplex: "half",
  });

  // Two encoding hazards:
  //   1. fetch() auto-decompresses upstream's body but the Response object
  //      still carries upstream's Content-Encoding/-Length. We strip them
  //      so the client doesn't double-decode and length doesn't lie.
  //   2. Deno.serve auto-compresses outgoing responses when the inbound
  //      request has Accept-Encoding: br/gzip. We're forwarding bytes for
  //      a downstream proxy (uvicorn) that may not decode again, so set
  //      Content-Encoding: identity to opt out.
  const resHeaders = new Headers(upstream.headers);
  resHeaders.delete("content-length");
  resHeaders.set("content-encoding", "identity");
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: resHeaders,
  });
}

await Deno.mkdir(WRAPPER_DIR, { recursive: true });
let functions = await loadFunctions();
const functionEnv = await loadFunctionEnv();
console.log(`[supervisor] listening on :${SUPERVISOR_PORT}, functions=${await functionsDir()} (${functions.size}), env-keys=${Object.keys(functionEnv).length}`);

const teardown = () => {
  for (const child of children) {
    try { child.kill("SIGTERM"); } catch { /* already gone */ }
  }
  Deno.exit(0);
};
Deno.addSignalListener("SIGTERM", teardown);
Deno.addSignalListener("SIGINT", teardown);

Deno.serve({ port: SUPERVISOR_PORT }, (req, info) => handle(req, info, functionEnv));
