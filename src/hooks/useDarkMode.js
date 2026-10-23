import { createContext, useContext, useState, useCallback, useEffect, createElement } from "react";

const STORAGE_KEY = "tt_dark_mode";

const DarkModeContext = createContext({ darkMode: false, toggleDarkMode: () => {} });

function getSystemDark() {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  } catch { return false; }
}

function getStored() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null) return stored === "true";
  } catch {}
  return null;
}

export function DarkModeProvider({ children }) {
  const [darkMode, setDarkMode] = useState(() => {
    const stored = getStored();
    return stored !== null ? stored : getSystemDark();
  });

  // React to live system theme changes when the user hasn't set a manual preference
  useEffect(() => {
    let mql;
    try { mql = window.matchMedia('(prefers-color-scheme: dark)'); } catch { return; }
    const handler = (e) => {
      if (getStored() === null) setDarkMode(e.matches);
    };
    mql.addEventListener?.("change", handler);
    return () => mql.removeEventListener?.("change", handler);
  }, []);

  // Apply the dark theme class directly on <html> so every page — including
  // public routes (Landing, Support, Terms, Privacy, Feedback) — inherits the
  // dark palette via CSS variables, instead of per-component wrappers.
  useEffect(() => {
    document.documentElement.classList.toggle("dark-honest", darkMode);
  }, [darkMode]);

  const toggleDarkMode = useCallback((val) => {
    setDarkMode((prev) => {
      const next = typeof val === "boolean" ? val : !prev;
      try { localStorage.setItem(STORAGE_KEY, String(next)); } catch {}
      return next;
    });
  }, []);

  return createElement(
    DarkModeContext.Provider,
    { value: { darkMode, toggleDarkMode } },
    children
  );
}

export function useDarkMode() {
  return useContext(DarkModeContext);
}