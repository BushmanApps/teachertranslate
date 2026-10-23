import { AlertTriangle } from "lucide-react";

export default function DisclaimerBanner({ isBrutal }) {
  return (
    <div className={`rounded-xl p-3 text-xs leading-relaxed flex gap-2 items-start ${
      isBrutal 
        ? "bg-orange-950/60 border border-orange-700 text-orange-200" 
        : "bg-amber-50 border border-amber-200 text-amber-800"
    }`}>
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
      <p>
        <strong>Disclaimer:</strong> Teacher Translate is designed to help families better understand school reports. Translations are AI-generated interpretations and are <strong>not literal translations</strong>. Curriculum references are based on the <strong>Australian Curriculum Version 9.0</strong>. Your local state or territory may use an interpretation or adapted version of this curriculum. For any concerns about your child's progress, please speak directly with their teacher.
      </p>
    </div>
  );
}