import { motion } from "framer-motion";
import PerformanceBadge from "./PerformanceBadge";
import { getAcUrl } from "@/lib/acUrl.js";
import DisclaimerBanner from "./DisclaimerBanner";
import ShareResultButton from "./ShareResultButton";
import { ChevronDown, ChevronUp, ExternalLink } from "lucide-react";
import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import ExportPDFButton from "./ExportPDFButton";
import YearLevelModal from "./YearLevelModal";
import YearChangeWarning from "./YearChangeWarning";
import { base44 } from "@/api/base44Client";
import TrialLockCard from "./TrialLockCard";

function getCurriculumCodes(section) {
  if (section.curriculum_codes?.length > 0) return section.curriculum_codes;
  if (section.ac_code && section.ac_code !== "null") {
    return [{
      code: section.ac_code,
      curriculum_content: section.curriculum_content,
      performance_note: section.performance_note,
      activity_suggestion: section.activity_suggestion,
    }];
  }
  return [];
}

function getCurriculumContent(entry) {
  if (entry.curriculum_content && entry.curriculum_content !== "null") return entry.curriculum_content;
  const note = entry.performance_note;
  const code = entry.code;
  if (!note || note === "null" || !code) return "";
  const marker = `(${code})`;
  const codeIndex = note.indexOf(marker);
  return (codeIndex >= 0 ? note.slice(0, codeIndex) : note)
    .replace(/^AC v9\.0[^:]*:\s*/i, "")
    .trim();
}

function limitSectionsForTrial(sections) {
  const actualSections = (sections || []).filter((section) => !section._trial_lock);
  const totalBySubject = new Map();
  const hiddenBySubject = new Map();

  for (const section of actualSections) {
    const subject = section.subject_or_area || "General";
    totalBySubject.set(subject, (totalBySubject.get(subject) || 0) + 1);
  }
  for (const section of sections || []) {
    if (!section._trial_lock) continue;
    const subject = section.subject_or_area || "General";
    hiddenBySubject.set(subject, Math.max(hiddenBySubject.get(subject) || 0, Number(section.hidden_count) || 0));
  }

  const visibleBySubject = new Map();
  const limited = [];
  for (const section of actualSections) {
    const subject = section.subject_or_area || "General";
    const visible = (visibleBySubject.get(subject) || 0) + 1;
    visibleBySubject.set(subject, visible);
    if (visible > 3) continue;

    limited.push(section);
    if (visible === 3) {
      const hiddenCount = Math.max((totalBySubject.get(subject) || 0) - 3, hiddenBySubject.get(subject) || 0);
      if (hiddenCount > 0) {
        limited.push({ _trial_lock: true, subject_or_area: subject, hidden_count: hiddenCount });
      }
    }
  }
  return limited;
}

function SectionCard({ section, isBrutal, mode, index, isSubscribed, onUpgrade, showYearExpectations, confirmedYear }) {
  const [expanded, setExpanded] = useState(false);
  const codes = getCurriculumCodes(section);
  const hasResources = codes.length > 0 || section.activity_suggestion;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
      className={`rounded-2xl p-4 space-y-3 ${
        isBrutal ? "bg-zinc-800 border border-zinc-700" : "bg-white border border-border shadow-sm"
      }`}
    >
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className={`font-bold text-xs ${isBrutal ? "text-orange-400 font-fredoka" : "text-primary"}`}>
          {section.subject_or_area}
        </h3>
        <PerformanceBadge level={section.performance_level} isBrutal={isBrutal} />
      </div>

      <div className={`translation-output rounded-xl p-3 text-xs italic ${
        isBrutal ? "bg-zinc-900 text-zinc-400" : "bg-muted text-muted-foreground"
      }`}>
        "{section.original_excerpt}"
      </div>

      <div className={`translation-output text-sm leading-relaxed ${isBrutal ? "text-zinc-100" : "text-foreground"}`}>
        {mode === "brutal" ? (section.brutal_direct || section.brutal) : mode === "hilarious" ? section.brutal : section.honest_helpful}
      </div>

      {hasResources && (
        <div className={`space-y-2 rounded-xl border p-3 text-xs ${
          isBrutal ? "bg-zinc-700 text-zinc-200 border-zinc-600" : "bg-green-50 text-green-900 border-green-100"
        }`}>
          {codes.map((entry, entryIndex) => {
            const code = entry.code && entry.code !== "null" ? entry.code : null;
            const content = getCurriculumContent(entry);
            const acUrl = code ? (getAcUrl(code) || `https://www.australiancurriculum.edu.au/search/?q=${code}`) : null;
            return (
              <div key={`${code || "curriculum"}-${entryIndex}`} className="space-y-1.5">
                {content && (
                  <p>
                    <span className="text-lg">📚</span><span className="text-sm font-bold"> Curriculum content: </span>{content}
                    {code && acUrl && <> {"("}<a href={acUrl} target="_blank" rel="noopener noreferrer" className="underline font-semibold" onClick={() => base44.analytics.track({ eventName: "australian_curriculum_link_clicked", properties: { code } })}>{code}</a>{")"}</>}
                  </p>
                )}
                {entry.activity_suggestion && entry.activity_suggestion !== "null" && (
                  <p><span className="text-lg">🏠</span><span className="text-sm font-bold"> Try at home: </span>{entry.activity_suggestion}</p>
                )}
                {code && (
                  <a
                    href={`https://www.scootle.edu.au/ec/search?q=${code}&acCode=${code}&v=text&field=title&field=text.all&field=topic`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`inline-flex items-center gap-1 font-semibold underline ${isBrutal ? "text-orange-400" : "text-green-700"}`}
                    onClick={() => base44.analytics.track({ eventName: "scootle_link_clicked", properties: { code } })}
                  >
                    Find Scootle resources for {code} <ExternalLink className="w-4 h-4" />
                  </a>
                )}
              </div>
            );
          })}
          {!codes.length && section.activity_suggestion && section.activity_suggestion !== "null" && (
            <p><span className="text-lg">🏠</span><span className="text-sm font-bold"> Try at home: </span>{section.activity_suggestion}</p>
          )}
        </div>
      )}

      {showYearExpectations && codes.map((entry, entryIndex) => {
        const code = entry.code && entry.code !== "null" ? entry.code : null;
        const expectation = isBrutal ? entry.brutal_plain_english : entry.plain_english;
        if (!expectation || expectation === "null") return null;
        const acUrl = code ? (getAcUrl(code) || `https://www.australiancurriculum.edu.au/search/?q=${code}`) : null;
        return (
          <div key={`expectation-${entryIndex}`} className={`text-xs rounded-lg p-2 border ${
            isBrutal ? "bg-orange-950/40 text-orange-300 border-orange-800" : "bg-amber-50 text-amber-800 border-amber-100"
          }`}>
            <span className="font-bold">{isBrutal ? "💀 Reality check " : `📚 Year level expectations (${confirmedYear}): `}</span>
            {expectation}{code && acUrl && <> {"("}<a href={acUrl} target="_blank" rel="noopener noreferrer" className="underline font-semibold">{code}</a>{")"}</>}
          </div>
        );
      })}

      {hasResources && (isSubscribed ? (
        <>
          <button onClick={() => setExpanded(!expanded)} className={`flex items-center gap-1 text-xs font-semibold w-full text-left ${isBrutal ? "text-orange-400" : "text-primary"}`}>
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {expanded ? "Hide year level assessment" : "Show year level assessment"}
          </button>
          {expanded && codes.map((entry, entryIndex) => {
            const note = entry.performance_note;
            if (!note || note === "null") return null;
            return <p key={`assessment-${entryIndex}`} className={`text-xs rounded-lg p-2 ${isBrutal ? "bg-orange-950/40 text-orange-300 border border-orange-800" : "bg-blue-50 text-blue-800 border border-blue-100"}`}><span className="text-lg">📚</span><span className="text-sm font-bold"> Year level assessment: </span>{note}</p>;
          })}
        </>
      ) : (
        <button onClick={onUpgrade} className={`w-full rounded-lg border border-dashed p-2 text-left text-xs ${isBrutal ? "border-orange-700 text-orange-300" : "border-primary/40 text-primary"}`}>
          🔒 Unlock Pro to view this student's year level assessment
        </button>
      ))}
    </motion.div>
  );
}
export default function TranslationResult({ result, mode, studentName, studentYear, isSubscribed, onUpgrade, isBrutal: isBrutalProp, shareModalOpen, onOpenShare, onCloseShare, exportModalOpen, onOpenExport, onCloseExport, onChangeYear, autoShowExpectations }) {
  const isBrutal = isBrutalProp ?? mode === "brutal";
  const [showYearExpectations, setShowYearExpectations] = useState(!!autoShowExpectations);
  const [pendingYear, setPendingYear] = useState(null);
  const [confirmedYear, setConfirmedYear] = useState(studentYear || "");
  const [showYearModal, setShowYearModal] = useState(false);

  const handleToggleYearExpectations = () => {
    if (!isSubscribed) {
      onUpgrade();
      return;
    }
    if (!showYearExpectations) {
      setShowYearModal(true);
    } else {
      setShowYearExpectations(false);
    }
  };

  // Keep the expectations label in step with the child's current year
  // (e.g. after the year is changed and the report re-translated).
  useEffect(() => {
    setConfirmedYear(studentYear || "");
  }, [studentYear]);

  const handleConfirmYear = (selectedYear) => {
    setShowYearModal(false);
    if (selectedYear && selectedYear !== studentYear && onChangeYear) {
      setPendingYear(selectedYear);
      return;
    }
    setConfirmedYear(studentYear || "");
    setShowYearExpectations(true);
  };

  const handleConfirmRetranslate = () => {
    const y = pendingYear;
    setPendingYear(null);
    onChangeYear(y);
  };

  if (!result) return null;

  const displaySections = isSubscribed ? (result.sections || []) : limitSectionsForTrial(result.sections);

  return (
    <div className="space-y-5">
      {/* Buttons row above the summary box */}
      <div className="flex items-center justify-end flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <ShareResultButton
            result={result}
            mode={mode}
            studentName={studentName}
            studentYear={studentYear}
            isBrutal={isBrutal}
            isSubscribed={isSubscribed}
            onUpgrade={onUpgrade}
            isOpen={shareModalOpen}
            onOpen={onOpenShare}
            onClose={onCloseShare}
          />
          {isSubscribed ? (
            <ExportPDFButton
              result={result}
              mode={mode}
              studentName={studentName}
              studentYear={studentYear}
              isBrutal={isBrutal}
              isOpen={exportModalOpen}
              onOpen={onOpenExport}
              onClose={onCloseExport}
            />
          ) : (
            <button
              onClick={onUpgrade}
              className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-xl transition-all opacity-70 ${
                isBrutal
                  ? "bg-zinc-800 text-zinc-400 border border-zinc-700"
                  : "bg-muted text-muted-foreground border border-border"
              }`}
            >
              🔒 Export PDF
            </button>
          )}
        </div>
      </div>

      {/* Overall Summary */}
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        className={`rounded-2xl p-5 space-y-3 ${
          isBrutal
            ? "bg-gradient-to-br from-orange-950 to-zinc-900 border border-orange-700"
            : "bg-gradient-to-br from-purple-50 to-pink-50 border border-purple-100"
        }`}
      >
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h2 className={`font-fredoka text-lg ${isBrutal ? "text-orange-400" : "text-primary"}`}>
            {mode === "brutal" ? "💥 The brutal truth" : mode === "hilarious" ? "🤣 The hilarious reality" : "😊 The honest summary"}
          </h2>
          <PerformanceBadge level={result.overall_performance_level} isBrutal={isBrutal} />
        </div>

        {studentName && (
          <p className={`text-xs font-semibold ${isBrutal ? "text-zinc-400" : "text-muted-foreground"}`}>
            Report for: {studentName} — {studentYear}
          </p>
        )}

        <p className={`translation-output text-sm leading-relaxed font-semibold ${isBrutal ? "text-white" : "text-foreground"}`}>
          {mode === "brutal" ? (result.overall_brutal_direct || result.overall_brutal) : mode === "hilarious" ? result.overall_brutal : result.overall_honest_helpful}
        </p>

        {result.overall_performance_summary && (
          isSubscribed ? (
            <div className={`translation-output text-xs rounded-xl p-3 ${
              isBrutal ? "bg-orange-950/60 text-orange-200" : "bg-white/60 text-foreground/80"
            }`}>
              <span className="font-bold">Year level assessment: </span>
              {result.overall_performance_summary}
            </div>
          ) : (
            <button
              onClick={onUpgrade}
              className={`w-full text-xs rounded-xl p-3 text-left opacity-60 border border-dashed ${
                isBrutal ? "border-orange-700 text-orange-300" : "border-primary/40 text-primary"
              }`}
            >
              🔒 Year level assessment — <span className="font-bold">Pro subscribers only</span>
            </button>
          )
        )}
      </motion.div>

      {/* Per-section breakdowns */}
      {result.sections && result.sections.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h3 className={`text-sm font-bold uppercase tracking-wide ${
              isBrutal ? "text-zinc-400" : "text-muted-foreground"
            }`}>
              Sentence by Sentence
            </h3>
            {isSubscribed ? (
              <button
                onClick={handleToggleYearExpectations}
                className={`flex items-center gap-2 text-xs font-semibold px-3 py-1.5 rounded-full border-2 transition-all select-none ml-auto ${
                  isBrutal
                    ? showYearExpectations
                      ? "bg-orange-600 text-white border-orange-500"
                      : "bg-zinc-800 text-zinc-300 border-zinc-700 hover:border-orange-700"
                    : showYearExpectations
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-white text-muted-foreground border-border hover:border-primary/50"
                }`}
              >
                {isBrutal ? "💀" : "📊"} {isBrutal ? "Reality check" : "Year level expectations"}
                <span className={`relative inline-flex items-center w-9 h-5 rounded-full transition-colors border-2 ${showYearExpectations ? (isBrutal ? "bg-orange-950 border-orange-400" : "bg-white/30 border-white") : (isBrutal ? "bg-zinc-700 border-zinc-600" : "bg-gray-300 border-gray-400")}`}>
                  <span className={`inline-block w-3.5 h-3.5 rounded-full shadow-sm transform transition-transform ${showYearExpectations ? (isBrutal ? "bg-orange-400 translate-x-4" : "bg-white translate-x-4") : (isBrutal ? "bg-zinc-400 translate-x-0.5" : "bg-white translate-x-0.5")}`} />
                </span>
              </button>
            ) : (
              <button
                onClick={onUpgrade}
                className={`flex items-center gap-2 text-xs font-semibold px-3 py-1.5 rounded-full border-2 transition-all select-none opacity-60 ml-auto ${
                  isBrutal
                    ? "bg-zinc-800 text-zinc-400 border-zinc-700"
                    : "bg-white text-muted-foreground border-border"
                }`}
              >
                🔒 {isBrutal ? "Reality check" : "Year level expectations"}
              </button>
            )}
          </div>
          {displaySections.map((section, i) =>
            section._trial_lock ? (
              <TrialLockCard
                key={i}
                subject={section.subject_or_area}
                hiddenCount={section.hidden_count}
                isBrutal={isBrutal}
                onUpgrade={onUpgrade}
              />
            ) : (
              <SectionCard
                key={i}
                section={section}
                isBrutal={isBrutal}
                mode={mode}
                index={i}
                isSubscribed={isSubscribed}
                onUpgrade={onUpgrade}
                showYearExpectations={isSubscribed && showYearExpectations}
                confirmedYear={confirmedYear}
              />
            )
          )}
        </div>
      )}

      <DisclaimerBanner isBrutal={isBrutal} />

      {createPortal(
        <YearLevelModal
          isOpen={showYearModal}
          onClose={() => setShowYearModal(false)}
          onConfirm={handleConfirmYear}
          currentYear={confirmedYear}
          isBrutal={isBrutal}
        />,
        document.body
      )}
      <YearChangeWarning
        year={pendingYear}
        isBrutal={isBrutal}
        isSubscribed={isSubscribed}
        onCancel={() => { setPendingYear(null); setShowYearModal(true); }}
        onConfirm={handleConfirmRetranslate}
      />
    </div>
  );
}