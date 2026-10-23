export default function ModeToggle({ mode, onModeChange, isBrutal, isHilarious, darkMode, compact }) {
  const modes = [
    { key: "honest_helpful", label: "Honest", icon: "😊" },
    { key: "hilarious", label: "Hilarious", icon: "🤣" },
    { key: "brutal", label: "Brutal", icon: "💥" },
  ];

  const containerStyle = !isBrutal && !isHilarious
    ? {
        background: darkMode ? "hsl(220 20% 14%)" : "#e8b89a",
        boxShadow: darkMode ? "3px 3px 0 hsl(220 20% 10%)" : "3px 3px 0 #d4a086",
      }
    : isHilarious
      ? { background: darkMode ? "hsl(330 25% 16%)" : undefined, boxShadow: "3px 3px 0 #f0b6d4" }
      : isBrutal
        ? { boxShadow: "3px 3px 0 hsl(20 5% 6%)" }
        : {};

  if (compact) {
    return (
      <div
        className={`mode-toggle flex items-center p-1 rounded-full gap-1 select-none ${
          isBrutal ? "bg-zinc-900 border border-orange-600" : isHilarious ? "bg-pink-100 border border-pink-500" : "border border-transparent"
        }`}
        style={containerStyle}
      >
        {modes.map((m) => {
          const active = mode === m.key;
          let cls = "rounded-full transition-all duration-300 select-none flex items-center justify-center ";
          cls += "w-11 h-11 text-xl ";
          if (m.key === "brutal") {
            cls += active ? "bg-orange-600" : isBrutal ? "text-zinc-400" : "text-foreground/60";
          } else if (m.key === "hilarious") {
            cls += active ? "bg-pink-500" : isHilarious ? "text-pink-200" : "text-foreground/60";
          } else {
            cls += active ? "bg-[hsl(var(--primary))]" : "text-foreground/60";
          }
          return (
            <button key={m.key} onClick={() => onModeChange(m.key)} className={cls} aria-label={m.label}>
              <span>{m.icon}</span>
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div
      className={`mode-toggle flex items-center p-1.5 rounded-2xl gap-1.5 w-full select-none whitespace-nowrap ${
        isBrutal
          ? "bg-zinc-900 border border-orange-600"
          : isHilarious
          ? "bg-pink-100 border border-pink-500"
          : ""
      }`}
      style={containerStyle}
    >
      {modes.map((m) => {
        const active = mode === m.key;
        let cls =
          "flex-1 py-3 px-2 rounded-xl text-xs sm:text-sm font-bold transition-all duration-300 select-none flex items-center justify-center ";
        if (m.key === "brutal") {
          cls += active
            ? "bg-orange-600 text-white shadow-sm"
            : isBrutal
            ? "bg-transparent text-zinc-400 hover:text-white border border-orange-600"
            : "text-foreground/60 hover:text-foreground";
        } else if (m.key === "hilarious") {
          cls += active
            ? "bg-pink-500 text-white shadow-sm"
            : isHilarious
            ? "bg-transparent text-pink-200 hover:text-white border border-pink-500"
            : "text-foreground/60 hover:text-foreground";
        } else {
          cls += active
            ? "text-primary-foreground bg-[hsl(var(--primary))] shadow-sm"
            : "text-foreground/60 hover:text-foreground";
        }
        return (
          <button key={m.key} onClick={() => onModeChange(m.key)} className={cls}>
            <span className="text-xl sm:text-2xl mr-1">{m.icon}</span> {m.label}
          </button>
        );
      })}
    </div>
  );
}