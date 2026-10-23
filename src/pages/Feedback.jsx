import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useBackToHome } from "@/hooks/useBackToHome";
import { Loader2, CheckCircle, Send, Info } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Switch } from "@/components/ui/switch";
import { base44 } from "@/api/base44Client";
import AppHeader from "@/components/AppHeader";
import { useDarkMode } from "@/hooks/useDarkMode";
import { useThemeColor } from "@/hooks/useThemeColor";

export default function Feedback() {
  const navigate = useNavigate();
  useBackToHome();
  const { darkMode } = useDarkMode();
  useThemeColor({ isDark: darkMode });
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [feedbackType, setFeedbackType] = useState("General");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [emailError, setEmailError] = useState("");
  const [copyRequested, setCopyRequested] = useState(false);
  const [showCopyInfo, setShowCopyInfo] = useState(false);
  const [currentUserEmail, setCurrentUserEmail] = useState("");

  useEffect(() => {
    base44.auth.me().then((u) => {
      if (u?.email) setCurrentUserEmail(u.email.toLowerCase());
    }).catch(() => {});
  }, []);

  const handleToggleCopy = (checked) => {
    setCopyRequested(checked);
    if (checked) setShowCopyInfo(true);
  };

  const validateEmail = (value) => {
    if (!value.trim()) return true;
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(value.trim());
  };

  const handleSubmit = async () => {
    if (!message.trim()) return;
    if (!validateEmail(email)) {
      setEmailError("Please enter a valid email address.");
      return;
    }
    setEmailError("");
    setSending(true);
    try {
      await base44.functions.invoke("submitFeedback", {
        name,
        email,
        feedbackType,
        message,
        copyRequested,
      });
      setSent(true);
      base44.analytics.track({ eventName: "feedback_submitted", properties: { feedbackType } });
    } catch (e) {
      console.error("Failed to send feedback:", e);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <AppHeader title="Feedback" />

      <div className="max-w-lg mx-auto px-4 py-6 pb-28">
        <div className="rounded-3xl p-5 bg-[#a8d8c8]/80 border border-border space-y-4">
          <p className="text-sm text-muted-foreground">
            We'd love to hear your feedback — suggestions, bug reports, or just a kind word. It all helps us make Teacher Translate better for you.
          </p>
          <div className="space-y-2">
            <label className="text-sm font-bold">Your name (optional)</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Sarah" className="w-full rounded-xl border px-4 py-2.5 text-sm bg-background border-input focus:outline-none focus:ring-2 focus:ring-ring" />
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-bold">Your email (optional)</label>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Send me a copy</span>
                <Switch checked={copyRequested} onCheckedChange={handleToggleCopy} />
              </div>
            </div>
            {copyRequested && (
              <div className="flex items-start gap-2 text-xs text-muted-foreground bg-muted rounded-lg px-3 py-2">
                <Info className="w-4 h-4 shrink-0 mt-0.5" />
                <span>
                  For privacy reasons, a copy can only be sent to your registered Teacher Translate login email.
                  {currentUserEmail ? " If the email below matches your login, you'll receive a copy." : ""}
                </span>
              </div>
            )}
            <input
              value={email}
              onChange={(e) => { setEmail(e.target.value); setEmailError(""); }}
              placeholder="e.g. sarah@email.com.au"
              className={`w-full rounded-xl border px-4 py-2.5 text-sm bg-background border-input focus:outline-none focus:ring-2 focus:ring-ring ${emailError ? "border-red-500" : ""}`}
            />
            {emailError && <p className="text-xs text-red-500 mt-1">{emailError}</p>}
          </div>
          <div className="space-y-2">
            <label className="text-sm font-bold">Feedback type</label>
            <div className="grid grid-cols-2 gap-2">
              {["General", "Bug Report", "Feature Request", "Question"].map((t) => (
                <button key={t} onClick={() => setFeedbackType(t)} className={`py-2 px-3 rounded-xl text-xs font-semibold border-2 transition-all select-none ${
                  feedbackType === t ? "border-primary bg-primary text-primary-foreground" : "border-primary-foreground text-foreground hover:border-primary/50"
                }`}>
                  {t}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-bold">Your feedback *</label>
            <textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Tell us what you think..." rows={5} className="w-full rounded-xl border px-4 py-2.5 text-sm bg-background border-input focus:outline-none focus:ring-2 focus:ring-ring resize-none" />
          </div>
          <button onClick={handleSubmit} disabled={!message.trim() || sending} className="w-full py-3 rounded-2xl font-bold text-sm bg-primary text-primary-foreground disabled:opacity-40 flex items-center justify-center gap-2 select-none">
            {sending ? <><Loader2 className="w-4 h-4 animate-spin" /> Sending...</> : <><Send className="w-4 h-4" /> Send Feedback</>}
          </button>
        </div>
      </div>

      {/* Copy request info popup */}
      <AnimatePresence>
        {showCopyInfo && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
            onClick={() => setShowCopyInfo(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-sm rounded-3xl p-6 bg-white border border-border text-center space-y-4 shadow-2xl"
            >
              <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mx-auto">
                <Info className="w-6 h-6 text-primary" />
              </div>
              <h2 className="font-fredoka text-lg text-foreground">Send me a copy</h2>
              <p className="text-sm text-muted-foreground leading-relaxed text-left">
                If you enter the same email address you used to log in to Teacher Translate, a copy of your feedback will be sent to that email.
              </p>
              <p className="text-xs text-muted-foreground leading-relaxed text-left">
                For privacy reasons, we can only send a copy to your registered app login email — we won't send copies to any other address.
              </p>
              <button
                onClick={() => setShowCopyInfo(false)}
                className="w-full py-3 bg-primary text-primary-foreground font-bold rounded-xl text-sm"
              >
                Got it
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Success dialog */}
      <AnimatePresence>
        {sent && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
            onClick={() => navigate("/")}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-sm rounded-3xl p-8 bg-white border border-border text-center space-y-4 shadow-2xl"
            >
              <CheckCircle className="w-16 h-16 mx-auto text-green-600" />
              <h2 className="font-fredoka text-xl text-foreground">Feedback Received — Thank You!</h2>
              <p className="text-sm text-muted-foreground">
                Your feedback has been sent to our team. We genuinely appreciate you taking the time to share your thoughts.
              </p>
              <button
                onClick={() => navigate("/")}
                className="w-full py-3 bg-primary text-primary-foreground font-bold rounded-xl text-sm"
              >
                Back to Home
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}