import { useNavigate } from "react-router-dom";
import OnboardingScreen from "@/components/OnboardingScreen";
import { useStudents } from "@/hooks/useStudents";
import { useAuth } from "@/lib/AuthContext";
import { recordConsentGiven } from "@/lib/recordConsent";
import { markSetupShown } from "@/lib/setupSession";

// Standalone view of the consent (intro) screen — starts at the consent
// step even for returning users, so it can be previewed directly.
export default function Consent() {
  const navigate = useNavigate();
  const { user: currentUser } = useAuth();
  const { addStudent } = useStudents(currentUser);

  const finish = () => {
    markSetupShown();
    navigate("/", { replace: true });
  };

  return (
    <OnboardingScreen
      startAtStep={1}
      onConsent={() => recordConsentGiven(currentUser)}
      onComplete={({ studentName, studentYear }) => {
        addStudent({ studentName, studentYear });
        finish();
      }}
      onSkip={finish}
    />
  );
}