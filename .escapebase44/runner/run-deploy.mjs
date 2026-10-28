// <define:__AUTOMATIONS__>
var define_AUTOMATIONS_default = [];

// <define:__DEPLOY_CREDENTIAL_KEYS__>
var define_DEPLOY_CREDENTIAL_KEYS_default = ["VERCEL_TOKEN", "SUPABASE_TOKEN", "EB44_REPORT_URL", "EB44_SSH_PRIVATE_KEY", "ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_P8", "ASC_TEAM_ID", "ANDROID_KEYSTORE_B64", "ANDROID_KEYSTORE_PASSWORD", "ANDROID_KEY_ALIAS", "ANDROID_KEY_PASSWORD"];

// <define:__EB44_PIPELINE__>
var define_EB44_PIPELINE_default = { version: 2 };

// <define:__PROVIDER_CONFIG__>
var define_PROVIDER_CONFIG_default = { appUrl: "https://teachertranslate.eb44.app", app: { projectId: "prj_b9CXPEioPHkR0HyKVBvVyHn1bjTN", orgId: "team_vBDBNvmO3uIesdpGV4k57yDt", projectName: "teachertranslate", teamSlug: "tt-1c6c" }, edge: { projectRef: "toeynygydmamcxnxakhb" }, db: null };

// <define:__USER_SECRET_KEYS__>
var define_USER_SECRET_KEYS_default = ["BASE44_APP_ID", "STRIPE_PUBLISHABLE_KEY", "STRIPE_SECRET_KEY", "STRIPE_TEST_PUBLISHABLE_KEY", "STRIPE_TEST_SECRET_KEY", "STRIPE_TEST_WEBHOOK_SECRET", "STRIPE_WEBHOOK_SECRET"];

// src/providers/vercel/deploy.ts
import { execSync } from "child_process";
import { writeFileSync, mkdirSync } from "fs";

// src/providers/lib/backend-env.ts
function buildBackendEnv(runtimeEnv, overrides) {
  const out = { ...runtimeEnv };
  out.FRONTEND_DIR = overrides.FRONTEND_DIR;
  out.EB44_BACKGROUND_TASKS = overrides.backgroundTasks ? "true" : "false";
  return out;
}

// src/providers/lib/provider-fetch.ts
var RETRY_DELAYS_MS = [1e3, 2e3, 4e3, 8e3, 16e3];
var RETRY_AFTER_CAP_MS = 3e4;
var REPEATABLE_METHODS = /* @__PURE__ */ new Set(["GET", "HEAD", "OPTIONS", "PUT", "DELETE"]);
function methodRepeatable(method) {
  return REPEATABLE_METHODS.has((method ?? "GET").toUpperCase());
}
function retryAfterMs(res) {
  const header = res.headers.get("retry-after");
  if (!header) return null;
  const seconds = Number(header);
  if (Number.isFinite(seconds)) return Math.min(Math.max(seconds, 0) * 1e3, RETRY_AFTER_CAP_MS);
  const at = Date.parse(header);
  if (Number.isNaN(at)) return null;
  return Math.min(Math.max(at - Date.now(), 0), RETRY_AFTER_CAP_MS);
}
function shouldRetryStatus(status) {
  return status === 429 || status >= 500;
}
function callLabel(input, method) {
  const href = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  try {
    const u = new URL(href);
    return `${(method ?? "GET").toUpperCase()} ${u.origin}${u.pathname}`;
  } catch {
    return `${(method ?? "GET").toUpperCase()} ${href}`;
  }
}
function createProviderRetry(deps = {}) {
  const sleep = deps.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const delays = deps.delaysMs ?? RETRY_DELAYS_MS;
  const log = deps.log ?? ((line) => console.log(line));
  return async function providerRetry2(send, options) {
    const repeatable = options.repeatable ?? methodRepeatable(options.method);
    if (!repeatable) return send();
    let lastResponse;
    for (let attempt = 0; ; attempt++) {
      const last = attempt === delays.length;
      let res;
      try {
        res = await send();
      } catch (err) {
        if (options.signal?.aborted) throw err;
        if (last) {
          if (lastResponse) return lastResponse;
          throw err;
        }
        log(`[provider-fetch] ${options.label} failed to connect (${err instanceof Error ? err.message : String(err)}) \u2014 retrying in ${delays[attempt] / 1e3} s (attempt ${attempt + 1} of ${delays.length + 1})`);
        await sleep(delays[attempt]);
        continue;
      }
      if (!shouldRetryStatus(res.status) || last) return res;
      lastResponse = res;
      const wait = retryAfterMs(res) ?? delays[attempt];
      log(`[provider-fetch] ${options.label} answered ${res.status} \u2014 retrying in ${wait / 1e3} s (attempt ${attempt + 1} of ${delays.length + 1})`);
      await sleep(wait);
    }
  };
}
function createProviderFetch(deps = {}) {
  const baseFetch = deps.fetch ?? fetch;
  const retry = createProviderRetry(deps);
  return function providerFetch2(input, init) {
    const { repeatable, ...rest } = init ?? {};
    const method = rest.method ?? (input instanceof Request ? input.method : "GET");
    return retry(() => baseFetch(input, rest), {
      method,
      repeatable,
      label: callLabel(input, method),
      signal: rest.signal
    });
  };
}
function unclear(err) {
  const status = err?.status;
  if (typeof status === "number") return shouldRetryStatus(status);
  return err instanceof TypeError && "cause" in err;
}
function createFromTheTop(deps = {}) {
  const sleep = deps.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const delays = deps.delaysMs ?? RETRY_DELAYS_MS;
  const log = deps.log ?? ((line) => console.log(line));
  return async function fromTheTop2(label, operation) {
    for (let attempt = 0; ; attempt++) {
      try {
        return await operation();
      } catch (err) {
        if (!unclear(err) || attempt === delays.length) throw err;
        log(`[provider-fetch] ${label}: ended without a clear answer (${err instanceof Error ? err.message : String(err)}) \u2014 from the top in ${delays[attempt] / 1e3} s (attempt ${attempt + 1} of ${delays.length + 1})`);
        await sleep(delays[attempt]);
      }
    }
  };
}
var providerFetch = createProviderFetch();
var providerRetry = createProviderRetry();
var fromTheTop = createFromTheTop();

// src/providers/vercel/deploy.ts
var VERCEL_API = "https://api.vercel.com";
async function deploy(config, ctx) {
  const { projectId, orgId } = config.app;
  const token = process.env.VERCEL_TOKEN;
  console.log(`[vercel] starting deploy (project=${projectId})`);
  mkdirSync(".vercel", { recursive: true });
  writeFileSync(".vercel/project.json", JSON.stringify({ projectId, orgId }));
  const backendEnv = {
    ...buildBackendEnv(ctx.runtimeEnv, { FRONTEND_DIR: "dist", backgroundTasks: false }),
    VITE_BASE44_APP_ID: ctx.runtimeEnv.APP_ID
  };
  const envVars = Object.entries(backendEnv).map(([key, value]) => ({
    key,
    value,
    type: "encrypted",
    target: ["production"]
  }));
  console.log(`[vercel] reseeding ${envVars.length} env var(s)`);
  const res = await providerFetch(`${VERCEL_API}/v10/projects/${projectId}/env?upsert=true`, {
    method: "POST",
    repeatable: true,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(envVars)
  });
  if (!res.ok) {
    throw new Error(`Failed to set Vercel env vars: ${res.status}`);
  }
  if (ctx.runtimeEnvRemovals.length > 0) {
    const listRes = await providerFetch(`${VERCEL_API}/v9/projects/${projectId}/env`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!listRes.ok) {
      throw new Error(`Failed to list Vercel env vars: ${listRes.status}`);
    }
    const existing = await listRes.json();
    const toRemove = existing.envs.filter(
      (e) => ctx.runtimeEnvRemovals.includes(e.key) && (Array.isArray(e.target) ? e.target.includes("production") : e.target === "production")
    );
    for (const e of toRemove) {
      console.log(`[vercel] removing env var ${e.key}`);
      const del = await providerFetch(`${VERCEL_API}/v9/projects/${projectId}/env/${e.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!del.ok) {
        throw new Error(`Failed to remove Vercel env var ${e.key}: ${del.status}`);
      }
    }
  }
  console.log("[vercel] installing uv (python builder dep)");
  execSync("curl -LsSf https://astral.sh/uv/install.sh | sh", { stdio: "inherit", shell: "/bin/sh" });
  process.env.PATH = `${process.env.HOME}/.local/bin:${process.env.PATH ?? ""}`;
  console.log("[vercel] installing vercel CLI");
  execSync("npm install --global vercel@latest", { stdio: "inherit" });
  console.log("[vercel] vercel pull");
  execSync(`vercel pull --yes --environment=production --token=${token}`, { stdio: "inherit" });
  console.log("[vercel] vercel build");
  execSync(`vercel build --prod --token=${token}`, { stdio: "inherit" });
  console.log("[vercel] vercel deploy");
  execSync(`vercel deploy --prebuilt --prod --token=${token}`, { stdio: "inherit" });
  console.log("[vercel] deploy complete");
}
async function explainUnhealthy(config) {
  const { projectId, orgId } = config.app;
  const token = process.env.VERCEL_TOKEN;
  const res = await providerFetch(
    `${VERCEL_API}/v6/deployments?projectId=${encodeURIComponent(projectId)}&teamId=${encodeURIComponent(orgId)}&target=production&limit=3`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  if (!res.ok) return `(Vercel answered ${res.status} listing the project's deployments)`;
  const { deployments } = await res.json();
  if (deployments.length === 0) return "(the project has no production deployment)";
  return deployments.map((d) => {
    const when = new Date(d.createdAt).toISOString();
    const sha = d.meta?.githubCommitSha ? ` commit ${d.meta.githubCommitSha.slice(0, 8)}` : "";
    const error = d.errorMessage ? `
    error: ${d.errorMessage}` : "";
    return `--- ${d.uid} (${when}${sha}): ${d.state ?? d.readyState ?? "?"} \u2014 https://${d.url}${error}`;
  }).join("\n");
}

// src/providers/lib/function-bundle.ts
var RUNTIME_SHIM_FILE = "_eb44_runtime.ts";
var ENTRY_WRAPPER_FILE = "_eb44_entry.ts";
var HTTP_COMPAT_FILE = "_eb44_http_compat.ts";
var FUNCTION_IMPORT_MAP_FILE = "deno.json";
function sharedDirOf(functionsDir) {
  const parent = dirname(functionsDir);
  return parent ? `${parent}/shared` : "shared";
}
function parseJsonc(text) {
  let out = "";
  let i = 0;
  const n = text.length;
  while (i < n) {
    const c = text[i];
    if (c === '"') {
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
      let j = i + 1;
      for (; ; ) {
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
var CONFIG_FILE = /^function\.jsonc?$/;
var ENTRY_FILE = /^entry\.(?:ts|js)$/;
function discoverFunctions(input) {
  const root = trimSlashes(input.functionsDir) + "/";
  const files = /* @__PURE__ */ new Set();
  for (const raw of input.paths) {
    const path = normalize(raw);
    if (!path.startsWith(root)) continue;
    if (hasHiddenSegment(path.slice(root.length))) continue;
    files.add(path);
  }
  const functions = [];
  const problems = [];
  const configuredDirs = /* @__PURE__ */ new Set();
  for (const path of [...files].sort()) {
    if (!CONFIG_FILE.test(basename(path))) continue;
    const dir = dirname(path);
    if (configuredDirs.has(dir)) {
      problems.push(`${dir} holds both function.json and function.jsonc \u2014 keep one`);
      continue;
    }
    configuredDirs.add(dir);
    let parsed;
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
    if (!relDir) continue;
    if (relDir.split("/").some((segment) => segment.includes("."))) continue;
    if (basename(path) === "entry.js" && files.has(`${dir}/entry.ts`)) continue;
    functions.push({ name: relDir, dir, entry: basename(path), config: null, configPath: null });
  }
  const seen = /* @__PURE__ */ new Map();
  for (const fn of functions) {
    const other = seen.get(fn.name);
    if (other !== void 0) problems.push(`two functions are named "${fn.name}": ${other} and ${fn.dir}`);
    else seen.set(fn.name, fn.dir);
  }
  functions.sort((a, b) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
  return { functions, problems };
}
function asFunctionConfig(parsed) {
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return "expected an object";
  const raw = parsed;
  const name = typeof raw.name === "string" ? raw.name.trim() : "";
  if (!name) return "`name` is missing";
  if (name.includes(".")) return `\`name\` cannot contain dots ("${name}")`;
  if (typeof raw.entry !== "string" || !raw.entry) return "`entry` is missing";
  if (raw.automations !== void 0 && raw.automations !== null) {
    if (!Array.isArray(raw.automations)) return "`automations` must be a list";
    for (const a of raw.automations) {
      if (!a || typeof a !== "object" || Array.isArray(a)) return "every automation must be an object";
      const auto = a;
      if (typeof auto.name !== "string" || !auto.name) return "an automation has no `name`";
      if (typeof auto.type !== "string" || !auto.type) return `automation "${auto.name}" has no \`type\``;
    }
  }
  return {
    name,
    entry: raw.entry,
    ...Array.isArray(raw.automations) ? { automations: raw.automations } : {}
  };
}
function functionSourceFiles(fn, paths, functionsDir) {
  const own = fn.dir + "/";
  const shared = sharedDirOf(trimSlashes(functionsDir)) + "/";
  const out = /* @__PURE__ */ new Set();
  for (const raw of paths) {
    const path = normalize(raw);
    const under = path.startsWith(own) ? own : path.startsWith(shared) ? shared : null;
    if (!under) continue;
    if (hasHiddenSegment(path.slice(under.length))) continue;
    out.add(path);
  }
  return [...out].sort();
}
function bundleFunction(input) {
  const { fn } = input;
  const sources = functionSourceFiles(fn, input.paths, input.functionsDir);
  const entryPath = normalize(`${fn.dir}/${fn.entry}`);
  const ownImportMap = `${fn.dir}/${FUNCTION_IMPORT_MAP_FILE}`;
  const runtime = runtimeSupport({
    entryPath,
    entrySource: input.readText(entryPath),
    importMap: sources.includes(ownImportMap) ? { dir: fn.dir, content: input.readText(ownImportMap) } : null
  });
  return {
    name: fn.name,
    entry: runtime.entry,
    importMap: FUNCTION_IMPORT_MAP_FILE,
    files: [
      ...runtime.files.map((f) => ({ path: f.path, content: f.content })),
      ...sources.map((path) => ({ path, from: path }))
    ]
  };
}
var RUNTIME_SHIM_SOURCE = `// EscapeBase44: local implementation of Base44's \`base44:runtime\` module.
// The deno.json import map beside this file resolves \`base44:runtime\` here,
// so function code written on Base44 runs unchanged off it.

export const secrets = {
  // Secrets are plain environment variables on this deployment \u2014 the same
  // store Base44's secrets.get() reads.
  get(name: string): string | undefined {
    return Deno.env.get(name);
  },
};

type EdgeRuntimeGlobal = { waitUntil(promise: Promise<unknown>): void };

// As on Base44: the caller gets back the promise it handed in (so
// \`const work = waitUntil(task())\` composes), and a task that fails is
// reported against the function instead of surfacing as an unhandled
// rejection \u2014 which ends a Deno process.
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
var HTTP_COMPAT_SOURCE = `// EscapeBase44: pin the Base44 SDK's HTTP transport to axios's fetch adapter.
//
// Supabase's edge runtime pins a Deno node-compat layer that cannot write a
// request body on DELETE \u2014 the polyfill never arms the body writer, so
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
// dependency resolves to (^1.6.2 in sdk<=0.8.31, ^1.18.1 in 0.8.41+ \u2014 both
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
  // Never fail a function over the compat layer \u2014 keep axios defaults.
}
`;
function runtimeSupport(input) {
  const root = input.root ?? "./";
  const files = [
    { path: RUNTIME_SHIM_FILE, content: RUNTIME_SHIM_SOURCE },
    { path: HTTP_COMPAT_FILE, content: HTTP_COMPAT_SOURCE },
    { path: FUNCTION_IMPORT_MAP_FILE, content: buildImportMap(input.importMap, root) }
  ];
  let entry = input.entryPath;
  if (needsServeWrapper(input.entrySource)) {
    files.push({ path: ENTRY_WRAPPER_FILE, content: buildDefaultExportEntry(`${root}${input.entryPath}`) });
    entry = ENTRY_WRAPPER_FILE;
  } else if (servesItself(input.entrySource)) {
    files.push({ path: ENTRY_WRAPPER_FILE, content: buildClassicEntry(`${root}${input.entryPath}`) });
    entry = ENTRY_WRAPPER_FILE;
  }
  return { entry, files };
}
function needsServeWrapper(entrySource) {
  if (servesItself(entrySource)) return false;
  return /\bexport\s+default\b/.test(entrySource) || /\bas\s+default\s*[,}]/.test(entrySource);
}
function servesItself(entrySource) {
  return /\bDeno\.serve\s*\(/.test(entrySource);
}
function buildDefaultExportEntry(entry) {
  return `// EscapeBase44: Base44's runtime serves a function's default-export
// handler itself; on this deployment this generated entry starts the server.
// The compat import must stay first \u2014 see ${HTTP_COMPAT_FILE}.
import "./${HTTP_COMPAT_FILE}";
import handler from ${JSON.stringify(entry)};

Deno.serve(handler);
`;
}
function buildClassicEntry(entry) {
  return `// EscapeBase44: generated deploy entry. The compat import must run
// before the function's own code \u2014 see ${HTTP_COMPAT_FILE}. The function
// module starts its own server (Deno.serve) exactly as it did on Base44.
import "./${HTTP_COMPAT_FILE}";
import ${JSON.stringify(entry)};
`;
}
function buildImportMap(own, root) {
  let config = {};
  if (own) {
    try {
      const parsed = JSON.parse(own.content);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) config = parsed;
    } catch {
    }
  }
  const imports = {};
  for (const [specifier, target] of Object.entries(config.imports ?? {})) {
    if (typeof target !== "string") continue;
    imports[specifier] = own && /^\.\.?\//.test(target) ? `${root}${normalize(`${own.dir}/${target}`)}${target.endsWith("/") ? "/" : ""}` : target;
  }
  config.imports = { ...imports, "base44:runtime": `./${RUNTIME_SHIM_FILE}` };
  return JSON.stringify(config, null, 2) + "\n";
}
function trimSlashes(path) {
  return path.replace(/\\/g, "/").replace(/^(?:\.\/|\/)+/, "").replace(/\/+$/, "");
}
function normalize(path) {
  const out = [];
  for (const segment of path.replace(/\\/g, "/").split("/")) {
    if (segment === "" || segment === ".") continue;
    if (segment === "..") out.pop();
    else out.push(segment);
  }
  return out.join("/");
}
function dirname(path) {
  const i = path.lastIndexOf("/");
  return i < 0 ? "" : path.slice(0, i);
}
function basename(path) {
  return path.slice(path.lastIndexOf("/") + 1);
}
function hasHiddenSegment(relative) {
  return relative.split("/").some((segment) => segment.startsWith("."));
}

// src/providers/lib/function-refusals.ts
var FILE_URL = /file:\/\/\/[^\s"']+/g;
function inRepoPaths(message, rootOf) {
  return message.replace(FILE_URL, (url) => {
    const tail = /(?::\d+:\d+)?[.,;)]*$/.exec(url)[0];
    const path = rootOf(url.slice(0, url.length - tail.length));
    return path === null ? url : path + tail;
  });
}
function refusalReason(message, rootOf) {
  const text = inRepoPaths(message, rootOf);
  const missing = /Module not found "([^"\s]+)"\.\s+at (\S+?):\d+:\d+/.exec(text);
  if (missing) return `${missing[2]} imports ${missing[1]}, which does not exist`;
  const caused = /Caused by:\s*\n\s*([^\n]+)/.exec(text) ?? /\(reason: ([^\n]+)/.exec(text);
  const first = (caused ? caused[1] : text.trim().split("\n")[0]).trim();
  return first.replace(/\)\.?$/, "").slice(0, 400);
}
function ownFilesVerdict(message, rootOf) {
  const inRoot = (url) => rootOf(url) !== null;
  const missing = /Module not found "(file:\/\/\/[^"\s]+)"\.\s+at (file:\/\/\/\S+?):\d+:\d+/.exec(message);
  if (missing) return inRoot(missing[1]) && inRoot(missing[2]) ? refusalReason(message, rootOf) : null;
  const unparsed = /could not be parsed: [^\n]*? at (file:\/\/\/\S+?):\d+:\d+/.exec(message);
  if (unparsed) return inRoot(unparsed[1]) ? refusalReason(message, rootOf) : null;
  const scheme = /Unsupported scheme "[^"]+" for module "([^"]+)"[\s\S]*?\n\s+at (file:\/\/\/\S+?):\d+:\d+/.exec(message);
  if (scheme) return inRoot(scheme[2]) ? `${rootOf(scheme[2])} imports "${scheme[1]}", a module this runtime does not have` : null;
  return null;
}

// src/providers/lib/function-sources.ts
import { createHash } from "crypto";
import { existsSync, mkdirSync as mkdirSync2, mkdtempSync, readFileSync, readdirSync, statSync, writeFileSync as writeFileSync2, copyFileSync } from "fs";
import { dirname as dirname2, join } from "path";

// src/providers/lib/deploy-paths.ts
var FUNCTIONS_DIR = ".escapebase44/functions";
var FUNCTIONS_MANIFEST_PATH = `${FUNCTIONS_DIR}/_manifest.json`;

// src/providers/lib/function-sources.ts
function listRepoFiles(dir, root = ".") {
  const out = [];
  const walk = (rel) => {
    const abs = join(root, rel);
    if (!existsSync(abs)) return;
    for (const entry of readdirSync(abs)) {
      if (entry.startsWith(".")) continue;
      const child = `${rel}/${entry}`;
      if (statSync(join(root, child)).isDirectory()) walk(child);
      else out.push(child);
    }
  };
  walk(dir.replace(/\/+$/, ""));
  return out;
}
function readRepoFunctions(functionsDir, root = ".") {
  const paths = [...listRepoFiles(functionsDir, root), ...listRepoFiles(sharedDirOf(functionsDir), root)];
  const { functions, problems } = discoverFunctions({
    paths,
    functionsDir,
    readText: (path) => readFileSync(join(root, path), "utf-8")
  });
  if (problems.length > 0) {
    throw new Error(`The backend functions under ${functionsDir} cannot be deployed:
  - ${problems.join("\n  - ")}`);
  }
  return { functions, paths };
}
function readFunctionBundles(functionsDir, root = ".") {
  const { functions, paths } = readRepoFunctions(functionsDir, root);
  const bundles = functions.map((fn) => bundleFunction({ fn, paths, functionsDir, readText: (path) => readFileSync(join(root, path), "utf-8") }));
  return { functions, bundles };
}
function bundleFileBytes(file, root = ".") {
  if (file.content !== void 0) return Buffer.from(file.content, "utf-8");
  return readFileSync(join(root, file.from));
}
function functionSourcePaths(functions, root = ".") {
  if (functions.tree === "legacy") return listAllFiles(FUNCTIONS_DIR, root);
  const out = /* @__PURE__ */ new Set();
  for (const bundle of functions.bundles) {
    for (const file of bundle.files) if (file.from) out.add(file.from);
  }
  return [...out].sort();
}
var AUTOMATION_FILE_FIELDS = [
  "id",
  "type",
  "name",
  "description",
  "is_active",
  "function_args",
  "entity_name",
  "event_types",
  "schedule_mode",
  "schedule_type",
  "cron_expression",
  "repeat_unit",
  "repeat_interval",
  "one_time_date",
  "repeat_on_days",
  "repeat_on_day_of_month",
  "start_time",
  "ends_type",
  "ends_on_date",
  "ends_after_count",
  "integration_type",
  "events",
  "resource_id",
  "trigger_conditions"
];
function derivedAutomationId(functionName, automationName) {
  return createHash("sha256").update(`${functionName}\0${automationName}`).digest("hex").slice(0, 24);
}
function repoAutomations(functions) {
  const out = /* @__PURE__ */ new Map();
  const ids = /* @__PURE__ */ new Map();
  for (const fn of functions) {
    const list = [];
    for (const raw of fn.config?.automations ?? []) {
      const name = String(raw.name);
      const id = typeof raw.id === "string" && raw.id ? raw.id : derivedAutomationId(fn.name, name);
      const owner = ids.get(id);
      if (owner !== void 0) {
        throw new Error(
          `${fn.configPath}: automation "${name}" has the same id as ${owner} \u2014 give each automation of a function its own name (and no copied \`id\`)`
        );
      }
      ids.set(id, `"${name}" of ${fn.name}`);
      const entry = {};
      for (const field of AUTOMATION_FILE_FIELDS) entry[field] = raw[field] ?? null;
      entry.id = id;
      entry.type = String(raw.type);
      entry.name = name;
      entry.is_active = raw.is_active !== false;
      list.push(entry);
    }
    out.set(fn.name, list);
  }
  return out;
}
function scheduledAutomations(automations) {
  const out = [];
  for (const [functionName, list] of automations) {
    for (const a of list) {
      if (a.type !== "scheduled" || !a.is_active) continue;
      if (a.schedule_mode !== "one-time" && a.schedule_mode !== "recurring") {
        console.warn(`Scheduled automation "${a.name}" on ${functionName} has no schedule_mode \u2014 skipping`);
        continue;
      }
      out.push({
        id: a.id,
        created_by: "",
        type: "scheduled",
        name: a.name,
        is_active: true,
        functionName,
        function_args: a.function_args ?? null,
        schedule_mode: a.schedule_mode,
        schedule_type: a.schedule_type ?? void 0,
        cron_expression: a.cron_expression,
        repeat_unit: a.repeat_unit,
        repeat_interval: a.repeat_interval,
        one_time_date: a.one_time_date,
        repeat_on_days: a.repeat_on_days,
        repeat_on_day_of_month: a.repeat_on_day_of_month,
        start_time: a.start_time,
        ends_type: a.ends_type ?? void 0,
        ends_on_date: a.ends_on_date,
        ends_after_count: a.ends_after_count
      });
    }
  }
  return out;
}
function readDeployedFunctions(config, root = ".") {
  if (!config.functionsDir) return { tree: "legacy" };
  const { functions, bundles } = readFunctionBundles(config.functionsDir, root);
  return { tree: "base44", functionsDir: config.functionsDir, bundles, automations: repoAutomations(functions) };
}
function readLegacyManifest(root = ".") {
  const path = join(root, FUNCTIONS_MANIFEST_PATH);
  return existsSync(path) ? JSON.parse(readFileSync(path, "utf-8")) : { functions: {} };
}
function readLegacyFunctions(root = ".") {
  const manifest = readLegacyManifest(root);
  return Object.keys(manifest.functions).map((name) => {
    const dir = `${FUNCTIONS_DIR}/${name}`;
    const files = listAllFiles(dir, root).map((path) => ({
      path: path.slice(dir.length + 1),
      content: readFileSync(join(root, path), "utf-8")
    }));
    return {
      name,
      entry: manifest.functions[name].entry,
      importMap: files.some((f) => f.path === "deno.json"),
      files
    };
  });
}
function listAllFiles(dir, root) {
  const out = [];
  const walk = (rel) => {
    const abs = join(root, rel);
    if (!existsSync(abs)) return;
    for (const entry of readdirSync(abs)) {
      const child = `${rel}/${entry}`;
      if (statSync(join(root, child)).isDirectory()) walk(child);
      else out.push(child);
    }
  };
  walk(dir);
  return out;
}

// src/providers/lib/cron-emitter.ts
function buildTriggerSpec(a, backendUrl) {
  const base = backendUrl.replace(/\/$/, "");
  return {
    cron: a.cron,
    id: a.id,
    url: `${base}/api/internal/fire-automation/${a.id}`,
    oneTimeMs: a.oneTimeMs
  };
}
var WORKFLOWS_TICK_CRON = "* * * * *";
function buildWorkflowsTickUrl(backendUrl) {
  return `${backendUrl.replace(/\/$/, "")}/api/internal/workflows/tick`;
}

// src/providers/supabase/cron.ts
function cronJobName(automationId) {
  return `eb44-${automationId}`;
}
function buildScheduleSql(automation, backendUrl, cronSecret) {
  const name = cronJobName(automation.id);
  const spec = buildTriggerSpec(automation, backendUrl);
  const headers = JSON.stringify({ "X-Eb44-Cron-Secret": cronSecret });
  return `
DO $eb44$
BEGIN
    PERFORM cron.unschedule(${sqlLiteral(name)});
EXCEPTION WHEN OTHERS THEN NULL;
END $eb44$;
SELECT cron.schedule(
    ${sqlLiteral(name)},
    ${sqlLiteral(spec.cron)},
    $eb44cmd$SELECT net.http_post(
        url := ${sqlLiteral(spec.url)},
        headers := ${sqlLiteral(headers)}::jsonb
    );$eb44cmd$
);
`;
}
function buildReconcileSql(keepJobNames) {
  const keepArray = keepJobNames.length === 0 ? "ARRAY[]::text[]" : `ARRAY[${keepJobNames.map(sqlLiteral).join(",")}]`;
  return `
DO $eb44$
DECLARE
    j text;
BEGIN
    FOR j IN
        SELECT jobname FROM cron.job
        WHERE jobname LIKE 'eb44-%'
          AND NOT (jobname = ANY (${keepArray}))
    LOOP
        PERFORM cron.unschedule(j);
    END LOOP;
END $eb44$;
`;
}
var ENABLE_EXTENSIONS_SQL = `
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;
`;
var WORKFLOWS_TICK_JOB = "eb44-workflows-tick";
function buildWorkflowsTickSql(backendUrl, cronSecret) {
  const url = buildWorkflowsTickUrl(backendUrl);
  const headers = JSON.stringify({ "X-Eb44-Cron-Secret": cronSecret });
  return `
DO $eb44$
BEGIN
    PERFORM cron.unschedule(${sqlLiteral(WORKFLOWS_TICK_JOB)});
EXCEPTION WHEN OTHERS THEN NULL;
END $eb44$;
SELECT cron.schedule(
    ${sqlLiteral(WORKFLOWS_TICK_JOB)},
    ${sqlLiteral(WORKFLOWS_TICK_CRON)},
    $eb44cmd$SELECT net.http_post(
        url := ${sqlLiteral(url)},
        headers := ${sqlLiteral(headers)}::jsonb
    );$eb44cmd$
);
`;
}
function sqlLiteral(s) {
  return `'${s.replace(/'/g, "''")}'`;
}

// src/providers/supabase/slug.ts
import { createHash as createHash2 } from "crypto";
var HASH_LEN = 4;
var SAFE_SLUG_RE = /^[A-Za-z0-9_-]+$/;
function supabaseFunctionSlug(funcName) {
  if (SAFE_SLUG_RE.test(funcName)) return funcName;
  const sanitized = funcName.replace(/[^A-Za-z0-9_-]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
  const hash = createHash2("sha256").update(funcName).digest("hex").slice(0, HASH_LEN);
  return `${sanitized}-${hash}`;
}
function supabaseFunctionUrl(projectRef, funcName) {
  return `https://${projectRef}.supabase.co/functions/v1/${supabaseFunctionSlug(funcName)}`;
}

// src/providers/supabase/deploy.ts
var SUPABASE_API = "https://api.supabase.com/v1";
var MODULE_NOT_FOUND = /Failed to bundle the function \(reason: Module not found "file:\/\/[^"\s]*?\/source\/([^"\s]+)"\.\s+at file:\/\/[^"\s]*?\/source\/([^\s:]+):\d+:\d+/;
var oursGenerated = (path) => path.split("/").pop().startsWith("_eb44_");
function ownCodeDoesNotLoad(refusal, upload) {
  if (refusal.status !== 400) return null;
  let message;
  try {
    message = JSON.parse(refusal.body).message;
  } catch {
    return null;
  }
  if (typeof message !== "string" || !message.startsWith("Failed to bundle the function")) return null;
  const held = new Set(upload.files.map((f) => f.path));
  const found = MODULE_NOT_FOUND.exec(message);
  if (found) {
    const [, missing, importer] = found;
    if (held.has(missing) || !held.has(importer) || oursGenerated(importer)) return null;
    return `${importer} imports ${missing}, which does not exist`;
  }
  if (message.includes("Module not found")) return null;
  return ownFilesVerdict(message, (url) => {
    const at = url.indexOf("/source/");
    const path = at === -1 ? null : url.slice(at + "/source/".length);
    return path !== null && held.has(path) && !oursGenerated(path) ? path : null;
  });
}
function standInFor(name, reason) {
  const source = `// EscapeBase44: this function's own code does not load, so the deploy put this
// stand-in in its place; the next deploy tries the function's code again.
// ${reason}
Deno.serve(() => Response.json({ error: "This function's code does not load", reason: ${JSON.stringify(reason)} }, { status: 500 }));
`;
  return { name, entry: ENTRY_WRAPPER_FILE, importMap: null, files: [{ path: ENTRY_WRAPPER_FILE, bytes: source }] };
}
function deployedByUs(fn) {
  return typeof fn.entrypoint_path === "string" && fn.entrypoint_path.split("/").pop() === ENTRY_WRAPPER_FILE;
}
function droppedFromRepo(project, deployedSlugs) {
  return project.filter((fn) => deployedByUs(fn) && !deployedSlugs.has(fn.slug)).map((fn) => fn.slug);
}
function uploadsOf(ctx) {
  if (ctx.functions.tree === "legacy") {
    return readLegacyFunctions().map((fn) => ({
      name: fn.name,
      entry: fn.entry,
      // The function dir ships a deno.json whose import map resolves
      // Base44's `base44:runtime` module to the local shim — without
      // import_map_path the bundler rejects the scheme outright.
      // Conditional so this runner stays correct on a repo assembled
      // before the map existed.
      importMap: fn.importMap ? "deno.json" : null,
      files: fn.files.map((f) => ({ path: f.path, bytes: f.content }))
    }));
  }
  return ctx.functions.bundles.map((bundle) => ({
    name: bundle.name,
    entry: bundle.entry,
    importMap: bundle.importMap,
    files: bundle.files.map((f) => ({ path: f.path, bytes: bundleFileBytes(f) }))
  }));
}
async function deploy2(appUrl, config, automations, ctx) {
  const token = process.env.SUPABASE_TOKEN;
  const { projectRef } = config.edge;
  const uploads = uploadsOf(ctx);
  console.log(`[supabase] deploying ${uploads.length} function(s) to project ${projectRef}`);
  await setProjectSecrets(token, projectRef, ctx);
  const results = [];
  const refusedEdits = [];
  for (const upload of uploads) {
    console.log(`[supabase]   bundling ${upload.name}`);
    const slug = supabaseFunctionSlug(upload.name);
    const refused = await deployFunction(token, projectRef, slug, upload);
    const url = supabaseFunctionUrl(projectRef, upload.name);
    if (refused === null) {
      results.push({ name: upload.name, url });
      continue;
    }
    const notLoading = ownCodeDoesNotLoad(refused, upload);
    if (notLoading === null) {
      throw new Error(`Deploy function "${slug}" failed: ${refused.status} ${refused.body.slice(0, 500)}`);
    }
    if (!ctx.migrationDay) {
      console.error(`[supabase]   ${upload.name} does not load (${notLoading}) \u2014 not deployed; what is live under that name stays`);
      refusedEdits.push(`${upload.name}: ${notLoading}`);
      continue;
    }
    console.warn(`[supabase]   ${upload.name} does not load (${notLoading}) \u2014 deployed as a function that answers 500 with that reason`);
    const standIn = await deployFunction(token, projectRef, slug, standInFor(upload.name, notLoading));
    if (standIn !== null) {
      throw new Error(`Deploy function "${slug}" failed: ${standIn.status} ${standIn.body.slice(0, 500)}`);
    }
    results.push({ name: upload.name, url, notLoading });
  }
  if (refusedEdits.length > 0) {
    throw new Error(
      `${refusedEdits.length} function(s) do not load and were not deployed (the version that was live stays live): ` + refusedEdits.join("; ")
    );
  }
  if (ctx.functions.tree === "base44" && !ctx.migrationDay) {
    await removeDroppedFunctions(token, projectRef, new Set(uploads.map((u) => supabaseFunctionSlug(u.name))));
  }
  const scheduledAutomations2 = automations.filter((a) => a.cron);
  const keep = scheduledAutomations2.map((a) => cronJobName(a.id));
  if (ctx.hasWorkflows) keep.push(WORKFLOWS_TICK_JOB);
  if (keep.length > 0) {
    console.log(
      `[supabase] reconciling ${scheduledAutomations2.length} cron job(s)` + (ctx.hasWorkflows ? " + the workflows tick" : "")
    );
    await runSql(token, projectRef, ENABLE_EXTENSIONS_SQL);
    await runSql(token, projectRef, buildReconcileSql(keep));
    const cronSecret = process.env.EB44_CRON_SECRET;
    for (const a of scheduledAutomations2) {
      await runSql(token, projectRef, buildScheduleSql(a, appUrl, cronSecret));
    }
    if (ctx.hasWorkflows) {
      await runSql(token, projectRef, buildWorkflowsTickSql(appUrl, cronSecret));
    }
  } else {
    await runSql(token, projectRef, buildReconcileSql([])).catch(() => {
    });
  }
  console.log(`[supabase] deployed ${uploads.length} function(s)`);
  return results;
}
async function setProjectSecrets(token, projectRef, ctx) {
  const managed = Object.entries(ctx.functionEnv.env).map(([name, value]) => ({ name, value }));
  const removals = ctx.functionEnv.removals;
  const listRes = await providerFetch(`${SUPABASE_API}/projects/${projectRef}/secrets`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!listRes.ok) {
    throw new Error(`List project secrets failed: ${listRes.status}`);
  }
  const existing = await listRes.json();
  const existingNames = new Set(existing.map((s) => s.name));
  const toDelete = removals.filter((name) => existingNames.has(name));
  if (toDelete.length > 0) {
    const del = await providerFetch(`${SUPABASE_API}/projects/${projectRef}/secrets`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(toDelete)
    });
    if (!del.ok) {
      throw new Error(`Delete project secrets failed: ${del.status} ${(await del.text()).slice(0, 500)}`);
    }
  }
  console.log(`[supabase] reseeding ${managed.length} secret(s)`);
  const res = await providerFetch(`${SUPABASE_API}/projects/${projectRef}/secrets`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(managed),
    repeatable: true
  });
  if (!res.ok) {
    throw new Error(`Set project secrets failed: ${res.status} ${(await res.text()).slice(0, 500)}`);
  }
}
async function removeDroppedFunctions(token, projectRef, deployedSlugs) {
  const list = await providerFetch(`${SUPABASE_API}/projects/${projectRef}/functions`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!list.ok) {
    throw new Error(`List project functions failed: ${list.status} ${(await list.text()).slice(0, 500)}`);
  }
  const dropped = droppedFromRepo(await list.json(), deployedSlugs);
  for (const slug of dropped) {
    const res = await providerFetch(`${SUPABASE_API}/projects/${projectRef}/functions/${encodeURIComponent(slug)}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok && res.status !== 404) {
      throw new Error(`Remove function "${slug}" failed: ${res.status} ${(await res.text()).slice(0, 500)}`);
    }
    console.log(`[supabase]   removed ${slug} \u2014 the repo no longer holds it`);
  }
}
async function deployFunction(token, projectRef, slug, upload) {
  const form = new FormData();
  form.append("metadata", new Blob([JSON.stringify({
    name: slug,
    entrypoint_path: upload.entry,
    verify_jwt: false,
    ...upload.importMap ? { import_map_path: upload.importMap } : {}
  })], { type: "application/json" }));
  for (const f of upload.files) {
    const part = typeof f.bytes === "string" ? f.bytes : new Uint8Array(f.bytes);
    form.append("file", new Blob([part], { type: "application/typescript" }), f.path);
  }
  const res = await providerFetch(
    `${SUPABASE_API}/projects/${projectRef}/functions/deploy?slug=${encodeURIComponent(slug)}`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
      repeatable: true
    }
  );
  if (!res.ok) return { status: res.status, body: await res.text() };
  return null;
}
async function runSql(token, projectRef, query) {
  const res = await providerFetch(`${SUPABASE_API}/projects/${projectRef}/database/query`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
    repeatable: true
  });
  if (!res.ok) {
    throw new Error(`SQL exec failed: ${res.status} ${(await res.text()).slice(0, 500)}`);
  }
}

// src/migration/push/run-deploy.ts
import { existsSync as existsSync3, readFileSync as readFileSync4, readdirSync as readdirSync3 } from "fs";

// src/migration/push/compose-env.ts
import { readFileSync as readFileSync2 } from "fs";
var CONFIG_PATH = ".escapebase44/config.json";
var SECRETS_FILE_ENV = "EB44_SECRETS_FILE";
var GITHUB_INJECTED_SECRETS = /* @__PURE__ */ new Set(["github_token", "GITHUB_TOKEN"]);
function readRepoConfig() {
  const raw = JSON.parse(readFileSync2(CONFIG_PATH, "utf-8"));
  if (typeof raw.appUrl !== "string" || typeof raw.env !== "object") {
    throw new Error(`${CONFIG_PATH} is malformed \u2014 expected { appUrl, env }`);
  }
  return raw;
}
function readSecretsBlob() {
  const path = process.env[SECRETS_FILE_ENV];
  if (!path) throw new Error(`${SECRETS_FILE_ENV} not set \u2014 the workflow must write the secrets file`);
  const blob = JSON.parse(readFileSync2(path, "utf-8"));
  for (const name of GITHUB_INJECTED_SECRETS) delete blob[name];
  return blob;
}
var EMAIL_SENDER_NAMES = {
  ses: "SES_",
  gmail: "GMAIL_",
  resend: "RESEND_"
};
var FILE_STORE_NAMES = {
  s3: "S3_",
  "vercel-blob": "BLOB_"
};
var SANDBOX_EJECT_EXCLUDED_PREFIXES = [
  // the server and the cloud account it runs in
  "EB44_SSH",
  "EB44_BOX_",
  "AWS_",
  "GCP_",
  ...Object.values(FILE_STORE_NAMES),
  ...Object.values(EMAIL_SENDER_NAMES),
  // the channels the app's agents answer people on
  "WHATSAPP_",
  "TELEGRAM_"
];
var AI_KEYS = { OPENAI_API_KEY: true, OPENROUTER_API_KEY: true };
var SIGN_IN_CLIENT_SECRETS = ["GOOGLE_CLIENT_SECRET", "MICROSOFT_CLIENT_SECRET"];
var SANDBOX_KEPT_SECRETS = /* @__PURE__ */ new Set([
  ...Object.keys(AI_KEYS),
  ...SIGN_IN_CLIENT_SECRETS,
  "BASE44_APP_ID"
]);
function runnerProcessEnv(config, secrets) {
  const env = {};
  for (const [key, value] of Object.entries(config.env)) {
    if (value !== "") env[key] = value;
  }
  for (const [key, value] of Object.entries(secrets)) env[key] = value;
  return env;
}
function composeRuntimeEnv(config, secrets, deployCredentialKeys) {
  const excluded = new Set(deployCredentialKeys);
  const env = {};
  const removals = [];
  for (const [key, value] of Object.entries(config.env)) {
    if (value !== "") env[key] = value;
  }
  for (const [key, value] of Object.entries(secrets)) {
    if (excluded.has(key)) continue;
    if (value === "") {
      delete env[key];
      removals.push(key);
    } else {
      env[key] = value;
    }
  }
  return { env, removals };
}

// src/migration/push/reconcile-doors.ts
var CORE_RECONCILE_FILE = "app/core/reconcile.py";
var MODULE_REGISTRIES = ["functions", "workflows", "actors"];
function reconcileDoors(fs, repo) {
  if (fs.exists(CORE_RECONCILE_FILE)) return [{ kind: "core", path: "/api/internal/reconcile" }];
  const doors = [];
  for (const registry of MODULE_REGISTRIES) {
    if (registry === "workflows" && !repo.hasWorkflowFiles) continue;
    const router = `app/modules/${registry}/router.py`;
    if (!fs.exists(router)) continue;
    if (!fs.read(router).includes('"/reconcile"')) continue;
    doors.push({ kind: "module", registry, path: `/api/internal/${registry}/reconcile` });
  }
  return doors;
}
function reconcileBody(door, payload) {
  if (door.kind === "core") return payload;
  switch (door.registry) {
    case "functions":
      return { functions: payload.functions };
    case "workflows":
      return { files: payload.workflows };
    case "actors":
      return { actors: payload.actors };
  }
}

// src/migration/push/functions-host.ts
var FUNCTIONS_DOOR = "app/modules/functions/router.py";
var SCHEDULES_DOOR = "app/modules/automations/router.py";
function cannotRunFunctions(input) {
  if (input.functions === 0 || input.hasHost && input.hasDoor) return null;
  return "this app had no backend functions when it was migrated, so it was set up without " + (input.hasHost ? "the backend module that serves them" : "a place to run them");
}
function wayToRunFunctions(input) {
  return input.hasDoor ? `Turn them on from the builder, or from the App Store card ("Push notifications") on the app's EscapeBase44 page; then deploy again.` : `Remove them from ${input.functionsDir}/, or write to daniel.frishtik@gmail.com.`;
}

// src/migration/push/report.ts
import { renameSync, writeFileSync as writeFileSync3 } from "fs";
import { join as join2 } from "path";
var REPORT_FILE = "eb44-report.json";
var REPORT_DELIVERED_FILE = "eb44-report.delivered";
async function sendReport(url, report, deps = {}) {
  const send = deps.fetch ?? providerFetch;
  const log = deps.log ?? ((line) => console.error(line));
  const body = JSON.stringify(report);
  let dir = "dir" in deps ? deps.dir : process.env.RUNNER_TEMP;
  if (dir) {
    try {
      writeFileSync3(join2(dir, REPORT_FILE), body, { mode: 384 });
    } catch (err) {
      log(`[run-deploy] the report could not be written to ${dir} (${err instanceof Error ? err.message : String(err)})`);
      dir = void 0;
    }
  }
  let why;
  try {
    const res = await send(url, {
      method: "POST",
      repeatable: true,
      headers: { "Content-Type": "application/json" },
      body
    });
    if (res.ok) {
      if (dir) renameSync(join2(dir, REPORT_FILE), join2(dir, REPORT_DELIVERED_FILE));
      return "delivered";
    }
    why = `our endpoint answered ${res.status}: ${(await res.text()).replace(/\s+/g, " ").trim().slice(0, 200)}`;
  } catch (err) {
    why = err instanceof Error ? err.message : String(err);
  }
  log(`[run-deploy] the report did not get through (${why})${dir ? " \u2014 the workflow's last step sends it again" : ""}`);
  return dir ? "handed over" : "lost";
}

// src/providers/lib/function-env.ts
import { readFileSync as readFileSync3 } from "fs";
import { join as join3 } from "path";
var SOURCE_EXTENSIONS = /* @__PURE__ */ new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".mts"]);
var ENV_READ_RE = /\b(?:Deno\.env|secrets)\.get\(\s*["'`]([A-Za-z_][A-Za-z0-9_]*)["'`]\s*\)/g;
function scanFunctionEnvNames(sourcePaths, root = ".") {
  const names = /* @__PURE__ */ new Set();
  for (const path of sourcePaths) {
    const dot = path.lastIndexOf(".");
    if (dot < 0 || !SOURCE_EXTENSIONS.has(path.slice(dot))) continue;
    const source = readFileSync3(join3(root, path), "utf-8");
    for (const m of source.matchAll(ENV_READ_RE)) names.add(m[1]);
  }
  return names;
}
function deriveFunctionEnv(input) {
  const names = new Set(input.floorKeys);
  for (const n of scanFunctionEnvNames(input.sourcePaths, input.root)) names.add(n);
  names.delete("BASE_URL");
  const env = { BASE_URL: input.appUrl };
  for (const name of [...names].sort()) {
    const value = input.runtimeEnv[name];
    if (value) env[name] = value;
  }
  const removals = input.runtimeEnvRemovals.filter((n) => names.has(n));
  return { env, removals };
}

// src/providers/lib/cron-schedule.ts
function normalize2(a) {
  if (a.schedule_mode === "one-time") {
    if (!a.one_time_date) return null;
    const target = new Date(a.one_time_date);
    const ms = target.getTime();
    if (isNaN(ms) || ms < Date.now()) return null;
    const cron = `${target.getUTCMinutes()} ${target.getUTCHours()} ${target.getUTCDate()} ${target.getUTCMonth() + 1} *`;
    return { cron, oneTimeMs: ms };
  }
  if (a.schedule_type === "cron") {
    if (!a.cron_expression) return null;
    return { cron: a.cron_expression };
  }
  const n = a.repeat_interval ?? 1;
  const [startHourStr, startMinStr] = (a.start_time ?? "00:00").split(":");
  const startHour = Number.parseInt(startHourStr || "0", 10);
  const startMin = Number.parseInt(startMinStr || "0", 10);
  switch (a.repeat_unit) {
    case "minutes":
      return { cron: `*/${n} * * * *` };
    case "hours":
      return { cron: `0 */${n} * * *` };
    case "days":
      return { cron: `${startMin} ${startHour} */${n} * *` };
    case "weeks": {
      const days = (a.repeat_on_days ?? []).filter((d) => Number.isInteger(d) && d >= 0 && d <= 6);
      const dow = days.length > 0 ? days.join(",") : "*";
      return { cron: `${startMin} ${startHour} * * ${dow}` };
    }
    case "months":
      return { cron: `${startMin} ${startHour} ${a.repeat_on_day_of_month ?? 1} */${n} *` };
    default:
      return null;
  }
}
function normalizeAutomations(automations) {
  const result = [];
  for (const a of automations) {
    const s = normalize2(a);
    if (!s) {
      console.warn(`Automation ${a.id} (${a.name}) on ${a.functionName} couldn't be normalized to cron \u2014 skipping`);
      continue;
    }
    result.push({
      id: a.id,
      functionName: a.functionName,
      cron: s.cron,
      oneTimeMs: s.oneTimeMs
    });
  }
  return result;
}

// src/providers/lib/actors-files.ts
import { existsSync as existsSync2, readdirSync as readdirSync2, statSync as statSync2 } from "fs";
import { join as join4 } from "path";
var ACTORS_DIR = "base44/actors";
var ACTOR_ENTRY = /^base44\/actors\/([A-Za-z_][A-Za-z0-9_]*)\/(entry\.ts|entry\.js)$/;
function listActors(files) {
  const byName = /* @__PURE__ */ new Map();
  for (const path of Object.keys(files)) {
    const m = ACTOR_ENTRY.exec(path.replace(/^(?:\.\/|\/)+/, ""));
    if (!m) continue;
    const existing = byName.get(m[1]);
    if (existing && existing.entry === "entry.ts") continue;
    byName.set(m[1], { name: m[1], entry: m[2] });
  }
  return [...byName.values()].sort((a, b) => a.name.localeCompare(b.name));
}
function readRepoActors(root = ".") {
  const dir = join4(root, ACTORS_DIR);
  if (!existsSync2(dir)) return [];
  const paths = {};
  for (const name of readdirSync2(dir)) {
    const folder = join4(dir, name);
    if (!statSync2(folder).isDirectory()) continue;
    for (const file of readdirSync2(folder)) paths[`${ACTORS_DIR}/${name}/${file}`] = "";
  }
  return listActors(paths);
}

// src/migration/push/run-deploy.ts
var WORKFLOWS_DIR = "base44/workflows";
var EMAILS_DIR = "base44/emails";
function readWorkflowFiles() {
  if (!existsSync3(WORKFLOWS_DIR)) return {};
  const files = {};
  for (const name of readdirSync3(WORKFLOWS_DIR)) {
    if (!name.endsWith(".jsonc")) continue;
    files[`${WORKFLOWS_DIR}/${name}`] = readFileSync4(`${WORKFLOWS_DIR}/${name}`, "utf-8");
  }
  return files;
}
function readEmailTemplateFiles(dir = EMAILS_DIR, files = {}) {
  if (!existsSync3(dir)) return files;
  for (const entry of readdirSync3(dir, { withFileTypes: true })) {
    const path = `${dir}/${entry.name}`;
    if (entry.isDirectory()) readEmailTemplateFiles(path, files);
    else if (entry.name.endsWith(".html")) files[path] = readFileSync4(path, "utf-8");
  }
  return files;
}
async function reconcile(appUrl, payload, repo) {
  const doors = reconcileDoors({ exists: existsSync3, read: (p) => readFileSync4(p, "utf-8") }, repo);
  if (doors.length === 0) {
    console.log("[run-deploy] no registry door to converge (the backend declares none this checkout carries files for) \u2014 nothing to do");
    return;
  }
  for (const door of doors) {
    const url = `${appUrl.replace(/\/$/, "")}${door.path}`;
    const body = reconcileBody(door, payload);
    const label = door.kind === "core" ? "reconciled" : `${door.registry} reconciled`;
    const maxAttempts = 4;
    let lastError;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        const res = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Eb44-Cron-Secret": process.env.EB44_CRON_SECRET ?? ""
          },
          body: JSON.stringify(body)
        });
        const text = await res.text();
        if (!res.ok) throw new Error(`${door.path} returned ${res.status}: ${text.slice(0, 500)}`);
        console.log(`[run-deploy] ${label}: ${text.slice(0, 1200)}`);
        lastError = void 0;
        break;
      } catch (err) {
        lastError = err;
        if (attempt < maxAttempts) await new Promise((r) => setTimeout(r, 5e3 * attempt));
      }
    }
    if (lastError !== void 0) throw lastError;
  }
}
async function healthCheck(appUrl) {
  const url = `${appUrl.replace(/\/$/, "")}/health`;
  const deadline = Date.now() + 5 * 6e4;
  let last = "";
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(1e4) });
      const body = (await res.text()).trim();
      if (res.ok) {
        const parsed = JSON.parse(body);
        if (parsed.status === "ok" && Object.keys(parsed).length === 1) {
          console.log("[run-deploy] health check passed");
          return;
        }
      }
      last = `${res.status} ${body.slice(0, 200)}`;
    } catch (err) {
      last = err instanceof Error ? err.message : String(err);
    }
    await new Promise((r) => setTimeout(r, 5e3));
  }
  console.error("[run-deploy] === why the app is not serving ===");
  try {
    console.error(await explainUnhealthy(define_PROVIDER_CONFIG_default));
  } catch (err) {
    console.error(`(could not read the provider's view: ${err instanceof Error ? err.message : String(err)})`);
  }
  throw new Error(`Health check failed: ${url} never served the app's health signature (last: ${last})`);
}
async function main() {
  const config = readRepoConfig();
  const secrets = readSecretsBlob();
  Object.assign(process.env, runnerProcessEnv(config, secrets));
  const { env: runtimeEnv, removals } = composeRuntimeEnv(config, secrets, define_DEPLOY_CREDENTIAL_KEYS_default);
  if (process.env.GITHUB_SHA) runtimeEnv.EB44_BUILD_MARKER = process.env.GITHUB_SHA;
  if (existsSync3("capacitor.config.json")) {
    try {
      const capacitor = JSON.parse(readFileSync4("capacitor.config.json", "utf-8"));
      if (capacitor.appId) {
        if (!runtimeEnv.MOBILE_BUNDLE_ID) runtimeEnv.MOBILE_BUNDLE_ID = capacitor.appId;
        if (!runtimeEnv.MOBILE_IOS_BUNDLE_ID) runtimeEnv.MOBILE_IOS_BUNDLE_ID = capacitor.appId;
        if (!runtimeEnv.MOBILE_ANDROID_PACKAGE) runtimeEnv.MOBILE_ANDROID_PACKAGE = capacitor.appId;
      }
    } catch (err) {
      console.warn("[run-deploy] capacitor.config.json unreadable \u2014 the mobile ids were not derived:", err);
    }
  }
  if (existsSync3("mobile/native.json")) {
    try {
      const native = JSON.parse(readFileSync4("mobile/native.json", "utf-8"));
      if (native.links) runtimeEnv.MOBILE_APP_LINKS = "true";
    } catch (err) {
      console.warn("[run-deploy] mobile/native.json unreadable \u2014 links were not turned on:", err);
    }
  }
  const appUrl = config.appUrl;
  const reportUrl = secrets.EB44_REPORT_URL;
  console.log(`[run-deploy] pipeline v${define_EB44_PIPELINE_default.version} appUrl=${appUrl} reporting=${Boolean(reportUrl)}`);
  try {
    const workflowFiles = readWorkflowFiles();
    const hasWorkflows = Object.keys(workflowFiles).length > 0;
    const repoFunctions = readDeployedFunctions(config);
    const withoutAHost = [];
    const automations = repoFunctions.tree === "base44" ? normalizeAutomations(scheduledAutomations(repoFunctions.automations)) : define_AUTOMATIONS_default;
    if (repoFunctions.tree === "base44") {
      console.log(
        `[run-deploy] functions: ${repoFunctions.bundles.length} under ${repoFunctions.functionsDir}, ${automations.length} schedule(s)`
      );
      const names = repoFunctions.bundles.map((b) => b.name);
      const hasDoor = existsSync3(FUNCTIONS_DOOR);
      const noFunctions = cannotRunFunctions({
        functions: names.length,
        hasHost: define_PROVIDER_CONFIG_default.edge != null,
        hasDoor
      });
      if (noFunctions !== null) {
        if (!reportUrl) {
          throw new Error(
            `${names.length} backend function(s) are in the repo (${names.join(", ")}) and cannot run: ${noFunctions}. ` + wayToRunFunctions({ hasDoor, functionsDir: repoFunctions.functionsDir })
          );
        }
        for (const name of names) {
          console.warn(`[run-deploy] ${name} cannot run: ${noFunctions}`);
          withoutAHost.push({ name, reason: noFunctions });
        }
      }
      if (automations.length > 0 && !existsSync3(SCHEDULES_DOOR)) {
        throw new Error(
          `${automations.length} function schedule(s) are declared (${automations.map((a) => a.functionName).join(", ")}) and this app's backend has no scheduler (${SCHEDULES_DOOR}): the app had no schedules when it was migrated, so that module was left out. Remove the schedule from the function's function.jsonc, or write to daniel.frishtik@gmail.com.`
        );
      }
    }
    const functionEnv = deriveFunctionEnv({
      sourcePaths: functionSourcePaths(repoFunctions),
      appUrl,
      runtimeEnv,
      runtimeEnvRemovals: removals,
      floorKeys: define_USER_SECRET_KEYS_default
    });
    const ctx = {
      hasWorkflows,
      runtimeEnv,
      runtimeEnvRemovals: removals,
      functionEnv,
      automations,
      functions: repoFunctions,
      migrationDay: Boolean(reportUrl),
      functionsNotLoading: /* @__PURE__ */ new Map()
    };
    console.log("[run-deploy] === deploying app ===");
    await deploy(define_PROVIDER_CONFIG_default, ctx);
    console.log("[run-deploy] app deployed");
    console.log("[run-deploy] === deploying edge functions ===");
    const deployed = await deploy2(appUrl, define_PROVIDER_CONFIG_default, automations, ctx);
    console.log(`[run-deploy] edge deployed (${deployed.length} function(s))`);
    const functions = deployed.map(({ name, url }) => repoFunctions.tree === "base44" ? { name, url, automations: repoFunctions.automations.get(name) ?? [] } : { name, url });
    const notLoading = deployed.filter((fn) => fn.notLoading);
    console.log("[run-deploy] === health check ===");
    await healthCheck(appUrl);
    const emailTemplateFiles = readEmailTemplateFiles();
    const actors = readRepoActors();
    console.log(
      `[run-deploy] === reconciling ${functions.length} function(s), ${Object.keys(workflowFiles).length} workflow file(s) + ${Object.keys(emailTemplateFiles).length} email template(s), ${actors.length} actor(s) ===`
    );
    await reconcile(appUrl, { functions, workflows: { ...workflowFiles, ...emailTemplateFiles }, actors }, { hasWorkflowFiles: hasWorkflows });
    for (const fn of notLoading) {
      console.log(`::warning title=${fn.name} does not load::${fn.notLoading} \u2014 it is deployed all the same, and its calls fail until its code is fixed`);
    }
    if (reportUrl) {
      console.log("[run-deploy] posting migration-day report");
      const outcome = await sendReport(reportUrl, {
        success: true,
        appUrl,
        functions: deployed.map(({ name, url }) => ({ name, url })),
        notLoading: [...notLoading.map((fn) => ({ name: fn.name, reason: fn.notLoading })), ...withoutAHost],
        mongoUrl: runtimeEnv.MONGO_URL,
        mongoDbName: runtimeEnv.MONGO_DB
      });
      if (outcome === "delivered") console.log("[run-deploy] report ok");
      if (outcome === "lost") process.exit(1);
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("Deploy failed:", message);
    if (err instanceof Error && err.stack) console.error(err.stack);
    if (reportUrl) await sendReport(reportUrl, { success: false, error: message });
    process.exit(1);
  }
}
main();
