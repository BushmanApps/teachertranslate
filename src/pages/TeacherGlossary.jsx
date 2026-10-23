import { useState, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useBackToHome } from "@/hooks/useBackToHome";
import { useModeSwipe } from "@/hooks/useModeSwipe";
import { ChevronDown } from "lucide-react";
import { base44 } from "@/api/base44Client";
import ModeToggle from "@/components/ModeToggle";
import GlossaryCard from "@/components/GlossaryCard";
import YearLevelModal from "@/components/YearLevelModal";
import BrutalAckModal from "@/components/BrutalAckModal";
import HilariousBubbles from "@/components/HilariousBubbles";
import BrutalBubbles from "@/components/BrutalBubbles";
import StickyCompactBar from "@/components/StickyCompactBar";
import BottomNav from "@/components/BottomNav";
import { getGlossaryForYear } from "@/lib/glossaryData";
import { useDarkMode } from "@/hooks/useDarkMode";
import { useThemeColor } from "@/hooks/useThemeColor";

const MODE_ORDER = ["honest_helpful", "hilarious", "brutal"];

export default function TeacherGlossary() {
  const location = useLocation();
  const navigate = useNavigate();
  useBackToHome();
  const [mode, setMode] = useState(location.state?.mode || "honest_helpful");
  const [selectedYear, setSelectedYear] = useState("Year 5");
  const [showYearModal, setShowYearModal] = useState(false);
  const [showBrutalAck, setShowBrutalAck] = useState(false);
  const [brutalAcknowledged, setBrutalAcknowledged] = useState(
    () => sessionStorage.getItem("ttBrutalAck") === "1"
  );
  const headerRef = useRef(null);

  const handleModeChange = (newMode) => {
    if (newMode === "brutal" && !brutalAcknowledged) {
      setShowBrutalAck(true);
      return;
    }
    setMode(newMode);
  };

  const handleAcceptBrutal = () => {
    sessionStorage.setItem("ttBrutalAck", "1");
    setBrutalAcknowledged(true);
    setMode("brutal");
    setShowBrutalAck(false);
  };
  const isBrutal = mode === "brutal";
  const isHilarious = mode === "hilarious";
  const { darkMode } = useDarkMode();
  const isDark = darkMode && !isBrutal;
  const isDarkHonest = isDark && !isHilarious;
  const isDarkHilarious = isDark && isHilarious;

  useThemeColor({ isBrutal, isHilarious, isDark });

  const [modeScrolled, setModeScrolled] = useState(false);

  // Collapse the sticky mode selector to icons once the header has scrolled away.
  useEffect(() => {
    const onScroll = () => setModeScrolled((window.scrollY || 0) > 110);
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  // Swipe to move between translation modes (same as Home).
  const swipeToNextMode = () => {
    const i = MODE_ORDER.indexOf(mode);
    const next = MODE_ORDER[Math.min(i + 1, MODE_ORDER.length - 1)];
    if (next !== mode) handleModeChange(next);
  };
  const swipeToPrevMode = () => {
    const i = MODE_ORDER.indexOf(mode);
    const prev = MODE_ORDER[Math.max(i - 1, 0)];
    if (prev !== mode) handleModeChange(prev);
  };
  const modeSwipe = useModeSwipe(swipeToNextMode, swipeToPrevMode);

  // Footer nav — glossary lives under the Bonus tab, so that tab is active.
  // Tapping any tab returns to the home console at that tab.
  const handleTabChange = (tab) => {
    if (tab === "teacher_talk") navigate("/write-back");
    else navigate(`/?tab=${tab}`);
  };

  // Scroll to top when navigating to the glossary
  useEffect(() => {
    document.getElementById('root')?.scrollTo(0, 0);
  }, [location.pathname]);

  // Default to the user's first student's year level
  useEffect(() => {
    (async () => {
      try {
        const students = await base44.entities.Student.list();
        if (students && students.length > 0 && students[0].student_year) {
          setSelectedYear(students[0].student_year);
        }
      } catch (e) {
        // keep default
      }
    })();
  }, []);

  const entries = getGlossaryForYear(selectedYear);
  const yearLabel = selectedYear === "Kindergarten / Preparatory" ? "Kindy / Prep" : selectedYear;

  const description = isBrutal
    ? `Common teacher-speak for ${yearLabel}, brutally translated. Because sometimes you need it straight.`
    : isHilarious
      ? `Common teacher-speak for ${yearLabel}, roasted for your entertainment. Don't take it personally.`
      : `Common teacher report card comments for ${yearLabel}, decoded into plain English.`;

  return (
    <div
      className={`min-h-screen transition-colors duration-500 ${isBrutal ? "brutal-mode bg-zinc-950 isolate" : isHilarious ? (isDarkHilarious ? "dark-hilarious text-foreground isolate" : "hilarious-mode isolate") : isDarkHonest ? "dark-honest bg-background text-foreground" : "honest-bg-anim"}`}
      style={isBrutal ? {} : isHilarious ? { background: isDarkHilarious ? "hsl(330 30% 8%)" : "hsl(330 60% 95%)" } : isDarkHonest ? {
        backgroundImage: `linear-gradient(hsl(220 20% 6% / 0.80), hsl(220 20% 6% / 0.80)), url('https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets/images/public/69fc81cf4f6a0ae5ab617e2b/e47c595be_generated_image.png')`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundAttachment: "fixed"
      } : {
        backgroundImage: `url('https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets/images/public/69fc81cf4f6a0ae5ab617e2b/e47c595be_generated_image.png')`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundAttachment: "fixed"
      }}>

      {isHilarious && <HilariousBubbles headerRef={headerRef} />}
      {isBrutal && <BrutalBubbles headerRef={headerRef} />}

      {/* Header card — scrolls away */}
      <div ref={headerRef} className={`px-4 pt-safe ${isBrutal ? "bg-zinc-950/95" : ""}`}>
        <div className="max-w-lg md:max-w-3xl xl:max-w-5xl mx-auto pt-4 pb-2">
          <div className={`flex items-center justify-between rounded-2xl px-4 py-3 overflow-hidden ${isBrutal ? "bg-zinc-900 border border-zinc-800" : "bg-[#fde8cb]/90 backdrop-blur-sm shadow-sm"}`}>
            <div className="flex items-center gap-2 flex-shrink-0">
              <img
                src="https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets/images/public/69fc81cf4f6a0ae5ab617e2b/c7bffff4e_TTLogo01.png"
                alt="Teacher Translate"
                onClick={() => navigate("/welcome")}
                className="w-12 h-12 object-contain cursor-pointer flex-shrink-0"
              />
              <h1 className={`font-fredoka text-xl sm:text-[24px] leading-tight ${isBrutal ? "text-orange-400" : "text-foreground"}`}>
                <span className="block sm:inline pr-1">Teacher</span>
                <span className="block sm:inline">Glossary</span>
              </h1>
            </div>
            <button
              onClick={() => setShowYearModal(true)}
              className={`flex items-center gap-1 text-xs font-semibold px-3 py-1.5 rounded-full border transition-all select-none whitespace-nowrap ${
                isBrutal
                  ? "bg-zinc-800 text-zinc-400 border-zinc-700 hover:bg-zinc-700"
                  : "bg-white/70 text-foreground border-border hover:bg-white"
              }`}
            >
              {yearLabel}
              <ChevronDown className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Mode Toggle — sticky; collapses to the same compact bar as translations */}
      <div className="sticky top-0 z-20 max-w-lg md:max-w-3xl xl:max-w-5xl mx-auto px-4 py-2">
        {modeScrolled ? (
          <StickyCompactBar
            mode={mode}
            onModeChange={handleModeChange}
            isBrutal={isBrutal}
            isHilarious={isHilarious}
            darkMode={isDark}
            activeStudent={{ student_year: selectedYear }}
            isSubscribed={true}
            scansLeft={0}
            onOpenSettings={() => setShowYearModal(true)}
            onHistoryClick={() => navigate("/?tab=translate")}
            onOpenPaywall={() => navigate("/?tab=translate")}
            onLogoClick={() => navigate("/welcome")}
          />
        ) : (
          <div className="flex justify-center">
            <ModeToggle mode={mode} onModeChange={handleModeChange} isBrutal={isBrutal} isHilarious={isHilarious} darkMode={isDark} compact={modeScrolled} />
          </div>
        )}
      </div>

      <div className="max-w-lg mx-auto px-4 py-6 space-y-3 pb-28" {...modeSwipe}>
        <p className={`text-sm ${isBrutal ? "text-zinc-400" : isHilarious ? "text-pink-900/70" : "text-muted-foreground"}`}>
          {description}
        </p>
        {(() => {
          // Group entries by category
          const grouped = entries.reduce((acc, entry) => {
            const cat = entry.category || "Other";
            if (!acc[cat]) acc[cat] = [];
            acc[cat].push(entry);
            return acc;
          }, {});
          const categories = Object.keys(grouped);
          let globalIndex = 0;
          return categories.map((cat) => (
            <div key={cat} className="space-y-2">
              <h2 className={`font-fredoka text-sm font-bold uppercase tracking-wide pt-3 pb-1 ${isBrutal ? "text-orange-400/80" : isHilarious ? "text-pink-600/80" : "text-primary/70"}`}>
                {cat}
              </h2>
              {grouped[cat].map((entry, i) => (
                <GlossaryCard key={`${selectedYear}-${cat}-${i}`} entry={entry} mode={mode} index={globalIndex++} />
              ))}
            </div>
          ));
        })()}
      </div>

      <BottomNav
        activeTab="bonus"
        onTabChange={handleTabChange}
        onActiveTabPress={() => navigate("/?tab=bonus")}
        isBrutal={isBrutal}
        isHilarious={isHilarious}
        darkMode={isDark}
        isSubscribed={true}
      />

      <YearLevelModal
        isOpen={showYearModal}
        onClose={() => setShowYearModal(false)}
        onConfirm={(year) => {
          setSelectedYear(year);
          setShowYearModal(false);
        }}
        currentYear={selectedYear}
        isBrutal={isBrutal}
      />

      <BrutalAckModal
        isOpen={showBrutalAck}
        onClose={() => setShowBrutalAck(false)}
        onAccept={handleAcceptBrutal}
      />
    </div>
  );
}