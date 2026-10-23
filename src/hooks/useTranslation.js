import { useState, useRef, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";

const FREE_SCAN_LIMIT = 3;

// Module-level cache so the last translation survives Home unmounting when
// the user navigates to the glossary or feedback page and comes back.
let _lastResult = null;

export function useTranslation({ userProfile, setUserProfile, activeStudent, currentUser, mode, onLimitReached }) {
  const [translating, setTranslating] = useState(false);
  const [result, setResult] = useState(_lastResult);

  useEffect(() => {
    _lastResult = result;
  }, [result]);
  const [error, setError] = useState(null);
  const [pendingText, setPendingText] = useState(null);
  const sessionTranslationCount = useRef(0);

  const saveTranslationRecord = async (text, translationResult, studentName, studentYear) => {
    const original_comments = (translationResult.sections || [])
      .map(s => s.original_excerpt)
      .filter(Boolean);

    const created = await base44.entities.Translation.create({
      original_comments,
      honest_helpful_translation: translationResult.overall_honest_helpful,
      brutal_translation: translationResult.overall_brutal,
      brutal_direct_translation: translationResult.overall_brutal_direct,
      sections: translationResult.sections || [],
      student_id: activeStudent?.id,
      student_year: studentYear,
      student_name: studentName,
      performance_level: translationResult.overall_performance_level,
      performance_summary: translationResult.overall_performance_summary,
      subject_area: translationResult.sections?.[0]?.subject_or_area || "General",
      mode,
      translation_timestamp: new Date().toLocaleString("en-AU", { timeZone: "Australia/Sydney" }),
      creator_email: currentUser?.email
    });
    return created?.id || null;
  };

  // The server counts scans; just mirror its count in the UI.
  const syncScansUsed = (serverScans) => {
    if (typeof serverScans === "number") {
      setUserProfile(prev => ({ ...prev, scans_used: serverScans }));
    }
  };

  const runTranslation = async (text, studentName, studentYear) => {
    setResult(null);
    setError(null);
    setTranslating(true);
    try {
      const res = await base44.functions.invoke("translateReport", {
        reportText: text,
        studentYear,
        studentName,
        mode
      });

      if (res.data?.result) {
        const newResult = res.data.result;
        setResult({ ...newResult, original_text: text });

        sessionTranslationCount.current += 1;
        trackEvent("translation_completed", {
          success: true,
          grade_level: studentYear,
          mode,
          session_request_count: sessionTranslationCount.current
        });

        const isSubscribed = !!userProfile?.is_subscribed;
        if (isSubscribed) {
          const translationId = await saveTranslationRecord(text, newResult, studentName, studentYear);
          if (translationId) {
            setResult(prev => prev ? { ...prev, id: translationId } : prev);
          }
        }
        syncScansUsed(res.data.scans_used);
      }
    } catch (e) {
      console.error(e);
      setError("The report took too long to process. Please try again — if the report is very long, try translating one subject section at a time.");
      trackEvent("translation_completed", {
        success: false,
        grade_level: activeStudent?.student_year,
        mode
      });
    } finally {
      setTranslating(false);
    }
  };

  const retranslate = async (text, studentName, studentYear, idOverride) => {
    const existingId = idOverride || result?.id;
    setResult(null);
    setError(null);
    setTranslating(true);
    try {
      const res = await base44.functions.invoke("translateReport", {
        reportText: text,
        studentYear,
        studentName,
        mode
      });
      if (res.data?.result) {
        const newResult = res.data.result;
        setResult({ ...newResult, original_text: text, student_name: studentName, student_year: studentYear, id: existingId });
        syncScansUsed(res.data.scans_used);
        const isSubscribed = !!userProfile?.is_subscribed;
        if (existingId) {
          await base44.entities.Translation.update(existingId, {
            honest_helpful_translation: newResult.overall_honest_helpful,
            brutal_translation: newResult.overall_brutal,
            brutal_direct_translation: newResult.overall_brutal_direct,
            sections: newResult.sections || [],
            student_year: studentYear,
            student_name: studentName,
            performance_level: newResult.overall_performance_level,
            performance_summary: newResult.overall_performance_summary,
            subject_area: newResult.sections?.[0]?.subject_or_area || "General"
          });
        } else if (isSubscribed) {
          const translationId = await saveTranslationRecord(text, newResult, studentName, studentYear);
          if (translationId) {
            setResult(prev => prev ? { ...prev, id: translationId } : prev);
          }
        }
      }
    } catch (e) {
      console.error(e);
      setError("The report took too long to process. Please try again.");
    } finally {
      setTranslating(false);
    }
  };

  const handleTextReady = (text) => {
    const isSubscribed = !!userProfile?.is_subscribed;
    const scansUsed = userProfile?.scans_used || 0;
    const canScan = isSubscribed || scansUsed < FREE_SCAN_LIMIT;
    if (!canScan) {
      onLimitReached("limit");
      return;
    }
    setPendingText(text);
    return true;
  };

  const handleLoadFromHistory = (translation) => {
    setResult({
      id: translation.id,
      overall_honest_helpful: translation.honest_helpful_translation,
      overall_brutal: translation.brutal_translation,
      overall_brutal_direct: translation.brutal_direct_translation,
      overall_performance_level: translation.performance_level,
      overall_performance_summary: translation.performance_summary,
      sections: translation.sections || [],
      original_text: (translation.original_comments || []).join(" ")
    });
  };

  const handleReset = () => { setResult(null); setError(null); };

  return {
    FREE_SCAN_LIMIT,
    translating,
    result,
    setResult,
    error,
    setError,
    pendingText,
    setPendingText,
    handleTextReady,
    runTranslation,
    retranslate,
    handleLoadFromHistory,
    handleReset,
  };
}