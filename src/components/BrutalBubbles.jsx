import { useMemo, useState, useEffect } from "react";

const EMOJIS = ["💀", "🔥", "💥", "⚡", "😈", "🖤", "💢", "⚠️", "🤬", "😤", "🩸", "☠️"];

const makeBubbles = () => Array.from({ length: 28 }, (_, i) => ({
  id: i,
  emoji: EMOJIS[i % EMOJIS.length],
  left: Math.round(Math.random() * 92),
  top: Math.round(Math.random() * 90),
  size: 22 + Math.round(Math.random() * 30),
  duration: 6 + Math.random() * 12,
  delay: Math.random() * 4,
  rotate: Math.round(Math.random() * 40 - 20),
}));

export default function BrutalBubbles({ headerRef }) {
  const bubbles = useMemo(() => makeBubbles(), []);
  const [top, setTop] = useState(0);

  useEffect(() => {
    const measure = () => {
      if (headerRef?.current) {
        const rect = headerRef.current.getBoundingClientRect();
        setTop(rect.bottom);
      }
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (headerRef?.current) ro.observe(headerRef.current);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, { passive: true });
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure);
    };
  }, [headerRef]);

  return (
    <div className="fixed inset-x-0 bottom-0 pointer-events-none overflow-hidden -z-10" style={{ top }} aria-hidden="true">
      {bubbles.map((b) => (
        <span
          key={b.id}
          className="absolute select-none"
          style={{
            left: `${b.left}%`, top: `${b.top}%`, fontSize: `${b.size}px`, opacity: 0.6,
            "--r": `${b.rotate}deg`,
            animation: `emoji-jiggle 1s ease-in-out ${-b.delay}s infinite`
          }}
        >
          {b.emoji}
        </span>
      ))}
    </div>
  );
}