import { useState, useEffect } from "react";
import { X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useIsMobile } from "@/hooks/use-mobile";
import MobileActionSheet from "@/components/MobileActionSheet";

const YEAR_LEVELS = [
  "Kindergarten / Preparatory",
  "Year 1", "Year 2", "Year 3", "Year 4", "Year 5", "Year 6",
  "Year 7", "Year 8", "Year 9", "Year 10", "Year 11", "Year 12",
];

function ConfirmStudentContent({ name, setName, year, setYear, onConfirm, isBrutal, onClose }) {
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className={`font-fredoka text-xl ${isBrutal ? "text-orange-400" : "text-primary"}`}>
          ✏️ Confirm Student Details
        </h2>
        <button onClick={onClose} className="p-1 rounded-full hover:bg-muted select-none">
          <X className="w-5 h-5" />
        </button>
      </div>

      <p className={`text-sm ${isBrutal ? "text-zinc-400" : "text-muted-foreground"}`}>
        Please confirm or update the child's name and year level before translating.
      </p>

      <div className="space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-bold">Child's first name (optional)</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value.replace(/[<>]/g, "").slice(0, 12))}
            maxLength={12}
            placeholder="e.g. Emma"
            onBlur={(e) => {
              // Keyboard closing: reset the sheet scroll so the whole card
              // (including the Translate button) is visible without scrolling.
              const sc = e.target.closest(".overflow-y-auto");
              if (sc) sc.scrollTop = 0;
            }}
            className={`w-full rounded-xl border px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring ${
              isBrutal ? "bg-zinc-800 border-zinc-600 text-white" : "bg-background border-input"
            }`}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-bold">Year Level</label>
          <div className="grid grid-cols-3 gap-2">
            {YEAR_LEVELS.map((y) => {
              const isKinder = y === "Kindergarten / Preparatory";
              return (
                <button
                  key={y}
                  onClick={() => setYear(y)}
                  className={`${isKinder ? "col-span-3" : ""} py-2.5 px-3 rounded-xl text-xs font-semibold border-2 transition-all text-center select-none ${
                    year === y
                      ? isBrutal
                        ? "border-orange-500 bg-orange-600 text-white"
                        : "border-primary bg-primary text-primary-foreground"
                      : isBrutal
                        ? "border-zinc-700 text-zinc-300 hover:border-orange-700"
                        : "border-border text-foreground hover:border-primary/50"
                  }`}
                >
                  {isKinder ? "Kindergarten / Foundation / Prep" : y}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <button
        onClick={() => onConfirm({ studentName: name, studentYear: year })}
        disabled={!year}
        className={`w-full py-3 rounded-2xl font-bold text-sm transition-all disabled:opacity-40 select-none ${
          isBrutal
            ? "bg-orange-600 hover:bg-orange-700 text-white"
            : "bg-primary hover:bg-primary/90 text-primary-foreground"
        }`}
      >
        Translate Report ✨
      </button>
    </div>
  );
}

export default function ConfirmStudentModal({ isOpen, onClose, onConfirm, isBrutal, studentName, studentYear }) {
  const [name, setName] = useState("");
  const [year, setYear] = useState("");
  const isMobile = useIsMobile();

  useEffect(() => {
    if (isOpen) {
      setName(studentName || "");
      setYear(studentYear || "");
    }
  }, [isOpen, studentName, studentYear]);

  // Global Enter key handler — works even if no field is focused
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e) => {
      if (e.key === "Enter" && year) {
        e.preventDefault();
        onConfirm({ studentName: name, studentYear: year });
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, name, year, onConfirm]);

  if (isMobile) {
    return (
      <MobileActionSheet isOpen={isOpen} onClose={onClose} isBrutal={isBrutal}>
        <ConfirmStudentContent
          name={name}
          setName={setName}
          year={year}
          setYear={setYear}
          onConfirm={onConfirm}
          isBrutal={isBrutal}
          onClose={onClose}
        />
      </MobileActionSheet>
    );
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            transition={{ type: "spring", damping: 25 }}
            className={`w-full max-w-lg rounded-3xl p-6 space-y-5 max-h-[90vh] overflow-y-auto ${
              isBrutal ? "bg-zinc-900 text-white" : "bg-white"
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            <ConfirmStudentContent
              name={name}
              setName={setName}
              year={year}
              setYear={setYear}
              onConfirm={onConfirm}
              isBrutal={isBrutal}
              onClose={onClose}
            />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}