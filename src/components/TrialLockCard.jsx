import { Lock } from "lucide-react";

export default function TrialLockCard({ subject, hiddenCount, isBrutal, onUpgrade }) {
  return (
    <div className={`rounded-2xl p-4 text-center space-y-2 ${
      isBrutal
        ? "bg-zinc-800/50 border-2 border-dashed border-orange-700"
        : "bg-muted/50 border-2 border-dashed border-primary/30"
    }`}>
      <div className="flex items-center justify-center gap-2">
        <Lock className={`w-4 h-4 ${isBrutal ? "text-orange-400" : "text-primary"}`} />
        <p className={`text-sm font-bold ${isBrutal ? "text-orange-400" : "text-primary"}`}>
          {hiddenCount} more {subject} sentence{hiddenCount > 1 ? "s" : ""} not shown
        </p>
      </div>
      <button
        onClick={onUpgrade}
        className={`text-xs font-semibold underline underline-offset-2 ${
          isBrutal ? "text-orange-300" : "text-primary"
        }`}
      >
        Upgrade to Pro to see the full report translation
      </button>
    </div>
  );
}