#!/usr/bin/env node
// Run by Capacitor after every copy of the web app into a native project
// (package.json's "capacitor:copy:after" script): the app's own native
// settings that live in the bundled config — the splash colour, the status
// bar, the ads mode (mobile/native.json, MOBILE.md) — written back into the
// copy Capacitor just made, so a sync run by hand keeps them. mobile/setup.mjs
// does the same after its own sync.
import { existsSync } from "node:fs";
import { readNativeSettings, adsContext, applyBundledConfig, detectCapabilities } from "./native-patches.mjs";

const root = process.env.CAPACITOR_ROOT_DIR || process.cwd();
const platform = process.env.CAPACITOR_PLATFORM_NAME;
if (platform === "ios" || platform === "android") {
  const dist = process.env.CAPACITOR_WEB_DIR || root + "/dist";
  const capabilities = existsSync(dist) ? detectCapabilities(dist) : { webAds: false };
  applyBundledConfig(root, readNativeSettings(root), adsContext(root, process.env, capabilities), [platform]);
}
