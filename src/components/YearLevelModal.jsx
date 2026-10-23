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

function YearLevelContent({ year, setYear, onConfirm, isBrutal, onClose }) {
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className={`font-fredoka text-xl ${isBrutal ? "text-orange-400" : "text-primary"}`}>
          📊 Confirm Year Level
        </h2>
        <button onClick={onClose} className="p-1 rounded-full hover:bg-muted select-none">
          <X className="w-5 h-5" />
        </button>
      </div>

      <p className={`text-sm ${isBrutal ? "text-zinc-400" : "text-muted-foreground"}`}>
        Please confirm the child's year level to show Australian Curriculum expectations for each outcome.
      </p>

      <div className="space-y-2">
        <label className="text-sm font-bold">Year Level</label>
        <div className="grid grid-cols-3 gap-1.5 max-h-52 overflow-y-auto pr-1">
          {YEAR_LEVELS.map((y) => {
            const isKinder = y === "Kindergarten / Preparatory";
            return (
              <button
                key={y}
                onClick={() => setYear(y)}
                className={`${isKinder ? "col-span-3" : ""} py-1.5 px-2 rounded-xl text-xs font-semibold border-2 transition-all text-center select-none ${
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

      <button
        onClick={() => onConfirm(year)}
        disabled={!year}
        className={`w-full py-3 rounded-2xl font-bold text-sm transition-all disabled:opacity-40 select-none ${
          isBrutal
            ? "bg-orange-600 hover:bg-orange-700 text-white"
            : "bg-primary hover:bg-primary/90 text-primary-foreground"
        }`}
      >
        Show Year Level Expectations
      </button>
    </div>
  );
}

export default function YearLevelModal({ isOpen, onClose, onConfirm, currentYear, isBrutal }) {
  const [year, setYear] = useState("");
  const isMobile = useIsMobile();

  useEffect(() => {
    if (isOpen) setYear(currentYear || "");
  }, [isOpen, currentYear]);

  // Global Enter key handler
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e) => {
      if (e.key === "Enter" && year) {
        e.preventDefault();
        onConfirm(year);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, year, onConfirm]);

  if (isMobile) {
    return (
      <MobileActionSheet isOpen={isOpen} onClose={onClose} isBrutal={isBrutal}>
        <YearLevelContent year={year} setYear={setYear} onConfirm={onConfirm} isBrutal={isBrutal} onClose={onClose} />
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
            <YearLevelContent year={year} setYear={setYear} onConfirm={onConfirm} isBrutal={isBrutal} onClose={onClose} />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}