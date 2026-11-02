import { useState, useEffect, useRef, useCallback } from "react";
import { Settings, RotateCcw, Loader2, Clock, AlertCircle } from "lucide-react";
import { base44 } from "@/api/base44Client";
import { useNavigate, useLocation, Navigate } from "react-router-dom";
import { useModalHistory } from "@/hooks/useModalHistory";
import { useModeSwipe } from "@/hooks/useModeSwipe";
import { useUserData } from "@/hooks/useUserData";
import { useStudents } from "@/hooks/useStudents";
import { useTranslation } from "@/hooks/useTranslation";
import { useDarkMode } from "@/hooks/useDarkMode";
import { useThemeColor } from "@/hooks/useThemeColor";

import { useAuth } from "@/lib/AuthContext";
import renameStudentInResult from "@/lib/renameStudent";
import { isSetupShown } from "@/lib/setupSession";
import { hasValidConsent } from "@/lib/consentCheck";
import { safePushState, safeAddPopState } from "@/lib/safeWebApi";
import { getGlobalMode, setGlobalMode } from "@/lib/globalBackState";
import ModeToggle from "@/components/ModeToggle";
import UploadSection from "@/components/UploadSection";
import TranslationResult from "@/components/TranslationResult";
import SettingsModal from "@/components/SettingsModal";
import PaywallModal from "@/components/PaywallModal";
import TeacherTalkTranslator from "@/components/TeacherTalkTranslator";
import AddStudentModal from "@/components/AddStudentModal";
import BottomNav from "@/components/BottomNav";
import TranslatingScreen from "@/components/TranslatingScreen";
import HistoryModal from "@/components/HistoryModal";
import ConfirmStudentModal from "@/components/ConfirmStudentModal";
import BonusPanel from "@/components/BonusPanel";
import BrutalAckModal from "@/components/BrutalAckModal";
import HilariousBubbles from "@/components/HilariousBubbles";
import BrutalBubbles from "@/components/BrutalBubbles";
import StickyCompactBar from "@/components/StickyCompactBar";
import { useCheckoutResumeSync } from "@/hooks/useCheckoutResumeSync";
import { toast } from "@/components/ui/use-toast";

// Mode is stored in a shared module (globalBackState.js) so the global
// back-button interceptor in App.jsx can read the current translation mode.

// Swipe order: left goes Honest → Hilarious → Brutal, right goes back.
const MODE_ORDER = ["honest_helpful", "hilarious", "brutal"];


export default function Home() {
  const [mode, setMode] = useState(getGlobalMode());
  // Brutal mode acknowledgment is remembered for the whole session, so the
  // popup only ever shows once per session.
  const [brutalAcknowledged, setBrutalAcknowledged] = useState(
    () => sessionStorage.getItem("ttBrutalAck") === "1"
  );

  useEffect(() => {
    setGlobalMode(mode);
  }, [mode]);

  // Listen for the global back-button interceptor's request to switch
  // back to Honest mode (fired when no mode pushState entry exists to pop).
  useEffect(() => {
    const handleBackToHonest = () => setMode("honest_helpful");
    window.addEventListener("tt:back-to-honest", handleBackToHonest);
    return () => window.removeEventListener("tt:back-to-honest", handleBackToHonest);
  }, []);

  // Refs that always hold the latest state for the popstate handler.
  // Updated during render (not in an effect) so the handler reads fresh
  // values even before React re-renders after a popstate event.
  const modeRef = useRef(mode);
  modeRef.current = mode;

  const handleModeChange = (newMode) => {
    if (newMode === "brutal" && !brutalAcknowledged && activeTab !== "teacher_talk") {
      openModal("brutal-ack");
      return;
    }
    setMode(newMode);
  };

  const handleAcceptBrutal = () => {
    sessionStorage.setItem("ttBrutalAck", "1");
    setBrutalAcknowledged(true);
    // Close the modal first (it steps back in history), then switch mode on
    // the next tick so the resulting popstate can't reset it to Honest.
    // Wait for the modal's history pop to finish (and any back handlers
    // that reset mode on it) before switching, so Brutal sticks.
    const apply = () => setTimeout(() => setMode("brutal"), 50);
    window.addEventListener("popstate", apply, { once: true });
    closeModal();
    setTimeout(() => {
      window.removeEventListener("popstate", apply);
      setMode("brutal");
    }, 400);
  };

  // Swipe on the translation result to move between the three modes.
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
  const { darkMode, toggleDarkMode } = useDarkMode();
  const [paywallVariant, setPaywallVariant] = useState("limit");
  const [revealExpectations, setRevealExpectations] = useState(false);

  const openPaywall = (variant = "limit") => {
    setPaywallVariant(variant);
    openModal("paywall");
  };
  const handleHistoryClick = () => {
    if (!isSubscribed) {
      openPaywall("feature");
    } else {
      openModal("history");
    }
  };
  const { activeModal, openModal, closeModal } = useModalHistory();
  const activeModalRef = useRef(activeModal);
  activeModalRef.current = activeModal;
  const showSettings = activeModal === "settings";
  const showHistory = activeModal === "history";
  const showAddStudent = activeModal === "add-student";
  const showBrutalAck = activeModal === "brutal-ack";
  const showPaywall = activeModal === "paywall";
  const showConfirmStudent = activeModal === "confirm-student";
  const showShare = activeModal === "share";
  const showExport = activeModal === "export";
  const [refreshing, setRefreshing] = useState(false);
  const [pullDistance, setPullDistance] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [modeScrolled, setModeScrolled] = useState(false);
  const touchStartY = useRef(null);
  const mainRef = useRef(null);
  const headerRef = useRef(null);
  const uploadCardRef = useRef(null);
  const modeToggleRef = useRef(null);
  const scrollPositions = useRef({ translate: 0, teacher_talk: 0 });

  const { isAuthenticated, isLoadingAuth } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Data hooks (react-query powered)
  const { currentUser, userProfile, setUserProfile, isLoading: userDataLoading, refresh: refreshUserData } = useUserData();
  const { students, activeStudent, setActiveStudent, isLoading: studentsLoading, onboardingComplete, addStudent, deleteStudent, updateStudent, refresh: refreshStudents } = useStudents(currentUser);

  const isHilarious = mode === "hilarious";
  const isBrutal = mode === "brutal";
  const isDark = darkMode && !isBrutal;
  const isDarkHonest = isDark && !isHilarious;
  const isDarkHilarious = isDark && isHilarious;
  const scansUsed = userProfile?.scans_used || 0;
  const isSubscribed = !!userProfile?.is_subscribed;

  // Refresh subscription status when the app returns to the foreground
  // after a native subscription purchase.
  useCheckoutResumeSync({ refreshUserData, isSubscribed, closeModal });

  useThemeColor({ isBrutal, isHilarious, isDark });

  const {
    FREE_SCAN_LIMIT,
    translating, result, setResult, pendingText, setPendingText,
    handleTextReady: hookHandleTextReady, runTranslation, retranslate,
    handleLoadFromHistory, handleReset,
    error, setError
  } = useTranslation({ userProfile, setUserProfile, activeStudent, currentUser, mode, onLimitReached: openPaywall });

  const handleTextReady = (text) => {
    if (hookHandleTextReady(text)) {
      openModal("confirm-student");
    }
  };

  const loaded = !userDataLoading && !studentsLoading;


  // Refresh native subscription status and reload data
  useEffect(() => {
    const params = new URLSearchParams(location.search);

    if (params.get("subscribed") === "1") {
      const syncAndReload = async () => {
        try {
          await base44.functions.invoke("checkSubscription", {});
          console.log("Subscription status synced");
        } catch (e) {
          console.error("Failed to sync subscription:", e);
        } finally {
          await Promise.all([refreshUserData(), refreshStudents()]);
          try { sessionStorage.removeItem("tt_checkout_pending"); } catch {}
          toast({
            title: "Welcome to Pro! ✨",
            description: "Your subscription is now active.",
          });
          navigate("/", { replace: true });
        }
      };
      syncAndReload();
    }
  }, [location.search]);

  // Switch to Bonus tab when returning from Feedback page
  useEffect(() => {
    if (location.state?.openBonus) {
      const params = new URLSearchParams(location.search);
      params.set("tab", "bonus");
      navigate({ pathname: "/", search: params.toString() }, { replace: true, state: null });
      setActiveTab("bonus");
    }
  }, [location.state]);

  const [activeTab, setActiveTab] = useState(() => {
    const tabParam = new URLSearchParams(location.search).get("tab");
    if (tabParam === "teacher_talk" || location.pathname === "/write-back") return "teacher_talk";
    if (tabParam === "bonus") return "bonus";
    return "translate";
  });
  const tabRef = useRef(activeTab);
  tabRef.current = activeTab;

  // Remember the current tab so a hardware back return lands on it again.
  useEffect(() => {
    try {
      sessionStorage.setItem("tt_active_tab", activeTab);
    } catch (e) {






      // sessionStorage blocked — tab restore simply won't apply
    }}, [activeTab]); // Sync activeTab with URL search params so native back-swipe transitions between tabs
  useEffect(() => {const tabParam = new URLSearchParams(location.search).get("tab");const newTab = tabParam === "teacher_talk" || location.pathname === "/write-back" ? "teacher_talk" : tabParam === "bonus" ? "bonus" : "translate";
      if (newTab !== activeTab) {
        scrollPositions.current[activeTab] = window.scrollY;
        setActiveTab(newTab);
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            window.scrollTo(0, scrollPositions.current[newTab] || 0);
          });
        });
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [location.search, location.pathname]);

  // Redirect unauthenticated users to landing
  useEffect(() => {
    if (!isLoadingAuth && !isAuthenticated) {
      navigate("/welcome", { replace: true });
    }
  }, [isAuthenticated, isLoadingAuth, navigate]);

  // Every fresh app session opens on the welcome screen — but only on a
  // true cold start. If the user just finished onboarding or consent
  // (tt_setup_shown is set this session), they entered the app
  // intentionally and should land on the console, not bounce back to
  // the welcome screen.
  useEffect(() => {
    if (isSetupShown()) return;
    try {
      if (!sessionStorage.getItem("ttWelcomeShown")) {
        navigate("/welcome", { replace: true });
      }
    } catch (e) {
      // sessionStorage blocked after data clear — redirect to welcome
      navigate("/welcome", { replace: true });
    }
  }, []);

  // Hardware back button — standard history pushState + popstate listener.
  // Modals and tabs are tracked in the URL (via useModalHistory and tab
  // search params), so React Router handles their back navigation naturally.
  // Mode is in-memory, so we push a dedicated history entry for non-Honest
  // modes (see the effect below) giving the back button an entry to pop.
  useEffect(() => {
    const isHomePath = () => window.location.pathname === "/" || window.location.pathname === "/write-back";
    if (!isHomePath()) return;

    const handlePopState = () => {
      if (!isHomePath()) return;

      // Priority 1: A URL-modal was just open — this back closed it.
      // activeModalRef still holds the old modal name because React
      // hasn't re-rendered yet (popstate fires before the batched re-render).
      if (activeModalRef.current) return;

      // Priority 2: Tab was non-translate — this back switched it.
      // tabRef still holds the old tab; the URL pop handled the switch.
      if (tabRef.current && tabRef.current !== "translate") return;

      // Priority 3: Mode is not Honest — switch to Honest.
      // The mode pushState entry was just consumed by this back press.
      if (modeRef.current !== "honest_helpful") {
        setMode("honest_helpful");
        return;
      }

      // Priority 4: Nothing to close or switch — let back navigate
      // normally (previous page or exit the app).
    };

    return safeAddPopState(handlePopState);
  }, []);

  // Push a history entry for non-Honest modes so the hardware back button
  // has an entry to pop (switching mode back to Honest) instead of
  // navigating away from the home screen. Only pushes when no mode entry
  // already exists in the history stack.
  useEffect(() => {
    if (mode !== "honest_helpful") {
      try {
        if (!window.history.state?.tt_mode) {
          safePushState({ tt_mode: mode });
        }
      } catch (e) {












        // SecurityError after data clear — mode is in-memory, back button
        // still works via the native wrapper's popstate events.
      }}}, [mode]);const handleAddStudent = ({ studentName, studentYear }) => {setResult(null);closeModal();addStudent({ studentName, studentYear });};const handleSettingsSave = async ({ studentYear, studentName }) => {const yearChanged = studentYear !== activeStudent.student_year;const oldName = (activeStudent.student_name || "").trim();
    const newName = (studentName || "").trim();
    const nameChanged = oldName !== newName;
    // Name-only change: swap the name in the open report synchronously,
    // before any await, so it survives the modal closing.
    const reportName = (result?.student_name ?? oldName).trim();
    const renamed = nameChanged && !yearChanged && result ?
    { ...renameStudentInResult(result, reportName, newName), student_name: studentName, student_year: studentYear } :
    null;
    if (renamed) setResult(renamed);
    try {
      await updateStudent(studentName, studentYear);

      if (renamed) {
        if (renamed.id) {
          await base44.entities.Translation.update(renamed.id, {
            student_name: studentName,
            student_year: studentYear,
            honest_helpful_translation: renamed.overall_honest_helpful,
            brutal_translation: renamed.overall_brutal,
            brutal_direct_translation: renamed.overall_brutal_direct,
            performance_summary: renamed.overall_performance_summary,
            sections: renamed.sections
          });
        }
        return;
      }

      // If year changed and there's a current result, re-run the translation
      if (yearChanged && result) {
        await retranslate(result.original_text, studentName, studentYear);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteStudent = () => {
    setResult(null);
    closeModal();
    deleteStudent(activeStudent);
  };

  const handleSelectStudent = (student, keepReport = false) => {
    if (student.id === activeStudent?.id) return;
    if (keepReport && result) {
      if (student.student_year !== activeStudent?.student_year) {
        retranslate(result.original_text, student.student_name, student.student_year);
      } else {
        setResult(renameStudentInResult(result, (activeStudent?.student_name || "").trim(), (student.student_name || "").trim()));
      }
    } else {
      setResult(null);
    }
    setActiveStudent(student);
  };

  const handleConfirmStudent = async ({ studentName, studentYear }) => {
    const text = pendingText;
    closeModal();
    setPendingText(null);

    // Find or create the student by name (updates year if same name, creates new if different name)
    await addStudent({ studentName, studentYear });

    await runTranslation(text, studentName, studentYear);
  };

  const handleTabChange = (tab) => {
    if (tab === "bonus" && !isSubscribed) {
      openPaywall("feature");
      return;
    }
    if (tab === "teacher_talk" && !isSubscribed) {
      openPaywall("feature");
      return;
    }
    scrollPositions.current[activeTab] = window.scrollY;
    const params = new URLSearchParams(location.search);
    params.set("tab", tab);
    // Replace (not push) so tab toggles don't stack stale history entries.
    navigate({ pathname: "/", search: params.toString() }, { replace: true });
    setActiveTab(tab);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        window.scrollTo(0, scrollPositions.current[tab] || 0);
      });
    });
  };

  // Focusing the manual textarea inside the upload card scrolls the card
  // flush to the top of the viewport, directly under the minimized sticky
  // mode toggle. Instant, and independent of the keyboard appearing.
  const handleUploadFocus = useCallback((e) => {
    if (e.target?.tagName !== "TEXTAREA" && !e.target?.closest?.("textarea")) return;
    const align = () => {
      const card = uploadCardRef.current;
      if (!card) return;
      const toggleH = modeToggleRef.current?.getBoundingClientRect().height || 0;
      const target = Math.max(0, window.scrollY + card.getBoundingClientRect().top - toggleH);
      window.scrollTo({ top: target, behavior: "auto" });
    };
    align();
    // Re-align briefly: the toggle collapses to its compact height and the
    // card itself may re-scroll as the manual field mounts.
    const id = setInterval(align, 50);
    setTimeout(() => clearInterval(id), 1200);
  }, []);

  const MAX_PULL = 80;
  const TRIGGER_THRESHOLD = 60;

  const handleTouchStart = useCallback((e) => {
    // Only begin pull-to-refresh when the page is scrolled right to the top.
    if (window.scrollY <= 0) {
      touchStartY.current = e.touches[0].clientY;
      setIsDragging(true);
    }
  }, []);

  const handleTouchMove = useCallback((e) => {
    if (touchStartY.current === null) return;
    // Abort if the user has scrolled the page away from the top.
    if (window.scrollY > 1) {
      touchStartY.current = null;
      setPullDistance(0);
      setIsDragging(false);
      return;
    }
    const delta = e.touches[0].clientY - touchStartY.current;
    if (delta > 0) {
      // Rubber-band resistance: diminish as we pull further
      const resisted = Math.min(MAX_PULL, delta * 0.5);
      setPullDistance(resisted);
    }
  }, []);

  const handleTouchEnd = useCallback(async (e) => {
    if (touchStartY.current === null) return;
    // Verify scroll is still at top before triggering refresh
    if (window.scrollY > 1) {
      touchStartY.current = null;
      setPullDistance(0);
      setIsDragging(false);
      return;
    }
    const delta = e.changedTouches[0].clientY - touchStartY.current;
    touchStartY.current = null;
    setIsDragging(false);

    if (delta >= TRIGGER_THRESHOLD && !refreshing) {
      setPullDistance(MAX_PULL);
      setRefreshing(true);
      try {
        await Promise.all([refreshUserData(), refreshStudents()]);
      } finally {
        setRefreshing(false);
        setPullDistance(0);
      }
    } else {
      setPullDistance(0);
    }
  }, [refreshing, refreshUserData, refreshStudents]);

  // Collapse the sticky mode selector to icons once the header has scrolled away.
  // Listen on both window and #root so it works whether the document or a
  // root element is the scroll container.
  useEffect(() => {
    const onScroll = () => setModeScrolled((window.scrollY || 0) > 110);
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  if (!loaded) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>);

  }

  // After logging in, check whether the user has previously given consent
  // (stored on their UserProfile). If not, send them to the Consent screen.
  // Skip the check when the onboarding flow just ran — consent is already
  // collected there, so the user goes straight to the home console.
  if (userProfile && !hasValidConsent(userProfile) && !isSetupShown()) {
    return <Navigate to="/consent" replace />;
  }

  // At the start of a session, once consent is confirmed, send the user
  // through the onboarding screen (child/year setup) before the home
  // console — once it's completed this session they go straight home.
  // A back-button return from a public page (privacy/terms/support) goes
  // straight home instead of replaying the session-start flow.
  const returnedFromPublicPage = sessionStorage.getItem("ttBackToApp") === "1";
  if (userProfile && !isSetupShown() && !returnedFromPublicPage) {
    return <Navigate to="/onboarding" replace />;
  }

  // Header name/year follow the open report (e.g. one loaded from history).
  const headerStudent = result ? {
    ...activeStudent,
    student_name: result.student_name ?? activeStudent?.student_name,
    student_year: result.student_year || activeStudent?.student_year
  } : activeStudent;

  const scansLeft = Math.max(0, FREE_SCAN_LIMIT - scansUsed);
  const canScan = isSubscribed || scansUsed < FREE_SCAN_LIMIT;

  return (
    <div
      className={`min-h-screen transition-colors duration-500 ${isBrutal ? "brutal-mode bg-zinc-950 isolate" : isHilarious ? isDarkHilarious ? "dark-hilarious text-foreground isolate" : "hilarious-mode isolate" : isDarkHonest ? "dark-honest bg-background text-foreground" : "honest-bg-anim"}`}
      style={isBrutal ? {} : isHilarious ? {
        background: isDarkHilarious ? "hsl(330 30% 8%)" : "hsl(330 60% 95%)"
      } : isDarkHonest ? {
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
      <div ref={headerRef} className={`px-4 pt-safe ${
      isBrutal ?
      "bg-zinc-950/95" :
      isDarkHonest || isDarkHilarious ? "" :
      isHilarious ? "" :
      ""}`
      }>
        <div className="max-w-lg md:max-w-3xl xl:max-w-5xl mx-auto pt-4 pb-2">
          {/* Header card */}
          <div className={`flex items-center justify-between rounded-2xl px-4 py-3 overflow-hidden ${
          isBrutal ? "bg-zinc-900 border border-zinc-800" : "bg-[#fde8cb]/90 backdrop-blur-sm shadow-sm"}`
          }>
            <div className="flex items-center gap-2 flex-shrink-0">
              <img
                src="https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets/images/public/69fc81cf4f6a0ae5ab617e2b/c7bffff4e_TTLogo01.png"
                alt="Teacher Translate"
                onClick={() => navigate("/welcome")}
                className="w-12 h-12 object-contain cursor-pointer flex-shrink-0" />
              
              <h1 className={`font-fredoka text-xl sm:text-[24px] leading-tight ${
              isBrutal ? "text-orange-400" : "text-foreground"}`
              }>
                <span className="block sm:inline pr-1">Teacher</span>{""}
                <span className="block sm:inline">Translate</span>
              </h1>
            </div>
            <div className="flex flex-col items-end gap-1 flex-nowrap min-w-0 overflow-hidden">
              {/* Top row: name (right-justified to align with year) + Pro (centered over icons) */}
              <div className="flex items-center gap-3 flex-nowrap w-full justify-end">
                <div className="flex-shrink-0">
                  {headerStudent?.student_name &&
                  <button
                    onClick={() => openModal("settings")}
                    className={`text-sm font-bold whitespace-nowrap transition-all select-none ${
                    isBrutal ? "text-zinc-200 hover:text-orange-400" : "text-foreground hover:text-primary"}`
                    }>
                    
                    {headerStudent.student_name}
                  </button>
                  }
                </div>
                <div className="w-[70px] flex justify-end flex-shrink-0">
                  {!isSubscribed &&
                  <button
                    onClick={() => openPaywall("feature")}
                    className={`flex flex-col items-center text-[10px] font-bold rounded-full border overflow-hidden transition-all select-none w-full ${
                    isBrutal ? "border-zinc-700" : "border-border"}`
                    }>
                    
                    <span className={`w-full px-1 py-0.5 text-center ${
                    scansLeft === 0 ?
                    "bg-red-100 text-red-700" :
                    scansLeft === 1 ?
                    "bg-orange-100 text-orange-700" :
                    isBrutal ? "bg-zinc-800 text-zinc-400" : "bg-white/70 text-foreground"}`
                    }>
                      {scansLeft} left
                    </span>
                    <span className={`w-full px-1 py-0.5 text-center ${
                    isBrutal ? "bg-orange-600 text-white" : "bg-primary text-primary-foreground"}`
                    }>
                      Go Pro
                    </span>
                  </button>
                  }
                  {isSubscribed &&
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full border border-emerald-200 whitespace-nowrap bg-[hsl(var(--primary))] text-primary-foreground flex-shrink-0">✨ Pro</span>
                  }
                </div>
              </div>
              {/* Bottom row: year level + history & settings icons */}
              <div className="flex items-center gap-1.5 flex-nowrap">
                {headerStudent?.student_year &&
                <button
                  onClick={() => openModal("settings")}
                  className={`text-xs font-semibold px-2 py-0.5 rounded-full border transition-all select-none whitespace-nowrap ${
                  isBrutal ? "bg-zinc-800 text-zinc-400 border-zinc-700 hover:bg-zinc-700" : "bg-white/70 text-foreground border-border hover:bg-white"}`
                  }>

                    {headerStudent.student_year === "Kindergarten / Preparatory" ?
                  <>
                        <span className="sm:hidden">Kindy</span>
                        <span className="hidden sm:inline">Kindy / Prep</span>
                      </> :
                  headerStudent.student_year}
                  </button>
                }
                <button
                  onClick={() => {
                    if (!isSubscribed) {
                      openPaywall("feature");
                    } else {
                      openModal("history");
                    }
                  }}
                  className={`p-1.5 rounded-xl transition-all select-none flex-shrink-0 ${
                  isBrutal ? "hover:bg-zinc-800 text-zinc-400" : "text-foreground/60 hover:text-foreground"}`
                  }>
                  
                  <Clock className="w-5 h-5" />
                </button>
                <button
                  onClick={() => openModal("settings")}
                  className={`p-1.5 rounded-xl transition-all select-none flex-shrink-0 ${
                  isBrutal ? "hover:bg-zinc-800 text-zinc-400" : "text-foreground/60 hover:text-foreground"}`
                  }>
                  
                  <Settings className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Mode Toggle — sticky. When scrolled on the translation tab it
                locks into a consolidated compact header bar (logo + mode
                icons + name/year/controls). On other tabs it just shrinks
                to compact icons as before. */}
      <div ref={modeToggleRef} className="sticky top-0 z-20 max-w-lg md:max-w-3xl xl:max-w-5xl mx-auto px-4 py-2">
        {modeScrolled && activeTab === "translate" ?
        <StickyCompactBar
          mode={mode}
          onModeChange={handleModeChange}
          isBrutal={isBrutal}
          isHilarious={isHilarious}
          darkMode={isDark}
          activeStudent={headerStudent}
          isSubscribed={isSubscribed}
          scansLeft={scansLeft}
          onOpenSettings={() => openModal("settings")}
          onHistoryClick={handleHistoryClick}
          onOpenPaywall={() => openPaywall("feature")}
          onLogoClick={() => navigate("/welcome")} /> :

        <div className="flex justify-center">
            <ModeToggle
            mode={mode}
            onModeChange={handleModeChange}
            isBrutal={isBrutal}
            isHilarious={isHilarious}
            darkMode={isDark}
            compact={modeScrolled} />
          </div>
        }
      </div>

      {/* Pull-to-refresh indicator — height follows drag, spinner tracks finger position */}
      <div
        className="flex justify-center items-start overflow-hidden"
        style={{
          height: refreshing ? MAX_PULL : pullDistance,
          transition: isDragging ? "none" : "height 0.3s ease"
        }}>
        <Loader2
          className={`w-5 h-5 ${refreshing ? "animate-spin" : ""} ${isBrutal ? "text-orange-400" : "text-primary"}`}
          style={{
            opacity: refreshing || pullDistance > 10 ? 1 : 0,
            transition: isDragging ? "none" : "opacity 0.3s ease"
          }} />
        
      </div>

      {/* Main Content */}
      <div
        ref={mainRef}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        style={{
          transform: `translateY(${pullDistance}px)`,
          transition: isDragging ? "none" : "transform 0.3s ease"
        }}
        className="max-w-lg md:max-w-3xl xl:max-w-5xl mx-auto px-4 py-6 space-y-6 pb-28">
        
        <div style={{ display: activeTab === "translate" ? "block" : "none" }} className="space-y-6">
              {error && !result && !translating &&
          <div className={`rounded-2xl p-4 flex items-start gap-3 ${
          isBrutal ? "bg-orange-950/40 border border-orange-800" : "bg-red-50 border border-red-200"}`
          }>
              
                  <AlertCircle className={`w-5 h-5 shrink-0 mt-0.5 ${isBrutal ? "text-orange-400" : "text-red-500"}`} />
                  <div className="flex-1">
                    <p className={`text-sm font-bold ${isBrutal ? "text-orange-300" : "text-red-700"}`}>Translation timed out</p>
                    <p className={`text-xs mt-1 ${isBrutal ? "text-orange-400/70" : "text-red-600"}`}>
                      The report took too long to process. Please try again — if the report is very long, try translating one subject section at a time, or copy the text from your file and paste it manually instead of uploading.
                    </p>
                  </div>
                  <button
              onClick={() => setError(null)}
              className={`text-xs font-bold shrink-0 ${isBrutal ? "text-orange-400" : "text-red-600"}`}>
                    Dismiss
                  </button>
                </div>
          }
              {!result && !translating &&
          <div ref={uploadCardRef} onFocusCapture={handleUploadFocus} onClickCapture={handleUploadFocus} className={`rounded-3xl sm:p-5 space-y-3 sm:space-y-4 relative pt-4 pr-4 pl-4 pb-8 ${
          isBrutal ? "bg-zinc-900 border border-zinc-800" : "bg-[#a8d8c8]/80 backdrop-blur-sm shadow-md"}`
          }
          style={!isBrutal && !isDark ? { boxShadow: isHilarious ? "4px 4px 0 #f0b6d4, 8px 8px 0 #d89bc0" : "4px 4px 0 #8cc4b0, 8px 8px 0 #74b09a" } : {}}>
              
                  <div>
                    <h2 className={`font-fredoka text-2xl font-bold ${isBrutal ? "text-orange-400" : "text-foreground"}`}>
                      {isBrutal ? "Hand over the report." : "Upload or scan a report"}
                    </h2>
                    <p className={`text-sm mt-1 ${isBrutal ? "text-zinc-400" : "text-foreground/70"}`}>
                      {isBrutal ?
                "We'll tell you what your teacher really wants to say! No sugarcoating." :
                isHilarious ?
                "We'll roast the teacher-speak — giggles guaranteed." :
                "We'll decode the teacher-speak and tell you what it really means."}
                    </p>
                  </div>
                  <UploadSection
              onTextReady={handleTextReady}
              isBrutal={isBrutal}
              disabled={!canScan}
              onBlocked={() => openPaywall("limit")} />
              
                  {!canScan &&
            <button
              onClick={() => openPaywall("limit")}
              className="w-full py-3 bg-primary text-white font-bold rounded-2xl text-sm select-none">
                
                      🔓 Unlock Unlimited — Subscribe Now
                    </button>
            }
                </div>
          }

              {translating &&
          <TranslatingScreen isBrutal={isBrutal} studentName={activeStudent?.student_name} />
          }

              {result && !translating &&
          <div className="space-y-4" {...modeSwipe}>
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className={`font-fredoka text-lg ${isBrutal ? "text-orange-400" : "text-primary"}`}>
                        {`${(result.student_name ?? activeStudent?.student_name) || "Your child"}, ${result.student_year || activeStudent?.student_year}`}
                      </h2>
                      <p className={`text-xs mt-0.5 ${isBrutal ? "text-zinc-500" : "text-muted-foreground"}`}>
                        {new Date().toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}
                      </p>
                    </div>
                    <button
                onClick={() => {setRevealExpectations(false);handleReset();}}
                className={`flex items-center gap-1.5 text-sm font-bold px-4 py-2 rounded-full border-2 shadow-sm active:scale-95 transition-all select-none ${isBrutal ? "border-orange-700/60 text-orange-300" : "border-primary/30 text-primary"} ${
                isBrutal ? "bg-zinc-800 hover:bg-zinc-700" : "bg-white/80 hover:bg-primary/10"}`
                }>
                  
                      <RotateCcw className="w-3.5 h-3.5" /> New report
                    </button>
                  </div>
                  <TranslationResult
              result={result}
              mode={mode}
              studentName={result.student_name ?? activeStudent?.student_name}
              studentYear={result.student_year || activeStudent?.student_year}
              isSubscribed={isSubscribed}
              isBrutal={isBrutal}
              onUpgrade={() => openPaywall("feature")}
              shareModalOpen={showShare}
              onOpenShare={() => openModal("share")}
              onCloseShare={closeModal}
              exportModalOpen={showExport}
              onOpenExport={() => openModal("export")}
              onCloseExport={closeModal}
              autoShowExpectations={revealExpectations}
              onChangeYear={(y) => {
                setRevealExpectations(true);
                handleSettingsSave({ studentYear: y, studentName: activeStudent?.student_name || "" });
              }} />
              
                </div>
          }
        </div>

        {isSubscribed &&
        <div style={{ display: activeTab === "bonus" ? "block" : "none" }}>
          <BonusPanel
            isBrutal={isBrutal}
            onNavigate={(path) => {
              navigate(path, { state: { mode } });
            }} />
        </div>
        }

        {isSubscribed &&
        <div style={{ display: activeTab === "teacher_talk" ? "block" : "none" }}>
              <div
            className={`rounded-3xl p-5 ${
            isBrutal ? "bg-zinc-900 border border-zinc-800" : "bg-[#a8d8c8]/80 backdrop-blur-sm"}`
            }
            style={!isBrutal && !isDark ? { boxShadow: isHilarious ? "4px 4px 0 #f0b6d4, 8px 8px 0 #d89bc0" : "4px 4px 0 #8cc4b0, 8px 8px 0 #74b09a" } : {}}>
              
                <TeacherTalkTranslator
              studentYear={activeStudent?.student_year}
              studentName={activeStudent?.student_name}
              isBrutalMode={isBrutal}
              mode={mode}
              onResetMode={() => setMode("honest_helpful")} />
              
              </div>
        </div>
        }
      </div>

      <BottomNav
        activeTab={activeTab}
        onTabChange={handleTabChange}
        onActiveTabPress={() => {
          if (activeTab === "translate") handleReset();
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }}
        isBrutal={isBrutal}
        isHilarious={isHilarious}
        darkMode={isDark}
        isSubscribed={isSubscribed} />
      

      <SettingsModal
        isOpen={showSettings}
        onClose={closeModal}
        studentYear={activeStudent?.student_year}
        studentName={activeStudent?.student_name}
        creatorEmail={activeStudent?.creator_email}
        students={students}
        activeStudentId={activeStudent?.id}
        onSelectStudent={handleSelectStudent}
        onAddNewStudent={() => openModal("add-student")}
        onSave={handleSettingsSave}
        onDelete={students && students.length > 1 ? handleDeleteStudent : null}
        isBrutal={isBrutal}
        darkMode={isDark}
        onToggleDarkMode={toggleDarkMode}
        hasActiveResult={!!result}
        isSubscribed={isSubscribed}
        subscriptionRenewal={userProfile?.subscription_renewal}
        onUpgrade={() => openPaywall("feature")} />
      

      <AddStudentModal
        isOpen={showAddStudent}
        onClose={closeModal}
        onAdd={handleAddStudent}
        isBrutal={isBrutal} />
      

      <PaywallModal
        isOpen={showPaywall}
        onClose={closeModal}
        isBrutal={isBrutal}
        variant={paywallVariant} />
      

      <ConfirmStudentModal
        isOpen={showConfirmStudent}
        onClose={() => {closeModal();setPendingText(null);}}
        onConfirm={handleConfirmStudent}
        isBrutal={isBrutal}
        studentName={activeStudent?.student_name}
        studentYear={activeStudent?.student_year} />

      <HistoryModal
        isOpen={showHistory}
        onClose={closeModal}
        isBrutal={isBrutal}
        onLoadTranslation={(t) => {
          handleLoadFromHistory(t);
          setResult((prev) => prev && { ...prev, student_name: t.student_name || "", student_year: t.student_year || "" });
          // Sync the active student so the header name/year and the settings
          // bar reflect the loaded report. If the Student record still
          // exists, switch to it; if it was deleted, use a transient object
          // carrying the report's name/year so the header still updates.
          const match = students?.find((s) => s.id === t.student_id);
          if (match) {
            if (match.id !== activeStudent?.id) setActiveStudent(match);
          } else if (t.student_name || t.student_year) {
            setActiveStudent({
              id: t.student_id,
              student_name: t.student_name || "",
              student_year: t.student_year || "",
              creator_email: currentUser?.email
            });
          }
          // Older saved reports may carry curriculum codes from a different
          // year level — re-translate them against the report's own year.
          const yearNum = t.student_year?.startsWith("Kindergarten") ? "F" : (t.student_year || "").match(/\d+/)?.[0];
          const codes = (t.sections || []).flatMap((s) => [...(s.curriculum_codes || []).map((c) => c.code), s.ac_code]).filter((c) => c && c !== "null");
          const stale = yearNum && codes.some((c) => c.match(/^AC9[A-Z]+?(\d+|F)/)?.[1] !== yearNum);
          if (stale) retranslate((t.original_comments || []).join(" "), t.student_name || "", t.student_year, t.id);
        }}
        isSubscribed={isSubscribed}
        onUpgrade={() => openPaywall("feature")} />

      <BrutalAckModal
        isOpen={showBrutalAck}
        onClose={closeModal}
        onAccept={handleAcceptBrutal} />
      
    </div>);

}