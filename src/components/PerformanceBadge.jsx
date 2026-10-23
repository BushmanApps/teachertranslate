export default function PerformanceBadge({ level, isBrutal }) {
  const configs = {
    ahead: {
      label: isBrutal ? "🚀 Overachiever" : "⭐ Ahead of Year Level",
      className: "text-emerald-700",
      brutalClass: "text-yellow-500"
    },
    average: {
      label: isBrutal ? "😐 Middling" : "✅ At Year Level",
      className: "text-blue-800",
      brutalClass: "text-orange-400"
    },
    behind: {
      label: isBrutal ? "🚨 Falling Behind" : "⚠️ Below Year Level",
      className: "text-red-700",
      brutalClass: "text-red-400"
    },
    mixed: {
      label: isBrutal ? "🎭 All Over The Shop" : "📊 Mixed Results",
      className: "text-purple-700",
      brutalClass: "text-purple-400"
    },
    unknown: {
      label: "❓ Unclear",
      className: "text-gray-500",
      brutalClass: "text-gray-400"
    }
  };

  const config = configs[level] || configs.unknown;
  const cls = isBrutal ? config.brutalClass : config.className;

  return (
    <span className={`inline-block text-xs font-bold ${cls}`}>
      {config.label}
    </span>
  );
}