import { useState } from "react";
import { X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const YEAR_LEVELS = [
  "Kindergarten / Prep",
  "Year 1", "Year 2", "Year 3", "Year 4", "Year 5", "Year 6",
  "Year 7", "Year 8", "Year 9", "Year 10", "Year 11", "Year 12",
];

export default function AddStudentModal({ isOpen, onClose, onAdd, isBrutal }) {
  // The modal's open/close state (including the phone's back button
  // closing it) is handled by the shared modal-history system on Home,
  // which pushes a history entry when the modal opens and pops it when
  // the back button or the close button is pressed.
  const [studentName, setStudentName] = useState("");
  const [studentYear, setStudentYear] = useState("");

  const handleAdd = () => {
    onAdd({ studentName, studentYear });
    setStudentName("");
    setStudentYear("");
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 25 }}
            className={`w-full max-w-lg rounded-t-3xl p-6 space-y-5 ${
              isBrutal ? "bg-zinc-900 text-white" : "bg-white"
            }`}
            style={{ paddingBottom: "calc(1.5rem + env(safe-area-inset-bottom))" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h2 className={`font-fredoka text-xl ${isBrutal ? "text-orange-400" : "text-primary"}`}>
                🎒 Add Student
              </h2>
              <button onClick={onClose} className="p-1 rounded-full hover:bg-muted select-none">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-bold">Child's first name (optional)</label>
                <input
                  value={studentName}
                  onChange={(e) => setStudentName(e.target.value.replace(/[<>]/g, "").slice(0, 12))}
                  maxLength={12}
                  placeholder="e.g. Emma"
                  className={`w-full rounded-xl border px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring ${
                    isBrutal ? "bg-zinc-800 border-zinc-600 text-white" : "bg-background border-input"
                  }`}
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-bold">Year Level</label>
                <div className="grid grid-cols-2 gap-2 max-h-52 overflow-y-auto pr-1">
                  {YEAR_LEVELS.map((y) => (
                    <button
                      key={y}
                      onClick={() => setStudentYear(y)}
                      className={`py-2 px-3 rounded-xl text-xs font-semibold border-2 transition-all text-left select-none ${
                        studentYear === y
                          ? isBrutal
                            ? "border-orange-500 bg-orange-600 text-white"
                            : "border-primary bg-primary text-primary-foreground"
                          : isBrutal
                            ? "border-zinc-700 text-zinc-300 hover:border-orange-700"
                            : "border-border text-foreground hover:border-primary/50"
                      }`}
                    >
                      {y}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <button
              onClick={handleAdd}
              disabled={!studentYear}
              className={`w-full py-3 rounded-2xl font-bold text-sm transition-all disabled:opacity-40 select-none ${
                isBrutal
                  ? "bg-orange-600 hover:bg-orange-700 text-white"
                  : "bg-primary hover:bg-primary/90 text-primary-foreground"
              }`}
            >
              Add Student 🎒
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}