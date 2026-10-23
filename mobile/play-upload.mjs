// Uploads the signed Android bundle to Google Play's internal testing
// track. Run by the Mobile release workflow after a green build:
//   node mobile/play-upload.mjs <path to the .aab> <package name>
// with IAP_GOOGLE_SA_JSON_B64 (the Play service account's JSON key, base64)
// in the environment. Every stop is one EB44 {"code":…} line; the words for
// each code live on your EscapeBase44 success page.
import { createSign } from "node:crypto";
import { readFileSync } from "node:fs";

const [aabPath, packageName] = process.argv.slice(2);
const SA_B64 = process.env.IAP_GOOGLE_SA_JSON_B64 || "";

function emit(fact) { console.log("EB44 " + JSON.stringify(fact)); }
function stop(code, extra) {
  emit(Object.assign({ code: code }, extra || {}));
  console.log("::error::Stopped (" + code + "). Your EscapeBase44 success page says what to do.");
  process.exit(1);
}

function base64url(input) {
  return Buffer.from(input).toString("base64").replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
}

// A service account signs its own JWT; Google trades it for an access token.
async function accessToken(sa) {
  const now = Math.floor(Date.now() / 1000);
  const header = base64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const claims = base64url(JSON.stringify({
    iss: sa.client_email,
    scope: "https://www.googleapis.com/auth/androidpublisher",
    aud: "https://oauth2.googleapis.com/token",
    iat: now,
    exp: now + 600,
  }));
  const signer = createSign("RSA-SHA256");
  signer.update(header + "." + claims);
  const assertion = header + "." + claims + "." + base64url(signer.sign(sa.private_key));
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=" + encodeURIComponent(assertion),
  });
  const json = await r.json().catch(function () { return {}; });
  if (!r.ok || !json.access_token) stop("play-upload-failed", { detail: "the service account could not sign in: " + (json.error_description || json.error || r.status) });
  return json.access_token;
}

const API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/";
const UPLOAD = "https://androidpublisher.googleapis.com/upload/androidpublisher/v3/applications/";

async function call(token, method, url, body, contentType) {
  const r = await fetch(url, {
    method: method,
    headers: Object.assign({ Authorization: "Bearer " + token }, contentType ? { "Content-Type": contentType } : {}),
    body: body,
  });
  const text = await r.text();
  let json = {};
  try { json = JSON.parse(text); } catch (e) { json = {}; }
  return { status: r.status, json: json, text: text };
}

// Google's answers, classified: the app is not in Play yet (404), the
// account was not given the permission (403), the version code was already
// uploaded (400 with those words), anything else with Google's own message.
function classify(r, what) {
  const message = ((r.json.error || {}).message) || r.text.slice(0, 300);
  if (r.status === 404) stop("play-app-missing", { detail: message });
  // The service account's Google Cloud project has never had the Play API
  // switched on (a Firebase project's account, typically) — Google names
  // the page that switches it on in its message.
  const enable = /API has not been used|it is disabled/i.test(message) && (message.match(/https:\/\/console\.developers\.google\.com\/apis\/api\/androidpublisher\.googleapis\.com\/overview\?project=\d+/) || [])[0];
  if (r.status === 403 && enable) stop("play-api-disabled", { detail: message, enableUrl: enable });
  if (r.status === 403 || r.status === 401) stop("play-no-permission", { detail: message });
  if (r.status === 400 && /already been used|already exists|has already/i.test(message)) stop("play-version-used", { detail: message });
  stop("play-upload-failed", { detail: what + ": " + r.status + " " + message });
}

async function main() {
  if (!aabPath || !packageName) stop("play-upload-failed", { detail: "usage: play-upload.mjs <aab> <package>" });
  let sa;
  try {
    sa = JSON.parse(Buffer.from(SA_B64, "base64").toString("utf-8"));
    if (!sa.client_email || !sa.private_key) throw new Error("not a service account key");
  } catch (e) {
    stop("play-upload-failed", { detail: "IAP_GOOGLE_SA_JSON_B64 is not a service account key: " + e.message });
  }
  const token = await accessToken(sa);
  const base = API + encodeURIComponent(packageName) + "/edits";

  let r = await call(token, "POST", base, "{}", "application/json");
  if (r.status !== 200) classify(r, "opening an edit");
  const editId = r.json.id;

  r = await call(token, "POST", UPLOAD + encodeURIComponent(packageName) + "/edits/" + editId + "/bundles?uploadType=media", readFileSync(aabPath), "application/octet-stream");
  if (r.status !== 200) classify(r, "uploading the bundle");
  const versionCode = r.json.versionCode;

  r = await call(token, "PUT", base + "/" + editId + "/tracks/internal",
    JSON.stringify({ track: "internal", releases: [{ versionCodes: [String(versionCode)], status: "completed" }] }), "application/json");
  if (r.status !== 200) classify(r, "putting the build on the internal track");

  r = await call(token, "POST", base + "/" + editId + ":commit", "", null);
  if (r.status !== 200) classify(r, "committing the edit");

  emit({ kind: "play-uploaded", platform: "android", packageName: packageName, versionCode: versionCode, track: "internal" });
  console.log("Uploaded version code " + versionCode + " to Google Play's internal testing track.");
}

main().catch(function (e) { stop("play-upload-failed", { detail: String(e && e.message || e) }); });
