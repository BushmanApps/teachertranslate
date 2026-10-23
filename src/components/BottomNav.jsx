import { FileText, PenLine, Gift, ArrowUp } from "lucide-react";
import useContentOverflow from "@/hooks/useContentOverflow";

export default function BottomNav({ activeTab, onTabChange, onActiveTabPress, isBrutal, isSubscribed, darkMode, isHilarious }) {
  const tabs = [
    { id: "translate", label: "Translate", icon: FileText },
    { id: "teacher_talk", label: "Write Back", icon: PenLine, proOnly: true },
    { id: "bonus", label: "Bonus", icon: Gift, proOnly: true }
  ];

  const bgClass = isBrutal
    ? "bg-zinc-900/95 backdrop-blur-md border-t border-zinc-800"
    : "bg-[hsl(var(--primary))]";

  const boxShadow = !isBrutal
    ? {
        boxShadow: darkMode
          ? (isHilarious ? "0 -3px 0 hsl(330 30% 6%)" : "0 -3px 0 hsl(220 20% 6%)")
          : isHilarious ? "0 -3px 0 #d89bc0" : "0 -3px 0 #a0a0c8"
      }
    : {};

  // Once the page holds more content than the screen (e.g. a translation),
  // shrink to an icon-only pill in the bottom-right corner.
  const compact = useContentOverflow();

  // Only iOS reserves a home-gesture inset. Android WebViews report a
  // non-zero env(safe-area-inset-bottom) even when nothing is there, so the
  // inset is applied on iOS only.
  const isIOS = typeof navigator !== "undefined" && /iP(hone|ad|od)/.test(navigator.userAgent);
  const safeClass = isIOS ? "pb-safe" : "";

  const handlePress = (id) => {
    if (id === activeTab && onActiveTabPress) {
      onActiveTabPress(id);
    } else {
      onTabChange(id);
    }
  };

  if (compact) {
    const tabButtons = tabs.map(({ id, label, icon: Icon, proOnly }) => {
      const active = activeTab === id;
      const locked = proOnly && !isSubscribed;
      let cls = "relative flex items-center justify-center w-11 h-11 rounded-full transition-all select-none ";
      if (locked) {
        cls += isBrutal ? "opacity-50 text-white" : "opacity-30 text-primary-foreground";
      } else if (active) {
        cls += isBrutal ? "text-white bg-white/15" : "text-primary-foreground bg-black/15";
      } else {
        cls += isBrutal ? "text-white/50" : "text-primary-foreground/60";
      }
      return (
        <button key={id} onClick={() => handlePress(id)} className={cls} aria-label={label}>
          <Icon className="w-6 h-6" />
          {locked &&
            <span className="absolute top-0 right-0 text-[8px] font-bold bg-amber-400 text-amber-900 rounded-full px-1">
              PRO
            </span>
          }
        </button>
      );
    });

    return (
      <>
        {/* Mobile / tablet — bottom-right corner pill */}
        <div className={`fixed bottom-0 right-0 z-30 select-none pr-3 ${safeClass} xl:hidden`}>
          <div
            className={`flex items-center gap-1 rounded-t-2xl px-2 py-1.5 ${
              isBrutal ? "bg-zinc-900/95 backdrop-blur-md border-t border-x border-zinc-800" : "bg-[hsl(var(--primary))] shadow-lg"
            }`}>
            {tabButtons}
          </div>
        </div>

        {/* Desktop — sits at the bottom, in the gutter to the right of the
            translations (not overlapping); jump-to-top arrow is outside the
            tab card and stretched to the card's height so edges align */}
        <div className={`hidden xl:flex fixed bottom-0 left-0 right-0 z-30 select-none ${safeClass} pointer-events-none`}>
          <div className="relative w-full max-w-5xl mx-auto px-4">
            <div className="absolute bottom-0 left-full ml-6 flex items-stretch gap-3 pb-3 pointer-events-auto">
              <div
                className={`flex items-center gap-1 rounded-2xl px-2 py-1.5 ${
                  isBrutal ? "bg-zinc-900/95 backdrop-blur-md border border-zinc-800" : "bg-[hsl(var(--primary))] shadow-lg"
                }`}>
                {tabButtons}
              </div>
              <button
                onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
                aria-label="Jump to top"
                className={`flex items-center justify-center w-11 rounded-2xl transition-all select-none ${
                  isBrutal
                    ? "bg-zinc-900/95 backdrop-blur-md border border-zinc-800 text-white/80 hover:text-white"
                    : "bg-[hsl(var(--primary))] shadow-lg text-primary-foreground/80 hover:text-primary-foreground"
                }`}>
                <ArrowUp className="w-6 h-6" />
              </button>
            </div>
          </div>
        </div>
      </>
    );
  }

  return (
    <div
      className={`fixed bottom-0 left-0 right-0 z-30 select-none ${safeClass} ${bgClass}`}
      style={{ ...boxShadow }}>
      <div className="flex w-full max-w-lg md:max-w-3xl xl:max-w-5xl mx-auto overflow-hidden">
        {tabs.map(({ id, label, icon: Icon, proOnly }) => {
          const active = activeTab === id;
          const locked = proOnly && !isSubscribed;

          let tabClass = `flex-1 flex flex-col items-center justify-center py-4 gap-1.5 transition-all select-none `;
          if (locked) {
            tabClass += isBrutal ? "opacity-50 text-[hsl(var(--card))]" : "opacity-20 text-primary-foreground";
          } else if (active) {
            tabClass += isBrutal ? "text-white" : "text-primary-foreground";
          } else {
            tabClass += isBrutal ? "text-white/50" : "text-primary-foreground/60";
          }

          return (
            <button
              key={id}
              onClick={() => handlePress(id)}
              className={tabClass}>
              <div className="relative">
                <Icon className="w-6 h-6" />
                {locked &&
                  <span className="absolute -top-1 -right-2 text-[8px] font-bold bg-amber-400 text-amber-900 rounded-full px-1">
                    PRO
                  </span>
                }
              </div>
              <span className="text-xs font-bold">{label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}