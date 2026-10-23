// <define:__DEPLOY_CREDENTIAL_KEYS__>
var define_DEPLOY_CREDENTIAL_KEYS_default = ["VERCEL_TOKEN", "SUPABASE_TOKEN", "EB44_REPORT_URL", "EB44_SSH_PRIVATE_KEY", "ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_P8", "ASC_TEAM_ID", "ANDROID_KEYSTORE_B64", "ANDROID_KEYSTORE_PASSWORD", "ANDROID_KEY_ALIAS", "ANDROID_KEY_PASSWORD"];

// <define:__EB44_PIPELINE__>
var define_EB44_PIPELINE_default = { version: 2 };

// <define:__USER_SECRET_KEYS__>
var define_USER_SECRET_KEYS_default = ["BASE44_APP_ID", "STRIPE_PUBLISHABLE_KEY", "STRIPE_SECRET_KEY", "STRIPE_TEST_PUBLISHABLE_KEY", "STRIPE_TEST_SECRET_KEY", "STRIPE_TEST_WEBHOOK_SECRET", "STRIPE_WEBHOOK_SECRET"];

// src/migration/push/eject-env.ts
import { mkdirSync as mkdirSync2, writeFileSync as writeFileSync2 } from "fs";

// src/migration/push/compose-env.ts
import { readFileSync } from "fs";
var CONFIG_PATH = ".escapebase44/config.json";
var SECRETS_FILE_ENV = "EB44_SECRETS_FILE";
var GITHUB_INJECTED_SECRETS = /* @__PURE__ */ new Set(["github_token", "GITHUB_TOKEN"]);
function readRepoConfig() {
  const raw = JSON.parse(readFileSync(CONFIG_PATH, "utf-8"));
  if (typeof raw.appUrl !== "string" || typeof raw.env !== "object") {
    throw new Error(`${CONFIG_PATH} is malformed \u2014 expected { appUrl, env }`);
  }
  return raw;
}
function readSecretsBlob() {
  const path = process.env[SECRETS_FILE_ENV];
  if (!path) throw new Error(`${SECRETS_FILE_ENV} not set \u2014 the workflow must write the secrets file`);
  const blob = JSON.parse(readFileSync(path, "utf-8"));
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
var SANDBOX_EJECT_EXCLUDED_NAMES = [
  // the database
  "MONGO_URL",
  "MONGO_DB",
  // the running app: its token secrets, its service identity, its cron door
  "APP_JWT_SECRET",
  "SERVICE_JWT_SECRET",
  "SERVICE_PRINCIPAL_ID",
  "EB44_CRON_SECRET",
  // which store and which sender (their names follow by prefix)
  "STORAGE_PROVIDER",
  "EMAIL_PROVIDER",
  "EMAIL_FROM"
];
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
function isSandboxExcluded(name) {
  return SANDBOX_EJECT_EXCLUDED_NAMES.includes(name) || SANDBOX_EJECT_EXCLUDED_PREFIXES.some((p) => name.startsWith(p));
}
var AI_KEYS = { OPENAI_API_KEY: true, OPENROUTER_API_KEY: true };
var SIGN_IN_CLIENT_SECRETS = ["GOOGLE_CLIENT_SECRET", "MICROSOFT_CLIENT_SECRET"];
var SANDBOX_KEPT_SECRETS = /* @__PURE__ */ new Set([
  ...Object.keys(AI_KEYS),
  ...SIGN_IN_CLIENT_SECRETS,
  "BASE44_APP_ID"
]);
function sandboxRuntimeEnv(env, secretNames) {
  const out = {};
  for (const [k, v] of Object.entries(env)) {
    if (isSandboxExcluded(k)) continue;
    if (secretNames.has(k) && !SANDBOX_KEPT_SECRETS.has(k)) continue;
    out[k] = v;
  }
  return out;
}
function ejectedEnv(profile, config, secrets, deployCredentialKeys) {
  const composed = composeRuntimeEnv(config, secrets, deployCredentialKeys);
  if (profile === "sandbox") return { runtimeEnv: sandboxRuntimeEnv(composed.env, new Set(Object.keys(secrets))), removals: composed.removals, deployCredentials: {} };
  const deployCredentials = {};
  for (const key of deployCredentialKeys) {
    if (key === "EB44_REPORT_URL") continue;
    const value = secrets[key];
    if (value) deployCredentials[key] = value;
  }
  return { runtimeEnv: composed.env, removals: composed.removals, deployCredentials };
}
var DEV_ENV_DEFAULTS = {
  // The address the backend mints links against: vite itself, which
  // proxies /api to the backend and forwards the browser's host.
  BASE_URL: "http://localhost:5173",
  // Where the backend reads index.html on startup; the dev script creates
  // it empty (vite serves the frontend, uvicorn's static mount is idle).
  FRONTEND_DIR: "dist",
  // The proxy.py hook that routes /functions/{name} to the local supervisor
  // instead of the deployed function URL. Unset in prod.
  ESCAPEBASE44_DEV_FUNCTIONS_BASE_URL: "http://localhost:8002"
};
var DEV_VITE_ENV = {
  VITE_BASE44_BACKEND_URL: "http://localhost:5173",
  VITE_BASE44_APP_BASE_URL: ""
};
function devEnvLocal(runtimeEnv, deployCredentials, functionEnvNames) {
  return {
    ...runtimeEnv,
    ...deployCredentials,
    ...DEV_ENV_DEFAULTS,
    ...DEV_VITE_ENV,
    ESCAPEBASE44_FUNCTION_ENV_ALLOWLIST: functionEnvNames.join(",")
  };
}
function serializeEnvFile(env) {
  const escape = (value) => value.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\$/g, "\\$").replace(/`/g, "\\`").replace(/\n/g, "\\n");
  return Object.entries(env).map(([k, v]) => `${k}="${escape(v)}"`).join("\n") + "\n";
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

// src/providers/lib/function-env.ts
import { readFileSync as readFileSync2 } from "fs";
import { join } from "path";
var SOURCE_EXTENSIONS = /* @__PURE__ */ new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".mts"]);
var ENV_READ_RE = /\b(?:Deno\.env|secrets)\.get\(\s*["'`]([A-Za-z_][A-Za-z0-9_]*)["'`]\s*\)/g;
function scanFunctionEnvNames(sourcePaths, root = ".") {
  const names = /* @__PURE__ */ new Set();
  for (const path of sourcePaths) {
    const dot = path.lastIndexOf(".");
    if (dot < 0 || !SOURCE_EXTENSIONS.has(path.slice(dot))) continue;
    const source = readFileSync2(join(root, path), "utf-8");
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

// src/providers/lib/function-sources.ts
import { createHash } from "crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync as readFileSync3, readdirSync, statSync, writeFileSync, copyFileSync } from "fs";
import { dirname as dirname2, join as join2 } from "path";

// src/providers/lib/deploy-paths.ts
var FUNCTIONS_DIR = ".escapebase44/functions";
var FUNCTIONS_MANIFEST_PATH = `${FUNCTIONS_DIR}/_manifest.json`;

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

// src/providers/lib/function-sources.ts
function listRepoFiles(dir, root = ".") {
  const out = [];
  const walk = (rel) => {
    const abs = join2(root, rel);
    if (!existsSync(abs)) return;
    for (const entry of readdirSync(abs)) {
      if (entry.startsWith(".")) continue;
      const child = `${rel}/${entry}`;
      if (statSync(join2(root, child)).isDirectory()) walk(child);
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
    readText: (path) => readFileSync3(join2(root, path), "utf-8")
  });
  if (problems.length > 0) {
    throw new Error(`The backend functions under ${functionsDir} cannot be deployed:
  - ${problems.join("\n  - ")}`);
  }
  return { functions, paths };
}
function readFunctionBundles(functionsDir, root = ".") {
  const { functions, paths } = readRepoFunctions(functionsDir, root);
  const bundles = functions.map((fn) => bundleFunction({ fn, paths, functionsDir, readText: (path) => readFileSync3(join2(root, path), "utf-8") }));
  return { functions, bundles };
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
function readDeployedFunctions(config, root = ".") {
  if (!config.functionsDir) return { tree: "legacy" };
  const { functions, bundles } = readFunctionBundles(config.functionsDir, root);
  return { tree: "base44", functionsDir: config.functionsDir, bundles, automations: repoAutomations(functions) };
}
function listAllFiles(dir, root) {
  const out = [];
  const walk = (rel) => {
    const abs = join2(root, rel);
    if (!existsSync(abs)) return;
    for (const entry of readdirSync(abs)) {
      const child = `${rel}/${entry}`;
      if (statSync(join2(root, child)).isDirectory()) walk(child);
      else out.push(child);
    }
  };
  walk(dir);
  return out;
}

// src/migration/push/eject-env.ts
var ARTIFACT_DIR = "eb44-env";
async function main() {
  console.log(`[eject-env] pipeline v${define_EB44_PIPELINE_default.version}`);
  const config = readRepoConfig();
  const secrets = readSecretsBlob();
  const profile = process.env.EB44_EJECT_PROFILE === "sandbox" ? "sandbox" : "full";
  const { runtimeEnv, removals, deployCredentials } = ejectedEnv(profile, config, secrets, define_DEPLOY_CREDENTIAL_KEYS_default);
  const functionEnv = deriveFunctionEnv({
    sourcePaths: functionSourcePaths(readDeployedFunctions(config)),
    appUrl: config.appUrl,
    runtimeEnv,
    runtimeEnvRemovals: removals,
    floorKeys: define_USER_SECRET_KEYS_default
  });
  const devEnv = devEnvLocal(runtimeEnv, deployCredentials, Object.keys(functionEnv.env));
  const payload = { appUrl: config.appUrl, profile, runtimeEnv, deployCredentials, devEnv };
  const deliveryUrl = process.env.EB44_DELIVERY_URL;
  if (deliveryUrl) {
    console.log(`[eject-env] delivering ${Object.keys(runtimeEnv).length} runtime + ${Object.keys(deployCredentials).length} credential value(s)`);
    const form = new FormData();
    form.set("file", new Blob([JSON.stringify(payload)], { type: "application/json" }), "payload.json");
    const res = await fetch(deliveryUrl, { method: "POST", body: form });
    if (!res.ok) {
      throw new Error(`Delivery failed: ${res.status} ${(await res.text()).slice(0, 300)}`);
    }
    console.log("[eject-env] delivered");
  } else {
    mkdirSync2(ARTIFACT_DIR, { recursive: true });
    writeFileSync2(`${ARTIFACT_DIR}/payload.json`, JSON.stringify(payload, null, 2) + "\n");
    writeFileSync2(`${ARTIFACT_DIR}/runtime.env`, serializeEnvFile(runtimeEnv));
    writeFileSync2(`${ARTIFACT_DIR}/deploy-credentials.env`, serializeEnvFile(deployCredentials));
    writeFileSync2(`${ARTIFACT_DIR}/env.local`, serializeEnvFile(devEnv));
    console.log("[eject-env] wrote artifact files");
  }
}
main().catch((err) => {
  console.error("Eject failed:", err instanceof Error ? err.message : String(err));
  process.exit(1);
});
