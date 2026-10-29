// Applied to the generated native projects on every setup (they are never
// committed, so every regeneration must re-apply it). Each edit is
// idempotent — done once, recognized after — and loud when Capacitor's
// template no longer has the shape it expects, so nothing ships half-wired.
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { deflateSync } from "node:zlib";

export const SCHEME = "eb44-69fc81cf4f6a0ae5ab617e2b";

function insertBefore(file, marker, anchor, addition) {
  const text = readFileSync(file, "utf-8");
  if (text.includes(marker)) return;
  if (!text.includes(anchor)) throw new Error(file + ": expected to find " + JSON.stringify(anchor));
  writeFileSync(file, text.replace(anchor, addition + anchor));
}
function replaceOnce(file, pattern, replacement) {
  const text = readFileSync(file, "utf-8");
  if (!pattern.test(text)) throw new Error(file + ": expected to find " + pattern);
  writeFileSync(file, text.replace(pattern, replacement));
}
// A block of ours between two marker lines: written before the anchor the
// first time, replaced whole after — so what it holds can change from one
// build to the next.
function writeBlock(file, begin, end, body, anchor) {
  const text = readFileSync(file, "utf-8");
  const block = begin + "\n" + body + end + "\n";
  const at = text.indexOf(begin);
  if (at >= 0) {
    const stop = text.indexOf(end, at);
    if (stop < 0) throw new Error(file + ": expected to find " + JSON.stringify(end));
    writeFileSync(file, text.slice(0, at) + block + text.slice(stop + end.length + 1));
    return;
  }
  if (!text.includes(anchor)) throw new Error(file + ": expected to find " + JSON.stringify(anchor));
  writeFileSync(file, text.replace(anchor, block + anchor));
}
function filesUnder(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const path = dir + "/" + name;
    if (statSync(path).isDirectory()) out.push(...filesUnder(path));
    else out.push(path);
  }
  return out;
}

// ── The app's own native settings: mobile/native.json ───────────────────

// Read and checked once per build, before anything is installed: a file
// that does not parse, or holds a key this kit does not know, stops the build
// with its own words — never a half-applied set of settings, never a typo
// silently ignored.
export class NativeSettingsError extends Error {}
const SETTING_KEYS = ["orientation", "splash", "statusBar", "links", "ios", "android", "capacitor"];
const ORIENTATIONS = ["default", "portrait", "landscape"];
export function readNativeSettings(root) {
  const path = root + "/mobile/native.json";
  if (!existsSync(path)) return {};
  let settings;
  try {
    settings = JSON.parse(readFileSync(path, "utf-8"));
  } catch (err) {
    throw new NativeSettingsError("mobile/native.json is not valid JSON: " + err.message);
  }
  const bad = function (what) { throw new NativeSettingsError("mobile/native.json: " + what); };
  const isObject = function (v) { return v !== null && typeof v === "object" && !Array.isArray(v); };
  if (!isObject(settings)) bad("it must hold one JSON object");
  for (const key of Object.keys(settings)) {
    if (!SETTING_KEYS.includes(key)) bad(JSON.stringify(key) + " is not a setting (the settings are " + SETTING_KEYS.join(", ") + ")");
  }
  if (settings.orientation !== undefined && !ORIENTATIONS.includes(settings.orientation)) bad("orientation must be one of " + ORIENTATIONS.join(", "));
  const splash = settings.splash;
  if (splash !== undefined) {
    if (!isObject(splash)) bad("splash must be an object");
    for (const key of Object.keys(splash)) {
      if (!["backgroundColor", "darkBackgroundColor", "image"].includes(key)) bad("splash." + key + " is not a splash setting (backgroundColor, darkBackgroundColor, image)");
    }
    for (const key of ["backgroundColor", "darkBackgroundColor"]) {
      if (splash[key] !== undefined && !/^#[0-9a-fA-F]{6}$/.test(splash[key])) bad("splash." + key + " must be a colour like #ff8a34");
    }
    // A logo of the app's own, or false: no logo, the colour alone.
    if (splash.image !== undefined && splash.image !== false && (typeof splash.image !== "string" || !/\.png$/i.test(splash.image) || !existsSync(root + "/" + splash.image))) {
      bad("splash.image must be a .png file in the repo, or false for none (" + JSON.stringify(splash.image) + " is not)");
    }
  }
  const bar = settings.statusBar;
  if (bar !== undefined) {
    if (!isObject(bar)) bad("statusBar must be an object");
    for (const key of Object.keys(bar)) if (!["style", "hidden"].includes(key)) bad("statusBar." + key + " is not a status bar setting (style, hidden)");
    if (bar.style !== undefined && !["auto", "light", "dark"].includes(bar.style)) bad("statusBar.style must be auto, light or dark");
    if (bar.hidden !== undefined && typeof bar.hidden !== "boolean") bad("statusBar.hidden must be true or false");
  }
  if (settings.links !== undefined && typeof settings.links !== "boolean") bad("links must be true or false");
  if (settings.capacitor !== undefined && !isObject(settings.capacitor)) bad("capacitor must be an object of Capacitor config keys");
  const ios = settings.ios;
  if (ios !== undefined) {
    if (!isObject(ios)) bad("ios must be an object");
    for (const key of Object.keys(ios)) if (!["infoPlist", "entitlements"].includes(key)) bad("ios." + key + " is not an iOS setting (infoPlist, entitlements)");
    // A property list holds strings, numbers, true/false, lists and objects.
    const plistable = function (v) {
      if (Array.isArray(v)) return v.every(plistable);
      if (isObject(v)) return Object.keys(v).every(function (k) { return plistable(v[k]); });
      return typeof v === "string" || typeof v === "boolean" || (typeof v === "number" && Number.isFinite(v));
    };
    for (const key of ["infoPlist", "entitlements"]) {
      if (ios[key] === undefined) continue;
      if (!isObject(ios[key])) bad("ios." + key + " must be an object of " + (key === "infoPlist" ? "Info.plist" : "entitlement") + " keys");
      for (const name of Object.keys(ios[key])) {
        if (!plistable(ios[key][name])) bad("ios." + key + "." + name + " must be text, a number, true/false, a list or an object (not null)");
      }
    }
    const protection = (ios.entitlements || {})["com.apple.developer.default-data-protection"];
    if (protection !== undefined && !DATA_PROTECTION_LEVEL[protection]) {
      bad("ios.entitlements.com.apple.developer.default-data-protection must be one of " + Object.keys(DATA_PROTECTION_LEVEL).join(", "));
    }
  }
  const android = settings.android;
  if (android !== undefined) {
    if (!isObject(android)) bad("android must be an object");
    for (const key of Object.keys(android)) if (!["permissions", "blockedPermissions", "manifest"].includes(key)) bad("android." + key + " is not an Android setting (permissions, blockedPermissions, manifest)");
    const perms = android.permissions;
    if (perms !== undefined && (!Array.isArray(perms) || perms.some(function (p) { return typeof p !== "string" || !/^[A-Za-z0-9_.]+$/.test(p); }))) {
      bad("android.permissions must be a list of permission names, like \"ACCESS_BACKGROUND_LOCATION\"");
    }
    // A name, or a family: "android.permission.health.*".
    const blocked = android.blockedPermissions;
    if (blocked !== undefined && (!Array.isArray(blocked) || blocked.some(function (p) { return typeof p !== "string" || !/^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*(\.\*)?$/.test(p); }))) {
      bad("android.blockedPermissions must be a list of permission names, like \"ACCESS_BACKGROUND_LOCATION\", or families, like \"android.permission.health.*\"");
    }
    const both = (android.permissions || []).map(permissionName).filter(function (p) { return (android.blockedPermissions || []).map(permissionName).includes(p); });
    if (both.length) bad(both[0] + " is in both android.permissions and android.blockedPermissions");
    const manifest = android.manifest;
    if (manifest !== undefined) {
      if (!isObject(manifest)) bad("android.manifest must be an object");
      for (const key of Object.keys(manifest)) {
        if (!["root", "application", "activity"].includes(key)) bad("android.manifest." + key + " is not a place in the manifest (root, application, activity)");
        const xml = [].concat(manifest[key]);
        if (xml.some(function (x) { return typeof x !== "string" || !/^\s*</.test(x); })) bad("android.manifest." + key + " must be XML elements, as text");
      }
    }
  }
  return settings;
}

// ── Property lists (Info.plist, App.entitlements) ────────────────────────

function xmlEscape(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function xmlUnescape(text) {
  return String(text).replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
}

// A JSON value as a property-list value.
export function plistValue(value, indent) {
  const pad = "\t".repeat(indent);
  if (value === true) return "<true/>";
  if (value === false) return "<false/>";
  if (typeof value === "number") return Number.isInteger(value) ? "<integer>" + value + "</integer>" : "<real>" + value + "</real>";
  if (typeof value === "string") return "<string>" + xmlEscape(value) + "</string>";
  if (Array.isArray(value)) {
    if (!value.length) return "<array/>";
    return "<array>\n" + value.map(function (v) { return pad + "\t" + plistValue(v, indent + 1) + "\n"; }).join("") + pad + "</array>";
  }
  if (value !== null && typeof value === "object") {
    const keys = Object.keys(value);
    if (!keys.length) return "<dict/>";
    return "<dict>\n" + keys.map(function (k) { return pad + "\t<key>" + xmlEscape(k) + "</key>\n" + pad + "\t" + plistValue(value[k], indent + 1) + "\n"; }).join("") + pad + "</dict>";
  }
  throw new NativeSettingsError("a property list holds strings, numbers, true/false, lists and objects — not " + JSON.stringify(value));
}

// Where the element that starts at 'at' ends (balanced; self-closing tags).
function elementEnd(text, at) {
  const open = text.slice(at).match(/^<([A-Za-z]+)(\/?)>/);
  if (!open) throw new Error("expected a property-list element at " + at);
  if (open[2] === "/") return at + open[0].length;
  const tags = new RegExp("<(/?)" + open[1] + "(/?)>", "g");
  tags.lastIndex = at;
  let depth = 0, m;
  while ((m = tags.exec(text))) {
    if (m[2] === "/") continue;
    depth += m[1] === "/" ? -1 : 1;
    if (depth === 0) return m.index + m[0].length;
  }
  throw new Error("unbalanced <" + open[1] + "> at " + at);
}

// The entries of the dict whose "<dict>" starts at 'at': [key, start of the
// key element, start of its value, end of its value]; and where it closes.
function dictEntries(text, at) {
  const end = elementEnd(text, at);
  const close = end - "</dict>".length;
  const entries = [];
  let cursor = at + "<dict>".length;
  while (true) {
    const next = text.indexOf("<", cursor);
    if (next < 0 || next >= close) break;
    if (!text.startsWith("<key>", next)) throw new Error("unexpected element in a dict at " + next);
    const keyEnd = text.indexOf("</key>", next);
    const valueAt = text.indexOf("<", keyEnd + "</key>".length);
    const valueEnd = elementEnd(text, valueAt);
    entries.push([xmlUnescape(text.slice(next + "<key>".length, keyEnd)), next, valueAt, valueEnd]);
    cursor = valueEnd;
  }
  return { entries: entries, close: close };
}
function rootDict(text) {
  const at = text.indexOf("<dict>");
  if (at < 0) throw new Error("not a property list with a dict");
  return dictEntries(text, at);
}

function parsePlistValue(xml) {
  xml = xml.trim();
  if (xml === "<true/>") return true;
  if (xml === "<false/>") return false;
  if (xml === "<array/>") return [];
  if (xml === "<dict/>") return {};
  let m;
  if ((m = xml.match(/^<string>([\s\S]*)<\/string>$/))) return xmlUnescape(m[1]);
  if ((m = xml.match(/^<integer>(-?\d+)<\/integer>$/))) return Number(m[1]);
  if ((m = xml.match(/^<real>([^<]+)<\/real>$/))) return Number(m[1]);
  if (xml.startsWith("<array>")) {
    const out = [];
    let cursor = "<array>".length;
    while (true) {
      const next = xml.indexOf("<", cursor);
      if (next < 0 || xml.startsWith("</array>", next)) break;
      const end = elementEnd(xml, next);
      out.push(parsePlistValue(xml.slice(next, end)));
      cursor = end;
    }
    return out;
  }
  if (xml.startsWith("<dict>")) {
    const out = {};
    for (const e of dictEntries(xml, 0).entries) out[e[0]] = parsePlistValue(xml.slice(e[2], e[3]));
    return out;
  }
  throw new Error("unreadable property-list value " + xml.slice(0, 40));
}

// The root dict of a property list, as JSON values.
export function plistObject(text) {
  const out = {};
  for (const e of rootDict(text).entries) out[e[0]] = parsePlistValue(text.slice(e[2], e[3]));
  return out;
}

// Sets one root-level key of a property list: its value replaced, or the key
// added at the end of the root dict.
export function plistSet(text, key, value) {
  const { entries, close } = rootDict(text);
  const hit = entries.find(function (e) { return e[0] === key; });
  const valueXml = plistValue(value, 1);
  if (hit) return text.slice(0, hit[2]) + valueXml + text.slice(hit[3]);
  return text.slice(0, close).replace(/\s*$/, "\n") + "\t<key>" + xmlEscape(key) + "</key>\n\t" + valueXml + "\n" + text.slice(close);
}

export function plistDocument(dict) {
  let doc = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0">\n<dict>\n</dict>\n</plist>\n';
  for (const key of Object.keys(dict)) doc = plistSet(doc, key, dict[key]);
  return doc;
}

// ── iOS ──────────────────────────────────────────────────────────────────

// Two entitlement sets made one: a list value is the two lists joined, any
// other value is the second set's.
export function mergeEntitlements(base, more) {
  const out = Object.assign({}, base);
  for (const key of Object.keys(more)) {
    if (Array.isArray(more[key]) && Array.isArray(out[key])) {
      out[key] = out[key].concat(more[key].filter(function (v) { return !out[key].includes(v); }));
    } else {
      out[key] = more[key];
    }
  }
  return out;
}

// Every entitlement the iPhone app is signed with: the kit's own (push — the
// release build swaps in production at signing time — and Sign in with
// Apple), the links (associated domains for every address the app answers
// on) and the app's own. The preflight enables on the App ID the capability
// each one needs; the build checks every one is still in the signed app.
export function iosEntitlements(settings, hosts) {
  const kit = {
    "aps-environment": "development",
    "com.apple.developer.applesignin": ["Default"],
  };
  if (settings.links) {
    kit["com.apple.developer.associated-domains"] = [].concat(
      hosts.map(function (h) { return "applinks:" + h; }),
      hosts.map(function (h) { return "webcredentials:" + h; }),
    );
  }
  return mergeEntitlements(kit, (settings.ios || {}).entitlements || {});
}

// The App ID capability each entitlement needs, in the names App Store
// Connect's API takes (its CapabilityType). An entitlement not named here
// needs no capability, or one that also needs identifiers made by hand
// (iCloud containers, app groups, merchant ids) — the build's check names it
// when the signed app comes out without it.
export const CAPABILITY_OF_ENTITLEMENT = {
  "aps-environment": "PUSH_NOTIFICATIONS",
  "com.apple.developer.applesignin": "APPLE_ID_AUTH",
  "com.apple.developer.associated-domains": "ASSOCIATED_DOMAINS",
  "com.apple.developer.healthkit": "HEALTHKIT",
  "com.apple.developer.healthkit.access": "HEALTHKIT",
  "com.apple.developer.healthkit.background-delivery": "HEALTHKIT",
  "com.apple.developer.nfc.readersession.formats": "NFC_TAG_READING",
  "com.apple.developer.homekit": "HOMEKIT",
  "com.apple.developer.siri": "SIRIKIT",
  "com.apple.developer.networking.wifi-info": "ACCESS_WIFI_INFORMATION",
  "com.apple.developer.networking.multipath": "MULTIPATH",
  "com.apple.developer.networking.HotspotConfiguration": "HOT_SPOT",
  "com.apple.developer.networking.vpn.api": "PERSONAL_VPN",
  "com.apple.developer.networking.networkextension": "NETWORK_EXTENSIONS",
  "com.apple.developer.networking.custom-protocol": "NETWORK_CUSTOM_PROTOCOL",
  "com.apple.developer.coremedia.hls.low-latency": "COREMEDIA_HLS_LOW_LATENCY",
  "com.apple.developer.authentication-services.autofill-credential-provider": "AUTOFILL_CREDENTIAL_PROVIDER",
  "com.apple.developer.ClassKit-environment": "CLASSKIT",
  "com.apple.developer.game-center": "GAME_CENTER",
  "com.apple.developer.user-management": "USER_MANAGEMENT",
  "com.apple.developer.default-data-protection": "DATA_PROTECTION",
  "com.apple.external-accessory.wireless-configuration": "WIRELESS_ACCESSORY_CONFIGURATION",
  "inter-app-audio": "INTER_APP_AUDIO",
};
const DATA_PROTECTION_LEVEL = {
  NSFileProtectionComplete: "COMPLETE_PROTECTION",
  NSFileProtectionCompleteUnlessOpen: "PROTECTED_UNLESS_OPEN",
  NSFileProtectionCompleteUntilFirstUserAuthentication: "PROTECTED_UNTIL_FIRST_USER_AUTH",
};

// What the App ID must have for these entitlements: one entry per capability,
// with the settings Apple refuses the capability without.
export function capabilitiesFor(entitlements) {
  const out = [];
  for (const key of Object.keys(entitlements)) {
    const type = CAPABILITY_OF_ENTITLEMENT[key];
    if (!type || out.some(function (c) { return c.type === type; })) continue;
    const capability = { type: type, entitlement: key };
    if (type === "APPLE_ID_AUTH") capability.settings = [{ key: "APPLE_ID_AUTH_APP_CONSENT", options: [{ key: "PRIMARY_APP_CONSENT" }] }];
    if (type === "DATA_PROTECTION") {
      const level = DATA_PROTECTION_LEVEL[entitlements[key]];
      if (!level) throw new NativeSettingsError("ios.entitlements: " + key + " must be one of " + Object.keys(DATA_PROTECTION_LEVEL).join(", "));
      capability.settings = [{ key: "DATA_PROTECTION_PERMISSION_LEVEL", options: [{ key: level }] }];
    }
    out.push(capability);
  }
  return out;
}

// The screen orientations each setting allows, iPhone and iPad ("default" is
// Capacitor's template: every way but upside down on an iPhone, every way on
// an iPad).
const IOS_ORIENTATIONS = {
  default: [
    ["UIInterfaceOrientationPortrait", "UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight"],
    ["UIInterfaceOrientationPortrait", "UIInterfaceOrientationPortraitUpsideDown", "UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight"],
  ],
  portrait: [
    ["UIInterfaceOrientationPortrait"],
    ["UIInterfaceOrientationPortrait", "UIInterfaceOrientationPortraitUpsideDown"],
  ],
  landscape: [
    ["UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight"],
    ["UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight"],
  ],
};

// The Info.plist keys the settings call for, beside the kit's own; the app's
// own ios.infoPlist goes last, so its words replace the kit's. A setting the
// file does not name writes nothing (a project committed in the repo keeps
// what its owner set there).
export function iosInfoPlist(settings, ads) {
  const out = {};
  if (settings.orientation !== undefined) {
    out.UISupportedInterfaceOrientations = IOS_ORIENTATIONS[settings.orientation][0];
    out["UISupportedInterfaceOrientations~ipad"] = IOS_ORIENTATIONS[settings.orientation][1];
  }
  const bar = settings.statusBar || {};
  // While the launch screen shows (the running app's bars are the shell's and
  // SystemBars' to set).
  if (bar.hidden !== undefined) out.UIStatusBarHidden = bar.hidden;
  if (bar.style !== undefined) out.UIStatusBarStyle = { auto: "UIStatusBarStyleDefault", light: "UIStatusBarStyleLightContent", dark: "UIStatusBarStyleDarkContent" }[bar.style];
  // Google's ads SDK rides the build when either platform shows ads (it is
  // one package for both): a platform with an AdMob app runs it under that
  // id; one without runs it only for the ads inside the app's own pages
  // (Google's WebView API for Ads). With neither key the SDK stops the app at
  // launch.
  if (ads.installed && !ads.iosAppId) out.GADIntegrationManager = "webview";
  if (ads.installed && ads.iosAppId) {
    out.GADApplicationIdentifier = ads.iosAppId;
    // Google's own ad network, for Apple's ad attribution (the app adds other
    // networks' ids in ios.infoPlist.SKAdNetworkItems), and the words of the
    // tracking question window.eb44.ads.tracking() asks.
    out.SKAdNetworkItems = [{ SKAdNetworkIdentifier: "cstr6suwn9.skadnetwork" }];
    out.NSUserTrackingUsageDescription = "Your data will be used to show you ads that are more relevant to you.";
  }
  return Object.assign(out, (settings.ios || {}).infoPlist || {});
}

export function applyIosSettings(root, settings, ctx) {
  const plistPath = root + "/ios/App/App/Info.plist";
  let plist = readFileSync(plistPath, "utf-8");
  const keys = iosInfoPlist(settings, ctx.ads);
  for (const key of Object.keys(keys)) plist = plistSet(plist, key, keys[key]);
  writeFileSync(plistPath, plist);
  // The entitlements file: the kit's and the app's, on top of what a project
  // the owner committed already holds (ios/ in the repo is theirs).
  const path = root + "/ios/App/App/App.entitlements";
  const existing = existsSync(path) ? plistObject(readFileSync(path, "utf-8")) : {};
  writeFileSync(path, plistDocument(mergeEntitlements(existing, iosEntitlements(settings, ctx.hosts))));
}

// ── Android ──────────────────────────────────────────────────────────────

function permissionName(name) {
  return name.includes(".") ? name : "android.permission." + name;
}
// The permissions the app removes from the final manifest, whoever declares
// them (a plugin's own manifest declares what it might need: the health one
// declares reading and writing every kind of health data, and Google Play
// refuses health permissions an app does not use). A family —
// "android.permission.health.*" — is every permission of it that a plugin's
// manifest declares; one the app declares itself stays (applyAndroidSettings
// writes the app's own first): the app lists what it uses and blocks the rest.
export function blockedPermissions(settings, root) {
  const own = settings.android || {};
  const out = [];
  const add = function (name) { if (!out.includes(name)) out.push(name); };
  for (const entry of own.blockedPermissions || []) {
    if (!entry.endsWith(".*")) { add(permissionName(entry)); continue; }
    const family = entry.slice(0, -1);
    for (const name of pluginPermissions(root)) if (name.startsWith(family)) add(name);
  }
  return out;
}
// Every permission the plugins' own manifests declare.
function pluginPermissions(root) {
  const names = [];
  for (const plugin of capacitorPlugins(root)) {
    if (!plugin.capacitor.android) continue;
    const file = plugin.dir + "/" + (plugin.capacitor.android.src || "android") + "/src/main/AndroidManifest.xml";
    if (!existsSync(file)) continue;
    for (const name of declared([readFileSync(file, "utf-8")])) if (!names.includes(name)) names.push(name);
  }
  return names;
}
function declared(lines) {
  const names = [];
  for (const line of lines) {
    const re = /<uses-permission[^>]*android:name="([^"]+)"/g;
    let m;
    while ((m = re.exec(line))) names.push(m[1]);
  }
  return names;
}

// The app's own manifest entries: its permissions and raw XML at the root
// (a permission the kit's own block already declares is left out — one
// manifest declaring a permission twice fails the build), in <application>
// (and the ads SDK's id), in the main <activity> (links that open the app).
// kitLines: the lines of the kit's own block (patchAndroid).
export function applyAndroidSettings(root, settings, ctx, kitLines) {
  const manifest = root + "/android/app/src/main/AndroidManifest.xml";
  const own = settings.android || {};
  const raw = own.manifest || {};
  const taken = declared(kitLines);
  const rootLines = [];
  for (const name of own.permissions || []) {
    const full = permissionName(name);
    if (taken.includes(full)) continue;
    taken.push(full);
    rootLines.push('    <uses-permission android:name="' + full + '" />');
  }
  for (const xml of [].concat(raw.root || [])) {
    const names = declared([xml]);
    if (names.length && names.every(function (n) { return taken.includes(n); })) continue;
    taken.push.apply(taken, names);
    rootLines.push("    " + xml.trim());
  }
  // Removed at the manifest merge, from every library's manifest: the
  // merger's own marker (the kit's own block leaves these out, patchAndroid).
  for (const full of blockedPermissions(settings, root)) {
    if (taken.includes(full)) continue;
    taken.push(full);
    rootLines.push('    <uses-permission android:name="' + full + '" tools:node="remove" />');
  }
  writeBlock(manifest, "    <!-- EscapeBase44 mobile kit: the app's own (mobile/native.json) -->", "    <!-- /the app's own -->",
    rootLines.map(function (l) { return l + "\n"; }).join(""), "</manifest>");

  const appLines = [];
  if (ctx.ads.installed) {
    appLines.push(ctx.ads.androidAppId
      ? '        <meta-data android:name="com.google.android.gms.ads.APPLICATION_ID" android:value="' + ctx.ads.androidAppId + '" />'
      : '        <meta-data android:name="com.google.android.gms.ads.INTEGRATION_MANAGER" android:value="webview" />');
  }
  for (const xml of [].concat(raw.application || [])) appLines.push("        " + xml.trim());
  writeBlock(manifest, "        <!-- EscapeBase44 mobile kit: the app's own, in the application -->", "        <!-- /the app's own, in the application -->",
    appLines.map(function (l) { return l + "\n"; }).join(""), "</application>");

  const activityLines = [];
  if (settings.links && ctx.hosts.length) {
    activityLines.push('            <intent-filter android:autoVerify="true">',
      '                <action android:name="android.intent.action.VIEW" />',
      '                <category android:name="android.intent.category.DEFAULT" />',
      '                <category android:name="android.intent.category.BROWSABLE" />',
      '                <data android:scheme="https" />');
    for (const host of ctx.hosts) activityLines.push('                <data android:host="' + host + '" />');
    activityLines.push("            </intent-filter>");
  }
  for (const xml of [].concat(raw.activity || [])) activityLines.push("            " + xml.trim());
  writeBlock(manifest, "            <!-- EscapeBase44 mobile kit: the app's own, in the activity -->", "            <!-- /the app's own, in the activity -->",
    activityLines.map(function (l) { return l + "\n"; }).join(""), "</activity>");

  // The merger's markers (tools:node, tools:replace …) need their namespace
  // on the manifest; the generated one declares only Android's.
  const merged = readFileSync(manifest, "utf-8");
  if (/\btools:[A-Za-z]+=/.test(merged) && !/xmlns:tools=/.test(merged)) {
    writeFileSync(manifest, merged.replace(/<manifest\b/, '<manifest xmlns:tools="http://schemas.android.com/tools"'));
  }

  // Orientation is an attribute of the main activity ("default" = none: the
  // phone's own rotation). Not named in the file: left as the project has it.
  if (settings.orientation !== undefined) {
    const text = readFileSync(manifest, "utf-8");
    const activity = /<activity\b[^>]*android:name="\.MainActivity"[^>]*>/.exec(text);
    if (!activity) throw new Error(manifest + ": expected the main activity");
    let tag = activity[0].replace(/\s+android:screenOrientation="[^"]*"/, "");
    const orientation = { portrait: "portrait", landscape: "sensorLandscape" }[settings.orientation];
    if (orientation) tag = tag.replace(/>$/, ' android:screenOrientation="' + orientation + '">');
    writeFileSync(manifest, text.replace(activity[0], tag));
  }

  // The splash on Android 12 and later — the system's own: a logo on a
  // colour, both read off the launch theme. Older Androids show the image
  // the assets tool made. Ours are marked items pointing at resources of the
  // kit's own (the colour, light and dark; the logo, inset so all of it shows
  // inside the circle Android draws it in), so what the file drops goes, and
  // a committed project's own items stay when the file names none.
  const splash = settings.splash || {};
  const res = root + "/android/app/src/main/res";
  const styles = res + "/values/styles.xml";
  const MARK = "<!-- EscapeBase44 mobile kit: the splash (mobile/native.json) -->";
  let xml = readFileSync(styles, "utf-8").replace(/\n[ \t]*<!-- EscapeBase44 mobile kit: the splash(?: colour)? \(mobile\/native\.json\) -->\n[ \t]*<item name="windowSplash[A-Za-z]+">[^<]*<\/item>/g, "");
  const items = [];
  const write = function (path, text) { mkdirSync(path.slice(0, path.lastIndexOf("/")), { recursive: true }); writeFileSync(path, text); };
  const gone = function (path) { if (existsSync(path)) rmSync(path); };
  if (splash.backgroundColor) {
    const colour = function (c) { return '<?xml version="1.0" encoding="utf-8"?>\n<!-- EscapeBase44 mobile kit: the splash colour (mobile/native.json) -->\n<resources>\n    <color name="eb44_splash_background">' + c + "</color>\n</resources>\n"; };
    write(res + "/values/eb44_splash.xml", colour(splash.backgroundColor));
    write(res + "/values-night/eb44_splash.xml", colour(splash.darkBackgroundColor || splash.backgroundColor));
    items.push(["windowSplashScreenBackground", "@color/eb44_splash_background"]);
  } else {
    gone(res + "/values/eb44_splash.xml");
    gone(res + "/values-night/eb44_splash.xml");
  }
  if (splash.image !== undefined) {
    write(res + "/drawable-nodpi/eb44_splash_logo.png", splash.image === false ? transparentPng(432) : readFileSync(root + "/" + splash.image));
    // Android draws the icon in a 288dp frame and shows only its middle
    // 192dp circle (measured on Android 15: a white square drawn straight
    // showed as a 192dp disc); inset 27% of the frame, a square logo shows
    // whole (132dp). A fraction: an inset in dp collapsed the logo to a dot.
    write(res + "/drawable/eb44_splash_icon.xml", '<?xml version="1.0" encoding="utf-8"?>\n<!-- EscapeBase44 mobile kit: the splash logo (mobile/native.json) -->\n' +
      '<inset xmlns:android="http://schemas.android.com/apk/res/android" android:drawable="@drawable/eb44_splash_logo" android:inset="27%" />\n');
    items.push(["windowSplashScreenAnimatedIcon", "@drawable/eb44_splash_icon"]);
  } else {
    gone(res + "/drawable-nodpi/eb44_splash_logo.png");
    gone(res + "/drawable/eb44_splash_icon.xml");
  }
  if (items.length) {
    const launch = /<style name="AppTheme\.NoActionBarLaunch"[^>]*>[\s\S]*?<\/style>/.exec(xml);
    if (!launch) throw new Error(styles + ": expected the launch theme");
    let theme = launch[0];
    for (const item of items) theme = theme.replace(new RegExp("\\n[ \\t]*<item name=\"" + item[0] + "\">[^<]*<\\/item>", "g"), "");
    const open = /^<style[^>]*>/.exec(theme)[0];
    xml = xml.replace(launch[0], open + items.map(function (item) {
      return "\n        " + MARK + '\n        <item name="' + item[0] + '">' + item[1] + "</item>";
    }).join("") + theme.slice(open.length));
  }
  writeFileSync(styles, xml);
}

// Only the images an asset catalog's image set names in its Contents.json.
export function pruneImageSet(dir) {
  if (!existsSync(dir + "/Contents.json")) return;
  const named = JSON.parse(readFileSync(dir + "/Contents.json", "utf-8")).images.map(function (i) { return i.filename; });
  for (const name of readdirSync(dir)) if (/\.png$/i.test(name) && !named.includes(name)) rmSync(dir + "/" + name);
}

// A transparent square PNG: the splash's "no logo" (splash.image false).
export function transparentPng(size) {
  const table = [];
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table.push(c >>> 0);
  }
  const crc = function (bytes) {
    let c = 0xffffffff;
    for (const b of bytes) c = table[(c ^ b) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
  const chunk = function (type, data) {
    const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
    const length = Buffer.alloc(4); length.writeUInt32BE(data.length);
    const sum = Buffer.alloc(4); sum.writeUInt32BE(crc(body));
    return Buffer.concat([length, body, sum]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0); header.writeUInt32BE(size, 4);
  header[8] = 8; header[9] = 6; // 8 bits a channel, RGBA
  // Every row: filter 0, then fully transparent pixels.
  const pixels = Buffer.alloc(size * (size * 4 + 1));
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", header), chunk("IDAT", deflateSync(pixels)), chunk("IEND", Buffer.alloc(0))]);
}

// ── What both platforms read at launch: the bundled Capacitor config ─────

function isPlain(v) { return v !== null && typeof v === "object" && !Array.isArray(v); }
// Objects merged key by key; anything else replaced.
export function deepMerge(target, source) {
  const out = Object.assign({}, target);
  for (const key of Object.keys(source)) {
    out[key] = isPlain(out[key]) && isPlain(source[key]) ? deepMerge(out[key], source[key]) : source[key];
  }
  return out;
}

// Capacitor copies capacitor.config.json into each native project on every
// sync; these are written into those copies — by setup after its sync, and
// by the capacitor:copy:after hook after anyone else's (mobile/after-copy.mjs),
// so a sync by hand keeps them.
export function bundledConfig(settings, ads, platform) {
  // The kit's default: the splash stays up until the page has painted (the
  // shell hides it; ten seconds at most), where the remote page's first load
  // used to show a white screen.
  let out = { plugins: { SplashScreen: { launchAutoHide: true, launchShowDuration: 10000, launchFadeOutDuration: 200 } } };
  // The splash's own colour. Not the web view's: on iPhone the page sits
  // below the status bar (contentInset), and the strip above it shows the
  // web view's colour on every page — a splash orange there, measured
  // 2026-10-21 on the Simulator.
  const color = (settings.splash || {}).backgroundColor;
  if (color) out = deepMerge(out, { plugins: { SplashScreen: { backgroundColor: color } } });
  // Capacitor's own system bars name a style by the background it suits
  // ("DARK" = light text); Expo's, which native.json takes, by the text.
  const style = { light: "DARK", dark: "LIGHT", auto: "DEFAULT" }[(settings.statusBar || {}).style];
  if (style) out = deepMerge(out, { plugins: { SystemBars: { style: style } } });
  // The app's own Capacitor settings (a plugin's config, android.useLegacyBridge …).
  out = deepMerge(out, settings.capacitor || {});
  // And what the kit needs whatever the app says: a purchase is finished
  // (iOS) or consumed (Android) only once the app's backend has it — a credit
  // pack must not vanish before it is delivered (the plugin reads this at
  // launch, before any page script runs); our shell's own settings — the
  // status bar alone hidden (Capacitor's "hidden" hides the navigation bar and
  // the home indicator too) and the ads mode the build carries here.
  return deepMerge(out, {
    plugins: {
      NativePurchases: { autoFinishTransactions: false },
      EB44Shell: {
        statusBarHidden: Boolean((settings.statusBar || {}).hidden),
        ads: !ads.installed ? "none" : (platform === "ios" ? ads.iosAppId : ads.androidAppId) ? "admob" : "webview",
      },
    },
  });
}

export function applyBundledConfig(root, settings, ads, platforms) {
  const paths = { ios: "/ios/App/App/capacitor.config.json", android: "/android/app/src/main/assets/capacitor.config.json" };
  for (const platform of platforms) {
    const path = root + paths[platform];
    if (!existsSync(path)) continue;
    const config = deepMerge(JSON.parse(readFileSync(path, "utf-8")), bundledConfig(settings, ads, platform));
    writeFileSync(path, JSON.stringify(config, null, 2) + "\n");
  }
}

// The Capacitor plugins the app depends on that an iPhone build cannot use.
// The iPhone project is a Swift package graph (Capacitor 8's template): a
// plugin with no Package.swift is left out of the app (Capacitor's own CLI
// warns and moves on — its calls then fail on iPhone), and one whose
// Package.swift asks for an older Capacitor stops the build at package
// resolution, deep inside Xcode. Both are named here first.
// The Capacitor plugins the app depends on, as Capacitor's own CLI finds
// them: a dependency whose package.json carries a "capacitor" key.
function capacitorPlugins(root) {
  const pkg = JSON.parse(readFileSync(root + "/package.json", "utf-8"));
  const out = [];
  for (const name of Object.keys(Object.assign({}, pkg.dependencies, pkg.devDependencies))) {
    const dir = root + "/node_modules/" + name;
    if (!existsSync(dir + "/package.json")) continue;
    const info = JSON.parse(readFileSync(dir + "/package.json", "utf-8"));
    if (info.capacitor) out.push({ name: name, dir: dir, capacitor: info.capacitor });
  }
  return out;
}

export function iosPluginProblems(root) {
  const leftOut = [], tooOld = [];
  for (const plugin of capacitorPlugins(root)) {
    if (!plugin.capacitor.ios) continue;
    if (!existsSync(plugin.dir + "/Package.swift")) { leftOut.push(plugin.name); continue; }
    const m = /capacitor-swift-pm[^)]*?from:\s*"(\d+)/.exec(readFileSync(plugin.dir + "/Package.swift", "utf-8"));
    if (m && Number(m[1]) < 8) tooOld.push(plugin.name + " (made for Capacitor " + m[1] + ")");
  }
  return { leftOut: leftOut, tooOld: tooOld };
}

// The oldest iOS and Android each plugin runs on, read off its own build
// files: Package.swift's platforms; build.gradle's minSdk when it is a number
// of its own (the usual form takes the app's value — no constraint). The
// health plugin needs Android 8 (API 26) where Capacitor's template says 24,
// and Android refuses to merge an app below a library's minimum.
export function pluginMinimums(root) {
  const out = { ios: null, android: null, iosBy: [], androidBy: [] };
  for (const plugin of capacitorPlugins(root)) {
    if (plugin.capacitor.ios && existsSync(plugin.dir + "/Package.swift")) {
      const m = /\.iOS\(\s*(?:\.v(\d+)(?:_(\d+))?|"(\d+)(?:\.(\d+))?[^"]*")\s*\)/.exec(readFileSync(plugin.dir + "/Package.swift", "utf-8"));
      if (m) {
        const v = Number(m[1] || m[3]) + Number(m[2] || m[4] || 0) / 10;
        if (out.ios === null || v > out.ios) { out.ios = v; out.iosBy = [plugin.name]; } else if (v === out.ios) out.iosBy.push(plugin.name);
      }
    }
    if (plugin.capacitor.android) {
      const dir = plugin.dir + "/" + (plugin.capacitor.android.src || "android");
      const file = [dir + "/build.gradle", dir + "/build.gradle.kts"].find(function (f) { return existsSync(f); });
      if (!file) continue;
      // A line that is the number alone ("minSdk 26", "minSdk = 26"); the
      // usual "… hasProperty('minSdkVersion') ? rootProject.ext… : 24" is not.
      for (const line of readFileSync(file, "utf-8").split("\n")) {
        const m = /^\s*minSdk(?:Version)?\s*(?:=\s*)?\(?\s*(\d+)\s*\)?\s*$/.exec(line);
        if (!m) continue;
        const v = Number(m[1]);
        if (out.android === null || v > out.android) { out.android = v; out.androidBy = [plugin.name]; } else if (v === out.android) out.androidBy.push(plugin.name);
      }
    }
  }
  return out;
}

// The app's own minimums raised to what its plugins need — never lowered.
// Before the sync: Capacitor's CLI writes the iPhone app's Swift package
// (CapApp-SPM) with the project's deployment target, so it follows.
export function raiseMinimums(root, platforms) {
  const need = pluginMinimums(root);
  const raised = {};
  const pbx = root + "/ios/App/App.xcodeproj/project.pbxproj";
  if (platforms.includes("ios") && need.ios !== null && existsSync(pbx)) {
    const text = readFileSync(pbx, "utf-8");
    const next = text.replace(/IPHONEOS_DEPLOYMENT_TARGET = (\d+(?:\.\d+)?);/g, function (all, v) {
      return Number(v) < need.ios ? "IPHONEOS_DEPLOYMENT_TARGET = " + need.ios.toFixed(1) + ";" : all;
    });
    if (next !== text) { writeFileSync(pbx, next); raised.ios = { to: need.ios.toFixed(1), by: need.iosBy }; }
  }
  const vars = root + "/android/variables.gradle";
  if (platforms.includes("android") && need.android !== null && existsSync(vars)) {
    const text = readFileSync(vars, "utf-8");
    const next = text.replace(/(minSdkVersion\s*=\s*)(\d+)/, function (all, head, v) {
      return Number(v) < need.android ? head + need.android : all;
    });
    if (next !== text) { writeFileSync(vars, next); raised.android = { to: need.android, by: need.androidBy }; }
  }
  return raised;
}

// The ads the build carries. Wanted: either platform has an AdMob app (the
// repo's facts ADMOB_APP_ID_IOS / ADMOB_APP_ID_ANDROID) or the app's own pages
// carry Google ad tags (read off the built web app). Installed: Google's SDK
// is in the project (setup installs it when wanted) — what the native keys
// must match, since an SDK in the app with neither key stops it at launch.
export const ADS_PLUGIN = "@capacitor-community/admob";
export function adsContext(root, env, capabilities) {
  const configPath = root + "/.escapebase44/config.json";
  const facts = existsSync(configPath) ? JSON.parse(readFileSync(configPath, "utf-8")).env || {} : {};
  const iosAppId = env.ADMOB_APP_ID_IOS || facts.ADMOB_APP_ID_IOS || "";
  const androidAppId = env.ADMOB_APP_ID_ANDROID || facts.ADMOB_APP_ID_ANDROID || "";
  const pkg = existsSync(root + "/package.json") ? JSON.parse(readFileSync(root + "/package.json", "utf-8")) : {};
  const listed = Boolean((pkg.dependencies || {})[ADS_PLUGIN] || (pkg.devDependencies || {})[ADS_PLUGIN]);
  return {
    wanted: Boolean(iosAppId || androidAppId || capabilities.webAds),
    installed: listed && existsSync(root + "/node_modules/" + ADS_PLUGIN + "/package.json"),
    iosAppId: iosAppId,
    androidAppId: androidAppId,
    web: Boolean(capabilities.webAds),
  };
}

// The flags @capacitor/assets makes the icon and the splash with. The splash
// colour applies to both looks (light and dark) unless a dark one is given.
export function assetsFlags(settings) {
  const splash = settings.splash || {};
  const flags = ["--iconBackgroundColor '#ffffff'", "--iconBackgroundColorDark '#ffffff'"];
  if (splash.backgroundColor) {
    flags.push("--splashBackgroundColor '" + splash.backgroundColor + "'",
      "--splashBackgroundColorDark '" + (splash.darkBackgroundColor || splash.backgroundColor) + "'");
  }
  return flags.join(" ");
}


// What the app's own code asks the phone for, read off the built web app
// (dist/ — every script the phone will load, the libraries included). Android
// grants a page only what the app's manifest declares, and shows what it
// declares on the Play listing — so the manifest gets exactly this, on every
// build, and nothing is stored. A library's unused code path counts (a map
// library that can locate you): one permission too many is never asked for
// at run time; one too few is a dead feature.
//   location   — any mention of the browser's geolocation
//   camera / microphone — each getUserMedia call: what it asks for is read off
//                 its argument when that is written in place ({ video: … });
//                 anywhere it is not, both
//   webAds     — Google's ad tags in the app's own pages (AdSense, Ad Manager):
//                the build then carries Google's ads SDK for the web view
//                (Google's WebView API for Ads), or the ads are not allowed
//                to run inside the app
export function detectCapabilities(distDir) {
  let code = "";
  for (const file of filesUnder(distDir)) {
    if (/\.(m?js|html)$/.test(file)) code += readFileSync(file, "utf-8") + "\n";
  }
  const found = {
    location: /\bgeolocation\b/.test(code),
    camera: false,
    microphone: false,
    webAds: /\badsbygoogle\b|pagead2\.googlesyndication\.com|securepubads\.g\.doubleclick\.net|\bgoogletag\.(?:cmd|defineSlot|pubads)\b/.test(code),
  };
  const asks = (literal, key) =>
    new RegExp("(?:^|[{,])\\s*[\"']?" + key + "[\"']?\\s*(?::\\s*(?!(?:!1|false)\\s*[,}])|[,}])").test(literal);
  for (const call of code.matchAll(/getUserMedia\s*\(\s*/g)) {
    const rest = code.slice(call.index + call[0].length, call.index + call[0].length + 600);
    let literal = null;
    if (rest[0] === "{") {
      let depth = 0;
      for (let i = 0; i < rest.length; i++) {
        if (rest[i] === "{") depth++;
        if (rest[i] === "}" && --depth === 0) { literal = rest.slice(0, i + 1); break; }
      }
    }
    if (literal === null) { found.camera = true; found.microphone = true; continue; }
    if (asks(literal, "video")) found.camera = true;
    if (asks(literal, "audio")) found.microphone = true;
  }
  return found;
}

// iOS: the URL scheme, the export-compliance declaration, the purpose
// strings, the AppDelegate hooks, the kit's own native code (Sign in with
// Apple; the shell that gives a download and window.print() the phone's own
// screens) and, last, the app's own settings (mobile/native.json — Info.plist
// keys, the entitlements file with the kit's push + Sign in with Apple in it).
// The bundle id and the version are written by setIosAppTarget, into the app
// target's own build settings. ctx: { hosts, ads } (setup.mjs).
export function patchIos(root, settings = {}, ctx = { hosts: [], ads: {} }) {
  const plist = root + "/ios/App/App/Info.plist";
  // The app's URL scheme — the OAuth return channel. The login page sends
  // Google sign-in through the system browser and the backend redirects to
  // <scheme>://oauth; this entry routes that URL back into the app.
  insertBefore(plist, SCHEME, "<key>CFBundleVersion</key>",
    "<key>CFBundleURLTypes</key>\n" +
    "\t<array>\n" +
    "\t\t<dict>\n" +
    "\t\t\t<key>CFBundleURLName</key>\n" +
    "\t\t\t<string>oauth-return</string>\n" +
    "\t\t\t<key>CFBundleURLSchemes</key>\n" +
    "\t\t\t<array><string>" + SCHEME + "</string></array>\n" +
    "\t\t</dict>\n" +
    "\t</array>\n" +
    "\t");
  // Export compliance: the app only talks HTTPS, which Apple exempts.
  // Without the declaration every TestFlight build sits on a "Missing
  // Compliance" question before anyone can install it.
  insertBefore(plist, "ITSAppUsesNonExemptEncryption", "<key>LSRequiresIPhoneOS</key>",
    "<key>ITSAppUsesNonExemptEncryption</key>\n\t<false/>\n\t");
  // Purpose strings. Apple's upload check reads them whenever the binary
  // can reach the camera, microphone or photo library — a web view can —
  // and rejects a build that has none. They show only if the app ever asks.
  insertBefore(plist, "NSCameraUsageDescription", "<key>LSRequiresIPhoneOS</key>",
    "<key>NSCameraUsageDescription</key>\n\t<string>Used when you take a photo or scan something inside the app.</string>\n\t" +
    "<key>NSMicrophoneUsageDescription</key>\n\t<string>Used when you record audio or make a call inside the app.</string>\n\t" +
    "<key>NSPhotoLibraryUsageDescription</key>\n\t<string>Used when you attach a picture from your library inside the app.</string>\n\t");
  // Location's purpose string, always there too: without it iOS never answers
  // a page that asks where the phone is — no prompt, no refusal, the page
  // waits forever (measured 2026-09-30). All four ride every build, so a
  // feature added to the web app later works in the installed app with no
  // new build; iOS shows a string only when the app asks.
  insertBefore(plist, "NSLocationWhenInUseUsageDescription", "<key>LSRequiresIPhoneOS</key>",
    "<key>NSLocationWhenInUseUsageDescription</key>\n\t<string>Used when the app shows what is near you or fills in where you are.</string>\n\t");

  // The entitlements file is the app's settings' (applyIosSettings, at the
  // end): push (Xcode's own development value — the release build swaps in
  // production at signing time), Sign in with Apple (the app signs people in
  // natively, nothing for the owner to set up, and App Store review wants the
  // button next to any social login), and whatever the app's features need.
  // Here: the project names the file, and the AppDelegate methods the
  // Capacitor push plugin listens for.
  const pbxproj = root + "/ios/App/App.xcodeproj/project.pbxproj";
  const pbx = readFileSync(pbxproj, "utf-8");
  if (!pbx.includes("CODE_SIGN_ENTITLEMENTS")) {
    if (!pbx.includes("CODE_SIGN_STYLE = Automatic;")) throw new Error(pbxproj + ": expected CODE_SIGN_STYLE = Automatic;");
    writeFileSync(pbxproj, pbx.split("CODE_SIGN_STYLE = Automatic;").join(
      "CODE_SIGN_STYLE = Automatic;\n\t\t\t\tCODE_SIGN_ENTITLEMENTS = App/App.entitlements;"));
  }
  const delegate = root + "/ios/App/App/AppDelegate.swift";
  const swift = readFileSync(delegate, "utf-8");
  if (!swift.includes("capacitorDidRegisterForRemoteNotifications")) {
    const at = swift.lastIndexOf("}");
    if (at < 0) throw new Error(delegate + ": expected a class body");
    writeFileSync(delegate, swift.slice(0, at) +
      "\n    // EscapeBase44 mobile kit: hand APNs' device token (or its refusal) to\n" +
      "    // the Capacitor push plugin.\n" +
      "    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {\n" +
      "        NotificationCenter.default.post(name: .capacitorDidRegisterForRemoteNotifications, object: deviceToken)\n" +
      "    }\n\n" +
      "    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {\n" +
      "        NotificationCenter.default.post(name: .capacitorDidFailToRegisterForRemoteNotifications, object: error)\n" +
      "    }\n" +
      swift.slice(at));
  }
  // The kit's own native code, appended to the app delegate's file (Swift
  // sources survive a `cap sync`): Sign in with Apple as a plugin of this
  // app's own (no package to drift) and the shell, both registered the way
  // Capacitor registers a plugin that lives in the app target — from a bridge
  // view controller of our own (capacitorDidLoad). Capacitor's template builds
  // its screen in code, in the scene delegate, so that is the line that names
  // ours. Registered, every page the app loads finds the plugins under
  // Capacitor.Plugins, and the login page shows the Apple button on that
  // alone. (Measured 2026-09-27 on 8.5.2: the storyboard is never loaded; and
  // an entry on the bundled config's plugin list is gone after the next
  // `cap sync`.) The block is always the file's tail: a project patched by
  // an older kit gets it replaced whole.
  const swift2 = readFileSync(delegate, "utf-8");
  const kitStart = swift2.indexOf(KIT_SWIFT_START);
  const ours = (kitStart < 0 ? swift2.trimEnd() + "\n\n" : swift2.slice(0, kitStart)) + KIT_SWIFT;
  if (ours !== swift2) writeFileSync(delegate, ours);
  replaceOnce(root + "/ios/App/App/SceneDelegate.swift",
    /rootViewController = (CAPBridgeViewController|EB44BridgeViewController)\(\)/,
    "rootViewController = EB44BridgeViewController()");
  applyIosSettings(root, settings, ctx);
}

const KIT_SWIFT_START = "// EscapeBase44 mobile kit: Sign in with Apple for the login page.";
const KIT_SWIFT = "// EscapeBase44 mobile kit: Sign in with Apple for the login page.\n// signIn({ nonce }) asks Apple for the person's identity (name + email on\n// their first sign-in) and hands the identity token back; the backend\n// verifies it against Apple's keys and the nonce it minted.\nimport AuthenticationServices\nimport Capacitor\nimport UniformTypeIdentifiers\nimport WebKit\n\n@objc(EB44AppleSignIn)\npublic class EB44AppleSignIn: CAPPlugin, CAPBridgedPlugin, ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {\n    public let identifier = \"EB44AppleSignIn\"\n    public let jsName = \"EB44AppleSignIn\"\n    public let pluginMethods: [CAPPluginMethod] = [CAPPluginMethod(name: \"signIn\", returnType: CAPPluginReturnPromise)]\n    private var pending: CAPPluginCall?\n\n    @objc func signIn(_ call: CAPPluginCall) {\n        guard let nonce = call.getString(\"nonce\"), !nonce.isEmpty else {\n            call.reject(\"nonce is required\", \"bad-request\")\n            return\n        }\n        pending = call\n        let request = ASAuthorizationAppleIDProvider().createRequest()\n        request.requestedScopes = [.fullName, .email]\n        request.nonce = nonce\n        let controller = ASAuthorizationController(authorizationRequests: [request])\n        controller.delegate = self\n        controller.presentationContextProvider = self\n        DispatchQueue.main.async { controller.performRequests() }\n    }\n\n    public func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {\n        return bridge?.viewController?.view.window ?? ASPresentationAnchor()\n    }\n\n    public func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {\n        guard let call = pending else { return }\n        pending = nil\n        guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,\n              let tokenData = credential.identityToken,\n              let identityToken = String(data: tokenData, encoding: .utf8) else {\n            call.reject(\"Apple returned no identity token\", \"no-token\")\n            return\n        }\n        call.resolve([\n            \"identityToken\": identityToken,\n            \"user\": credential.user,\n            \"email\": credential.email as Any,\n            \"givenName\": credential.fullName?.givenName as Any,\n            \"familyName\": credential.fullName?.familyName as Any,\n        ])\n    }\n\n    public func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {\n        guard let call = pending else { return }\n        pending = nil\n        if let authError = error as? ASAuthorizationError, authError.code == .canceled {\n            call.reject(\"cancelled\", \"cancelled\")\n        } else {\n            call.reject(error.localizedDescription, \"failed\")\n        }\n    }\n}\n\n// EscapeBase44 mobile kit: what a browser does with a page and a bare web\n// view does not. A file the page downloads or opens goes to the phone's\n// share sheet (Save to Files, AirDrop, Mail, Print); window.print() opens the\n// phone's print screen; a new tab on the app's own address opens in the app.\n// And the app's own settings that are the shell's to apply (its plugin config,\n// written from mobile/native.json): the status bar alone hidden, and Google's\n// ads SDK told about the web view when the build carries it.\n@objc(EB44Shell)\npublic class EB44Shell: CAPPlugin, CAPBridgedPlugin {\n    public let identifier = \"EB44Shell\"\n    public let jsName = \"EB44Shell\"\n    public let pluginMethods: [CAPPluginMethod] = [\n        CAPPluginMethod(name: \"printPage\", returnType: CAPPluginReturnPromise),\n        CAPPluginMethod(name: \"info\", returnType: CAPPluginReturnPromise),\n    ]\n    private var downloads: EB44Downloads?\n\n    override public func load() {\n        // After Capacitor's own SystemBars, which loads first and queues\n        // showing it: the hide is queued right behind, in the same pass of\n        // the main queue (queued one pass later, the clock showed over the\n        // splash for a moment — measured 2026-10-21, iPhone Simulator).\n        if getConfig().getBoolean(\"statusBarHidden\", false) {\n            bridge?.statusBarVisible = false\n        }\n        guard let webView = bridge?.webView, let navigation = webView.navigationDelegate, let ui = webView.uiDelegate else { return }\n        let downloads = EB44Downloads(navigation: navigation, ui: ui, host: bridge?.viewController)\n        self.downloads = downloads\n        webView.navigationDelegate = downloads\n        webView.uiDelegate = downloads\n        webView.configuration.userContentController.addUserScript(WKUserScript(\n            source: \"window.print = function () { window.Capacitor.Plugins.EB44Shell.printPage(); };\",\n            injectionTime: .atDocumentStart,\n            forMainFrameOnly: true))\n        registerForAds(webView)\n    }\n\n    // The app's own pages may carry Google's ad tags (AdSense, Ad Manager):\n    // registered with Google's ads SDK (its WebView API for Ads), they may\n    // run inside the app. Registering starts nothing: the SDK itself is\n    // started by window.eb44.ads.start(), after the consent question. Through\n    // the Objective-C runtime: the SDK is in the app only when the build\n    // carries ads.\n    private func registerForAds(_ webView: WKWebView) {\n        guard getConfig().getString(\"ads\", \"none\") != \"none\" else { return }\n        let shared = NSSelectorFromString(\"sharedInstance\"), register = NSSelectorFromString(\"registerWebView:\")\n        guard let sdk = NSClassFromString(\"GADMobileAds\") as? NSObject.Type, sdk.responds(to: shared),\n              let instance = sdk.perform(shared)?.takeUnretainedValue() as? NSObject, instance.responds(to: register) else {\n            print(\"EB44Shell: Google's ads SDK is not in this build; the web view was not registered\")\n            return\n        }\n        _ = instance.perform(register, with: webView)\n        print(\"EB44Shell: the web view is registered with Google's ads SDK\")\n    }\n\n    // What the build carries, for the page (window.eb44.ads.mode()).\n    @objc func info(_ call: CAPPluginCall) {\n        call.resolve([\"ads\": getConfig().getString(\"ads\", \"none\") ?? \"none\"])\n    }\n\n    @objc func printPage(_ call: CAPPluginCall) {\n        DispatchQueue.main.async {\n            guard let webView = self.bridge?.webView else {\n                call.reject(\"no web view\")\n                return\n            }\n            let info = UIPrintInfo(dictionary: nil)\n            info.outputType = .general\n            info.jobName = webView.title ?? \"\"\n            let printer = UIPrintInteractionController.shared\n            printer.printInfo = info\n            printer.printFormatter = webView.viewPrintFormatter()\n            printer.present(animated: true, completionHandler: nil)\n            call.resolve()\n        }\n    }\n}\n\n// The web view's delegate, in front of Capacitor's own: it decides the one\n// thing Capacitor does not — that a download is a download — and hands every\n// other question to Capacitor untouched.\nfinal class EB44Downloads: NSObject, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {\n    private let navigation: WKNavigationDelegate\n    private let ui: WKUIDelegate\n    private weak var host: UIViewController?\n    private var files: [WKDownload: URL] = [:]\n\n    init(navigation: WKNavigationDelegate, ui: WKUIDelegate, host: UIViewController?) {\n        self.navigation = navigation\n        self.ui = ui\n        self.host = host\n    }\n\n    override func responds(to aSelector: Selector!) -> Bool {\n        return super.responds(to: aSelector) || navigation.responds(to: aSelector) || ui.responds(to: aSelector)\n    }\n\n    override func forwardingTarget(for aSelector: Selector!) -> Any? {\n        if navigation.responds(to: aSelector) { return navigation }\n        if ui.responds(to: aSelector) { return ui }\n        return super.forwardingTarget(for: aSelector)\n    }\n\n    // A blob: or data: address is a file the page made; it has nowhere to\n    // open but a download.\n    private func isMadeByThePage(_ url: URL?) -> Bool {\n        return url?.scheme == \"blob\" || url?.scheme == \"data\"\n    }\n\n    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {\n        let topLevel = navigationAction.targetFrame?.isMainFrame ?? true\n        if navigationAction.shouldPerformDownload || (topLevel && isMadeByThePage(navigationAction.request.url)) {\n            decisionHandler(.download)\n            return\n        }\n        if navigation.webView?(webView, decidePolicyFor: navigationAction, decisionHandler: decisionHandler) == nil {\n            decisionHandler(.allow)\n        }\n    }\n\n    // The app's one screen shows the app's pages. An answer that is not a\n    // page — a PDF, a spreadsheet, an attachment — is a file: shown in place\n    // it would take the app's screen with no way back (an iPhone has no back\n    // button).\n    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {\n        let disposition = (navigationResponse.response as? HTTPURLResponse)?.value(forHTTPHeaderField: \"Content-Disposition\") ?? \"\"\n        let type = (navigationResponse.response.mimeType ?? \"\").lowercased()\n        let isAPage = type.isEmpty || type == \"text/html\" || type == \"application/xhtml+xml\"\n        if navigationResponse.isForMainFrame && (disposition.lowercased().hasPrefix(\"attachment\") || !isAPage) {\n            decisionHandler(.download)\n        } else {\n            decisionHandler(navigationResponse.canShowMIMEType ? .allow : .cancel)\n        }\n    }\n\n    // A new tab. One the page made (blob:, data:) is a file. One on the app's\n    // own address opens here, where the person is signed in — Capacitor would\n    // hand it to Safari, where they are not. Anything else is Capacitor's.\n    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {\n        let url = navigationAction.request.url\n        if isMadeByThePage(url) {\n            webView.startDownload(using: navigationAction.request) { download in download.delegate = self }\n            return nil\n        }\n        if let url = url, let here = webView.url, url.scheme == here.scheme, url.host == here.host, url.port == here.port {\n            webView.load(navigationAction.request)\n            return nil\n        }\n        return ui.webView?(webView, createWebViewWith: configuration, for: navigationAction, windowFeatures: windowFeatures) ?? nil\n    }\n\n    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {\n        download.delegate = self\n    }\n\n    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {\n        download.delegate = self\n    }\n\n    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {\n        // A folder of its own per file, so the name the page gave it stays its name.\n        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)\n        do {\n            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)\n        } catch {\n            completionHandler(nil)\n            return\n        }\n        // A name with no ending gets the one its kind has, so the phone knows\n        // what can open it.\n        var name = suggestedFilename\n        if (name as NSString).pathExtension.isEmpty, let kind = response.mimeType.flatMap({ UTType(mimeType: $0)?.preferredFilenameExtension }) {\n            name += \".\" + kind\n        }\n        let file = folder.appendingPathComponent(name)\n        files[download] = file\n        completionHandler(file)\n    }\n\n    func downloadDidFinish(_ download: WKDownload) {\n        guard let file = files.removeValue(forKey: download), var presenter = host else { return }\n        while let above = presenter.presentedViewController { presenter = above }\n        let sheet = UIActivityViewController(activityItems: [file], applicationActivities: nil)\n        sheet.popoverPresentationController?.sourceView = presenter.view\n        sheet.popoverPresentationController?.sourceRect = CGRect(x: presenter.view.bounds.midX, y: presenter.view.bounds.maxY, width: 0, height: 0)\n        sheet.completionWithItemsHandler = { _, _, _, _ in\n            try? FileManager.default.removeItem(at: file.deletingLastPathComponent())\n        }\n        presenter.present(sheet, animated: true)\n    }\n\n    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {\n        if let file = files.removeValue(forKey: download) {\n            try? FileManager.default.removeItem(at: file.deletingLastPathComponent())\n        }\n    }\n}\n\nclass EB44BridgeViewController: CAPBridgeViewController {\n    override open func capacitorDidLoad() {\n        bridge?.registerPluginInstance(EB44AppleSignIn())\n        bridge?.registerPluginInstance(EB44Shell())\n    }\n}\n";

// Android: the URL scheme, the push status-bar icon, what the app's pages may
// ask the phone for, the shell, the store identity and version, Firebase's
// config when the owner has set push up, the app's own settings
// (mobile/native.json). `capabilities` is what detectCapabilities read off
// the built web app; ctx: { hosts, ads } (setup.mjs).
export function patchAndroid(root, identity, googleServicesJson, capabilities, settings = {}, ctx = { hosts: [], ads: {} }) {
  const manifest = root + "/android/app/src/main/AndroidManifest.xml";
  insertBefore(manifest, SCHEME, "</activity>",
    "    <intent-filter>\n" +
    '        <action android:name="android.intent.action.VIEW" />\n' +
    '        <category android:name="android.intent.category.DEFAULT" />\n' +
    '        <category android:name="android.intent.category.BROWSABLE" />\n' +
    '        <data android:scheme="' + SCHEME + '" />\n' +
    "    </intent-filter>\n" +
    "    ");
  // The status-bar icon for push notifications: Android wants white pixels
  // on transparency there (the app icon would render as a white square).
  // A plain bell, as a vector drawable.
  mkdirSync(root + "/android/app/src/main/res/drawable", { recursive: true });
  writeFileSync(root + "/android/app/src/main/res/drawable/ic_push.xml",
    '<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="24dp" android:height="24dp" android:viewportWidth="24" android:viewportHeight="24">\n' +
    '  <path android:fillColor="#FFFFFFFF" android:pathData="M12,22c1.1,0 2,-0.9 2,-2h-4c0,1.1 0.89,2 2,2zM18,16v-5c0,-3.07 -1.64,-5.64 -4.5,-6.32L13.5,4c0,-0.83 -0.67,-1.5 -1.5,-1.5s-1.5,0.67 -1.5,1.5v0.68C7.63,5.36 6,7.92 6,11v5l-2,2v1h16v-1l-2,-2z" />\n' +
    "</vector>\n");
  insertBefore(manifest, "default_notification_icon", "</application>",
    '    <meta-data android:name="com.google.firebase.messaging.default_notification_icon" android:resource="@drawable/ic_push" />\n' +
    "    ");
  // What the app's pages may ask the phone for. Android refuses a page
  // anything the manifest does not declare — location, the camera, the
  // microphone — with no prompt; so the manifest declares what the app's own
  // code uses (capabilities), this build. The hardware is marked optional, so
  // Play still offers the app to a device without it.
  // The <queries> entry is for a "take a photo" upload (<input capture>):
  // Capacitor asks Android who can take the picture, and since Android 11 an
  // app sees other apps only through such an entry — without it the camera is
  // never offered and the person gets the photo gallery (measured 2026-09-30).
  // It is not a permission and is always there.
  const asked = [
    "    <queries>",
    '        <intent><action android:name="android.media.action.IMAGE_CAPTURE" /></intent>',
    '        <intent><action android:name="android.media.action.VIDEO_CAPTURE" /></intent>',
    "    </queries>",
  ];
  if (capabilities.location) asked.push(
    '    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />',
    '    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />');
  if (capabilities.camera) asked.push(
    '    <uses-permission android:name="android.permission.CAMERA" />',
    '    <uses-feature android:name="android.hardware.camera" android:required="false" />',
    '    <uses-feature android:name="android.hardware.camera.autofocus" android:required="false" />');
  if (capabilities.microphone) asked.push(
    '    <uses-permission android:name="android.permission.RECORD_AUDIO" />',
    '    <uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS" />',
    '    <uses-feature android:name="android.hardware.microphone" android:required="false" />');
  // A permission the app blocks (mobile/native.json) is left out here: one
  // manifest that declares it and removes it fails the merge.
  const blocked = blockedPermissions(settings, root);
  const kitLines = asked.filter(function (line) {
    const m = /<uses-permission android:name="([^"]+)"/.exec(line);
    return !(m && blocked.includes(m[1]));
  });
  writeBlock(manifest, "    <!-- EscapeBase44 mobile kit: what the app's pages may ask the phone for -->",
    "    <!-- /EscapeBase44 mobile kit -->", kitLines.join("\n") + "\n", "</manifest>");
  applyAndroidSettings(root, settings, ctx, kitLines);
  // The shell (downloads, print, share): a plugin of this app's own, written
  // next to Capacitor's MainActivity and registered there. It reaches the
  // web view's document-start hook through androidx.webkit, which Capacitor
  // already ships inside the app — the dependency line only lets app code
  // name it.
  const main = filesUnder(root + "/android/app/src/main/java").find((file) => file.endsWith("/MainActivity.java"));
  if (!main) throw new Error(root + "/android: expected to find MainActivity.java");
  const pkg = (readFileSync(main, "utf-8").match(/^package ([\w.]+);/m) || [])[1];
  if (!pkg) throw new Error(main + ": expected a package line");
  if (!readFileSync(main, "utf-8").includes("EB44Shell")) {
    replaceOnce(main, /public class MainActivity extends BridgeActivity \{\s*\}/, MAIN_ACTIVITY_BODY);
  }
  writeFileSync(main.slice(0, -"MainActivity.java".length) + "EB44Shell.java",
    SHELL_JAVA.split("__PACKAGE__").join(pkg).split("__PAGE_SCRIPT__").join(JSON.stringify(PAGE_SCRIPT)));
  // Store identity and version — the one line each in app/build.gradle.
  const gradle = root + "/android/app/build.gradle";
  insertBefore(gradle, "androidx.webkit:webkit", "    implementation project(':capacitor-android')",
    '    implementation "androidx.webkit:webkit:$androidxWebkitVersion"\n');
  replaceOnce(gradle, /applicationId "[^"]*"/, 'applicationId "' + identity.packageName + '"');
  replaceOnce(gradle, /versionCode \d+/, "versionCode " + identity.versionCode);
  replaceOnce(gradle, /versionName "[^"]*"/, 'versionName "' + identity.versionName + '"');
  // Firebase's app config for push, baked into the app when the owner has
  // set Android push up: read from their Firebase project for this very
  // package (mobile/firebase-config.mjs), never a stored copy.
  if (googleServicesJson) {
    writeFileSync(root + "/android/app/google-services.json", googleServicesJson);
  }
}

const MAIN_ACTIVITY_BODY = "public class MainActivity extends BridgeActivity {\n\n    // EscapeBase44 mobile kit: the shell (downloads, print, share, full screen).\n    @Override\n    public void onCreate(android.os.Bundle savedInstanceState) {\n        registerPlugin(EB44Shell.class);\n        super.onCreate(savedInstanceState);\n    }\n}";
const SHELL_JAVA = "package __PACKAGE__;\n\nimport android.app.Activity;\nimport android.app.Dialog;\nimport android.content.ActivityNotFoundException;\nimport android.content.Context;\nimport android.content.Intent;\nimport android.content.SharedPreferences;\nimport android.content.pm.ActivityInfo;\nimport android.net.Uri;\nimport android.os.Build;\nimport android.print.PrintAttributes;\nimport android.print.PrintManager;\nimport android.util.Base64;\nimport android.util.Log;\nimport android.view.View;\nimport android.view.ViewGroup;\nimport android.view.Window;\nimport android.view.WindowManager;\nimport android.webkit.CookieManager;\nimport android.webkit.MimeTypeMap;\nimport android.webkit.URLUtil;\nimport android.webkit.WebView;\nimport android.widget.Toast;\nimport androidx.activity.result.ActivityResultLauncher;\nimport androidx.activity.result.contract.ActivityResultContracts;\nimport androidx.core.view.WindowCompat;\nimport androidx.core.view.WindowInsetsCompat;\nimport androidx.core.view.WindowInsetsControllerCompat;\nimport androidx.webkit.WebViewCompat;\nimport androidx.webkit.WebViewFeature;\nimport com.getcapacitor.Bridge;\nimport com.getcapacitor.BridgeWebChromeClient;\nimport com.getcapacitor.JSObject;\nimport com.getcapacitor.Plugin;\nimport com.getcapacitor.PluginCall;\nimport com.getcapacitor.PluginMethod;\nimport com.getcapacitor.annotation.CapacitorPlugin;\nimport java.io.File;\nimport java.io.FileInputStream;\nimport java.io.FileOutputStream;\nimport java.io.IOException;\nimport java.io.InputStream;\nimport java.io.OutputStream;\nimport java.net.HttpURLConnection;\nimport java.net.URL;\nimport java.nio.charset.StandardCharsets;\nimport java.util.ArrayDeque;\nimport java.util.Collections;\nimport java.util.HashMap;\nimport java.util.Map;\nimport java.util.concurrent.ExecutorService;\nimport java.util.concurrent.Executors;\nimport org.json.JSONException;\nimport org.json.JSONObject;\nimport org.json.JSONTokener;\n\n// EscapeBase44 mobile kit: what a browser does with a page and a bare web\n// view does not. A file the page downloads is offered on Android's own Save\n// screen; window.print() opens Android's print screen; navigator.share opens\n// the share sheet; a video (or anything) the page puts full screen goes full\n// screen. And the app's own settings that are the shell's to apply (its\n// plugin config, written from mobile/native.json): the status bar alone\n// hidden, and Google's ads SDK told about the web view when the build\n// carries it.\n@CapacitorPlugin(name = \"EB44Shell\")\npublic class EB44Shell extends Plugin {\n\n    private static final String PAGE_SCRIPT = __PAGE_SCRIPT__;\n\n    // A downloaded file, held in the app's cache until the person has said\n    // where to save it.\n    private static final class Download {\n        final File file;\n        final String name;\n        final String mime;\n\n        Download(File file, String name, String mime) {\n            this.file = file;\n            this.name = name;\n            this.mime = mime == null || mime.isEmpty() ? \"application/octet-stream\" : mime;\n        }\n    }\n\n    private static final class Arriving {\n        final File file;\n        final OutputStream out;\n\n        Arriving(File file) throws IOException {\n            this.file = file;\n            this.out = new FileOutputStream(file);\n        }\n    }\n\n    private final ExecutorService io = Executors.newSingleThreadExecutor();\n    private final Map<String, Arriving> arriving = new HashMap<>();\n    private final ArrayDeque<Download> waiting = new ArrayDeque<>();\n    private Download onScreen;\n    private ActivityResultLauncher<Intent> saveScreen;\n    private int files = 0;\n\n    @Override\n    public void load() {\n        WebView webView = bridge.getWebView();\n        saveScreen = bridge.registerForActivityResult(new ActivityResultContracts.StartActivityForResult(), result ->\n            saved(result.getResultCode() == Activity.RESULT_OK && result.getData() != null ? result.getData().getData() : null)\n        );\n        webView.setDownloadListener((url, userAgent, contentDisposition, mimeType, contentLength) ->\n            download(url, userAgent, contentDisposition, mimeType)\n        );\n        if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {\n            Uri app = Uri.parse(bridge.getAppUrl());\n            WebViewCompat.addDocumentStartJavaScript(webView, PAGE_SCRIPT, Collections.singleton(app.getScheme() + \"://\" + app.getAuthority()));\n        }\n        // Capacitor's own client refuses full screen (it answers \"hidden\" at\n        // once); ours is the same client with full screen in it. Made here\n        // (its file and permission screens register before the activity\n        // starts), put on the web view just after: Capacitor sets its own when\n        // it loads the page, after the plugins load (measured 2026-10-21:\n        // set here directly, Capacitor's had replaced it 5 s later).\n        FullScreen fullScreen = new FullScreen(bridge);\n        bridge.executeOnMainThread(() -> webView.setWebChromeClient(fullScreen));\n        // After Capacitor's own SystemBars, which loads first and shows it.\n        if (getConfig().getBoolean(\"statusBarHidden\", false)) bridge.executeOnMainThread(this::hideStatusBar);\n        if (!\"none\".equals(getConfig().getString(\"ads\", \"none\"))) registerForAds(webView);\n    }\n\n    // What the build carries, for the page (window.eb44.ads.mode()).\n    @PluginMethod\n    public void info(PluginCall call) {\n        JSObject out = new JSObject();\n        out.put(\"ads\", getConfig().getString(\"ads\", \"none\"));\n        call.resolve(out);\n    }\n\n    private WindowInsetsControllerCompat bars() {\n        return WindowCompat.getInsetsController(getActivity().getWindow(), getActivity().getWindow().getDecorView());\n    }\n\n    private void hideStatusBar() {\n        WindowInsetsControllerCompat bars = bars();\n        bars.setSystemBarsBehavior(WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);\n        bars.hide(WindowInsetsCompat.Type.statusBars());\n    }\n\n    // The app's own pages may carry Google's ad tags (AdSense, Ad Manager):\n    // registered with Google's ads SDK (its WebView API for Ads), they may\n    // run inside the app — and they need the web view to keep third-party\n    // cookies (Google's doc; Capacitor leaves them off). Registering starts\n    // nothing: the SDK itself is started by window.eb44.ads.start(), after the\n    // consent question. Through reflection: the SDK is in the app only when\n    // the build carries ads.\n    private void registerForAds(WebView webView) {\n        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);\n        try {\n            Class.forName(\"com.google.android.gms.ads.MobileAds\").getMethod(\"registerWebView\", WebView.class).invoke(null, webView);\n            Log.i(\"EB44Shell\", \"the web view is registered with Google's ads SDK\");\n        } catch (Exception e) {\n            Log.w(\"EB44Shell\", \"the web view was not registered with Google's ads SDK\", e);\n        }\n    }\n\n    // Full screen: the page's own view in a window of its own over the app,\n    // every bar hidden, drawn into the camera band, the phone free to turn\n    // (unless the person locked rotation); Back, or the page, ends it. A\n    // window of its own: the app's is padded for the camera band and the\n    // navigation bar (Capacitor's SystemBars), so a view inside it left white\n    // strips at both (measured 2026-10-21, Android 15).\n    private final class FullScreen extends BridgeWebChromeClient {\n        private View view;\n        private CustomViewCallback done;\n        private Dialog dialog;\n        private int orientation;\n\n        FullScreen(Bridge bridge) {\n            super(bridge);\n        }\n\n        @Override\n        public void onShowCustomView(View shown, CustomViewCallback callback) {\n            if (view != null) {\n                callback.onCustomViewHidden();\n                return;\n            }\n            view = shown;\n            done = callback;\n            orientation = getActivity().getRequestedOrientation();\n            dialog = new Dialog(getActivity(), android.R.style.Theme_Black_NoTitleBar_Fullscreen);\n            dialog.setContentView(shown, new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));\n            dialog.setOnCancelListener(d -> onHideCustomView());\n            Window window = dialog.getWindow();\n            WindowCompat.setDecorFitsSystemWindows(window, false);\n            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {\n                WindowManager.LayoutParams attributes = window.getAttributes();\n                attributes.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;\n                window.setAttributes(attributes);\n            }\n            dialog.show();\n            WindowInsetsControllerCompat bars = WindowCompat.getInsetsController(window, window.getDecorView());\n            bars.setSystemBarsBehavior(WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);\n            bars.hide(WindowInsetsCompat.Type.systemBars());\n            getActivity().setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_FULL_USER);\n        }\n\n        @Override\n        public void onHideCustomView() {\n            if (view == null) return;\n            Dialog shownIn = dialog;\n            dialog = null;\n            view = null;\n            shownIn.setOnCancelListener(null);\n            shownIn.dismiss();\n            getActivity().setRequestedOrientation(orientation);\n            CustomViewCallback callback = done;\n            done = null;\n            callback.onCustomViewHidden();\n        }\n    }\n\n    // The web view says a download is starting. A blob: address is sent over\n    // by the page (file() below); anything else is fetched here.\n    private void download(String url, String userAgent, String contentDisposition, String mimeType) {\n        WebView webView = bridge.getWebView();\n        if (url.startsWith(\"blob:\")) {\n            webView.evaluateJavascript(\"window.__eb44shell ? window.__eb44shell.send(\" + JSONObject.quote(url) + \",\" + JSONObject.quote(mimeType == null ? \"\" : mimeType) + \") : false\", sent -> {\n                // The page no longer holds it (or this web view is too old to\n                // run the page script): say so rather than do nothing.\n                if (!\"true\".equals(sent)) say(\"Couldn't download the file\");\n            });\n            return;\n        }\n        webView.evaluateJavascript(\"window.__eb44shell ? window.__eb44shell.nameOf(\" + JSONObject.quote(key(url)) + \") : \\\"\\\"\", value -> {\n            String named = text(value);\n            io.execute(() -> fetch(url, userAgent, contentDisposition, mimeType, named));\n        });\n    }\n\n    private void fetch(String url, String userAgent, String contentDisposition, String mimeType, String named) {\n        File file = cacheFile();\n        try {\n            String mime = mimeType;\n            if (url.startsWith(\"data:\")) {\n                int comma = url.indexOf(',');\n                String head = url.substring(5, comma);\n                byte[] bytes = head.endsWith(\";base64\")\n                    ? Base64.decode(url.substring(comma + 1), Base64.DEFAULT)\n                    : Uri.decode(url.substring(comma + 1)).getBytes(StandardCharsets.UTF_8);\n                try (OutputStream out = new FileOutputStream(file)) {\n                    out.write(bytes);\n                }\n                if (mime == null || mime.isEmpty()) mime = head.split(\";\")[0];\n            } else {\n                HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();\n                String cookies = CookieManager.getInstance().getCookie(url);\n                if (cookies != null) connection.setRequestProperty(\"Cookie\", cookies);\n                if (userAgent != null) connection.setRequestProperty(\"User-Agent\", userAgent);\n                if (connection.getResponseCode() >= 400) throw new IOException(\"HTTP \" + connection.getResponseCode());\n                try (InputStream in = connection.getInputStream(); OutputStream out = new FileOutputStream(file)) {\n                    copy(in, out);\n                }\n            }\n            offer(new Download(file, named.isEmpty() ? URLUtil.guessFileName(url, contentDisposition, mime) : named, mime));\n        } catch (Exception e) {\n            file.delete();\n            say(\"Couldn't download the file\");\n        }\n    }\n\n    // One piece of a blob, from the page (base64), in order; the last piece\n    // closes the file.\n    @PluginMethod\n    public void file(PluginCall call) {\n        String id = call.getString(\"id\", \"\");\n        try {\n            Arriving piece = arriving.get(id);\n            if (piece == null) {\n                piece = new Arriving(cacheFile());\n                arriving.put(id, piece);\n            }\n            piece.out.write(Base64.decode(call.getString(\"data\", \"\"), Base64.DEFAULT));\n            if (Boolean.TRUE.equals(call.getBoolean(\"last\", false))) {\n                piece.out.close();\n                arriving.remove(id);\n                String mime = call.getString(\"mime\", \"\");\n                String name = call.getString(\"name\", \"\");\n                if (name.isEmpty()) {\n                    String extension = MimeTypeMap.getSingleton().getExtensionFromMimeType(mime);\n                    name = extension == null ? \"download\" : \"download.\" + extension;\n                }\n                offer(new Download(piece.file, name, mime));\n            }\n            call.resolve();\n        } catch (IOException e) {\n            arriving.remove(id);\n            say(\"Couldn't download the file\");\n            call.reject(\"could not write the file\");\n        }\n    }\n\n    @PluginMethod\n    public void printPage(PluginCall call) {\n        bridge.executeOnMainThread(() -> {\n            WebView webView = bridge.getWebView();\n            String title = webView.getTitle() == null || webView.getTitle().isEmpty() ? \"Document\" : webView.getTitle();\n            PrintManager printer = (PrintManager) getActivity().getSystemService(Context.PRINT_SERVICE);\n            printer.print(title, webView.createPrintDocumentAdapter(title), new PrintAttributes.Builder().build());\n            call.resolve();\n        });\n    }\n\n    @PluginMethod\n    public void share(PluginCall call) {\n        String title = call.getString(\"title\", \"\");\n        String text = call.getString(\"text\", \"\");\n        String url = call.getString(\"url\", \"\");\n        Intent send = new Intent(Intent.ACTION_SEND)\n            .setType(\"text/plain\")\n            .putExtra(Intent.EXTRA_SUBJECT, title)\n            .putExtra(Intent.EXTRA_TEXT, text.isEmpty() || url.isEmpty() ? text + url : text + \"\\n\" + url);\n        getActivity().startActivity(Intent.createChooser(send, title.isEmpty() ? null : title));\n        call.resolve();\n    }\n\n    // Android's own Save screen, one file at a time.\n    private void offer(Download download) {\n        bridge.executeOnMainThread(() -> {\n            waiting.add(download);\n            next();\n        });\n    }\n\n    private void next() {\n        if (onScreen != null || waiting.isEmpty()) return;\n        onScreen = waiting.poll();\n        // Android may end the app's process while its Save screen is open (a\n        // phone short of memory); the file in the cache outlives it, so what\n        // is on screen is written down for the app that comes back.\n        held().edit().putString(\"file\", onScreen.file.getPath()).putString(\"name\", onScreen.name).putString(\"mime\", onScreen.mime).apply();\n        Intent save = new Intent(Intent.ACTION_CREATE_DOCUMENT)\n            .addCategory(Intent.CATEGORY_OPENABLE)\n            .setType(onScreen.mime)\n            .putExtra(Intent.EXTRA_TITLE, onScreen.name);\n        try {\n            saveScreen.launch(save);\n        } catch (ActivityNotFoundException e) {\n            onScreen.file.delete();\n            onScreen = null;\n            held().edit().clear().apply();\n            say(\"This phone has no app to save files with\");\n            next();\n        }\n    }\n\n    // The person picked a place — or closed the screen, and where is null.\n    private void saved(Uri where) {\n        Download download = onScreen;\n        onScreen = null;\n        if (download == null && held().contains(\"file\")) {\n            download = new Download(new File(held().getString(\"file\", \"\")), held().getString(\"name\", \"\"), held().getString(\"mime\", \"\"));\n        }\n        held().edit().clear().apply();\n        if (download == null) return;\n        final Download file = download;\n        if (where == null) {\n            file.file.delete();\n        } else {\n            io.execute(() -> {\n                try (InputStream in = new FileInputStream(file.file); OutputStream out = getContext().getContentResolver().openOutputStream(where)) {\n                    copy(in, out);\n                    say(file.name + \" saved\");\n                } catch (Exception e) {\n                    say(\"Couldn't save \" + file.name);\n                }\n                file.file.delete();\n            });\n        }\n        next();\n    }\n\n    private SharedPreferences held() {\n        return getContext().getSharedPreferences(\"eb44-shell\", Context.MODE_PRIVATE);\n    }\n\n    private synchronized File cacheFile() {\n        return new File(getContext().getCacheDir(), \"eb44-download-\" + System.currentTimeMillis() + \"-\" + (++files));\n    }\n\n    private void say(String words) {\n        bridge.executeOnMainThread(() -> Toast.makeText(getContext(), words, Toast.LENGTH_SHORT).show());\n    }\n\n    private static void copy(InputStream in, OutputStream out) throws IOException {\n        byte[] buffer = new byte[65536];\n        int read;\n        while ((read = in.read(buffer)) != -1) out.write(buffer, 0, read);\n    }\n\n    // The same key the page's script keeps a file name under (a data: address\n    // can be megabytes long).\n    private static String key(String url) {\n        return url.length() <= 512 ? url : url.length() + \":\" + url.substring(0, 128) + url.substring(url.length() - 128);\n    }\n\n    private static String text(String json) {\n        try {\n            Object value = new JSONTokener(json).nextValue();\n            return value instanceof String ? (String) value : \"\";\n        } catch (JSONException e) {\n            return \"\";\n        }\n    }\n}\n";
const PAGE_SCRIPT = "(function () {\n  if (window.__eb44shell) return;\n  function shell() { return window.Capacitor.Plugins.EB44Shell; }\n  var blobs = {}, names = {}, sent = 0;\n  function key(url) { return url.length <= 512 ? url : url.length + \":\" + url.slice(0, 128) + url.slice(-128); }\n  var create = URL.createObjectURL, revoke = URL.revokeObjectURL;\n  URL.createObjectURL = function (object) {\n    var url = create.apply(this, arguments);\n    if (object instanceof Blob) blobs[url] = object;\n    return url;\n  };\n  URL.revokeObjectURL = function (url) {\n    setTimeout(function () { delete blobs[url]; delete names[key(String(url))]; }, 60000);\n    return revoke.apply(this, arguments);\n  };\n  function note(a) {\n    if (a.hasAttribute(\"download\") && a.href) names[key(a.href)] = a.getAttribute(\"download\");\n  }\n  var click = HTMLElement.prototype.click, dispatch = EventTarget.prototype.dispatchEvent;\n  HTMLAnchorElement.prototype.click = function () { note(this); return click.apply(this, arguments); };\n  HTMLAnchorElement.prototype.dispatchEvent = function (event) {\n    if (event && event.type === \"click\") note(this);\n    return dispatch.apply(this, arguments);\n  };\n  document.addEventListener(\"click\", function (event) {\n    var a = event.target && event.target.closest ? event.target.closest(\"a[download]\") : null;\n    if (a) note(a);\n  }, true);\n  window.__eb44shell = {\n    nameOf: function (k) { return names[k] || \"\"; },\n    send: function (url, mime) {\n      var blob = blobs[url];\n      if (!blob) return false;\n      var id = String(++sent), name = names[key(url)] || \"\", step = 393216, at = 0;\n      (function next() {\n        var reader = new FileReader();\n        reader.onload = function () {\n          var data = String(reader.result);\n          at += step;\n          shell().file({ id: id, data: data.slice(data.indexOf(\",\") + 1), last: at >= blob.size, name: name, mime: blob.type || mime })\n            .then(function () { if (at < blob.size) next(); });\n        };\n        reader.readAsDataURL(blob.slice(at, at + step));\n      })();\n      return true;\n    }\n  };\n  window.print = function () { shell().printPage(); };\n  if (!navigator.share) {\n    navigator.share = function (data) {\n      data = data || {};\n      if (data.files && data.files.length) return Promise.reject(new TypeError(\"Sharing files is not supported here\"));\n      return shell().share({ title: data.title || \"\", text: data.text || \"\", url: data.url || \"\" });\n    };\n  }\n})();";

// The Android identity a build uses: the store package name and version from
// the repo's facts (.escapebase44/config.json) and the build's env — an
// explicit env wins, then the fact, then the project's own namespace. The
// version code must rise with every Play upload, so it is the run number on
// top of whatever the app had reached before the migration.
export function androidIdentity(root, env) {
  const configPath = root + "/.escapebase44/config.json";
  const facts = existsSync(configPath) ? JSON.parse(readFileSync(configPath, "utf-8")).env || {} : {};
  const capacitor = JSON.parse(readFileSync(root + "/capacitor.config.json", "utf-8"));
  const base = Number(facts.MOBILE_ANDROID_VERSION_CODE_BASE || 0);
  const run = Number(env.GITHUB_RUN_NUMBER || 0);
  return {
    packageName: env.MOBILE_ANDROID_PACKAGE || facts.MOBILE_ANDROID_PACKAGE || capacitor.appId,
    versionName: env.MOBILE_VERSION || "1.0",
    versionCode: env.MOBILE_BUILD_NUMBER ? Number(env.MOBILE_BUILD_NUMBER) : base + Math.max(run, 1),
  };
}

// The iPhone app's store identity and version: the workflow's (the App Store
// Connect preflight's answer), else the repo's facts, else Capacitor's appId;
// a version and build number only when the workflow gives them (on your own
// machine the project keeps its own).
export function iosIdentity(root, env) {
  const configPath = root + "/.escapebase44/config.json";
  const facts = existsSync(configPath) ? JSON.parse(readFileSync(configPath, "utf-8")).env || {} : {};
  const capacitor = JSON.parse(readFileSync(root + "/capacitor.config.json", "utf-8"));
  return {
    bundleId: env.MOBILE_IOS_BUNDLE_ID || facts.MOBILE_IOS_BUNDLE_ID || capacitor.appId,
    version: env.MOBILE_IOS_VERSION || "",
    build: env.MOBILE_IOS_BUILD_NUMBER || "",
  };
}

// Written into the app target's own build settings (both configurations) —
// never passed to xcodebuild as arguments: those reach every target the build
// compiles, a plugin's own framework and resource bundle included, and Apple
// refuses an app with two bundles of one id (ITMS-90685; measured 2026-10-21
// with the barcode scanner's resource bundle). Keep the universal device
// family so an App Store update retains both iPhone and iPad support.
export function setIosAppTarget(root, identity) {
  const pbxproj = root + "/ios/App/App.xcodeproj/project.pbxproj";
  const wanted = { PRODUCT_BUNDLE_IDENTIFIER: identity.bundleId, TARGETED_DEVICE_FAMILY: "1,2" };
  if (identity.version) wanted.MARKETING_VERSION = identity.version;
  if (identity.build) wanted.CURRENT_PROJECT_VERSION = identity.build;
  let targets = 0;
  const pbx = readFileSync(pbxproj, "utf-8").replace(/buildSettings = \{([\s\S]*?)\n(\t+)\};/g, function (all, body, indent) {
    if (!/\bINFOPLIST_FILE = App\/Info\.plist;/.test(body)) return all;
    targets++;
    for (const key of Object.keys(wanted)) {
      const value = /^[A-Za-z0-9_.]+$/.test(wanted[key]) ? wanted[key] : JSON.stringify(wanted[key]);
      const line = new RegExp("\\n(\\t+)" + key + " = [^;]*;");
      body = line.test(body)
        ? body.replace(line, function (match, tabs) { return "\n" + tabs + key + " = " + value + ";"; })
        : "\n" + indent + "\t" + key + " = " + value + ";" + body;
    }
    return "buildSettings = {" + body + "\n" + indent + "};";
  });
  if (targets === 0) throw new Error(pbxproj + ": expected the app target's build settings (INFOPLIST_FILE = App/Info.plist)");
  writeFileSync(pbxproj, pbx);
}
