import { motion } from "framer-motion";

export default function GlossaryCard({ entry, mode, index }) {
  const isBrutal = mode === "brutal";
  const isHilarious = mode === "hilarious";

  const text = isBrutal ? entry.brutal : isHilarious ? entry.hilarious : entry.honest;

  const cardClass = isBrutal
    ? "bg-zinc-900 border border-zinc-800"
    : isHilarious
      ? "bg-[#ffe0ef] border border-pink-200"
      : "bg-white border border-border shadow-sm";

  const quoteClass = isBrutal
    ? "bg-zinc-950 text-zinc-400"
    : isHilarious
      ? "bg-pink-100 text-pink-900"
      : "bg-muted text-muted-foreground";

  const textClass = isBrutal
    ? "text-zinc-100"
    : isHilarious
      ? "text-pink-950"
      : "text-foreground";

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.05, 0.5) }}
      className={`selectable-text rounded-2xl p-4 space-y-3 ${cardClass}`}
    >
      <div className={`rounded-xl p-3 text-sm italic ${quoteClass}`}>
        &ldquo;{entry.teacher_speak}&rdquo;
      </div>
      <p className={`text-sm leading-relaxed ${textClass}`}>
        {text}
      </p>
    </motion.div>
  );
}