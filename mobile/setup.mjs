#!/usr/bin/env node
// Sets up the native iOS/Android projects for this app. Safe to rerun.
// Usage: npm run mobile:setup [-- ios|android]
//
// Installs Capacitor, builds the web app, generates ios/ + android/ (a
// project committed in the repo is used as it is), syncs the build in, builds
// the app icon and the splash, then applies everything the native projects
// need beyond Capacitor's templates (mobile/native-patches.mjs) — the app's
// own native settings (mobile/native.json, see MOBILE.md) with it.
import { execSync } from "node:child_process";
import { cpSync, existsSync, readFileSync, writeFileSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import {
  patchIos, patchAndroid, androidIdentity, detectCapabilities, readNativeSettings, NativeSettingsError,
  adsContext, applyBundledConfig, assetsFlags, plistObject, iosPluginProblems, raiseMinimums, pruneImageSet, iosIdentity, setIosAppTarget, ADS_PLUGIN, transparentPng,
} from "./native-patches.mjs";
import { androidFirebaseConfig, FirebaseStop } from "./firebase-config.mjs";

const want = process.argv[2]; // optional: only one platform
const platforms = want ? [want] : ["ios", "android"];
const root = process.cwd();

const run = (cmd) => execSync(cmd, { stdio: "inherit" });
function stop(code, extra) {
  console.log("EB44 " + JSON.stringify(Object.assign({ code: code }, extra || {})));
  console.log("::error::Stopped (" + code + "). Your EscapeBase44 success page says what to do.");
  process.exit(1);
}

// The app's own native settings, checked before anything is installed.
let settings;
try {
  settings = readNativeSettings(root);
} catch (err) {
  if (!(err instanceof NativeSettingsError)) throw err;
  stop("native-settings-invalid", { detail: err.message });
}

// Capacitor packages are installed on first use so the repo's normal
// `npm install` stays lean until someone actually goes mobile. They're
// saved to devDependencies because `cap sync` discovers plugins (the App
// plugin that receives the OAuth return URL and links that open the app, the
// push plugin, the splash screen, the NativePurchases plugin behind
// window.eb44.iap) through package.json. A plugin the app's own native
// features use is the app's own dependency (MOBILE.md).
run(
  "npm install --save-dev --no-audit --no-fund " +
    "@capacitor/core@^8 @capacitor/cli@^8 @capacitor/app@^8 @capacitor/browser@^8 " +
    "@capacitor/push-notifications@^8 @capacitor/splash-screen@^8 @capgo/native-purchases@^8 " +
    "@capacitor/ios@^8 @capacitor/android@^8",
);

// Always a fresh build of the web app: it is the bundle inside the native
// app, and what the Android permissions and the ads are read off.
run("npm run build");
const capabilities = detectCapabilities(root + "/dist");

// Google's ads SDK, when the app shows ads: an AdMob app on either platform,
// or Google's ad tags in the app's own pages (window.eb44.ads, MOBILE.md).
let ads = adsContext(root, process.env, capabilities);
if (ads.wanted && !ads.installed) {
  run("npm install --save-dev --no-audit --no-fund " + ADS_PLUGIN + "@^8");
  ads = adsContext(root, process.env, capabilities);
}

// Links that open the app: every address the app answers on — its own and
// any custom domain — as its live backend knows them.
let hosts = [];
if (settings.links) {
  const appUrl = JSON.parse(readFileSync("capacitor.config.json", "utf-8")).server?.url;
  const facts = existsSync(".escapebase44/config.json") ? JSON.parse(readFileSync(".escapebase44/config.json", "utf-8")).env || {} : {};
  try {
    const res = await fetch(new URL("/api/apps/" + facts.APP_ID + "/eb44/mobile/hosts", appUrl));
    if (!res.ok) throw new Error("the app answered HTTP " + res.status);
    hosts = (await res.json()).hosts || [];
  } catch (err) {
    stop("links-unavailable", { detail: String(err?.message ?? err) });
  }
  if (!hosts.length) stop("links-unavailable", { detail: "the app named no address" });
}

// A plugin the iPhone build cannot use is named before Xcode starts.
if (platforms.includes("ios")) {
  const problems = iosPluginProblems(root);
  if (problems.tooOld.length) stop("ios-plugin-unsupported", { plugins: problems.tooOld });
  if (problems.leftOut.length) {
    console.log("EB44 " + JSON.stringify({ kind: "ios-plugins-left-out", plugins: problems.leftOut }));
    console.log("::warning::Left out of the iPhone app (no Swift package): " + problems.leftOut.join(", ") + ". Their calls fail on iPhone; see MOBILE.md.");
  }
}

for (const p of platforms) {
  if (!existsSync(p)) run("npx cap add " + p);
}
// A plugin that needs a newer iOS or Android than the template's raises the
// app's own minimum (before the sync, which carries it into the iPhone app's
// Swift package).
const raised = raiseMinimums(root, platforms);
if (raised.ios || raised.android) console.log("EB44 " + JSON.stringify({ kind: "platform-minimums", ios: raised.ios, android: raised.android }));
run("npx cap sync " + (want ?? ""));
// The settings that live in the bundled config (mobile/after-copy.mjs does
// the same after a sync run by hand).
applyBundledConfig(root, settings, ads, platforms);

// App icon: build the native icon set from the app's LIVE favicon — the
// deployed site is the source of truth (the repo's index.html can carry a
// stale icon href from before migration edits). Without this the app
// ships with Capacitor's placeholder icon. Best-effort: no usable favicon
// (or an svg one, which the assets tool can't rasterize from a .png name)
// keeps the placeholder, and dropping a 1024px assets/logo.png wins over
// everything. The splash is the same logo on the splash colour, or the
// app's own splash image (mobile/native.json).
try {
  if (!existsSync("assets/logo.png")) {
    const appUrl = JSON.parse(readFileSync("capacitor.config.json", "utf-8")).server?.url;
    if (appUrl) {
      const html = await (await fetch(appUrl)).text();
      const m = html.match(/rel="icon"[^>]*href="([^"]+)"/) ?? html.match(/href="([^"]+)"[^>]*rel="icon"/);
      const iconUrl = m ? new URL(m[1], appUrl).toString() : null;
      if (iconUrl && !iconUrl.endsWith(".svg")) {
        const res = await fetch(iconUrl);
        if (res.ok) {
          mkdirSync("assets", { recursive: true });
          writeFileSync("assets/logo.png", Buffer.from(await res.arrayBuffer()));
          console.log("App icon source:", iconUrl);
        }
      } else {
        console.log("No usable favicon on the live site (" + (iconUrl ?? "none found") + ").");
      }
    }
  }
  const target = want ? "--" + want : "--ios --android";
  const flags = assetsFlags(settings);
  if (settings.splash?.image !== undefined) {
    // The tool makes the icons and the splash from one logo, so the splash's
    // own image (or none: a transparent one) is a pass of its own, first; its
    // splash files are kept and put back after the icons' pass. (The tool
    // takes an asset folder relative to the project — node_modules is never
    // committed.)
    const dir = "node_modules/.eb44-splash";
    rmSync(dir, { recursive: true, force: true });
    mkdirSync(dir, { recursive: true });
    if (settings.splash.image === false) writeFileSync(dir + "/logo.png", transparentPng(1024));
    else cpSync(settings.splash.image, dir + "/logo.png");
    run("npx --yes @capacitor/assets generate " + target + " --assetPath " + dir + " " + flags);
    const kept = splashFiles().map((file) => [file, readFileSync(file)]);
    if (existsSync("assets/logo.png")) run("npx --yes @capacitor/assets generate " + target + " " + flags);
    for (const [file, bytes] of kept) writeFileSync(file, bytes);
    rmSync(dir, { recursive: true, force: true });
  } else if (existsSync("assets/logo.png")) {
    run("npx --yes @capacitor/assets generate " + target + " " + flags);
  } else {
    console.log("Keeping the default app icon — drop a 1024px assets/logo.png and rerun to change it.");
  }
} catch (err) {
  console.log("Icon generation skipped:", err?.message ?? err);
}
// The assets tool's splash images replace the template's in Contents.json
// but leave the template's files in the set — unassigned children, an Xcode
// warning on every build.
if (platforms.includes("ios")) pruneImageSet(root + "/ios/App/App/Assets.xcassets/Splash.imageset");

// Every splash file the assets tool writes, for the platforms built here.
function splashFiles() {
  const out = [];
  const set = "ios/App/App/Assets.xcassets/Splash.imageset";
  if (platforms.includes("ios") && existsSync(set)) for (const name of readdirSync(set)) out.push(set + "/" + name);
  const res = "android/app/src/main/res";
  if (platforms.includes("android") && existsSync(res)) {
    for (const name of readdirSync(res)) if (name.startsWith("drawable") && existsSync(res + "/" + name + "/splash.png")) out.push(res + "/" + name + "/splash.png");
  }
  return out;
}

const adsMode = (appId) => (!ads.installed ? "none" : appId ? "admob" : "webview");
if (platforms.includes("ios")) {
  patchIos(root, settings, { hosts, ads });
  setIosAppTarget(root, iosIdentity(root, process.env));
  const entitlements = plistObject(readFileSync("ios/App/App/App.entitlements", "utf-8"));
  console.log("EB44 " + JSON.stringify({ kind: "ios-settings", entitlements: Object.keys(entitlements), links: hosts, ads: adsMode(ads.iosAppId) }));
}
if (platforms.includes("android")) {
  const identity = androidIdentity(root, process.env);
  // Push is set up when the Firebase key is here (the workflow passes it in
  // from the repo's secrets; on your own machine, export it yourself).
  let firebase = null;
  if (process.env.FCM_SERVICE_ACCOUNT_JSON_B64) {
    const appName = JSON.parse(readFileSync("capacitor.config.json", "utf-8")).appName || identity.packageName;
    try {
      firebase = await androidFirebaseConfig(Buffer.from(process.env.FCM_SERVICE_ACCOUNT_JSON_B64, "base64").toString("utf-8"), identity.packageName, appName);
    } catch (err) {
      if (!(err instanceof FirebaseStop)) throw err;
      stop(err.code, err.extra);
    }
    console.log("EB44 " + JSON.stringify({ kind: "firebase-config", projectId: firebase.projectId, appId: firebase.appId, packageName: identity.packageName, registered: firebase.registered }));
  }
  patchAndroid(root, identity, firebase ? firebase.config : null, capabilities, settings, { hosts, ads });
  console.log("EB44 " + JSON.stringify({
    kind: "android-identity",
    packageName: identity.packageName,
    versionCode: identity.versionCode,
    versionName: identity.versionName,
    push: Boolean(firebase),
    location: capabilities.location,
    camera: capabilities.camera,
    microphone: capabilities.microphone,
    permissions: (settings.android || {}).permissions || [],
    links: hosts,
    ads: adsMode(ads.androidAppId),
  }));
}

console.log("\nDone. Next: npm run mobile:ios (Mac) or npm run mobile:android — or build from your EscapeBase44 success page (no Mac needed). See MOBILE.md.");
