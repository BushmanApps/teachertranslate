import { useRef } from "react";

/**
 * Detects deliberate horizontal swipes (left/right) so the user can swipe
 * between translation modes. Vertical scrolling and small drags are ignored.
 */
export function useModeSwipe(onSwipeLeft, onSwipeRight) {
  const touchStart = useRef(null);

  const onTouchStart = (e) => {
    if (e.touches.length !== 1) {
      touchStart.current = null;
      return;
    }
    touchStart.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
  };

  const onTouchEnd = (e) => {
    if (!touchStart.current || e.changedTouches.length !== 1) return;
    const dx = e.changedTouches[0].clientX - touchStart.current.x;
    const dy = e.changedTouches[0].clientY - touchStart.current.y;
    touchStart.current = null;
    // Only treat it as a swipe when the gesture is clearly horizontal.
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      if (dx < 0) onSwipeLeft();
      else onSwipeRight();
    }
  };

  return { onTouchStart, onTouchEnd };
}