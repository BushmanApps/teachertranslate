// Firebase's config for this app's Android build (google-services.json),
// read from your own Firebase project with the key push was set up with.
// Your package is registered there as an Android app the first time, and
// read from then on. Used by mobile/setup.mjs.
import { createSign } from "node:crypto";

const TOKEN_URL = "https://oauth2.googleapis.com/token";
const API = "https://firebase.googleapis.com/v1beta1/";
const WAITS_MS = [1000, 2000, 4000, 8000];

export class FirebaseStop extends Error {
  constructor(code, extra) {
    super(code);
    this.code = code;
    this.extra = extra || {};
  }
}

function base64url(input) {
  return Buffer.from(input).toString("base64").replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
}

export function parseServiceAccount(text) {
  let sa = null;
  try { sa = JSON.parse(text); } catch (e) { sa = null; }
  if (!sa || typeof sa.client_email !== "string" || typeof sa.private_key !== "string" || typeof sa.project_id !== "string") {
    throw new FirebaseStop("firebase-key-malformed");
  }
  return sa;
}

// One call, answered: a dropped connection, a 429 and a 5xx are asked again
// on a short ladder when asking again cannot double anything.
async function ask(io, method, url, headers, body, repeatable) {
  const waits = repeatable ? WAITS_MS : [];
  for (let attempt = 0; ; attempt++) {
    let res = null, failure = null;
    try {
      res = await io.fetch(url, { method: method, headers: headers, body: body });
    } catch (err) {
      failure = String((err && err.message) || err);
    }
    const again = failure !== null || res.status === 429 || res.status >= 500;
    if (again && attempt < waits.length) { await io.sleep(waits[attempt]); continue; }
    if (failure !== null) throw new FirebaseStop("firebase-unreachable", { detail: failure });
    const text = await res.text();
    let json = null;
    try { json = text ? JSON.parse(text) : null; } catch (e) { json = null; }
    return { status: res.status, json: json || {}, text: text };
  }
}

function refusal(r, what) {
  const e = (r.json && r.json.error) || {};
  const detail = typeof e === "string" ? e + (r.json.error_description ? ": " + r.json.error_description : "") : (e.status || "") + (e.message ? ": " + e.message : "");
  if (r.status === 401 || r.status === 403) return new FirebaseStop("firebase-not-allowed", { what: what, status: r.status, detail: detail });
  if (r.status === 429 || r.status >= 500) return new FirebaseStop("firebase-unreachable", { what: what, status: r.status, detail: detail });
  return new FirebaseStop("firebase-error", { what: what, status: r.status, detail: detail || r.text.slice(0, 300) });
}

// A service account signs its own JWT; Google trades it for an access token.
async function accessToken(io, sa) {
  const now = Math.floor(Date.now() / 1000);
  const header = base64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const claims = base64url(JSON.stringify({
    iss: sa.client_email,
    scope: "https://www.googleapis.com/auth/firebase",
    aud: TOKEN_URL,
    iat: now,
    exp: now + 600,
  }));
  let assertion;
  try {
    const signer = createSign("RSA-SHA256");
    signer.update(header + "." + claims);
    assertion = header + "." + claims + "." + base64url(signer.sign(sa.private_key));
  } catch (err) {
    throw new FirebaseStop("firebase-key-malformed", { detail: String((err && err.message) || err) });
  }
  const r = await ask(io, "POST", TOKEN_URL, { "Content-Type": "application/x-www-form-urlencoded" },
    "grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=" + encodeURIComponent(assertion), true);
  if (r.status === 200 && r.json.access_token) return r.json.access_token;
  // Google's answer for a key that was deleted or disabled.
  if (r.status === 400 || r.status === 401) throw new FirebaseStop("firebase-key-refused", { detail: (r.json.error || "") + (r.json.error_description ? ": " + r.json.error_description : "") });
  throw refusal(r, "signing in");
}

async function findApp(io, headers, projectId, packageName) {
  let pageToken = "";
  do {
    const r = await ask(io, "GET", API + "projects/" + projectId + "/androidApps?pageSize=100" + (pageToken ? "&pageToken=" + encodeURIComponent(pageToken) : ""), headers, undefined, true);
    if (r.status !== 200) throw refusal(r, "listing the project's Android apps");
    const found = (r.json.apps || []).find(function (a) { return a.packageName === packageName; });
    if (found) return found;
    pageToken = r.json.nextPageToken || "";
  } while (pageToken);
  return null;
}

// Registering makes something new, so the call itself is made once; what
// runs again is the question "is it there?" — an answer that never arrived
// may still have registered the app, and asking first never doubles it.
async function registerApp(io, headers, projectId, packageName, displayName) {
  let last = null;
  for (let attempt = 0; attempt <= WAITS_MS.length; attempt++) {
    if (attempt > 0) {
      await io.sleep(WAITS_MS[attempt - 1]);
      const there = await findApp(io, headers, projectId, packageName);
      if (there) return there;
    }
    let r;
    try {
      r = await ask(io, "POST", API + "projects/" + projectId + "/androidApps", headers, JSON.stringify({ packageName: packageName, displayName: displayName }), false);
    } catch (err) {
      if (err instanceof FirebaseStop && err.code === "firebase-unreachable") { last = err; continue; }
      throw err;
    }
    if (r.status === 429 || r.status >= 500) { last = refusal(r, "registering " + packageName); continue; }
    // Registered a moment ago by another build of the same app.
    if (r.status === 409) { const there = await findApp(io, headers, projectId, packageName); if (there) return there; }
    if (r.status !== 200 || !r.json.name) throw refusal(r, "registering " + packageName);
    // A long-running operation: done within seconds.
    for (let i = 0; i < 40; i++) {
      const op = r.json.done ? r : await ask(io, "GET", API + r.json.name, headers, undefined, true);
      if (op.status !== 200) throw refusal(op, "registering " + packageName);
      if (op.json.done) {
        if (op.json.error) throw new FirebaseStop("firebase-error", { what: "registering " + packageName, detail: (op.json.error.message || JSON.stringify(op.json.error)) });
        return op.json.response;
      }
      await io.sleep(1500);
    }
    throw new FirebaseStop("firebase-unreachable", { what: "registering " + packageName, detail: "Firebase did not finish within a minute" });
  }
  throw last;
}

// → { config: the file's text, projectId, appId, registered: true when this
// call registered the package }
export async function androidFirebaseConfig(serviceAccountText, packageName, displayName, deps) {
  const io = Object.assign({ fetch: fetch, sleep: function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); } }, deps || {});
  const sa = parseServiceAccount(serviceAccountText);
  const token = await accessToken(io, sa);
  const headers = { Authorization: "Bearer " + token, "Content-Type": "application/json" };
  let app = await findApp(io, headers, sa.project_id, packageName);
  const registered = !app;
  if (!app) app = await registerApp(io, headers, sa.project_id, packageName, displayName);
  const r = await ask(io, "GET", API + app.name + "/config", headers, undefined, true);
  if (r.status !== 200 || !r.json.configFileContents) throw refusal(r, "reading the config of " + packageName);
  const config = Buffer.from(r.json.configFileContents, "base64").toString("utf-8");
  const clients = (JSON.parse(config).client || []).map(function (c) { return c.client_info && c.client_info.android_client_info && c.client_info.android_client_info.package_name; });
  if (clients.indexOf(packageName) < 0) throw new FirebaseStop("firebase-error", { what: "reading the config of " + packageName, detail: "the file Firebase returned does not hold this package" });
  return { config: config, projectId: sa.project_id, appId: app.appId, registered: registered };
}
