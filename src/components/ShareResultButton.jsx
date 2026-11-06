import { useState } from "react";
import { createPortal } from "react-dom";
import { Share2, Mail, Copy, Check, X, Lock, ExternalLink, Loader2 } from "lucide-react";
import { motion } from "framer-motion";
import { base44 } from "@/api/base44Client";
import { buildFullHTML, openFullResultsHTML } from "@/lib/generateShareHTML";
import { copyText } from "@/lib/clipboard";
import { toast } from "@/components/ui/use-toast";

const APP_URL = "https://TeacherTranslate.com.au";
const APP_CREDIT = `\n\n🍎 Decoded with Teacher Translate\n🔗 ${APP_URL}`;
const DISCLAIMER = "⚠️ Disclaimer: This translation is AI-generated for informational purposes only. Always consult your child's teacher directly for accurate information.";

function buildSocialExtract(result, shareMode, studentName) {
  const parts = [];
  if (shareMode === "honest_helpful" || shareMode === "all") {
    const summary = result.overall_honest_helpful;
    const trimmed = summary && summary.length > 280 ? summary.slice(0, 277) + "…" : summary;
    const kidRef = studentName ? `${studentName}'s` : "my child's";
    parts.push(`😊 Decoded ${kidRef} school report!\n\n"${trimmed}"`);
  }
  if (shareMode === "hilarious" || shareMode === "all") {
    const summary = result.overall_brutal;
    const trimmed = summary && summary.length > 280 ? summary.slice(0, 277) + "…" : summary;
    const kidRef = studentName ? `${studentName}'s` : "my child's";
    parts.push(`🤣 What ${kidRef} teacher REALLY wanted to say…\n\n"${trimmed}"`);
  }
  if (shareMode === "brutal" || shareMode === "all") {
    const summary = result.overall_brutal_direct || result.overall_brutal;
    const trimmed = summary && summary.length > 280 ? summary.slice(0, 277) + "…" : summary;
    const kidRef = studentName ? `${studentName}'s` : "my child's";
    parts.push(`💥 The brutal truth about ${kidRef} report…\n\n"${trimmed}"`);
  }
  return parts.join("\n\n---\n\n") + APP_CREDIT;
}

function buildFullText(result, shareMode, studentName, studentYear) {
  const name = studentName ? `Student: ${studentName} (${studentYear})` : `Year level: ${studentYear}`;

  const buildModeBlock = (m) => {
    const kidRef = studentName ? `${studentName}'s` : "my child's";
    const header = m === "brutal" ? `💥 THE BRUTAL TRUTH ABOUT ${kidRef.toUpperCase()} REPORT` : m === "hilarious" ? `🤣 THE HILARIOUS REALITY ABOUT ${kidRef.toUpperCase()} REPORT` : `😊 DECODING ${kidRef.toUpperCase()} SCHOOL REPORT`;
    const summary = m === "brutal" ? (result.overall_brutal_direct || result.overall_brutal) : m === "hilarious" ? result.overall_brutal : result.overall_honest_helpful;

    let sections = "";
    if (result.sections && result.sections.length > 0) {
      sections = "\n\n" + result.sections.map(s => {
        const text = m === "brutal" ? (s.brutal_direct || s.brutal) : m === "hilarious" ? s.brutal : s.honest_helpful;
        const quote = s.original_excerpt ? `"${s.original_excerpt}"\n` : "";
        return `📚 ${s.subject_or_area}\n${quote}${text}`;
      }).join("\n\n");
    }

    return `${header}\n${name}\n\n${summary}${sections}`;
  };

  const blocks = [];
  if (shareMode === "honest_helpful" || shareMode === "all") blocks.push(buildModeBlock("honest_helpful"));
  if (shareMode === "hilarious" || shareMode === "all") blocks.push(buildModeBlock("hilarious"));
  if (shareMode === "brutal" || shareMode === "all") blocks.push(buildModeBlock("brutal"));

  return blocks.join("\n\n══════════════\n\n") + `\n\n${DISCLAIMER}${APP_CREDIT}`;
}

const SHARE_MODES = [
  { key: "honest_helpful", label: "Honest", icon: "😊", desc: "Compassionate plain-English translation" },
  { key: "hilarious", label: "Hilarious", icon: "🤣", desc: "A funny, share-worthy translation" },
  { key: "brutal", label: "Brutal", icon: "💥", desc: "Very direct, slightly offensive truth" },
  { key: "all", label: "All", icon: "📋", desc: "Include all three translations" },
];

export default function ShareResultButton({ result, mode, studentName, studentYear, isBrutal, isSubscribed, onUpgrade, isOpen, onOpen, onClose }) {
  const [shareMode, setShareMode] = useState(null);
  const [copied, setCopied] = useState(null);
  const [emailSending, setEmailSending] = useState(false);
  const [emailSent, setEmailSent] = useState(false);
  const [recipientEmail, setRecipientEmail] = useState("");
  const [showRecipientInput, setShowRecipientInput] = useState(false);
  const [recipientSending, setRecipientSending] = useState(false);
  const [recipientSent, setRecipientSent] = useState(false);

  const socialText = buildSocialExtract(result, shareMode || "honest_helpful", studentName);
  const fullText = buildFullText(result, shareMode || "honest_helpful", studentName, studentYear);

  const handleCopy = async (text, key) => {
    try {
      await copyText(text);
      setCopied(key);
      setTimeout(() => setCopied(null), 2000);
    } catch (error) {
      toast({ title: "Couldn't copy the text", description: "Please try again." });
    }
  };

  const handleNativeShare = async (text) => {
    try {
      await navigator.share({ title: "Teacher Translate Results", text });
    } catch (e) {
      if (e.name !== "AbortError") {
        await copyText(text);
        setCopied("social");
        setTimeout(() => setCopied(null), 2000);
      }
    }
  };

  const handleEmail = () => {
    const html = buildFullHTML(result, shareMode || "honest_helpful", studentName, studentYear);
    openFullResultsHTML(html);
  };

  const handleEmailSend = async () => {
    setEmailSending(true);
    setEmailSent(false);
    try {
      await base44.functions.invoke("sendReportEmail", {
        translationId: result.id,
        shareMode: shareMode || "honest_helpful",
      });
      setEmailSent(true);
      setTimeout(() => setEmailSent(false), 3000);
    } catch (e) {
      console.error("Email send failed:", e);
      alert("Sorry, we couldn't send the email. Please try again.");
    } finally {
      setEmailSending(false);
    }
  };

  const handleSendToRecipient = async () => {
    const to = recipientEmail.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(to)) {
      toast({ title: "Please enter a valid email address." });
      return;
    }
    setRecipientSending(true);
    setRecipientSent(false);
    try {
      await base44.functions.invoke("sendReportEmail", {
        translationId: result.id,
        shareMode: shareMode || "honest_helpful",
        to,
      });
      setRecipientSent(true);
      setRecipientEmail("");
      setTimeout(() => { setRecipientSent(false); setShowRecipientInput(false); }, 2500);
    } catch (e) {
      console.error("Recipient email send failed:", e);
      alert("Sorry, we couldn't send the email. Please try again.");
    } finally {
      setRecipientSending(false);
    }
  };

  const handleShareFacebook = async (text) => {
    try {
      await copyText(text);
      setCopied("fb");
      toast({ title: "Copied to clipboard!", description: "Paste your translation into the Facebook post." });
      setTimeout(() => {
        setCopied(null);
        window.open(`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(APP_URL)}`, "_blank");
      }, 1200);
    } catch (error) {
      toast({ title: "Couldn't copy the extract", description: "Please try again." });
    }
  };

  const handleShareX = (text) => {
    const tweet = encodeURIComponent(text.slice(0, 280));
    window.open(`https://twitter.com/intent/tweet?text=${tweet}`, "_blank");
  };

  const handleShareWhatsApp = (text) => {
    const msg = encodeURIComponent(text);
    window.open(`https://wa.me/?text=${msg}`, "_blank");
  };

  const canNativeShare = typeof navigator !== "undefined" && !!navigator.share;

  const btnBase = `flex items-center gap-2 w-full px-4 py-2.5 rounded-xl text-sm font-semibold transition-all text-left`;
  const btnStyle = isBrutal
    ? `${btnBase} bg-zinc-800 hover:bg-zinc-700 text-zinc-100`
    : `${btnBase} bg-muted hover:bg-border text-foreground`;

  const sectionLabel = (label) => (
    <p className={`text-xs font-bold uppercase tracking-wide px-2 pt-2 pb-1 ${isBrutal ? "text-zinc-500" : "text-muted-foreground"}`}>
      {label}
    </p>
  );

  return (
    <div className="relative">
      <button
        onClick={() => { setShareMode(null); onOpen(); }}
        className={`flex items-center gap-2 px-4 py-2.5 rounded-2xl text-sm font-bold transition-all ${
          isBrutal
            ? "bg-orange-600 hover:bg-orange-700 text-white"
            : "bg-primary hover:bg-primary/90 text-primary-foreground"
        }`}
      >
        <Share2 className="w-4 h-4" />
        Share
      </button>

      {isOpen && createPortal(
        <>
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="fixed inset-0 z-[60] bg-black/30 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, x: "-50%", y: "-50%" }}
            animate={{ opacity: 1, scale: 1, x: "-50%", y: "-50%" }}
            className={`fixed left-1/2 top-1/2 z-[70] w-80 max-w-[92vw] max-h-[calc(100dvh-1.5rem)] overflow-y-auto overscroll-contain rounded-2xl shadow-xl border p-3 space-y-1.5 ${
              isBrutal ? "bg-zinc-900 border-zinc-700" : "bg-white border-border"
            }`}
          >
              <div className="flex items-center justify-between px-2 py-1">
                <span className={`font-fredoka text-lg font-bold ${isBrutal ? "text-orange-400" : "text-foreground"}`}>
                  {shareMode ? "Share" : "Which translation?"}
                </span>
                <button onClick={onClose} className="p-1 rounded-lg text-muted-foreground hover:text-foreground">
                  <X className="w-4 h-4" />
                </button>
              </div>

              {!shareMode ? (
                <div className="px-1 py-1 space-y-1">
                  {SHARE_MODES.map((sm) => (
                    <button
                      key={sm.key}
                      onClick={() => setShareMode(sm.key)}
                      className={`w-full flex items-start gap-3 px-3 py-2.5 rounded-xl text-left transition-all ${
                        isBrutal ? "hover:bg-zinc-800 text-zinc-100" : "hover:bg-muted text-foreground"
                      }`}
                    >
                      <span className="text-2xl leading-none mt-0.5">{sm.icon}</span>
                      <div className="flex-1">
                        <p className="text-sm font-bold">{sm.label}</p>
                        <p className={`text-xs ${isBrutal ? "text-zinc-500" : "text-muted-foreground"}`}>{sm.desc}</p>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <>
                  {sectionLabel("Social extract")}
                  <div className="flex gap-2 px-2 py-1">
                    <div className="relative flex-1">
                      <button
                        onClick={() => handleShareFacebook(socialText)}
                        title="Copies text to clipboard, then opens Facebook"
                        className="w-full flex items-center justify-center py-2.5 rounded-xl bg-[#1877F2] hover:bg-[#1665d8] text-white transition-all"
                      >
                        {copied === "fb"
                          ? <Check className="w-5 h-5" />
                          : <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24"><path d="M24 12.073C24 5.405 18.627 0 12 0S0 5.405 0 12.073C0 18.1 4.388 23.094 10.125 24v-8.437H7.078v-3.49h3.047V9.41c0-3.025 1.792-4.697 4.533-4.697 1.312 0 2.686.235 2.686.235v2.97h-1.513c-1.491 0-1.956.93-1.956 1.886v2.27h3.328l-.532 3.49h-2.796V24C19.612 23.094 24 18.1 24 12.073z"/></svg>
                        }
                      </button>
                      {copied === "fb" && (
                        <div className="absolute -top-7 left-1/2 -translate-x-1/2 whitespace-nowrap text-xs bg-black text-white px-2 py-0.5 rounded-lg">
                          Copied! Paste in Facebook
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => handleShareX(socialText)}
                      title="Post to X"
                      className="flex-1 flex items-center justify-center py-2.5 rounded-xl bg-black hover:bg-zinc-800 text-white transition-all"
                    >
                      <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.73-8.835L1.254 2.25H8.08l4.259 5.631 5.905-5.631zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
                    </button>
                    <button
                      onClick={() => handleShareWhatsApp(socialText)}
                      title="Share on WhatsApp"
                      className="flex-1 flex items-center justify-center py-2.5 rounded-xl bg-[#25D366] hover:bg-[#1fba58] text-white transition-all"
                    >
                      <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
                    </button>
                  </div>
                  {canNativeShare && (
                    <button onClick={() => handleNativeShare(socialText)} className={btnStyle}>
                      <Share2 className="w-4 h-4 shrink-0" />
                      Share via…
                    </button>
                  )}
                  <button onClick={() => handleCopy(socialText, "social")} className={btnStyle}>
                    {copied === "social" ? <Check className="w-4 h-4 shrink-0 text-green-500" /> : <Copy className="w-4 h-4 shrink-0" />}
                    {copied === "social" ? "Copied!" : "Copy extract"}
                  </button>

                  <div className={`mx-2 border-t ${isBrutal ? "border-zinc-700" : "border-border"}`} />

                  {sectionLabel("Full results")}
                  {isSubscribed ? (
                    <>
                      <button onClick={() => handleEmail()} className={btnStyle}>
                        <ExternalLink className="w-4 h-4 shrink-0" />
                        Open report in a new window
                      </button>
                      <button onClick={() => handleEmailSend()} className={btnStyle} disabled={emailSending}>
                        {emailSending
                          ? <Loader2 className="w-4 h-4 shrink-0 animate-spin" />
                          : emailSent
                            ? <Check className="w-4 h-4 shrink-0 text-green-500" />
                            : <Mail className="w-4 h-4 shrink-0" />}
                        {emailSending ? "Sending..." : emailSent ? "Email sent!" : "Email me the full report"}
                      </button>
                      {!showRecipientInput ? (
                        <button onClick={() => setShowRecipientInput(true)} className={btnStyle}>
                          <Mail className="w-4 h-4 shrink-0" />
                          Email the full report to someone
                        </button>
                      ) : (
                        <div className="px-2 py-1 space-y-2">
                          <div className="flex items-center gap-2">
                            <input
                              type="email"
                              value={recipientEmail}
                              onChange={(e) => setRecipientEmail(e.target.value)}
                              placeholder="recipient@email.com"
                              className={`flex-1 rounded-xl border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring ${
                                isBrutal ? "bg-zinc-800 border-zinc-600 text-zinc-100" : "bg-background border-input"
                              }`}
                            />
                            <button
                              onClick={() => setShowRecipientInput(false)}
                              className={`p-2 rounded-xl ${isBrutal ? "text-zinc-400 hover:bg-zinc-800" : "text-muted-foreground hover:bg-muted"}`}
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                          <button
                            onClick={handleSendToRecipient}
                            disabled={recipientSending}
                            className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold transition-all disabled:opacity-60 ${
                              isBrutal ? "bg-orange-600 hover:bg-orange-700 text-white" : "bg-primary hover:bg-primary/90 text-primary-foreground"
                            }`}
                          >
                            {recipientSending ? <Loader2 className="w-4 h-4 animate-spin" /> : recipientSent ? <Check className="w-4 h-4" /> : <Mail className="w-4 h-4" />}
                            {recipientSending ? "Sending..." : recipientSent ? "Sent!" : "Send report"}
                          </button>
                        </div>
                      )}
                      <button onClick={() => handleCopy(fullText, "full")} className={btnStyle}>
                        {copied === "full" ? <Check className="w-4 h-4 shrink-0 text-green-500" /> : <Copy className="w-4 h-4 shrink-0" />}
                        {copied === "full" ? "Copied!" : "Copy full results"}
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => onUpgrade?.()}
                      className={`${btnBase} opacity-60`}
                    >
                      <Lock className="w-4 h-4 shrink-0" />
                      Full results — Pro only
                    </button>
                  )}
                </>
              )}
            </motion.div>
          </>,
          document.body
        )}
    </div>
  );
}