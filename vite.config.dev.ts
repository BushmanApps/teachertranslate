// Dev-only Vite config. Used by `npm run dev` (which passes
// `--config vite.config.dev.ts`). Production builds (`vite build`) use the
// plain `vite.config.ts`, which this file wraps via `mergeConfig`.
//
// This file is committed to the repo and you own it — edit freely. The
// same `npm run dev` boots in the EscapeBase44 vibecoder sandbox and on
// your laptop; nothing in here is sandbox-specific. The only difference
// between the two environments is the `BASE_URL` value in `.env.local`
// (E2B preview URL in the sandbox; `http://localhost:5173` locally).

import { defineConfig, mergeConfig, type Plugin } from "vite";
import baseConfig from "./vite.config";

const PREVIEW_PORT = parseInt(process.env.PREVIEW_PORT ?? "5173", 10);
// When a local backend isn't available (e.g. the Bolt preview sandbox, which
// has no uv/deno/MongoDB), EB44_BACKEND_PROXY points the /api proxy at the
// live backend instead so login and data still work. Defaults to the local
// backend for normal laptop dev.
const BACKEND = process.env.EB44_BACKEND_PROXY ?? "http://localhost:8000";

// Reads a preview JWT from a URL fragment (`#preview-token=…`), scrubs the
// fragment from the URL bar (so it doesn't leak via bookmarks / history),
// then wraps `window.fetch` + `XMLHttpRequest` to attach
// `Authorization: Bearer <token>` to every same-origin `/api/...` request.
//
// This script is harmless in any environment. It early-returns when there's
// no fragment, which is the case for local dev (you do real Google /
// email-password login in a normal browser tab). The vibecoder sandbox uses
// the fragment to skip the Google consent screen — Google refuses to render
// inside iframes, so the parent vibecoder mints an `app_user` JWT signed
// with the deployed `APP_JWT_SECRET` and feeds it in via the fragment.
const PREVIEW_AUTH_INJECT_SCRIPT = `(function () {
  var match = window.location.hash.match(/(?:^|[#&])preview-token=([^&]+)/);
  if (!match) return;
  var token = decodeURIComponent(match[1]);
  // Strip the fragment so it doesn't leak into bookmarks or history.
  history.replaceState(null, '', window.location.pathname + window.location.search);

  var ORIG_FETCH = window.fetch.bind(window);
  window.fetch = function (input, init) {
    init = init || {};
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    if (url.indexOf('/api/') === 0 || url.indexOf(window.location.origin + '/api/') === 0) {
      var headers = new Headers(init.headers || (typeof input !== 'string' && input.headers) || undefined);
      if (!headers.has('Authorization')) {
        headers.set('Authorization', 'Bearer ' + token);
      }
      init.headers = headers;
    }
    return ORIG_FETCH(input, init);
  };

  // Also patch XMLHttpRequest in case the SDK or its deps use it.
  var ORIG_OPEN = XMLHttpRequest.prototype.open;
  var ORIG_SEND = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__previewUrl = url;
    return ORIG_OPEN.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (body) {
    var u = this.__previewUrl || '';
    if (typeof u === 'string' && (u.indexOf('/api/') === 0 || u.indexOf(window.location.origin + '/api/') === 0)) {
      try { this.setRequestHeader('Authorization', 'Bearer ' + token); } catch (e) {}
    }
    return ORIG_SEND.apply(this, arguments);
  };
})();`;

const previewAuthInjectPlugin: Plugin = {
  name: "escapebase44-preview-auth-inject",
  transformIndexHtml: {
    order: "pre",
    handler(html: string) {
      // Inject as the very first thing in <head> so the fetch/XHR wrappers
      // are installed before any of the user's app code runs.
      return html.replace(
        /<head([^>]*)>/i,
        `<head$1><script>${PREVIEW_AUTH_INJECT_SCRIPT}</script>`,
      );
    },
  },
};

// PostHog session-recording bridge for the vibecoder sandbox. Conditional
// on the POSTHOG_KEY env var — only the vibecoder sets it; local dev runs
// without it and this plugin is a no-op. With `recordCrossOriginIframes`
// set both here and in the parent, the iframe's posthog-js relays rrweb
// events up via postMessage so the sandbox preview shows up inside the
// parent's session recording.
const POSTHOG_KEY = process.env.POSTHOG_KEY ?? "";
const POSTHOG_HOST = process.env.POSTHOG_HOST ?? "https://us.i.posthog.com";

const POSTHOG_INJECT_SCRIPT = `(function () {
  if (!${JSON.stringify(POSTHOG_KEY)}) return;
  !function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossorigin="anonymous",p.async=!0,p.src=s.api_host+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="capture identify alias people.set people.set_once set_config register register_once unregister opt_out_capturing has_opted_out_capturing opt_in_capturing reset isFeatureEnabled onFeatureFlags getFeatureFlag getFeatureFlagPayload reloadFeatureFlags group updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures getActiveMatchingSurveys getSurveys getNextSurveyStep onSessionId".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);
  window.posthog.init(${JSON.stringify(POSTHOG_KEY)}, {
    api_host: ${JSON.stringify(POSTHOG_HOST)},
    capture_pageview: false,
    capture_pageleave: false,
    autocapture: false,
    person_profiles: 'identified_only',
    session_recording: {
      recordCrossOriginIframes: true,
    },
  });
})();`;

const posthogInjectPlugin: Plugin = {
  name: "escapebase44-posthog-inject",
  transformIndexHtml: {
    order: "pre",
    handler(html: string) {
      if (!POSTHOG_KEY) return html;
      return html.replace(
        /<head([^>]*)>/i,
        `<head$1><script>${POSTHOG_INJECT_SCRIPT}</script>`,
      );
    },
  },
};

export default mergeConfig(baseConfig, defineConfig({
  plugins: [previewAuthInjectPlugin, posthogInjectPlugin],
  server: {
    host: "0.0.0.0",
    port: PREVIEW_PORT,
    strictPort: true,
    // Vite v6+ blocks requests whose Host header isn't in this list (DNS
    // rebinding defense). `localhost` covers local dev; `.e2b.app` covers
    // the vibecoder sandbox's E2B preview subdomain. If you front the
    // dev server with a custom domain, add it here too.
    allowedHosts: ["localhost", "127.0.0.1", ".e2b.app"],
    proxy: {
      // Backend handles all API surfaces, including /api/apps/{id}/functions
      // (SDK invoke), /api/functions (SDK fetch), and /functions (non-SDK
      // alias). Function calls are forwarded from the backend to the local
      // supervisor via the `ESCAPEBASE44_DEV_FUNCTIONS_BASE_URL` env hook
      // (set in .env.local).
      //
      // `xfwd` hands the backend the address the browser actually used
      // (X-Forwarded-Host), so everything it derives from its arrival
      // address — a password-reset link, a login redirect, the socket
      // address of a realtime room — names this dev server, never
      // localhost:8000. The scheme comes from BASE_URL in .env.local (the
      // proxy only sees its own plain-http leg).
      "/api": { target: BACKEND, changeOrigin: true, xfwd: true },
      "/ws": { target: BACKEND.replace(/^http/, "ws"), ws: true, xfwd: true },
      "/health": { target: BACKEND, changeOrigin: true, xfwd: true },
      "/functions": { target: BACKEND, changeOrigin: true, xfwd: true },
      // The WebSockets of the app's realtime rooms (Base44 Actors). In local
      // dev these go to the actors host the dev script starts (localhost:8004).
      // In the preview sandbox that host isn't running, so fall back to the
      // live backend when EB44_BACKEND_PROXY is set.
      "/parties": { target: (process.env.EB44_BACKEND_PROXY ?? "ws://localhost:8004").replace(/^http/, "ws"), ws: true },
    },
  },
}));
