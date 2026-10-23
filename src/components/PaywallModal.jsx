import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { base44 } from "@/api/base44Client";
import { Loader2 } from "lucide-react";

const FEATURES = [
  { icon: "♾️", text: "Unlimited report translations" },
  { icon: "✍️", text: "Write Back — translate your thoughts to teacher talk" },
  { icon: "🤣", text: "Full Hilarious Mode access" },
  { icon: "📊", text: "Detailed year-level assessments" },
  { icon: "🏠", text: "Curriculum-linked supporting activities to try at home" },
  { icon: "🗂️", text: "View all previous translations" },
];

const VARIANTS = {
  limit: {
    emoji: "🔓",
    heading: "You've used your 3 free translations!",
    sub: "Subscribe to keep decoding teacher-speak.",
  },
  feature: {
    emoji: "✨",
    heading: "This is a Pro feature",
    sub: "Upgrade to unlock this and everything else\nTeacher Translate has to offer.",
  },
};

export default function PaywallModal({ isOpen, onClose, isBrutal, variant = "limit" }) {
  const content = VARIANTS[variant] || VARIANTS.limit;
  const [loading, setLoading] = useState(false);

  async function handleSubscribe() {
    // Remember that a checkout is in progress so the resume hook can
    // re-check subscription status when the app returns to the foreground.
    try { sessionStorage.setItem("tt_checkout_pending", "1"); } catch {}

    const isFramed = window.self !== window.top;
    const checkoutTab = isFramed ? window.open("", "_blank") : null;
    if (isFramed && !checkoutTab) {
      alert("Please allow popups to continue to checkout.");
      try { sessionStorage.removeItem("tt_checkout_pending"); } catch {}
      return;
    }
    if (checkoutTab) checkoutTab.opener = null;

    setLoading(true);
    try {
      const res = await base44.functions.invoke("createCheckout", {});
      if (res.data?.url) {
        if (checkoutTab) {
          checkoutTab.location.replace(res.data.url);
        } else {
          window.location.href = res.data.url;
        }
      }
    } catch (e) {
      checkoutTab?.close();
      try { sessionStorage.removeItem("tt_checkout_pending"); } catch {}
      alert("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            className={`w-full max-w-sm rounded-3xl overflow-hidden shadow-2xl ${isBrutal ? "bg-zinc-900" : "bg-white"}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-gradient-to-br from-purple-600 to-pink-500 p-6 text-white text-center space-y-2">
              <div className="text-6xl">{content.emoji}</div>
              <h2 className="font-fredoka text-2xl">{content.heading}</h2>
              <p className="text-sm text-white/80">
                {variant === "feature" ? (
                  <>
                    Upgrade to unlock this and everything else<br />
                    <strong>Teacher Translate</strong> has to offer.
                  </>
                ) : (
                  content.sub
                )}
              </p>
            </div>

            <div className="p-6 space-y-4">
              <div className="space-y-3">
                {FEATURES.map((f, i) => (
                  <div key={i} className="flex items-center gap-3 text-sm">
                    <span className="text-2xl">{f.icon}</span>
                    <span className={`font-medium ${isBrutal ? "text-zinc-200" : "text-foreground"}`}>{f.text}</span>
                  </div>
                ))}
              </div>

              <button
                className="w-full py-3.5 bg-gradient-to-r from-purple-600 to-pink-500 text-white font-bold rounded-2xl hover:opacity-90 transition-all shadow-lg flex items-center justify-center gap-2 disabled:opacity-70"
                onClick={handleSubscribe}
                disabled={loading}
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {loading ? "Loading..." : (
                  <div className="flex items-center gap-3">
                    <div className="flex flex-col items-center gap-0.5">
                      <div className="text-xl">$14.95 first year</div>
                      <div className="text-xs opacity-80">$29.95/year</div>
                    </div>
                    <div className="text-4xl">🚀</div>
                  </div>
                )}
              </button>

              <button
                onClick={onClose}
                className={`w-full py-2 text-sm transition-all ${isBrutal ? "text-zinc-500 hover:text-zinc-300" : "text-muted-foreground hover:text-foreground"}`}
              >
                Maybe later
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}