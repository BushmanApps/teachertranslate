import { BookOpen, MessageSquare, Sparkles, Gem } from "lucide-react";

export default function BonusPanel({ isBrutal, onNavigate }) {
  return (
    <div className={`rounded-3xl p-6 space-y-4 ${
      isBrutal ? "bg-zinc-900 text-white border border-zinc-800" : "bg-white border border-border shadow-sm"
    }`}>
      <div className="flex items-center gap-2">
        <h2 className={`font-fredoka text-xl ${isBrutal ? "text-orange-400" : "text-primary"}`}>
          ✨ Bonus Features
        </h2>
      </div>

      <p className={`text-sm flex items-center gap-1.5 ${isBrutal ? "text-zinc-400" : "text-muted-foreground"}`}>
        <Gem className="w-4 h-4 flex-shrink-0" />
        Exclusive Pro features to help you get the most out of Teacher Translate.
      </p>

      <button
        onClick={() => onNavigate("/glossary")}
        className={`w-full flex items-center gap-3 p-4 rounded-2xl transition-all ${
          isBrutal
            ? "bg-zinc-800 border border-zinc-700 hover:border-orange-700"
            : "bg-[#a8d8c8]/80 border border-border hover:border-primary/50"
        }`}
      >
        <div className={`p-2.5 rounded-xl ${isBrutal ? "bg-orange-600" : "bg-primary"} text-white`}>
          <BookOpen className="w-6 h-6" />
        </div>
        <div className="flex-1 text-left">
          <h3 className={`font-bold text-sm ${isBrutal ? "text-white" : "text-foreground"}`}>Teacher Glossary</h3>
          <p className={`text-xs ${isBrutal ? "text-zinc-400" : "text-muted-foreground"}`}>
            Common teacher report card comments decoded
          </p>
        </div>
      </button>

      <button
        onClick={() => onNavigate("/feedback")}
        className={`w-full flex items-center gap-3 p-4 rounded-2xl transition-all ${
          isBrutal
            ? "bg-zinc-800 border border-zinc-700 hover:border-orange-700"
            : "bg-[#fde8cb]/80 border border-border hover:border-primary/50"
        }`}
      >
        <div className={`p-2.5 rounded-xl ${isBrutal ? "bg-orange-600" : "bg-primary"} text-white`}>
          <MessageSquare className="w-6 h-6" />
        </div>
        <div className="flex-1 text-left">
          <h3 className={`font-bold text-sm ${isBrutal ? "text-white" : "text-foreground"}`}>Feedback</h3>
          <p className={`text-xs ${isBrutal ? "text-zinc-400" : "text-muted-foreground"}`}>
            Share your thoughts and suggestions
          </p>
        </div>
      </button>

      <p className={`text-center text-xs italic pt-1 ${isBrutal ? "text-zinc-500" : "text-muted-foreground"}`}>
        <Sparkles className="w-3 h-3 inline mr-1" />
        More features will be added here soon!
      </p>
    </div>
  );
}