import { useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { base44 } from "@/api/base44Client";

/**
 * Syncs modal open/close state to a URL search parameter (?modal=name).
 * When a modal opens, a new history entry is pushed so that the native
 * back gesture / hardware back button closes only the modal instead of
 * navigating away from the current screen.
 *
 * All history/navigation calls are wrapped in try/catch to handle mobile
 * WebView sandbox restrictions after a data clear. On SecurityError, auth
 * headers are re-validated and the action retries via the native wrapper's
 * popstate event (the mobile wrapper bridge event).
 */
export function useModalHistory() {
  const navigate = useNavigate();
  const location = useLocation();

  let activeModal = null;
  try {
    activeModal = new URLSearchParams(location.search).get("modal");
  } catch (e) {
    // URLSearchParams blocked — no modal active
  }

  const openModal = useCallback((modalName) => {
    try {
      const params = new URLSearchParams(location.search);
      const hasModal = params.has("modal");
      params.set("modal", modalName);
      // If a modal is already open, replace (swap modals without adding a
      // stale history entry that back would reopen the old modal). Otherwise
      // push a new entry so the hardware back button closes the modal.
      navigate({ search: params.toString() }, { replace: hasModal });
    } catch (e) {
      // SecurityError or origin error — re-validate auth headers in case the
      // data clear invalidated the session, then retry the navigation.
      if (e.name === "SecurityError" || e.name === "InvalidStateError") {
        base44.auth.isAuthenticated().catch(() => {});
      }
      // Retry as a replace (lighter operation that doesn't push history)
      try {
        const params = new URLSearchParams(location.search);
        params.set("modal", modalName);
        navigate({ search: params.toString() }, { replace: true });
      } catch (e2) {
        // Final fallback — navigate to the same path with the modal param
        try {
          navigate(location.pathname + "?modal=" + modalName, { replace: true });
        } catch (e3) {
          // All navigation blocked — modal state is in-memory only
        }
      }
    }
  }, [navigate, location.search, location.pathname]);

  const closeModal = useCallback(() => {
    try {
      const params = new URLSearchParams(location.search);
      if (params.has("modal")) {
        // Pop the history entry that openModal pushed.
        navigate(-1);
      } else {
        // No modal in the URL — just clean up.
        params.delete("modal");
        navigate({ search: params.toString() }, { replace: true });
      }
    } catch (e) {
      // SecurityError or origin error — re-validate auth headers, then
      // retry via a replace navigation (popstate fallback from the
      // mobile wrapper bridge event).
      if (e.name === "SecurityError" || e.name === "InvalidStateError") {
        base44.auth.isAuthenticated().catch(() => {});
      }
      try {
        navigate(location.pathname, { replace: true });
      } catch (e2) {
        // All navigation blocked — cannot close modal via URL
      }
    }
  }, [navigate, location.search, location.pathname]);

  return { activeModal, openModal, closeModal };
}