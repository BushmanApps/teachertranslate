import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { Loader2, ArrowLeft, Mail, Lock, ShieldCheck, Eye, EyeOff } from "lucide-react";

const GOOGLE_ICON = (
  <svg className="w-5 h-5" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
);
const APPLE_ICON = (
  <svg className="w-5 h-5 text-black" fill="currentColor" viewBox="0 0 24 24"><path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.32 2.58-2.34 4.5-3.74 4.25z"/></svg>
);
const FACEBOOK_ICON = (
  <svg className="w-5 h-5" fill="#1877F2" viewBox="0 0 24 24"><path d="M24 12.07C24 5.41 18.63 0 12 0S0 5.41 0 12.07c0 6.02 4.39 11.01 10.13 11.93v-8.44H7.08v-3.49h3.05V9.41c0-3.02 1.79-4.69 4.53-4.69 1.31 0 2.68.24 2.68.24v2.97h-1.51c-1.49 0-1.96.93-1.96 1.89v2.25h3.33l-.53 3.49h-2.8v8.44C19.61 23.08 24 18.09 24 12.07z"/></svg>
);

export default function Register() {
  const navigate = useNavigate();
  const [step, setStep] = useState("signup"); // "signup" | "otp"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const handleRegister = async (e) => {
    e.preventDefault();
    setError("");
    if (!email || !password) {
      setError("Please enter your email and password.");
      return;
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await base44.auth.register({ email, password });
      setStep("otp");
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    setError("");
    if (!otpCode) {
      setError("Please enter the verification code.");
      return;
    }
    setLoading(true);
    try {
      await base44.auth.verifyOtp({ email, otpCode });
      // Send brand-new users straight to the Consent screen after email
      // verification, instead of landing them back on the login page.
      navigate("/consent", { replace: true });
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "Invalid code. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleResendOtp = async () => {
    setError("");
    setLoading(true);
    try {
      await base44.auth.resendOtp(email);
    } catch (err) {
      setError("Failed to resend code. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center px-6 py-12 pt-safe"
      style={{
        backgroundImage: `url('https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets/images/public/69fc81cf4f6a0ae5ab617e2b/e47c595be_generated_image.png')`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundAttachment: "fixed",
      }}
    >
      <div className="bg-[#fde8cb]/95 backdrop-blur-sm rounded-3xl shadow-xl p-8 sm:p-10 max-w-md w-full space-y-6">
        <button
          onClick={() => navigate("/welcome")}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>

        <img
          src="https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets/images/public/69fc81cf4f6a0ae5ab617e2b/c7bffff4e_TTLogo01.png"
          alt="Teacher Translate"
          className="w-20 h-20 object-contain mx-auto"
        />

        {step === "signup" ? (
          <>
            <div className="text-center">
              <h1 className="font-fredoka text-3xl text-foreground">Create Account</h1>
              <p className="text-sm text-muted-foreground mt-1">Start your free trial (3 free translations) — no credit card required</p>
            </div>

            <div className="space-y-2.5">
              <button
                type="button"
                onClick={() => base44.auth.loginWithProvider("google", "/")}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2.5 py-2.5 bg-white hover:bg-gray-50 border-2 border-gray-200 text-foreground font-semibold rounded-2xl text-sm transition-all disabled:opacity-60"
              >
                {GOOGLE_ICON}
                Continue with Google
              </button>
              <button
                type="button"
                onClick={() => base44.auth.loginWithProvider("apple", "/")}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2.5 py-2.5 bg-white hover:bg-gray-50 border-2 border-gray-200 text-black font-semibold rounded-2xl text-sm transition-all disabled:opacity-60"
              >
                {APPLE_ICON}
                Continue with Apple
              </button>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex-1 h-px bg-border" />
              <span className="text-xs text-muted-foreground font-semibold">OR</span>
              <div className="flex-1 h-px bg-border" />
            </div>

            <form onSubmit={handleRegister} className="space-y-4">
              <div className="space-y-1">
                <label className="text-sm font-bold">Email</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    autoComplete="email"
                    className="w-full rounded-xl border border-input bg-background pl-10 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-sm font-bold">Password</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="At least 8 characters"
                    autoComplete="new-password"
                    className="w-full rounded-xl border border-input bg-background pl-10 pr-10 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                    tabIndex={-1}
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>

                  <div className="space-y-1">
                  <label className="text-sm font-bold">Confirm Password</label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <input
                      type={showConfirm ? "text" : "password"}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Re-enter your password"
                      autoComplete="new-password"
                      className="w-full rounded-xl border border-input bg-background pl-10 pr-10 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirm(!showConfirm)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                      tabIndex={-1}
                    >
                      {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  </div>
                  </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-700 hover:to-pink-600 text-white font-bold rounded-2xl text-base transition-all shadow-lg disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                {loading ? "Creating account..." : "Create Free Trial Account"}
              </button>
            </form>

            <div className="text-center">
              <button
                onClick={() => base44.auth.redirectToLogin("/")}
                className="text-sm text-primary font-semibold hover:underline"
              >
                Already have an account? Log in
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="text-center">
              <div className="w-16 h-16 mx-auto rounded-full bg-primary/10 flex items-center justify-center mb-3">
                <ShieldCheck className="w-8 h-8 text-primary" />
              </div>
              <h1 className="font-fredoka text-2xl text-foreground">Verify Your Email</h1>
              <p className="text-sm text-muted-foreground mt-1">
                We sent a verification code to <strong className="text-foreground">{email}</strong>
              </p>
            </div>

            <form onSubmit={handleVerifyOtp} className="space-y-4">
              <div className="space-y-1">
                <label className="text-sm font-bold">Verification Code</label>
                <input
                  type="text"
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ""))}
                  placeholder="Enter code"
                  autoComplete="one-time-code"
                  maxLength={6}
                  className="w-full rounded-xl border border-input bg-background px-4 py-2.5 text-center text-xl tracking-[0.5em] font-bold focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-700 hover:to-pink-600 text-white font-bold rounded-2xl text-base transition-all shadow-lg disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                {loading ? "Verifying..." : "Verify & Continue"}
              </button>
            </form>

            <div className="text-center">
              <button
                onClick={handleResendOtp}
                disabled={loading}
                className="text-sm text-primary font-semibold hover:underline disabled:opacity-60"
              >
                Didn't receive a code? Resend
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}