import { Clock, Settings } from "lucide-react";
import ModeToggle from "./ModeToggle";

// Consolidated sticky bar shown only on the translation tab once the user
// scrolls past the header. Locks the logo, compact mode icons and the
// key controls (name, year, history, settings, Pro/scans) to the top.
// Mobile shows logo + mode icons + name + year only; tablet/desktop adds
// the title, history, settings and Pro/scans controls.
export default function StickyCompactBar({
  mode,
  onModeChange,
  isBrutal,
  isHilarious,
  darkMode,
  activeStudent,
  isSubscribed,
  scansLeft,
  onOpenSettings,
  onHistoryClick,
  onOpenPaywall,
  onLogoClick,
}) {
  const containerCls = `grid grid-cols-[1fr_auto_1fr] items-center gap-2 w-full rounded-2xl px-2 py-1.5 overflow-hidden ${
    isBrutal
      ? "bg-zinc-900/90 backdrop-blur-sm border border-zinc-800"
      : "bg-[#fde8cb]/90 backdrop-blur-sm shadow-sm"
  }`;

  const yearLabel = activeStudent?.student_year === "Kindergarten / Preparatory"
    ? "Kindy / Prep"
    : activeStudent?.student_year;

  return (
    <div className={containerCls}>
      <div className="flex items-center gap-2 min-w-0">
      <img
        src="https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets/images/public/69fc81cf4f6a0ae5ab617e2b/c7bffff4e_TTLogo01.png"
        alt="Teacher Translate"
        onClick={onLogoClick}
        className="w-9 h-9 object-contain cursor-pointer flex-shrink-0"
      />

      {/* Title — only when there is room (desktop wide) */}
      <h1 className={`hidden lg:block font-fredoka text-base leading-tight flex-shrink-0 ${isBrutal ? "text-orange-400" : "text-foreground"}`}>
        Teacher Translate
      </h1>
      </div>

      {/* Compact mode icons — centered */}
      <ModeToggle
        mode={mode}
        onModeChange={onModeChange}
        isBrutal={isBrutal}
        isHilarious={isHilarious}
        darkMode={darkMode}
        compact
      />

      <div className="flex items-center justify-end gap-2 min-w-0">
      {/* Child name + year — stacked right-justified on mobile */}
      <div className="flex flex-col items-end md:flex-row md:items-center gap-0.5 md:gap-1.5 flex-nowrap min-w-0">
        {activeStudent?.student_name && (
          <button
            onClick={onOpenSettings}
            className={`text-sm font-bold whitespace-nowrap truncate max-w-[90px] sm:max-w-[140px] transition-all select-none ${
              isBrutal ? "text-zinc-200 hover:text-orange-400" : "text-foreground hover:text-primary"
            }`}
          >
            {activeStudent.student_name}
          </button>
        )}
        {yearLabel && (
          <button
            onClick={onOpenSettings}
            className={`text-xs font-semibold px-2 py-0.5 rounded-full border transition-all select-none whitespace-nowrap flex-shrink-0 ${
              isBrutal
                ? "bg-zinc-800 text-zinc-400 border-zinc-700 hover:bg-zinc-700"
                : "bg-white/70 text-foreground border-border hover:bg-white"
            }`}
          >
            {yearLabel}
          </button>
        )}
      </div>

      {/* History + settings — tablet/desktop only */}
      <div className="hidden md:flex items-center gap-1 flex-shrink-0">
        <button
          onClick={onHistoryClick}
          className={`p-1.5 rounded-xl transition-all select-none ${
            isBrutal ? "hover:bg-zinc-800 text-zinc-400" : "text-foreground/60 hover:text-foreground"
          }`}
        >
          <Clock className="w-5 h-5" />
        </button>
        <button
          onClick={onOpenSettings}
          className={`p-1.5 rounded-xl transition-all select-none ${
            isBrutal ? "hover:bg-zinc-800 text-zinc-400" : "text-foreground/60 hover:text-foreground"
          }`}
        >
          <Settings className="w-5 h-5" />
        </button>
      </div>

      {/* Pro / scans left — tablet/desktop only */}
      <div className="hidden md:block w-[70px] flex-shrink-0">
        {!isSubscribed ? (
          <button
            onClick={onOpenPaywall}
            className={`flex flex-col items-center text-[10px] font-bold rounded-full border overflow-hidden transition-all select-none w-full ${
              isBrutal ? "border-zinc-700" : "border-border"
            }`}
          >
            <span className={`w-full px-1 py-0.5 text-center ${
              scansLeft === 0
                ? "bg-red-100 text-red-700"
                : scansLeft === 1
                  ? "bg-orange-100 text-orange-700"
                  : isBrutal ? "bg-zinc-800 text-zinc-400" : "bg-white/70 text-foreground"
            }`}>
              {scansLeft} left
            </span>
            <span className={`w-full px-1 py-0.5 text-center ${
              isBrutal ? "bg-orange-600 text-white" : "bg-primary text-primary-foreground"
            }`}>
              Go Pro
            </span>
          </button>
        ) : (
          <span className="text-xs font-bold px-2 py-0.5 rounded-full border border-emerald-200 whitespace-nowrap bg-[hsl(var(--primary))] text-primary-foreground flex-shrink-0">
            ✨ Pro
          </span>
        )}
      </div>
      </div>
    </div>
  );
}