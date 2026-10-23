import { useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { getGlobalMode } from "@/lib/globalBackState";
import { safePushState, rePushSentinel } from "@/lib/safeWebApi";

const HOME_PATHS = ["/", "/write-back"];

/**
 * Global hardware back-button interceptor mounted at the absolute
 * application-layout layer (App.jsx → AnimatedRoutes).
 *
 * PROBLEM: On a clean mobile boot the native WebView's canGoBack()
 * returns false (no history entries), so the hardware back button
 * exits the app or navigates to the system back stack instead of
 * firing a popstate event that React Router can react to. The React
 * Router history stack and the native wrapper's canGoBack check are
 * desynced.
 *
 * SOLUTION: Two layers —
 *  1. Sentinel entry: push a dummy history entry on mount so
 *     canGoBack() is always true — the first back press pops the
 *     sentinel and fires popstate, giving existing handlers a chance
 *     to run.
 *  2. Native event interceptor: listen explicitly for the native
 *     mobile wrapper's back-button event plugin (multiple event
 *     names cover different wrapper implementations). When caught,
 *     bypass the default native handling entirely (preventDefault +
 *     stopPropagation) and manually run the back-button order of
 *     operations:
 *       a. Close open modals (tracked via ?modal= URL param)
 *       b. Navigate back from secondary pages
 *       c. Switch non-translate tabs back to Translate
 *       d. Cycle non-Honest modes back to Honest
 *       e. Navigate back in history if entries exist
 */
export function useGlobalBackHandler() {
  const navigate = useNavigate();
  const location = useLocation();
  const locationRef = useRef(location);
  locationRef.current = location;
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;
  const handlingRef = useRef(false);

  useEffect(() => {
    // ── Sentinel entry ──────────────────────────────────────────────
    // Ensure canGoBack() returns true on a clean boot so the native
    // wrapper calls goBack() (firing popstate) instead of exiting.
    safePushState({ tt_global_sentinel: true });

    // ── Manual back-button order of operations ──────────────────────
    const runBackOrder = () => {
      // Debounce rapid presses — a single back press should only
      // trigger one action, even if multiple events fire. The flag is
      // cleared in a finally block so a thrown error mid-order can never
      // leave it stuck true (which would permanently disable the button).
      if (handlingRef.current) return;
      handlingRef.current = true;
      try {
        runBackOrderInner();
      } finally {
        setTimeout(() => { handlingRef.current = false; }, 350);
      }
    };

    const runBackOrderInner = () => {
      const loc = locationRef.current;
      const nav = navigateRef.current;

      let params;
      try { params = new URLSearchParams(loc.search); }
      catch { params = new URLSearchParams(); }

      const isHome = HOME_PATHS.includes(loc.pathname);

      // 1. Close open modals (tracked via ?modal= in the URL)
      if (params.has("modal")) {
        nav(-1);
        return;
      }

      // 2. Non-home pages → navigate back, or to Home if no history
      if (!isHome) {
        try {
          if (window.history.state?.idx > 0) {
            nav(-1);
          } else {
            nav("/", { replace: true });
          }
        } catch (e) {
          nav("/", { replace: true });
        }
        return;
      }

      // 3. Non-translate tab on Home → switch to translate tab
      const tab = params.get("tab");
      if (tab && tab !== "translate") {
        params.delete("tab");
        const search = params.toString();
        nav({ search: search || "" }, { replace: true });
        return;
      }

      // 4. Non-Honest mode → pop the mode pushState entry (the existing
      //    Home.jsx popstate handler will set the mode to honest_helpful).
      //    If no pushState entry exists (SecurityError on clean boot),
      //    dispatch a custom event that Home.jsx listens for.
      if (getGlobalMode() !== "honest_helpful") {
        try {
          if (window.history.state?.tt_mode) {
            nav(-1);
          } else {
            window.dispatchEvent(new CustomEvent("tt:back-to-honest"));
          }
        } catch (e) {
          window.dispatchEvent(new CustomEvent("tt:back-to-honest"));
        }
        return;
      }

      // 5. Nothing to handle → navigate back if there's history.
      //    If there's no history (idx 0) the sentinel was consumed by the
      //    last back press (or a native Intent return) — silently
      //    re-push it so the next back press keeps working, instead of
      //    leaving the button permanently disabled. No visible UI change.
      try {
        if (window.history.state?.idx > 0) {
          nav(-1);
        } else {
          rePushSentinel();
        }
      } catch (e) {
        rePushSentinel();
      }
    };

    // ── Native back-button event listeners ─────────────────────────
    // Listen for the native mobile wrapper's back-button event plugin.
    // Multiple event names cover different wrapper implementations:
    //   'backbutton'         — Cordova / Capacitor
    //   'nativebackbutton'   — custom Base44 wrapper
    //   'hardwarebackbutton' — some Android wrappers
    // When caught, bypass the default native handling entirely
    // (preventDefault + stopPropagation) and manually run the order
    // of operations.
    const nativeBackEvents = [
      "backbutton",
      "nativebackbutton",
      "hardwarebackbutton",
    ];

    // Registers one document back-button listener and returns its cleanup.
    const registerDocBackListener = (eventName) => {
      const handler = (e) => {
        if (e?.preventDefault) e.preventDefault();
        if (e?.stopPropagation) e.stopPropagation();
        runBackOrder();
      };
      document.addEventListener(eventName, handler, { capture: true });
      return () => document.removeEventListener(eventName, handler, { capture: true });
    };

    let docCleanups = nativeBackEvents.map(registerDocBackListener);

    // Registers the Capacitor App backButton plugin listener and returns
    // its cleanup (async). Returns a no-op if Capacitor isn't available.
    const registerCapacitorBackListener = () => {
      let cleanup = null;
      try {
        if (window.Capacitor?.Plugins?.App?.addListener) {
          window.Capacitor.Plugins.App.addListener("backButton", () => {
            runBackOrder();
          }).then((listener) => {
            cleanup = () => listener?.remove?.();
          }).catch(() => {});
        }
      } catch (e) {
        // Capacitor not available
      }
      return () => cleanup?.();
    };

    let capacitorCleanup = registerCapacitorBackListener();

    // ── Resume recovery ─────────────────────────────────────────────
    // When the native file/camera chooser Intent returns, it consumes
    // the sentinel history entry and can drop the native back-button
    // listeners. On app resume (foreground), re-push the sentinel AND
    // re-register the listeners so the back button keeps reaching the app.
    // Belt-and-braces with the UploadSection re-push: either path alone
    // restores the button, both together cover missed resume events.
    const onResume = () => {
      rePushSentinel();
      // Re-register listeners in case the Intent return dropped them.
      // Remove the old ones first to avoid duplicates.
      docCleanups.forEach((c) => c());
      docCleanups = nativeBackEvents.map(registerDocBackListener);
      capacitorCleanup();
      capacitorCleanup = registerCapacitorBackListener();
    };

    // Capacitor appStateChange (active) — the primary resume signal in
    // the native wrapper. Guarded so a missing plugin doesn't throw.
    let capacitorResumeCleanup = null;
    try {
      if (window.Capacitor?.Plugins?.App?.addListener) {
        window.Capacitor.Plugins.App.addListener("appStateChange", ({ isActive }) => {
          if (isActive) onResume();
        }).then((listener) => {
          capacitorResumeCleanup = () => listener?.remove?.();
        }).catch(() => {});
      }
    } catch (e) {
      // Capacitor not available
    }

    // Web fallbacks: visibilitychange / pageshow / resume cover browsers
    // and any wrapper that doesn't bridge appStateChange. Only fire on a
    // return to visible (not on backgrounding).
    const onVisibility = () => {
      if (document.visibilityState === "visible") onResume();
    };
    const onPageShow = () => onResume();
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pageshow", onPageShow);

    return () => {
      docCleanups.forEach((c) => c());
      capacitorCleanup();
      capacitorResumeCleanup?.();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pageshow", onPageShow);
    };
  }, []);
}