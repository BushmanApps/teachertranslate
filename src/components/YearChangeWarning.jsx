import { createPortal } from "react-dom";
import { AlertTriangle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export default function YearChangeWarning({ year, isBrutal, isSubscribed, onCancel, onConfirm }) {
  return createPortal(
    <AnimatePresence>
      {year && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            className={`w-full max-w-sm rounded-3xl p-6 space-y-4 shadow-2xl ${isBrutal ? "bg-zinc-900 text-white" : "bg-white"}`}
          >
            <div className="flex items-center gap-3">
              <AlertTriangle className={`w-6 h-6 flex-shrink-0 ${isBrutal ? "text-orange-400" : "text-amber-500"}`} />
              <h3 className={`font-fredoka text-lg ${isBrutal ? "text-orange-400" : "text-primary"}`}>New Translation Required</h3>
            </div>
            <p className={`text-sm leading-relaxed ${isBrutal ? "text-zinc-300" : "text-foreground/80"}`}>
              Changing the year level will re-translate the current report using <strong>{year}</strong> curriculum standards and supporting resources.{!isSubscribed && " This will use up one of your free scans."}
            </p>
            <div className="flex gap-3">
              <button onClick={onCancel} className={`flex-1 py-2.5 rounded-2xl font-bold text-sm border select-none ${isBrutal ? "border-zinc-700 text-zinc-300" : "border-border text-foreground hover:bg-muted"}`}>
                Cancel
              </button>
              <button onClick={onConfirm} className={`flex-1 py-2.5 rounded-2xl font-bold text-sm select-none ${isBrutal ? "bg-orange-600 text-white" : "bg-primary text-primary-foreground"}`}>
                Yes, Re-translate
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}