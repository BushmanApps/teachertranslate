import { base44 } from "@/api/base44Client";

/**
 * Safe wrappers for browser history and storage APIs that can throw
 * SecurityError or InvalidStateError in mobile WebViews after a data clear
 * (cross-origin sandbox restrictions, wiped storage).
 *
 * On security/origin errors, we re-validate auth headers and fall back to
 * popstate-only handling — the native wrapper translates hardware back
 * button presses into popstate events regardless of pushState state.
 */

/**
 * Wraps sessionStorage.setItem in a try/catch. Storage can throw
 * SecurityError in sandboxed iframes after a data clear.
 */
export function safeSetSession(key, value) {
  try {
    sessionStorage.setItem(key, value);
  } catch (e) {
    // Storage blocked — non-critical, continue
  }
}

/**
 * Wraps sessionStorage.getItem in a try/catch.
 */
export function safeGetSession(key) {
  try {
    return sessionStorage.getItem(key);
  } catch (e) {
    return null;
  }
}

/**
 * Wraps localStorage.setItem in a try/catch.
 */
export function safeSetLocal(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (e) {
    // Storage blocked — non-critical, continue
  }
}

/**
 * Attempts window.history.pushState. Returns true on success, false if a
 * SecurityError or origin error was thrown. On such errors, re-validates
 * auth headers so the session is refreshed after a data clear.
 */
export function safePushState(state, url = "") {
  try {
    window.history.pushState(state, "", url);
    return true;
  } catch (e) {
    if (e.name === "SecurityError" || e.name === "InvalidStateError") {
      // Cross-origin or sandbox restriction — re-validate auth headers
      // in case the data clear invalidated the session token.
      base44.auth.isAuthenticated().catch(() => {});
    }
    return false;
  }
}

/**
 * Re-pushes the global back-button sentinel history entry.
 *
 * The native file/camera chooser Intent consumes the sentinel entry on
 * return, leaving the WebView with canGoBack()===false so the native
 * wrapper stops dispatching back-button events to JS. Re-pushing the
 * sentinel restores canGoBack() so subsequent back presses reach the
 * app again. Safe to call repeatedly — a duplicate sentinel is harmless.
 *
 * Returns true on success, false if pushState is blocked (sandbox).
 */
export function rePushSentinel() {
  return safePushState({ tt_global_sentinel: true });
}

/**
 * Registers a popstate listener safely. In sandboxed WebViews where
 * pushState is blocked, the native wrapper still generates popstate
 * events from hardware back button presses — this is the "mobile wrapper
 * bridge event" we rely on as the fallback.
 */
export function safeAddPopState(handler) {
  try {
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  } catch (e) {
    // If addEventListener itself is blocked, return a no-op cleanup
    return () => {};
  }
}