import { useState } from "react";
import { createPortal } from "react-dom";
import { Download, Loader2, X } from "lucide-react";
import { motion } from "framer-motion";
import { saveSinglePDF, saveCombinedPDF } from "@/lib/generatePDF";

const PDF_MODES = [
  { key: "honest_helpful", label: "Honest", icon: "😊", desc: "Compassionate plain-English translation" },
  { key: "hilarious", label: "Hilarious", icon: "🤣", desc: "A funny, share-worthy translation" },
  { key: "brutal", label: "Brutal", icon: "💥", desc: "Very direct, slightly offensive truth" },
  { key: "all", label: "All modes", icon: "📋", desc: "All three translations — each on its own page" },
];

function buildTranslationForMode(result, mode, studentName, studentYear) {
  return {
    mode,
    student_name: studentName,
    student_year: studentYear,
    honest_helpful_translation: result.overall_honest_helpful,
    brutal_translation: result.overall_brutal,
    brutal_direct_translation: result.overall_brutal_direct,
    performance_level: result.overall_performance_level,
    performance_summary: result.overall_performance_summary,
    sections: result.sections || [],
  };
}

export default function ExportPDFButton({ result, studentName, studentYear, mode, isBrutal, isOpen, onOpen, onClose }) {
  const [loading, setLoading] = useState(false);

  const handleExport = async (selectedMode) => {
    onClose();
    setLoading(true);
    try {
      if (selectedMode === "all") {
        const translations = ["honest_helpful", "hilarious", "brutal"].map((m) =>
          buildTranslationForMode(result, m, studentName, studentYear)
        );
        await saveCombinedPDF(translations);
      } else {
        const t = buildTranslationForMode(result, selectedMode, studentName, studentYear);
        await saveSinglePDF(t, studentName);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        onClick={onOpen}
        disabled={loading}
        className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-xl transition-all select-none disabled:opacity-50 ${
          isBrutal
            ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700 border border-zinc-700"
            : "bg-muted text-muted-foreground hover:bg-border border border-border"
        }`}
      >
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
        Export PDF
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
            className={`fixed left-1/2 top-1/2 z-[70] w-80 max-w-[92vw] rounded-2xl shadow-xl border p-3 space-y-1.5 ${
              isBrutal ? "bg-zinc-900 border-zinc-700" : "bg-white border-border"
            }`}
          >
            <div className="flex items-center justify-between px-2 py-1">
              <span className={`font-fredoka text-lg font-bold ${isBrutal ? "text-orange-400" : "text-foreground"}`}>
                Export PDF
              </span>
              <button onClick={onClose} className="p-1 rounded-lg text-muted-foreground hover:text-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="px-1 py-1 space-y-1">
              {PDF_MODES.map((m) => (
                <button
                  key={m.key}
                  onClick={() => handleExport(m.key)}
                  className={`w-full flex items-start gap-3 px-3 py-2.5 rounded-xl text-left transition-all ${
                    isBrutal ? "hover:bg-zinc-800 text-zinc-100" : "hover:bg-muted text-foreground"
                  }`}
                >
                  <span className="text-2xl leading-none mt-0.5">{m.icon}</span>
                  <div className="flex-1">
                    <p className="text-sm font-bold">{m.label}</p>
                    <p className={`text-xs ${isBrutal ? "text-zinc-500" : "text-muted-foreground"}`}>{m.desc}</p>
                  </div>
                </button>
              ))}
            </div>
          </motion.div>
        </>,
        document.body
      )}
    </>
  );
}