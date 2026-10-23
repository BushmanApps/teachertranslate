import { useState, useEffect } from "react";
import { Drawer, DrawerContent } from "@/components/ui/drawer";

function readDarkMode() {
  try {
    const stored = localStorage.getItem("tt_dark_mode");
    if (stored !== null) return stored === "true";
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  } catch {
    return false;
  }
}

/**
 * Bottom-sheet drawer for mobile. Applies the app's theme class
 * (brutal-mode / dark-honest) directly to the portal content so
 * CSS variables and class overrides work correctly outside the
 * main app container.
 */
export default function MobileActionSheet({ isOpen, onClose, isBrutal, darkMode: darkModeProp, children, className }) {
  const [localDarkMode, setLocalDarkMode] = useState(readDarkMode);

  // Re-read dark mode each time the sheet opens to catch toggle changes
  useEffect(() => {
    if (isOpen) setLocalDarkMode(readDarkMode());
  }, [isOpen]);

  const darkMode = darkModeProp !== undefined ? darkModeProp : localDarkMode;
  const themeClass = isBrutal ? "brutal-mode" : darkMode ? "dark-honest" : "";

  return (
    <Drawer open={isOpen} onOpenChange={(open) => !open && onClose()} shouldScaleBackground={false}>
      <DrawerContent className={`${themeClass} text-foreground rounded-t-3xl ${className || ""}`}>
        <div
          className="px-4 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-2 overflow-y-auto max-h-[92dvh]"
          style={{ overscrollBehavior: "contain" }}>
          {children}
        </div>
      </DrawerContent>
    </Drawer>
  );
}