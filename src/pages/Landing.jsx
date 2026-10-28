import { useEffect } from "react";
import { useAuth } from "@/lib/AuthContext";
import { useNavigate } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { Loader2 } from "lucide-react";
import TestimonialCarousel from "@/components/landing/TestimonialCarousel";
import SampleScreenshots from "@/components/landing/SampleScreenshots";
import AboutDeveloper from "@/components/landing/AboutDeveloper";

export default function Landing() {
  const { isAuthenticated, isLoadingAuth, isLoadingPublicSettings } = useAuth();
  const navigate = useNavigate();

  const isInIframe = typeof window !== "undefined" && window.self !== window.top;

  // Mark this app session as having seen the welcome screen, so returning
  // users aren't bounced back here mid-session after they continue.
  useEffect(() => {
    sessionStorage.setItem("ttWelcomeShown", "1");
  }, []);

  if (!isInIframe && (isLoadingAuth || isLoadingPublicSettings)) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>);

  }

  return (
    <div
      className="landing-root min-h-screen flex flex-col pt-safe"
      style={{
        backgroundImage: `url('https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets/images/public/69fc81cf4f6a0ae5ab617e2b/e47c595be_generated_image.png')`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundAttachment: "fixed"
      }}>
      
      {/* Hero */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 pt-2 pb-6 sm:px-6 sm:pt-4 sm:pb-12 text-center">
        <div className="bg-[#fde8cb]/90 backdrop-blur-sm rounded-3xl shadow-xl p-4 sm:p-8 md:p-12 max-w-lg w-full space-y-3 sm:space-y-6">
          <img
            src="https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets/images/public/69fc81cf4f6a0ae5ab617e2b/c7bffff4e_TTLogo01.png"
            alt="Teacher Translate"
            className="w-16 h-16 sm:w-28 sm:h-28 object-contain mx-auto" />
          

          <div>
            <h1 className="font-fredoka text-3xl sm:text-4xl md:text-5xl text-foreground leading-tight">
              Teacher Translate
            </h1>
            <p className="text-muted-foreground text-sm sm:text-base mt-1 sm:mt-2 leading-relaxed">
              <span className="sm:hidden">Decode what your child's teacher is <em className="font-semibold text-foreground">actually</em> trying to tell you.</span>
              <span className="hidden sm:inline">Decode what your child's teacher is<br /><em className="font-semibold text-foreground">actually</em>&nbsp; trying to tell you.</span>
            </p>
          </div>

          {/* Feature list */}
          <div className="space-y-1.5 sm:space-y-3 text-left">
            <div className="flex gap-2 sm:gap-3 items-start">
              <span className="text-xl sm:text-2xl">😊</span>
              <div>
                <p className="font-bold text-[13px] sm:text-sm">Honest mode</p>
                <p className="text-xs text-muted-foreground">Clear, kind translation of teacher-speak</p>
              </div>
            </div>
            <div className="flex gap-2 sm:gap-3 items-start">
              <span className="text-xl sm:text-2xl">🤣</span>
              <div>
                <p className="font-bold text-[13px] sm:text-sm">Hilarious Mode</p>
                <p className="text-xs text-muted-foreground">Funny, savage - but never mean</p>
              </div>
            </div>
            <div className="flex gap-2 sm:gap-3 items-start">
              <span className="text-xl sm:text-2xl">💥</span>
              <div>
                <p className="font-bold text-[13px] sm:text-sm">Brutal Mode</p>
                <p className="text-xs text-muted-foreground">No filter – the raw, inner monologue</p>
              </div>
            </div>
            <div className="flex gap-2 sm:gap-3 items-start">
              <span className="text-xl sm:text-2xl">📊</span>
              <div>
                <p className="font-bold text-[13px] sm:text-sm">Year Level Assessment (Pro)</p>
                <p className="text-xs text-muted-foreground">Confirm if your child is ahead, on track, or struggling</p>
              </div>
            </div>
            <div className="flex gap-2 sm:gap-3 items-start">
              <span className="text-xl sm:text-2xl">🏠</span>
              <div>
                <p className="font-bold text-[13px] sm:text-sm">Supporting Activities (Pro)</p>
                <p className="text-xs text-muted-foreground">Curriculum-linked activities to try at home</p>
              </div>
            </div>
            <div className="flex gap-2 sm:gap-3 items-start">
              <span className="text-xl sm:text-2xl">✏️</span>
              <div>
                <p className="font-bold text-[13px] sm:text-sm">Write Back (Pro)</p>
                <p className="text-xs text-muted-foreground">Reply to teachers in perfect "school-speak"</p>
              </div>
            </div>
          </div>
            <p className="text-muted-foreground text-xs sm:text-base mt-1 sm:mt-2 leading-relaxed">
              Let <em className="font-semibold text-foreground">Teacher Translate</em><font color="#fde8cb">.</font> decipher your child's school report comments - giving access to a more informed (and funnier) understanding of their learning.
            </p>
          <button
            onClick={() => isAuthenticated ? navigate("/", { replace: true }) : navigate("/register")}
            className="w-full py-3.5 sm:py-4 bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-700 hover:to-pink-600 text-white font-bold rounded-2xl text-base sm:text-lg transition-all shadow-lg transform hover:scale-[1.02]">
            
            {isAuthenticated ? "✨ Continue" : "✨ Create Free Trial Account"}
          </button>

          {!isAuthenticated &&
          <p className="text-xs text-muted-foreground">
              No credit card required • Free trial included
            </p>
          }
          {!isAuthenticated &&
          <button
            onClick={() => base44.auth.redirectToLogin("/")}
            className="w-full py-2.5 sm:py-3 border-2 border-primary text-primary font-bold rounded-2xl text-sm sm:text-base transition-all hover:bg-primary/5">
            
              Already have an account? Log in
            </button>
          }
        </div>
      </div>

      {/* Testimonials */}
      <div className="pr-6 pl-6 pb-16">
        <TestimonialCarousel />
      </div>

      {/* Sample screenshots */}
      <div className="pr-6 pl-6 pb-16">
        <SampleScreenshots />
      </div>

      {/* About the developer */}
      <div className="px-6 pb-10">
        <AboutDeveloper />
      </div>

      {/* Second Continue button */}
      <div className="px-6 pb-8">
        <button
          onClick={() => isAuthenticated ? navigate("/", { replace: true }) : navigate("/register")}
          className="block w-full max-w-lg mx-auto py-4 bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-700 hover:to-pink-600 text-white font-bold rounded-2xl text-lg transition-all shadow-lg transform hover:scale-[1.02]">
          {isAuthenticated ? "✨ Continue" : "✨ Create Free Trial Account"}
        </button>
      </div>

      {/* Footer */}
      <footer className="text-center py-6 text-xs space-y-1 mt-auto" style={{ paddingBottom: "calc(1.5rem + env(safe-area-inset-bottom))" }}>
        <p className="text-gray-700">© {new Date().getFullYear()} Teacher Translate</p>
        <p className="flex items-center justify-center gap-3">
          <a href="/terms" target="_blank" rel="noopener noreferrer" className="text-gray-700 font-semibold underline underline-offset-2 hover:text-gray-900 transition-colors">Terms of Use</a>
          <span className="text-gray-500">·</span>
          <a href="/privacy" target="_blank" rel="noopener noreferrer" className="text-gray-700 font-semibold underline underline-offset-2 hover:text-gray-900 transition-colors">Privacy Policy</a>
        </p>
      </footer>
    </div>);

}