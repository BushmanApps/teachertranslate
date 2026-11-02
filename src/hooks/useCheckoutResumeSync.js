import { useEffect, useRef } from "react";
import { base44 } from "@/api/base44Client";
import { toast } from "@/components/ui/use-toast";

const PENDING_KEY = "tt_checkout_pending";

/**
 * Refreshes subscription status when the app returns to the foreground
 * after a native subscription purchase in the external browser.
 *
 * Before opening native purchase, PaywallModal sets a sessionStorage flag. When
 * the app resumes (Capacitor appStateChange, visibilitychange, or
 * pageshow), this hook polls checkSubscription a few times — the native purchase
 * webhook can take a few seconds to fire — then refreshes user data and
 * shows a "Welcome to Pro" toast when the subscription is detected.
 */
export function useCheckoutResumeSync({ refreshUserData, isSubscribed, closeModal }) {
  const refreshingRef = useRef(false);
  const isSubscribedRef = useRef(isSubscribed);
  isSubscribedRef.current = isSubscribed;
  const refreshRef = useRef(refreshUserData);
  refreshRef.current = refreshUserData;
  const closeModalRef = useRef(closeModal);
  closeModalRef.current = closeModal;

  useEffect(() => {
    const pollSubscription = async () => {
      if (refreshingRef.current) return;

      let pending = false;
      try { pending = sessionStorage.getItem(PENDING_KEY) === "1"; } catch {}
      if (!pending) return;

      // Already Pro by the time we resume — just clean up
      if (isSubscribedRef.current) {
        try { sessionStorage.removeItem(PENDING_KEY); } catch {}
        return;
      }

      refreshingRef.current = true;
      try {
        let detected = false;
        // Poll up to 6 times (~15s): the webhook may lag a few seconds
        for (let i = 0; i < 6 && !detected; i++) {
          if (i > 0) await new Promise((r) => setTimeout(r, 2500));
          try {
            const res = await base44.functions.invoke("checkSubscription", { native: Boolean(window.eb44?.isMobileApp?.()) });
            if (res?.data?.is_subscribed) detected = true;
          } catch (e) {
            console.error("Resume sync check failed:", e);
          }
        }

        await refreshRef.current?.();
        try { sessionStorage.removeItem(PENDING_KEY); } catch {}

        if (detected) {
          toast({
            title: "Welcome to Pro! ✨",
            description: "Your subscription is now active.",
          });
          closeModalRef.current?.();
        }
      } finally {
        refreshingRef.current = false;
      }
    };

    const onResume = () => setTimeout(pollSubscription, 500);

    // Capacitor appStateChange — the primary resume signal in the native app
    let capCleanup = null;
    try {
      if (window.Capacitor?.Plugins?.App?.addListener) {
        window.Capacitor.Plugins.App.addListener("appStateChange", ({ isActive }) => {
          if (isActive) onResume();
        }).then((l) => { capCleanup = () => l?.remove?.(); }).catch(() => {});
      }
    } catch {}

    // Web fallbacks
    const onVisibility = () => {
      if (document.visibilityState === "visible") onResume();
    };
    const onPageShow = () => onResume();
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pageshow", onPageShow);

    return () => {
      capCleanup?.();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pageshow", onPageShow);
    };
  }, []);
}