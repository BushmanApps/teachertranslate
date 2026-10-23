import { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2 } from "lucide-react";

const STEPS = (name) => [
  "Interpreting teacher's comments",
  "Matching to the Australian Curriculum",
  `Plotting ${name ? `${name}'s` : "your child's"} progress`,
  "Collecting supporting activities",
];

const getDisclaimers = (name) => {
  const childRef = name ? name : "your child";
  return [
    `The relevant comments are being selected from the report and encrypted before translation begins.`,
    `Teacher Translate does not know the complexity of ${childRef}'s learning - as is rightfully so!`,
    "This means that influences such as English as an additional language or dialect (EAL/D), extension class enrolment or individual adjustments, are not factored-in to the translations.",
    `Please allow for ${childRef}'s unique circumstances when reading the translations. As always, ${childRef}'s teacher is the best person to speak to if you have questions in relation to their report and school progress.`
  ];
};

export default function TranslatingScreen({ isBrutal, studentName }) {
  const steps = STEPS(studentName);
  const disclaimers = getDisclaimers(studentName);
  const [stepIndex, setStepIndex] = useState(0);
  const [visibleDisclaimers, setVisibleDisclaimers] = useState([]);
  const [showLargeReportMsg, setShowLargeReportMsg] = useState(false);
  const [showPatienceMsg, setShowPatienceMsg] = useState(false);
  const timersRef = useRef([]);

  // Advance through steps 0→1→2→3, with the last step holding for ~5s
  // Timings (ms after mount): step1 at 6000, step2 at 13000, step3 at 20000
  useEffect(() => {
    const delays = [6000, 13000, 20000];
    delays.forEach((delay, i) => {
      timersRef.current.push(setTimeout(() => setStepIndex(i + 1), delay));
    });
    // Show first line of "large reports" message after 45 seconds, second line 5s later
    timersRef.current.push(setTimeout(() => setShowLargeReportMsg(true), 45000));
    timersRef.current.push(setTimeout(() => setShowPatienceMsg(true), 50000));
    return () => timersRef.current.forEach(clearTimeout);
  }, []);

  // Show each disclaimer 500ms after its corresponding step becomes visible
  useEffect(() => {
    const delay = 500;
    disclaimers.forEach((_, i) => {
      if (disclaimers[i] && i <= stepIndex && !visibleDisclaimers.includes(i)) {
        timersRef.current.push(setTimeout(() => {
          setVisibleDisclaimers((prev) => [...prev, i]);
        }, delay));
      }
    });
    return () => {};
  }, [stepIndex, visibleDisclaimers]);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`rounded-2xl p-8 text-center space-y-4 ${
        isBrutal ? "bg-zinc-900 border border-zinc-800" : "bg-white border border-border"
      }`}
    >
      <div className="text-4xl animate-bounce">{isBrutal ? "🤣" : "🔍"}</div>

      <div className="space-y-3 min-h-[80px] flex flex-col items-center justify-center">
        {steps.map((step, i) => (
          <AnimatePresence key={i}>
            {i <= stepIndex && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex flex-col items-center gap-1 self-stretch"
              >
                <motion.p
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: i === stepIndex ? 1 : 0.35, y: 0 }}
                  className={`text-sm font-medium ${
                    i === stepIndex
                      ? isBrutal ? "text-orange-400" : "text-primary"
                      : isBrutal ? "text-zinc-400" : "text-muted-foreground"
                  }`}
                >
                  {i < stepIndex ? "✓ " : ""}{step}
                </motion.p>
                {disclaimers[i] && visibleDisclaimers.includes(i) && (
                  <TypedDisclaimer
                    text={disclaimers[i]}
                    isBrutal={isBrutal}
                  />
                )}
              </motion.div>
            )}
          </AnimatePresence>
        ))}
      </div>

      <Loader2 className={`w-6 h-6 animate-spin mx-auto ${isBrutal ? "text-orange-500" : "text-primary"}`} />

      <AnimatePresence>
        {showLargeReportMsg && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className={`text-sm font-medium space-y-1 ${isBrutal ? "text-orange-400" : "text-primary"}`}
          >
            <p>Reports may take a little while to translate. Please allow 2 mintues for a full report (English, Mathematics and General comments) to be translated. </p>
            <AnimatePresence>
              {showPatienceMsg && (
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                >
                  Thank you for your patience.
                </motion.p>
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function TypedDisclaimer({ text, isBrutal }) {
  const words = text.split(" ");
  const [wordCount, setWordCount] = useState(0);

  useEffect(() => {
    setWordCount(0);
    const interval = setInterval(() => {
      setWordCount((prev) => {
        if (prev >= words.length) {
          clearInterval(interval);
          return prev;
        }
        return prev + 1;
      });
    }, 120);
    return () => clearInterval(interval);
  }, [text]);

  return (
    <p
      className={`text-xs italic font-medium w-full text-left self-stretch ${
        isBrutal ? "text-amber-400/80" : "text-amber-600"
      }`}
    >
      {words.slice(0, wordCount).join(" ")}
      {wordCount < words.length && <span className="animate-pulse">▋</span>}
    </p>
  );
}