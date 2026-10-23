// A migrated app's backend functions, the way Base44 itself holds them.
//
// SOURCE (the repo): Base44's own project tree —
//
//   base44/functions/<name>/entry.ts      the function (+ any sibling file)
//   base44/functions/<name>/function.jsonc  optional: { name, entry, automations }
//   base44/shared/**                      code every function may import
//                                         (`../../shared/x.ts`)
//
// BUNDLE (built at every deploy, never committed): what one function runs
// from — its own folder, the whole shared folder (Base44 bundles the shared
// folder's full contents with every function), and the runtime files of ours
// that make Base44's function-runtime contract hold on the host, at the
// bundle's root. The bundle's root is the repo's root, so every relative
// import resolves exactly as it does in the repo and on Base44:
//
//   deno.json                 import map: base44:runtime → ./_eb44_runtime.ts
//   _eb44_runtime.ts          Base44's `base44:runtime` module
//   _eb44_http_compat.ts      the SDK's HTTP transport pinned to fetch
//   _eb44_entry.ts            what the host boots
//   base44/functions/<name>/… the function's folder
//   base44/shared/…           the shared folder
//
// Until 2026-09-27 the migration froze each function's Base44 DEPLOY ARTIFACT
// under `.escapebase44/functions/<name>/` with the runtime files committed
// beside the owner's code, and the deploy shipped that folder alone: a
// function written after migration could not share code (the shared folder
// was a per-function copy made on migration day), and the project's real
// function tree sat in the repo unread. A builder agent that wrote Base44's
// documented shape — a helper under a shared folder — got "Module not found"
// from the deploy (2026-09-10).
//
// The rules here are Base44's, read off its CLI (`base44` 0.1.21,
// `readAllFunctions` / `loadFunctionCode`) and measured on its globs:
//   - a function is a folder holding `function.json(c)`, or — with no config —
//     a folder holding `entry.ts` / `entry.js` whose path has no dot in any
//     folder name (so `<name>.not-deployed/` is Base44's own way of saying
//     "not a function");
//   - its name is the config's `name`, else the folder's path under the
//     functions folder (`email/send`);
//   - its files are EVERY file under its folder, plus every file under the
//     shared folder; a path segment that starts with a dot is never read.
//     (The CLI reads `.js .ts .json .jsonc` only, and until 2026-09-29 so
//     did this. Base44's own function store holds whatever the builder
//     deployed: a paying customer's 20 functions were 20 `entry.ts` and 256
//     `.mjs` modules, every one of them was bundled without its modules and
//     answered 500 "does not load". What a function needs is what its code
//     imports and reads at run time — a module of any kind, a template, a
//     data file — and no list of extensions knows that.)
//
// PURE and import-free on purpose: the deploy runner bundles this file
// (Node), and the dev supervisor in every repo imports a copy of it (Deno) —
// one rule, read the same way on a laptop, in the builder and on deploy.

export const DEFAULT_FUNCTIONS_DIR = "base44/functions";

export const RUNTIME_SHIM_FILE = "_eb44_runtime.ts";
export const ENTRY_WRAPPER_FILE = "_eb44_entry.ts";
export const HTTP_COMPAT_FILE = "_eb44_http_compat.ts";
export const FUNCTION_IMPORT_MAP_FILE = "deno.json";

export interface FunctionConfig {
  name: string;
  entry: string;
  automations?: Record<string, unknown>[];
}

export interface RepoFunction {
  name: string;
  // The function's folder, repo-relative (posix).
  dir: string;
  // Its entry file, relative to the folder.
  entry: string;
  // The parsed `function.jsonc`; null for a function discovered by its entry
  // file alone.
  config: FunctionConfig | null;
  configPath: string | null;
}

export interface BundleFile {
  // Path inside the bundle (posix, relative to the bundle's root).
  path: string;
  // A generated file's text…
  content?: string;
  // …or the repo file it is a copy of (repo-relative), carried as bytes.
  from?: string;
}

export interface FunctionBundle {
  name: string;
  // What the host boots, relative to the bundle's root.
  entry: string;
  // The import map, relative to the bundle's root.
  importMap: string;
  files: BundleFile[];
}

// The shared folder is the functions folder's sibling (the CLI's
// `resolve(functionsDir, "..", "shared")`).
export function sharedDirOf(functionsDir: string): string {
  const parent = dirname(functionsDir);
  return parent ? `${parent}/shared` : "shared";
}

// ── JSONC ──────────────────────────────────────────────────────────────────
//
// `function.jsonc` is JSON with comments and trailing commas (Base44's config
// format). Parsed here rather than by a library: the deploy runner (Node)
// and the dev supervisor (Deno) must read a file the same way, and this file
// has no imports.
export function parseJsonc(text: string): unknown {
  let out = "";
  let i = 0;
  const n = text.length;
  while (i < n) {
    const c = text[i];
    if (c === '"') {
      // A string: copied whole, escapes included.
      let j = i + 1;
      while (j < n && text[j] !== '"') j += text[j] === "\\" ? 2 : 1;
      out += text.slice(i, j + 1);
      i = j + 1;
    } else if (c === "/" && text[i + 1] === "/") {
      while (i < n && text[i] !== "\n") i++;
    } else if (c === "/" && text[i + 1] === "*") {
      const end = text.indexOf("*/", i + 2);
      if (end < 0) throw new SyntaxError("unterminated comment");
      i = end + 2;
    } else if (c === ",") {
      // A comma followed (past whitespace and comments) by a closing bracket
      // is a trailing comma.
      let j = i + 1;
      for (;;) {
        while (j < n && /\s/.test(text[j])) j++;
        if (text[j] === "/" && text[j + 1] === "/") {
          while (j < n && text[j] !== "\n") j++;
        } else if (text[j] === "/" && text[j + 1] === "*") {
          const end = text.indexOf("*/", j + 2);
          if (end < 0) throw new SyntaxError("unterminated comment");
          j = end + 2;
        } else break;
      }
      if (text[j] !== "}" && text[j] !== "]") out += c;
      i++;
    } else {
      out += c;
      i++;
    }
  }
  return JSON.parse(out);
}

// ── discovery ──────────────────────────────────────────────────────────────

const CONFIG_FILE = /^function\.jsonc?$/;
const ENTRY_FILE = /^entry\.(?:ts|js)$/;

export interface Discovery {
  functions: RepoFunction[];
  // Why a deploy of this tree must not go ahead (an unreadable config, a
  // missing entry file, two functions with one name) — Base44's CLI refuses
  // the same trees.
  problems: string[];
}

export function discoverFunctions(input: {
  // Every file of the repo under the functions folder (repo-relative). Paths
  // elsewhere are ignored.
  paths: readonly string[];
  functionsDir: string;
  // The text of a `function.jsonc`.
  readText(path: string): string;
}): Discovery {
  const root = trimSlashes(input.functionsDir) + "/";
  const files = new Set<string>();
  for (const raw of input.paths) {
    const path = normalize(raw);
    if (!path.startsWith(root)) continue;
    if (hasHiddenSegment(path.slice(root.length))) continue;
    files.add(path);
  }

  const functions: RepoFunction[] = [];
  const problems: string[] = [];
  const configuredDirs = new Set<string>();

  for (const path of [...files].sort()) {
    if (!CONFIG_FILE.test(basename(path))) continue;
    const dir = dirname(path);
    // Two config files in one folder: `.jsonc` sorts after `.json`; the
    // first one read names the function, the second is reported.
    if (configuredDirs.has(dir)) {
      problems.push(`${dir} holds both function.json and function.jsonc — keep one`);
      continue;
    }
    configuredDirs.add(dir);
    let parsed: unknown;
    try {
      parsed = parseJsonc(input.readText(path));
    } catch (err) {
      problems.push(`${path} does not parse: ${err instanceof Error ? err.message : String(err)}`);
      continue;
    }
    const config = asFunctionConfig(parsed);
    if (typeof config === "string") {
      problems.push(`${path}: ${config}`);
      continue;
    }
    const entryPath = normalize(`${dir}/${config.entry}`);
    if (!files.has(entryPath)) {
      problems.push(`${path} names the entry "${config.entry}", and ${entryPath} does not exist`);
      continue;
    }
    functions.push({ name: config.name, dir, entry: config.entry, config, configPath: path });
  }

  for (const path of [...files].sort()) {
    if (!ENTRY_FILE.test(basename(path))) continue;
    const dir = dirname(path);
    if (configuredDirs.has(dir)) continue;
    const relDir = dir.length > root.length - 1 ? dir.slice(root.length) : "";
    // `entry.ts` directly in the functions folder names no function.
    if (!relDir) continue;
    if (relDir.split("/").some((segment) => segment.includes("."))) continue;
    // Both entries present: `entry.js` sorts first and the CLI would report
    // the pair as one name twice; the TypeScript one is the function.
    if (basename(path) === "entry.js" && files.has(`${dir}/entry.ts`)) continue;
    functions.push({ name: relDir, dir, entry: basename(path), config: null, configPath: null });
  }

  const seen = new Map<string, string>();
  for (const fn of functions) {
    const other = seen.get(fn.name);
    if (other !== undefined) problems.push(`two functions are named "${fn.name}": ${other} and ${fn.dir}`);
    else seen.set(fn.name, fn.dir);
  }

  functions.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
  return { functions, problems };
}

function asFunctionConfig(parsed: unknown): FunctionConfig | string {
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return "expected an object";
  const raw = parsed as Record<string, unknown>;
  const name = typeof raw.name === "string" ? raw.name.trim() : "";
  if (!name) return "`name` is missing";
  if (name.includes(".")) return `\`name\` cannot contain dots ("${name}")`;
  if (typeof raw.entry !== "string" || !raw.entry) return "`entry` is missing";
  if (raw.automations !== undefined && raw.automations !== null) {
    if (!Array.isArray(raw.automations)) return "`automations` must be a list";
    for (const a of raw.automations) {
      if (!a || typeof a !== "object" || Array.isArray(a)) return "every automation must be an object";
      const auto = a as Record<string, unknown>;
      if (typeof auto.name !== "string" || !auto.name) return "an automation has no `name`";
      if (typeof auto.type !== "string" || !auto.type) return `automation "${auto.name}" has no \`type\``;
    }
  }
  return {
    name,
    entry: raw.entry,
    ...(Array.isArray(raw.automations) ? { automations: raw.automations as Record<string, unknown>[] } : {}),
  };
}

// ── the bundle ─────────────────────────────────────────────────────────────

// The repo files one function is bundled from: everything under its folder
// and under the shared folder.
export function functionSourceFiles(fn: RepoFunction, paths: readonly string[], functionsDir: string): string[] {
  const own = fn.dir + "/";
  const shared = sharedDirOf(trimSlashes(functionsDir)) + "/";
  const out = new Set<string>();
  for (const raw of paths) {
    const path = normalize(raw);
    const under = path.startsWith(own) ? own : path.startsWith(shared) ? shared : null;
    if (!under) continue;
    if (hasHiddenSegment(path.slice(under.length))) continue;
    out.add(path);
  }
  return [...out].sort();
}

export function bundleFunction(input: {
  fn: RepoFunction;
  // Every file of the repo under the functions folder and the shared folder.
  paths: readonly string[];
  functionsDir: string;
  readText(path: string): string;
}): FunctionBundle {
  const { fn } = input;
  const sources = functionSourceFiles(fn, input.paths, input.functionsDir);
  const entryPath = normalize(`${fn.dir}/${fn.entry}`);
  const ownImportMap = `${fn.dir}/${FUNCTION_IMPORT_MAP_FILE}`;
  const runtime = runtimeSupport({
    entryPath,
    entrySource: input.readText(entryPath),
    importMap: sources.includes(ownImportMap)
      ? { dir: fn.dir, content: input.readText(ownImportMap) }
      : null,
  });
  return {
    name: fn.name,
    entry: runtime.entry,
    importMap: FUNCTION_IMPORT_MAP_FILE,
    files: [
      ...runtime.files.map((f) => ({ path: f.path, content: f.content })),
      ...sources.map((path) => ({ path, from: path })),
    ],
  };
}

// ── Base44's function-runtime contract, on a host that is not Base44 ───────
//
// Base44 shipped (2026-07-28) a built-in `base44:runtime` module for backend
// functions (`secrets.get()`, `waitUntil()`) plus default-export handlers —
// their runtime resolves the custom scheme and serves the default export
// itself. Supabase's runtime (in the cloud, and on the app's own server —
// the same image) does neither: the bundler rejects the scheme outright (a
// loud 400 at deploy — the Rush Collective failure), and an entry that never
// calls Deno.serve deploys green and then hangs every request. A third gap
// is the HTTP transport itself: Supabase pins a Deno node-compat layer that
// cannot write a request body on DELETE, which crashes the SDK's
// `entities.deleteMany` — see HTTP_COMPAT_SOURCE (the Stephen Forbes
// deleteTrip failure, 2026-08-05). All three gaps close here, without
// touching a byte of the owner's source:
//
//  - the import map + `_eb44_runtime.ts` make `base44:runtime` resolve
//    exactly as on Base44
//  - every servable entry is fronted by a generated `_eb44_entry.ts` that
//    imports `_eb44_http_compat.ts` before the function's own code, pinning
//    the SDK's axios onto its fetch adapter so node:http never enters the
//    request path
//  - an entry that default-exports its handler without calling Deno.serve
//    gets the same generated entry serving the handler itself
//
// Verified against Supabase's real runtime: import-map remap of the scheme
// bundles + serves; bare default-export hangs; wrapped default-export
// serves (2026-07-29); a verbatim customer deleteMany function crashes
// un-wrapped and completes wrapped, against a real fork backend
// (2026-08-06).

export const RUNTIME_SHIM_SOURCE = `// EscapeBase44: local implementation of Base44's \`base44:runtime\` module.
// The deno.json import map beside this file resolves \`base44:runtime\` here,
// so function code written on Base44 runs unchanged off it.

export const secrets = {
  // Secrets are plain environment variables on this deployment — the same
  // store Base44's secrets.get() reads.
  get(name: string): string | undefined {
    return Deno.env.get(name);
  },
};

type EdgeRuntimeGlobal = { waitUntil(promise: Promise<unknown>): void };

// As on Base44: the caller gets back the promise it handed in (so
// \`const work = waitUntil(task())\` composes), and a task that fails is
// reported against the function instead of surfacing as an unhandled
// rejection — which ends a Deno process.
export function waitUntil<T>(promise: Promise<T>): Promise<T> {
  const tracked = Promise.resolve(promise).catch((error: unknown) => {
    console.error("waitUntil task failed:", error);
  });
  // Supabase's edge runtime needs the promise registered to outlive the
  // response; a plain Deno process (local dev) already lets it settle.
  const edge = (globalThis as { EdgeRuntime?: EdgeRuntimeGlobal }).EdgeRuntime;
  if (edge) edge.waitUntil(tracked);
  return promise;
}
`;

export const HTTP_COMPAT_SOURCE = `// EscapeBase44: pin the Base44 SDK's HTTP transport to axios's fetch adapter.
//
// Supabase's edge runtime pins a Deno node-compat layer that cannot write a
// request body on DELETE — the polyfill never arms the body writer, so
// axios's node http adapter dies with "Cannot read properties of null
// (reading 'write')" (node:_http_outgoing _writeRaw). The Base44 SDK's
// entities.deleteMany is its one bodied DELETE, so every deleteMany call
// from a deployed function crashed. Base44's own runtime and a current
// local Deno CLI both carry the fixed polyfill, which made the same code
// work locally and on Base44 while failing only when deployed.
//
// Forcing axios onto its fetch adapter removes node:http from the request
// path entirely: native fetch handles every method+body combination on
// every runtime, so local dev and the deployed function behave identically.
//
// The version range must resolve to the same axios copy the SDK's own
// dependency resolves to (^1.6.2 in sdk<=0.8.31, ^1.18.1 in 0.8.41+ — both
// resolve to the latest 1.x, one shared instance, so this mutation reaches
// the SDK's client). Verified end-to-end on Supabase's real runtime
// 2026-08-06: a verbatim deleteMany function crashes without this module
// and completes with it.
import axios from "npm:axios@^1.6.2";

try {
  const ax = axios as { getAdapter?: (name: string) => unknown; defaults: { adapter?: unknown } };
  if (typeof ax.getAdapter === "function") {
    ax.getAdapter("fetch"); // throws if this axios build has no fetch adapter
    ax.defaults.adapter = "fetch";
  }
} catch {
  // Never fail a function over the compat layer — keep axios defaults.
}
`;

export interface RuntimeSupport {
  // What the host boots: the generated entry, or the function's own file
  // when it is neither dialect.
  entry: string;
  // The generated files, relative to the root the entry path is relative to.
  files: { path: string; content: string }[];
}

export function runtimeSupport(input: {
  // The function's own entry, relative to the root the generated files land
  // in (`base44/functions/<name>/entry.ts` in a bundle).
  entryPath: string;
  entrySource: string;
  // A `deno.json` the function ships itself (never observed on a Base44
  // app): ours merges over it, its relative targets re-based onto the root.
  importMap: { dir: string; content: string } | null;
  // How the generated files name a file of the repo: relative to
  // themselves (`./`, a bundle — the default), or by the repo's address
  // (`file:///…/`, the dev supervisor, whose generated files live in a
  // temp dir while the functions run from the repo).
  root?: string;
}): RuntimeSupport {
  const root = input.root ?? "./";
  const files: { path: string; content: string }[] = [
    { path: RUNTIME_SHIM_FILE, content: RUNTIME_SHIM_SOURCE },
    { path: HTTP_COMPAT_FILE, content: HTTP_COMPAT_SOURCE },
    { path: FUNCTION_IMPORT_MAP_FILE, content: buildImportMap(input.importMap, root) },
  ];
  let entry = input.entryPath;
  if (needsServeWrapper(input.entrySource)) {
    files.push({ path: ENTRY_WRAPPER_FILE, content: buildDefaultExportEntry(`${root}${input.entryPath}`) });
    entry = ENTRY_WRAPPER_FILE;
  } else if (servesItself(input.entrySource)) {
    files.push({ path: ENTRY_WRAPPER_FILE, content: buildClassicEntry(`${root}${input.entryPath}`) });
    entry = ENTRY_WRAPPER_FILE;
  }
  // A module with neither Deno.serve nor a default export (a bare helper
  // listed as a function) is left as-is — it isn't invocable on Base44
  // either, so there is nothing to front with the compat module.
  return { entry, files };
}

// A function as Base44's STORE holds it (`/backend-functions`: an entry and
// files under paths relative to the artifact's own root), made deployable
// as it is — the shape a repo generated before 2026-09-27 carries under
// `.escapebase44/functions/<name>/`, and the way to try a customer's store
// function on a real runtime without migrating anything.
export function applyRuntimeSupport<T extends { entry: string; files: { path: string; content: string }[] }>(fn: T): T {
  const own = fn.files.find((f) => f.path === FUNCTION_IMPORT_MAP_FILE);
  const support = runtimeSupport({
    entryPath: fn.entry,
    entrySource: fn.files.find((f) => f.path === fn.entry)?.content ?? "",
    importMap: own ? { dir: "", content: own.content } : null,
  });
  const generated = new Set(support.files.map((f) => f.path));
  return {
    ...fn,
    entry: support.entry,
    files: [...fn.files.filter((f) => !generated.has(f.path)).map((f) => ({ ...f })), ...support.files],
  };
}

// Base44 serves a default-export handler itself; anything that already
// calls Deno.serve is the classic dialect and starts its own server.
export function needsServeWrapper(entrySource: string): boolean {
  if (servesItself(entrySource)) return false;
  return /\bexport\s+default\b/.test(entrySource) || /\bas\s+default\s*[,}]/.test(entrySource);
}

export function servesItself(entrySource: string): boolean {
  return /\bDeno\.serve\s*\(/.test(entrySource);
}

function buildDefaultExportEntry(entry: string): string {
  return `// EscapeBase44: Base44's runtime serves a function's default-export
// handler itself; on this deployment this generated entry starts the server.
// The compat import must stay first — see ${HTTP_COMPAT_FILE}.
import "./${HTTP_COMPAT_FILE}";
import handler from ${JSON.stringify(entry)};

Deno.serve(handler);
`;
}

function buildClassicEntry(entry: string): string {
  return `// EscapeBase44: generated deploy entry. The compat import must run
// before the function's own code — see ${HTTP_COMPAT_FILE}. The function
// module starts its own server (Deno.serve) exactly as it did on Base44.
import "./${HTTP_COMPAT_FILE}";
import ${JSON.stringify(entry)};
`;
}

function buildImportMap(own: { dir: string; content: string } | null, root: string): string {
  let config: Record<string, unknown> = {};
  if (own) {
    try {
      const parsed = JSON.parse(own.content);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) config = parsed;
    } catch {
      // Unparseable config would have failed their bundle anyway — replace.
    }
  }
  const imports: Record<string, string> = {};
  for (const [specifier, target] of Object.entries((config.imports ?? {}) as Record<string, unknown>)) {
    if (typeof target !== "string") continue;
    // A relative target was relative to the function's folder; the map now
    // sits at the root.
    imports[specifier] = own && /^\.\.?\//.test(target)
      ? `${root}${normalize(`${own.dir}/${target}`)}${target.endsWith("/") ? "/" : ""}`
      : target;
  }
  config.imports = { ...imports, "base44:runtime": `./${RUNTIME_SHIM_FILE}` };
  return JSON.stringify(config, null, 2) + "\n";
}

// ── paths (posix, no imports) ──────────────────────────────────────────────

function trimSlashes(path: string): string {
  return path.replace(/\\/g, "/").replace(/^(?:\.\/|\/)+/, "").replace(/\/+$/, "");
}

export function normalize(path: string): string {
  const out: string[] = [];
  for (const segment of path.replace(/\\/g, "/").split("/")) {
    if (segment === "" || segment === ".") continue;
    if (segment === "..") out.pop();
    else out.push(segment);
  }
  return out.join("/");
}

function dirname(path: string): string {
  const i = path.lastIndexOf("/");
  return i < 0 ? "" : path.slice(0, i);
}

function basename(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

function hasHiddenSegment(relative: string): boolean {
  return relative.split("/").some((segment) => segment.startsWith("."));
}
