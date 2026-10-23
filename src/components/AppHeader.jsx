import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { useDarkMode } from "@/hooks/useDarkMode";

export default function AppHeader({
  title,
  onBack,
  isBrutal = false,
  isHilarious = false,
  variant = "app",
  maxWidth = "lg",
  rightContent,
  children
}) {
  const navigate = useNavigate();
  const { darkMode } = useDarkMode();

  const handleBack = onBack || (() => {
    // Use the router's history index (state.idx), NOT window.history.length:
    // in native WebViews the wrapper's redirect chain inflates history
    // length even when there is no app entry to pop back to.
    const idx = window.history.state?.idx;
    if (typeof idx === "number" && idx > 0) {
      navigate(-1);
    } else {
      navigate("/");
    }
  });

  const isPublic = variant === "public";
  const isDark = darkMode && !isBrutal && !isPublic;

  const headerBg = isBrutal
    ? "bg-zinc-950/95 backdrop-blur-md"
    : isDark
      ? "backdrop-blur-md border-b border-border"
      : isPublic
        ? "bg-[#fde8cb] border-b border-border"
        : isHilarious
          ? "backdrop-blur-sm"
          : "backdrop-blur-sm border-b border-white/20";

  const maxW = maxWidth === "3xl" ? "max-w-3xl" : "max-w-lg";

  const backBtnCls = isBrutal
    ? "p-2 rounded-xl bg-zinc-900 text-zinc-400 hover:bg-zinc-800"
    : isPublic
      ? "p-2 rounded-xl bg-white/70 text-foreground hover:bg-white"
      : "p-2 rounded-xl bg-[#fde8cb]/90 text-foreground";

  return (
    <div className={`sticky top-0 z-10 pt-safe ${headerBg}`}>
      <div className={`${maxW} mx-auto ${isPublic ? "px-6 py-5" : "px-4 pt-4 pb-2"} flex items-center gap-3`}>
        <button onClick={handleBack} className={`flex-shrink-0 ${backBtnCls}`}>
          <ArrowLeft className="w-5 h-5" />
        </button>
        <h1 className={`font-fredoka text-xl ${isBrutal ? "text-orange-400" : "text-foreground"}`}>
          {title}
        </h1>
        {rightContent && <div className="ml-auto flex items-center gap-2">{rightContent}</div>}
      </div>
      {children && <div className={`${maxW} mx-auto ${isPublic ? "px-6" : "px-4"} pb-2`}>{children}</div>}
    </div>
  );
}