/**
 * Shared mode state — accessible from the global back-button interceptor
 * (App.jsx) and the Home component. Replaces the module-level _cachedMode
 * that was previously inside Home.jsx so the interceptor can read the
 * current translation mode without a direct reference to Home's state.
 */
let _mode = "honest_helpful";

export function getGlobalMode() {
  return _mode;
}

export function setGlobalMode(mode) {
  _mode = mode;
}