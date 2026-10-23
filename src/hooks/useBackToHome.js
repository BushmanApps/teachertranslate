import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { safeSetSession, safePushState, safeAddPopState } from "@/lib/safeWebApi";

/**
 * Makes the Android back gesture / hardware back button navigate back
 * instead of exiting the app wrapper.
 *
 * For normal navigation (the user arrived from another screen, so there IS
 * prior history), the browser's native back already works — we leave it
 * alone. Only when the screen was opened directly (deep-link, new view,
 * no prior history) do we push a sentinel entry so the back gesture has
 * something to pop, redirecting to the fallback instead of closing the app.
 *
 * We use the router's history index (state.idx), NOT window.history.length:
 * in native WebViews the wrapper's own redirect chain inflates history
 * length even when there is no app entry to pop back to.
 *
 * All browser API calls are wrapped in try/catch to handle mobile WebView
 * sandbox restrictions after a data clear. If pushState is blocked by a
 * SecurityError, we fall back to popstate-only handling — the native
 * wrapper still generates popstate events from the hardware back button.
 */
export function useBackToHome(fallbackPath = "/") {
  const navigate = useNavigate();

  useEffect(() => {
    // Mark session flags (safe — won't throw if storage is blocked)
    safeSetSession("ttWelcomeShown", "1");
    safeSetSession("ttBackToApp", "1");

    // Native back already works when the router itself pushed previous entries.
    try {
      const idx = window.history.state?.idx;
      if (typeof idx === "number" && idx > 0) return;
    } catch (e) {
      // history.state access blocked — proceed with sentinel push
    }

    // Push a sentinel entry. In sandboxed WebViews this can throw a
    // SecurityError after a data clear; safePushState re-validates auth
    // headers on such errors and we fall back to popstate-only handling.
    const pushed = safePushState({ tt_back_home: true });

    const handlePopState = () => {
      // Return the user to the tab they were last on, if we saved one.
      let target = fallbackPath;
      try {
        const savedTab = sessionStorage.getItem("tt_active_tab");
        if (savedTab) target = `${fallbackPath}?tab=${savedTab}`;
      } catch (e) {
        // sessionStorage blocked — fall back to the plain path
      }
      try {
        navigate(target, { replace: true });
      } catch (e) {
        // Navigation blocked — force a page reload to the fallback
        window.location.href = target;
      }
    };

    // Register popstate listener (the native wrapper bridge event).
    // This fires from hardware back button presses regardless of whether
    // pushState succeeded.
    const cleanup = safeAddPopState(handlePopState);

    return cleanup;
  }, [navigate, fallbackPath]);
}