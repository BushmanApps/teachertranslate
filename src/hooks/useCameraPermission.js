import { useState, useEffect, useCallback } from "react";

// Tracks the camera permission state and exposes a `request()` that triggers
// the native permission prompt via getUserMedia.
// State values: "granted" | "denied" | "prompt" | "unknown"
export function useCameraPermission() {
  const [permission, setPermission] = useState("unknown");

  // Read the current state without prompting (Permissions API).
  useEffect(() => {
    let status;
    const setup = async () => {
      try {
        if (!navigator.permissions?.query) return;
        status = await navigator.permissions.query({ name: "camera" });
        setPermission(status.state);
        status.onchange = () => setPermission(status.state);
      } catch {
        // Permissions API unsupported — leave as "unknown".
      }
    };
    setup();
    return () => {
      if (status) status.onchange = null;
    };
  }, []);

  // Triggers the permission prompt. Returns true only if granted.
  const request = useCallback(async () => {
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        setPermission("denied");
        return false;
      }
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      stream.getTracks().forEach((t) => t.stop());
      setPermission("granted");
      return true;
    } catch (e) {
      setPermission("denied");
      return false;
    }
  }, []);

  return { permission, request };
}