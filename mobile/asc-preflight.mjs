#!/usr/bin/env node
// Asks App Store Connect what this build needs to know, with this repo's own
// key, before the Mac starts. Run by the Mobile release workflow; prints
// EB44 {…} lines the EscapeBase44 success page reads. Plain Node.
import { createSign, createPrivateKey } from "node:crypto";
import { readFileSync, existsSync, appendFileSync } from "node:fs";
import { readNativeSettings, NativeSettingsError, iosEntitlements, capabilitiesFor, mergeEntitlements, plistObject } from "./native-patches.mjs";

const env = process.env;
const facts = existsSync(".escapebase44/config.json")
  ? JSON.parse(readFileSync(".escapebase44/config.json", "utf-8")).env || {}
  : {};
const capacitor = JSON.parse(readFileSync("capacitor.config.json", "utf-8"));
const BUNDLE_ID = env.MOBILE_IOS_BUNDLE_ID || facts.MOBILE_IOS_BUNDLE_ID || capacitor.appId;
// The Base44 app this repo came from — its wrapper published under
// com.base<id>.app, the id a person already in the App Store must keep.
const BASE44_BUNDLE_ID = facts.APP_ID ? "com.base" + facts.APP_ID + ".app" : null;
const APP_NAME = capacitor.appName || "App";
const RUN_NUMBER = Number(env.GITHUB_RUN_NUMBER || 1);
// Where the App Store tells the app's own backend about renewals, refunds
// and credit packs bought (App Store Server Notifications) — when this repo's
// backend has the door for them.
const IAP_ROUTER = "app/modules/iap/router.py";
const NOTIFICATIONS_URL = existsSync(IAP_ROUTER) && readFileSync(IAP_ROUTER, "utf-8").includes("/apple/notifications") && facts.APP_ID && capacitor.server && capacitor.server.url
  ? new URL("/api/apps/" + facts.APP_ID + "/eb44/iap/apple/notifications", capacitor.server.url).toString()
  : null;

function emit(obj) { console.log("EB44 " + JSON.stringify(obj)); }
function stop(code, extra) {
  emit(Object.assign({ code: code }, extra || {}));
  console.log("::error::Stopped before building (" + code + "). Your EscapeBase44 success page says what to do.");
  process.exit(1);
}
function output(name, value) {
  if (env.GITHUB_OUTPUT) appendFileSync(env.GITHUB_OUTPUT, name + "=" + value + "\n");
}
function b64url(buf) {
  return Buffer.from(buf).toString("base64").replace(/=+$/g, "").replace(/\+/g, "-").replace(/\//g, "_");
}

// App Store Connect's JWT: ES256, the key id in the header, the issuer +
// a ≤20-minute expiry + the fixed audience in the payload.
function jwt() {
  const now = Math.floor(Date.now() / 1000);
  const header = b64url(JSON.stringify({ alg: "ES256", kid: env.ASC_KEY_ID, typ: "JWT" }));
  const payload = b64url(JSON.stringify({ iss: env.ASC_ISSUER_ID, iat: now, exp: now + 1200, aud: "appstoreconnect-v1" }));
  const key = createPrivateKey(env.ASC_KEY_P8);
  const signature = createSign("SHA256").update(header + "." + payload).sign({ key: key, dsaEncoding: "ieee-p1363" });
  return header + "." + payload + "." + b64url(signature);
}

const API = env.ASC_API_BASE || "https://api.appstoreconnect.apple.com";
let TOKEN = null;
async function asc(method, path, body) {
  let res;
  try {
    res = await fetch(API + path, {
      method: method,
      headers: { Authorization: "Bearer " + TOKEN, Accept: "application/json", "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    stop("apple-unreachable", { detail: String((err && err.message) || err) });
  }
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch (e) { json = null; }
  const errors = (json && json.errors) || [];
  return { status: res.status, json: json, detail: errors.map(function (e) { return (e.title || "") + (e.detail ? ": " + e.detail : ""); }).join("; ") };
}
function fail(r, what) {
  stop("apple-error", { status: r.status, what: what, detail: r.detail });
}

// Versions compare and bump as dotted numbers ("1.0" < "1.0.1" < "1.2").
function parts(v) { return String(v).split(".").map(function (x) { return Number(x) || 0; }); }
function compare(a, b) {
  const pa = parts(a), pb = parts(b), n = Math.max(pa.length, pb.length);
  for (let i = 0; i < n; i++) { const d = (pa[i] || 0) - (pb[i] || 0); if (d !== 0) return d; }
  return 0;
}
function bump(v) { const p = parts(v); p[p.length - 1] += 1; return p.join("."); }
// A version in one of these states has shipped (or is on its way out the
// door): Apple refuses a new build whose version is not higher than it.
// The TestFlight group made for a new app, and the team roles Apple lets
// test internally.
const TESTERS_GROUP = "Team";
const TESTER_ROLES = new Set(["ACCOUNT_HOLDER", "ADMIN", "APP_MANAGER", "DEVELOPER", "MARKETING"]);
const SHIPPED = new Set([
  "READY_FOR_SALE", "READY_FOR_DISTRIBUTION", "ACCEPTED", "PENDING_DEVELOPER_RELEASE", "PENDING_APPLE_RELEASE",
  "PROCESSING_FOR_APP_STORE", "PROCESSING_FOR_DISTRIBUTION", "PREORDER_READY_FOR_SALE", "REPLACED_WITH_NEW_VERSION",
  "REMOVED_FROM_SALE", "DEVELOPER_REMOVED_FROM_SALE",
]);

// The App ID capabilities for every entitlement the build will sign the app
// with (setup.mjs writes the same file): the kit's, the app's own, a
// committed project's own.
function neededCapabilities() {
  try {
    const committed = "ios/App/App/App.entitlements";
    const own = existsSync(committed) ? plistObject(readFileSync(committed, "utf-8")) : {};
    return capabilitiesFor(mergeEntitlements(own, iosEntitlements(readNativeSettings(process.cwd()), [])));
  } catch (err) {
    if (err instanceof NativeSettingsError) stop("native-settings-invalid", { detail: err.message });
    throw err;
  }
}

async function main() {
  const needed = neededCapabilities();
  if (!env.ASC_KEY_ID || !env.ASC_ISSUER_ID || !env.ASC_KEY_P8) stop("missing-apple-key");
  try { TOKEN = jwt(); } catch (err) { stop("key-malformed", { detail: String((err && err.message) || err) }); }
  if (env.MOBILE_VERSION && !/^\d+(\.\d+){0,2}$/.test(env.MOBILE_VERSION)) stop("bad-version", { version: env.MOBILE_VERSION });

  // 1. The key works, and the App Store record for this bundle id.
  let r = await asc("GET", "/v1/apps?filter[bundleId]=" + encodeURIComponent(BUNDLE_ID) + "&limit=200");
  if (r.status === 401) stop("key-invalid", { detail: r.detail });
  if (r.status !== 200) fail(r, "listing the apps");
  let app = (r.json.data || []).find(function (a) { return a.attributes && a.attributes.bundleId === BUNDLE_ID; }) || null;

  // 2. The key can manage signing (Apple's Admin role — cloud signing needs it).
  r = await asc("GET", "/v1/certificates?limit=1");
  if (r.status === 403) stop("key-not-admin", { detail: r.detail });
  if (r.status !== 200) fail(r, "reading the team's certificates");

  // 3. The bundle id exists on the team, with every capability the app's
  //    entitlements need — the export keeps an entitlement only when the App
  //    ID has its capability, and drops it silently otherwise. Registered
  //    here when missing (the same thing Xcode's automatic signing would do
  //    later).
  r = await asc("GET", "/v1/bundleIds?filter[identifier]=" + encodeURIComponent(BUNDLE_ID) + "&include=bundleIdCapabilities&limit=200");
  if (r.status !== 200) fail(r, "reading the bundle ids");
  let bundle = (r.json.data || []).find(function (b) { return b.attributes && b.attributes.identifier === BUNDLE_ID; }) || null;
  let has = function () { return false; };
  if (bundle) {
    const caps = (r.json.included || []).filter(function (c) { return c.type === "bundleIdCapabilities"; });
    const mine = ((bundle.relationships || {}).bundleIdCapabilities || {}).data || [];
    has = function (type) { return caps.some(function (c) { return c.attributes && c.attributes.capabilityType === type && mine.some(function (m) { return m.id === c.id; }); }); };
  } else {
    r = await asc("POST", "/v1/bundleIds", {
      data: { type: "bundleIds", attributes: { identifier: BUNDLE_ID, name: APP_NAME.replace(/[^A-Za-z0-9 ]+/g, " ").trim() || "App", platform: "IOS" } },
    });
    if (r.status !== 201) fail(r, "registering the bundle id " + BUNDLE_ID);
    bundle = r.json.data;
    emit({ kind: "bundle-id-registered", bundleId: BUNDLE_ID });
  }
  // Some capabilities want a setting named (Sign in with Apple: this app is
  // its own primary App ID — without it Apple answers 409 "Please select at
  // least one configuration"). A 409 is never "already there": Apple answers
  // 201 to a capability it already has.
  for (const capability of needed) {
    if (has(capability.type)) continue;
    const attributes = { capabilityType: capability.type };
    if (capability.settings) attributes.settings = capability.settings;
    r = await asc("POST", "/v1/bundleIdCapabilities", {
      data: { type: "bundleIdCapabilities", attributes: attributes, relationships: { bundleId: { data: { type: "bundleIds", id: bundle.id } } } },
    });
    if (r.status !== 201) fail(r, "enabling " + capability.type + " on " + BUNDLE_ID + " (for " + capability.entitlement + ")");
    emit({ kind: "capability-enabled", capability: capability.type, entitlement: capability.entitlement, bundleId: BUNDLE_ID });
  }

  // 4. The App Store record. Without one nothing can be uploaded — and if
  //    the person already has this app in the store under Base44's id, the
  //    right move is to keep that listing, not to make a second one.
  if (!app) {
    if (BASE44_BUNDLE_ID && BASE44_BUNDLE_ID !== BUNDLE_ID) {
      r = await asc("GET", "/v1/apps?filter[bundleId]=" + encodeURIComponent(BASE44_BUNDLE_ID) + "&limit=200");
      const existing = r.status === 200 ? (r.json.data || []).find(function (a) { return a.attributes && a.attributes.bundleId === BASE44_BUNDLE_ID; }) : null;
      if (existing) {
        stop("existing-base44-listing", { bundleId: BASE44_BUNDLE_ID, ascAppId: existing.id, appName: existing.attributes.name, ourBundleId: BUNDLE_ID });
      }
    }
    stop("no-app-record", { bundleId: BUNDLE_ID });
  }

  // 4b. The App Store's server notifications go to the app's own backend —
  //    set when the record sends them nowhere, or to Base44 (the app's old
  //    home, which no longer hears its purchases). A record that sends them
  //    to a purchases service the owner uses (RevenueCat and the like) is
  //    left alone, and said.
  if (NOTIFICATIONS_URL) {
    const a = app.attributes || {};
    // A URL that stays: set, and not Base44's.
    const kept = function (url) {
      if (!url) return false;
      try { return !/(^|\.)base44\.(com|app)$/.test(new URL(url).hostname); } catch (e) { return false; }
    };
    const set = {};
    if (!kept(a.subscriptionStatusUrl)) { set.subscriptionStatusUrl = NOTIFICATIONS_URL; set.subscriptionStatusUrlVersion = "V2"; }
    if (!kept(a.subscriptionStatusUrlForSandbox)) { set.subscriptionStatusUrlForSandbox = NOTIFICATIONS_URL; set.subscriptionStatusUrlVersionForSandbox = "V2"; }
    if (Object.keys(set).length) {
      r = await asc("PATCH", "/v1/apps/" + app.id, { data: { type: "apps", id: app.id, attributes: set } });
      if (r.status !== 200) fail(r, "pointing the App Store's notifications at the app");
      emit({ kind: "store-notifications-set", url: NOTIFICATIONS_URL, sandbox: Boolean(set.subscriptionStatusUrlForSandbox), production: Boolean(set.subscriptionStatusUrl) });
    }
    const production = set.subscriptionStatusUrl || a.subscriptionStatusUrl;
    if (production !== NOTIFICATIONS_URL) emit({ kind: "store-notifications-elsewhere", url: production });
  }

  // 5. TestFlight for the app's own team. A new app has no tester group,
  //    and without one a build never shows in anyone's TestFlight. When the
  //    app has no internal group, one is made here with every build in it
  //    and the team's own people are put in it — Apple mails each of them
  //    the invitation. A group the owner already has is theirs: nothing is
  //    touched. (Apple makes a second group of the same name when asked
  //    twice, and refuses a tester who is already in — so both are asked
  //    once, here, when there is no group.)
  r = await asc("GET", "/v1/betaGroups?filter[app]=" + app.id + "&filter[isInternalGroup]=true&limit=50");
  if (r.status !== 200) fail(r, "reading the app's TestFlight groups");
  if (!(r.json.data || []).length) {
    r = await asc("POST", "/v1/betaGroups", {
      data: {
        type: "betaGroups",
        attributes: { name: TESTERS_GROUP, isInternalGroup: true, hasAccessToAllBuilds: true },
        relationships: { app: { data: { type: "apps", id: app.id } } },
      },
    });
    if (r.status !== 201) fail(r, "creating the TestFlight group");
    const group = r.json.data;
    r = await asc("GET", "/v1/users?limit=200");
    if (r.status !== 200) fail(r, "reading the team's people");
    let invited = 0;
    for (const user of r.json.data || []) {
      const who = user.attributes || {};
      if (!who.username || !(who.roles || []).some(function (role) { return TESTER_ROLES.has(role); })) continue;
      const t = await asc("POST", "/v1/betaTesters", {
        data: {
          type: "betaTesters",
          attributes: { email: who.username, firstName: who.firstName || "", lastName: who.lastName || "" },
          relationships: { betaGroups: { data: [{ type: "betaGroups", id: group.id }] } },
        },
      });
      if (t.status !== 201) fail(t, "inviting " + who.username + " to TestFlight");
      invited += 1;
    }
    emit({ kind: "testers-invited", group: TESTERS_GROUP, invited: invited });
  }

  // 6. The version and build number this upload must carry. Version: the
  //    highest one App Store Connect has, bumped if that one has shipped
  //    (Apple refuses a build for an approved version). Build number: above
  //    both this repo's run count and whatever was uploaded before (a person
  //    who uploaded builds through Base44 has higher numbers than our runs).
  let version = env.MOBILE_VERSION || null;
  if (!version) {
    r = await asc("GET", "/v1/apps/" + app.id + "/appStoreVersions?filter[platform]=IOS&limit=200");
    if (r.status !== 200) fail(r, "reading the app's versions");
    let top = null;
    for (const v of r.json.data || []) {
      if (!top || compare(v.attributes.versionString, top.attributes.versionString) > 0) top = v;
    }
    if (!top) version = "1.0";
    else {
      const state = top.attributes.appVersionState || top.attributes.appStoreState;
      version = SHIPPED.has(state) ? bump(top.attributes.versionString) : top.attributes.versionString;
    }
  }
  r = await asc("GET", "/v1/builds?filter[app]=" + app.id + "&sort=-uploadedDate&limit=20");
  if (r.status !== 200) fail(r, "reading the app's builds");
  let highest = 0;
  for (const b of r.json.data || []) {
    const n = Number(b.attributes && b.attributes.version);
    if (Number.isFinite(n) && n > highest) highest = n;
  }
  const buildNumber = Math.max(RUN_NUMBER, highest + 1);
  // Apple has no build of this app yet: this upload is the one after which
  // Apple emails the testers their invitation (measured 2026-09-28: the
  // group made here before any build, the mail two minutes after the
  // upload). Every later build just appears in their TestFlight app.
  const firstBuild = (r.json.data || []).length === 0;

  output("bundle_id", BUNDLE_ID);
  output("asc_app_id", app.id);
  output("marketing_version", version);
  output("build_number", String(buildNumber));
  emit({ kind: "preflight", bundleId: BUNDLE_ID, ascAppId: app.id, appName: app.attributes.name, version: version, buildNumber: buildNumber, firstBuild: firstBuild });
}

main().catch(function (err) {
  stop("apple-error", { detail: String((err && err.stack) || err) });
});
