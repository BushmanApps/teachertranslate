import { useEffect } from "react";

/**
 * Dynamically updates <meta name="theme-color"> to match the active theme,
 * so native iOS/Android status bars blend with the app in WebView wrappers.
 */
export function useThemeColor({ isBrutal = false, isHilarious = false, isDark = false } = {}) {
  useEffect(() => {
    let meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.setAttribute("name", "theme-color");
      document.head.appendChild(meta);
    }
    const color = isBrutal ? "#09090b" : isDark ? (isHilarious ? "#1a0e16" : "#14181f") : isHilarious ? "#fce7f3" : "#fde8cb";
    meta.setAttribute("content", color);
  }, [isBrutal, isHilarious, isDark]);
}