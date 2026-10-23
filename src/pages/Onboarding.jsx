import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import OnboardingScreen from "@/components/OnboardingScreen";
import { useStudents } from "@/hooks/useStudents";
import { useUserData } from "@/hooks/useUserData";
import { useAuth } from "@/lib/AuthContext";
import { recordConsentGiven } from "@/lib/recordConsent";
import { markSetupShown } from "@/lib/setupSession";
import { hasValidConsent } from "@/lib/consentCheck";

export default function Onboarding() {
  const navigate = useNavigate();
  const { user: currentUser, isAuthenticated, isLoadingAuth } = useAuth();
  const { addStudent } = useStudents(currentUser);
  const { userProfile, isLoading: profileLoading } = useUserData();

  // A user who has already given consent (recorded on their UserProfile)
  // never sees the consent step again — even after clearing app storage —
  // and goes straight to the "About your child" step. The step is decided
  // once the profile has loaded.
  const [startAtStep, setStartAtStep] = useState(null);

  useEffect(() => {
    if (profileLoading || !userProfile) return;
    if (hasValidConsent(userProfile)) {
      setStartAtStep(2);
    } else {
      try {
        setStartAtStep(localStorage.getItem("tt_has_logged_in") === "1" ? 2 : 1);
      } catch {
        setStartAtStep(1);
      }
    }
  }, [profileLoading, userProfile]);

  // Remember this device has logged in before so future sessions skip the intro
  useEffect(() => {
    try { localStorage.setItem("tt_has_logged_in", "1"); } catch {}
  }, []);

  // Redirect unauthenticated users to the landing page
  useEffect(() => {
    if (!isLoadingAuth && !isAuthenticated) {
      navigate("/welcome", { replace: true });
    }
  }, [isAuthenticated, isLoadingAuth, navigate]);

  if (isLoadingAuth || !currentUser || startAtStep === null) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  const finish = () => {
    markSetupShown();
    navigate("/", { replace: true });
  };

  // Record the date/time the user consented to the Privacy Policy and Terms of Use
  const handleConsentGiven = () => recordConsentGiven(currentUser);

  const handleSetupComplete = async ({ studentName, studentYear }) => {
    // addStudent de-dupes by name (updates year) for existing users, creates for new ones
    await addStudent({ studentName, studentYear });
    finish();
  };

  return (
    <OnboardingScreen
      startAtStep={startAtStep}
      onConsent={handleConsentGiven}
      onComplete={handleSetupComplete}
      onSkip={finish}
    />
  );
}