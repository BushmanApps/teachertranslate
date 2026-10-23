// Session-persisted flag so Home and the Onboarding page agree on whether
// the initialisation flow has been shown this login session. Stored in
// sessionStorage so it survives full page loads (e.g. visiting the Privacy
// or Terms pages from settings and pressing back) but still resets when the
// session ends or the user logs out.
const KEY = "tt_setup_shown";

export function isSetupShown() {
  try { return sessionStorage.getItem(KEY) === "1"; } catch { return false; }
}

export function markSetupShown() {
  try { sessionStorage.setItem(KEY, "1"); } catch {}
}

export function clearSetupShown() {
  try { sessionStorage.removeItem(KEY); } catch {}
}