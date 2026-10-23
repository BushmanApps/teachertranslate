import { useState, useEffect } from "react";

/**
 * True when the page has meaningfully more content than fits the viewport
 * (e.g. a full translation result), so UI can collapse to save space.
 */
export default function useContentOverflow(factor = 1.25) {
  const [overflowing, setOverflowing] = useState(false);

  useEffect(() => {
    const check = () => {
      const docH = document.documentElement.scrollHeight;
      setOverflowing(docH > window.innerHeight * factor);
    };
    check();
    window.addEventListener("resize", check);
    window.addEventListener("scroll", check, { passive: true });
    const ro = new ResizeObserver(check);
    ro.observe(document.body);
    return () => {
      window.removeEventListener("resize", check);
      window.removeEventListener("scroll", check);
      ro.disconnect();
    };
  }, [factor]);

  return overflowing;
}