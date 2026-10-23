import { useRef, useEffect } from 'react';
import { Toaster } from "@/components/ui/toaster"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from '@/lib/query-client'
import { BrowserRouter as Router, Route, Routes, useLocation, useNavigationType } from 'react-router-dom';
import { AnimatePresence, motion } from "framer-motion";
import PageNotFound from './lib/PageNotFound';
import { AuthProvider, useAuth } from '@/lib/AuthContext';
import UserNotRegisteredError from '@/components/UserNotRegisteredError';
import { DarkModeProvider } from '@/hooks/useDarkMode';
import { useGlobalBackHandler } from '@/hooks/useGlobalBackHandler';
// Add page imports here
import Home from "./pages/Home";
import Onboarding from "./pages/Onboarding";
import Consent from "./pages/Consent";
import Landing from "./pages/Landing";
import Support from "./pages/Support";
import Privacy from "./pages/Privacy";
import Terms from "./pages/Terms";
import Register from "./pages/Register";
import TeacherGlossary from "./pages/TeacherGlossary";
import Feedback from "./pages/Feedback";

const HOME_KEYS = ["/", "/write-back"];

// Native push/pop slide. Uses `left` (not transform) so it never creates a
// containing block — fixed-position modals keep working and the document
// still scrolls natively (mobile address bar hides on scroll).
const pageVariants = {
  initial: (pop) => ({ left: pop ? "-100%" : "100%", opacity: 0 }),
  animate: { left: "0%", opacity: 1 },
  exit: (pop) => ({ left: pop ? "100%" : "-100%", opacity: 0 }),
};

function AnimatedRoutes() {
  const location = useLocation();
  const navType = useNavigationType();

  // Global hardware back-button interceptor — listens for the native
  // mobile wrapper's back-button event plugin and manually runs the
  // back-button order of operations (modals → tabs → mode → navigate).
  useGlobalBackHandler();
  const prevPathRef = useRef(location.pathname);
  // Treat navigation back to home from a sub-page as a POP so the screen
  // swipes right (back) instead of left (forward).
  // Home ↔ welcome transitions play in opposite directions: going to the
  // welcome page is a back swipe, returning to home (continue) is a forward swipe.
  const goingToWelcome = location.pathname === "/welcome" && HOME_KEYS.includes(prevPathRef.current);
  const goingFromWelcome = prevPathRef.current === "/welcome" && HOME_KEYS.includes(location.pathname);
  // Finishing the initialisation (onboarding/consent) screens plays a
  // forward swipe into the home console, matching the "continue" flow.
  const goingFromSetup = ["/onboarding", "/consent"].includes(prevPathRef.current) && HOME_KEYS.includes(location.pathname);
  const isPop = !goingFromWelcome && !goingFromSetup && (goingToWelcome || navType === "POP" || (HOME_KEYS.includes(location.pathname) && !HOME_KEYS.includes(prevPathRef.current)));
  const transitionKey = HOME_KEYS.includes(location.pathname) ? "home" : location.pathname;

  useEffect(() => {
    prevPathRef.current = location.pathname;
  }, [location.pathname]);

  // Keep the browser tab title consistent on every page
  useEffect(() => {
    document.title = "Teacher Translate";
  }, [location.pathname]);

  return (
    <div className="relative overflow-x-clip min-h-screen">
      <AnimatePresence mode="wait" initial={false} custom={isPop}>
        <motion.div
          key={transitionKey}
          custom={isPop}
          variants={pageVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={{ duration: 0.24, ease: [0.32, 0.72, 0, 1] }}
          style={{ position: "relative", transform: "none", willChange: "left, opacity" }}
        >
          <Routes location={location}>
            {/* Public pages */}
            <Route path="/welcome" element={<Landing />} />
            <Route path="/support" element={<Support />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/register" element={<Register />} />
            <Route path="/glossary" element={<TeacherGlossary />} />
            <Route path="/feedback" element={<Feedback />} />
            {/* Protected app routes */}
            <Route path="/" element={<Home />} />
            <Route path="/onboarding" element={<Onboarding />} />
            <Route path="/consent" element={<Consent />} />
            <Route path="/write-back" element={<Home />} />
            <Route path="*" element={<PageNotFound />} />
          </Routes>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

const AuthenticatedApp = () => {
  const { isLoadingAuth, isLoadingPublicSettings, authError, navigateToLogin } = useAuth();

  // Show loading spinner while checking app public settings or auth
  if (isLoadingPublicSettings || isLoadingAuth) {
    return (
      <div className="fixed inset-0 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-slate-200 border-t-slate-800 rounded-full animate-spin"></div>
      </div>
    );
  }

  // Handle authentication errors — but allow public pages through
  if (authError) {
    if (authError.type === 'user_not_registered') {
      return <UserNotRegisteredError />;
    }
    // auth_required: render public routes so unauthenticated users can still access them
  }

  // Render the main app
  return <AnimatedRoutes />;
};


function App() {

  return (
    <AuthProvider>
      <QueryClientProvider client={queryClientInstance}>
        <DarkModeProvider>
          <Router>
            <AuthenticatedApp />
          </Router>
          <Toaster />
          {/* Portrait-only overlay — blocks landscape on phones */}
          <div id="landscape-block" className="landscape-block">
            <div className="landscape-block-inner">
              <svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="5" y="2" width="14" height="20" rx="2" ry="2" />
                <path d="M12 18h.01" />
              </svg>
              <p className="landscape-block-title">Please rotate your device</p>
              <p className="landscape-block-sub">Teacher Translate works best in portrait mode.</p>
            </div>
          </div>
        </DarkModeProvider>
      </QueryClientProvider>
    </AuthProvider>
  )
}

export default App