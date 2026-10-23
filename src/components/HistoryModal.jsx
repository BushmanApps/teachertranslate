import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Clock, Trash2, FileText, Download, CheckSquare, Square, Loader2, Share2, Check } from "lucide-react";
import { base44 } from "@/api/base44Client";
import { saveSinglePDF, saveCombinedPDF } from "@/lib/generatePDF";

export default function HistoryModal({ isOpen, onClose, isBrutal, onLoadTranslation, isSubscribed, onUpgrade }) {
  const [translations, setTranslations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);
  const [editingCommentId, setEditingCommentId] = useState(null);
  const [commentDraft, setCommentDraft] = useState("");
  const [selected, setSelected] = useState(new Set());
  const [bulkDeleteConfirm, setBulkDeleteConfirm] = useState(false);
  const [bulkDownloading, setBulkDownloading] = useState(false);
  const [showDownloadPrompt, setShowDownloadPrompt] = useState(false);

  useEffect(() => {
    if (isOpen) {loadTranslations();setSelected(new Set());setBulkDeleteConfirm(false);}
  }, [isOpen]);

  const loadTranslations = async () => {
    setLoading(true);
    try {
      const data = await base44.entities.Translation.list();
      setTranslations(data || []);
    } catch (e) {console.error(e);} finally
    {setLoading(false);}
  };

  const handleDelete = async (id) => {
    try {
      await base44.entities.Translation.delete(id);
      setTranslations((prev) => prev.filter((t) => t.id !== id));
      setDeleteConfirmId(null);
    } catch (e) {console.error(e);}
  };

  const handleBulkDelete = async () => {
    try {
      await Promise.all([...selected].map((id) => base44.entities.Translation.delete(id)));
      setTranslations((prev) => prev.filter((t) => !selected.has(t.id)));
      setSelected(new Set());
      setBulkDeleteConfirm(false);
    } catch (e) {console.error(e);}
  };

  const handleBulkDownload = async (combined) => {
    setShowDownloadPrompt(false);
    setBulkDownloading(true);
    try {
      const toExport = translations.filter((t) => selected.has(t.id));
      if (combined) {
        await saveCombinedPDF(toExport);
      } else {
        for (const t of toExport) {
          await saveSinglePDF(t, t.student_name);
          await new Promise((r) => setTimeout(r, 300));
        }
      }
    } catch (e) {console.error(e);} finally
    {setBulkDownloading(false);}
  };

  const handleDownloadClick = () => {
    if (selected.size > 1) setShowDownloadPrompt(true);else
    handleBulkDownload(false);
  };

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selected.size === translations.length) setSelected(new Set());else
    setSelected(new Set(translations.map((t) => t.id)));
  };

  const handleLoad = (translation) => {onLoadTranslation(translation);onClose();};

  const [singleDownloadingId, setSingleDownloadingId] = useState(null);

  const handleSingleDownload = async (t) => {
    if (!isSubscribed) {onUpgrade();return;}
    setSingleDownloadingId(t.id);
    try {await saveSinglePDF(t, t.student_name);}
    catch (e) {console.error(e);} finally
    {setSingleDownloadingId(null);}
  };

  const [sharedId, setSharedId] = useState(null);

  const buildShareText = (t) => {
    const name = t.student_name || "My child";
    const modeLabel = t.mode === "brutal" ? "💥 Brutal" : t.mode === "hilarious" ? "🤣 Hilarious" : "😊 Honest";
    const summary = t.mode === "brutal" ? t.brutal_direct_translation || t.brutal_translation :
    t.mode === "hilarious" ? t.brutal_translation :
    t.honest_helpful_translation;
    return `📊 ${modeLabel} translation of ${name}'s school report\n\n"${summary}"\n\n🍎 Decoded with Teacher Translate\nhttps://TeacherTranslate.com.au`;
  };

  const handleShare = async (t) => {
    const text = buildShareText(t);
    try {
      if (navigator.share) {
        await navigator.share({ title: "Teacher Translate", text });
      } else {
        await navigator.clipboard.writeText(text);
        setSharedId(t.id);
        setTimeout(() => setSharedId(null), 2000);
      }
    } catch (e) {
      if (e.name !== "AbortError") {
        await navigator.clipboard.writeText(text);
        setSharedId(t.id);
        setTimeout(() => setSharedId(null), 2000);
      }
    }
  };

  const handleCommentSave = async (id) => {
    try {
      await base44.entities.Translation.update(id, { comments: commentDraft });
      setTranslations((prev) => prev.map((t) => t.id === id ? { ...t, comments: commentDraft } : t));
    } catch (e) {console.error(e);}
    setEditingCommentId(null);
  };

  const formatDate = (dateString) => {
    const normalized = dateString && !dateString.endsWith("Z") && !dateString.includes("+") ? dateString + "Z" : dateString;
    const date = new Date(normalized);
    const formatted = date.toLocaleString("en-AU", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Australia/Sydney" });
    const utcOffset = new Intl.DateTimeFormat("en-AU", { timeZone: "Australia/Sydney", timeZoneName: "short" }).formatToParts(date).find((p) => p.type === "timeZoneName")?.value;
    return `${formatted} (${utcOffset === "AEDT" ? "AEDT" : "AEST"})`;
  };

  const hasSelection = selected.size > 0;
  const allSelected = translations.length > 0 && selected.size === translations.length;

  return (
    <AnimatePresence>
      {isOpen &&
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
        onClick={onClose}>
        
          <motion.div
          initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }}
          transition={{ type: "spring", damping: 25, stiffness: 300 }}
          className={`w-full max-w-lg rounded-3xl overflow-hidden shadow-2xl ${isBrutal ? "bg-zinc-900" : "bg-white"}`}
          style={{ maxHeight: "85vh", paddingBottom: "calc(1rem + env(safe-area-inset-bottom))" }}
          onClick={(e) => e.stopPropagation()}>
          
            {/* Header */}
            <div className={`flex items-center justify-between p-4 border-b ${isBrutal ? "border-zinc-800" : "border-border"}`}>
              <h2 className={`font-fredoka text-xl flex items-center gap-2 ${isBrutal ? "text-orange-400" : "text-primary"}`}>
                <Clock className="w-5 h-5" />
                Translation History
              </h2>
              <button onClick={onClose} className={`p-2 rounded-full transition-colors ${isBrutal ? "hover:bg-zinc-800" : "hover:bg-muted"}`}>
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Select all / bulk actions bar */}
            {translations.length > 0 &&
          <div className={`flex items-center justify-between px-4 py-2 border-b ${isBrutal ? "border-zinc-800 bg-zinc-900" : "border-border bg-muted/30"}`}>
                <button
              onClick={toggleSelectAll}
              className={`flex items-center gap-2 text-xs font-semibold transition-colors ${isBrutal ? "text-zinc-300 hover:text-white" : "text-foreground/70 hover:text-foreground"}`}>
              
                  {allSelected ?
              <CheckSquare className={`w-4 h-4 ${isBrutal ? "text-orange-400" : "text-primary"}`} /> :
              <Square className="w-4 h-4" />}
                  {allSelected ? "Deselect all" : "Select all"}
                </button>

                <div className="flex items-center gap-2 min-h-[28px]">
                  {hasSelection &&
              <>
                    <span className={`text-xs ${isBrutal ? "text-zinc-400" : "text-muted-foreground"}`}>{selected.size} selected</span>
                    {isSubscribed ?
                <button
                  onClick={handleDownloadClick}
                  disabled={bulkDownloading}
                  className={`flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg transition-all ${isBrutal ? "bg-zinc-700 text-zinc-200 hover:bg-zinc-600" : "bg-muted text-foreground hover:bg-border"}`}>
                  
                        {bulkDownloading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                        PDF
                      </button> :

                <button
                  onClick={onUpgrade}
                  className={`flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg transition-all opacity-60 ${isBrutal ? "bg-zinc-800 text-zinc-400" : "bg-muted text-muted-foreground"}`}>
                  
                        🔒 PDF
                      </button>
                }
                    {bulkDeleteConfirm ?
                <div className="flex items-center gap-1">
                        <span className={`text-xs ${isBrutal ? "text-red-400" : "text-destructive"}`}>Sure?</span>
                        <button onClick={handleBulkDelete} className={`text-xs font-semibold px-2.5 py-1 rounded-lg ${isBrutal ? "bg-red-900/40 text-red-400" : "bg-destructive/10 text-destructive"}`}>Yes</button>
                        <button onClick={() => setBulkDeleteConfirm(false)} className={`text-xs px-2.5 py-1 rounded-lg ${isBrutal ? "bg-zinc-700 text-zinc-400" : "bg-muted text-muted-foreground"}`}>No</button>
                      </div> :

                <button
                  onClick={() => setBulkDeleteConfirm(true)}
                  className={`flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg transition-all ${isBrutal ? "bg-red-900/30 text-red-400 hover:bg-red-900/50" : "bg-destructive/10 text-destructive hover:bg-destructive/20"}`}>
                  
                        <Trash2 className="w-3.5 h-3.5" />
                        Delete
                      </button>
                }
                    </>
              }
                </div>
              </div>
          }

            <div className="p-4 overflow-y-auto" style={{ maxHeight: "calc(85vh - 130px)", overscrollBehavior: "contain" }}>
              {loading ?
            <div className="flex justify-center py-8">
                  <div className={`w-6 h-6 border-2 rounded-full animate-spin ${isBrutal ? "border-orange-400 border-t-transparent" : "border-primary border-t-transparent"}`} />
                </div> :
            translations.length === 0 ?
            <div className="text-center py-8">
                  <FileText className={`w-12 h-12 mx-auto mb-3 ${isBrutal ? "text-zinc-700" : "text-muted-foreground/50"}`} />
                  <p className={`text-sm ${isBrutal ? "text-zinc-400" : "text-muted-foreground"}`}>No translations yet</p>
                  <p className={`text-xs mt-1 ${isBrutal ? "text-zinc-500" : "text-muted-foreground/70"}`}>Your saved translations will appear here</p>
                </div> :

            <div className="space-y-3">
                  {translations.map((t) => {
                const isSelected = selected.has(t.id);
                return (
                  <div
                    key={t.id}
                    className={`rounded-2xl p-3 border transition-all ${
                    isSelected ?
                    isBrutal ? "bg-orange-950/30 border-orange-700" : "bg-primary/5 border-primary/40" :
                    isBrutal ? "bg-zinc-800/50 border-zinc-700 hover:border-zinc-600" : "bg-muted/50 border-border hover:border-primary/30"}`
                    }>
                    
                        <div className="flex items-start gap-2">
                          {/* Checkbox */}
                          <button onClick={() => toggleSelect(t.id)} className="mt-0.5 flex-shrink-0 p-0.5">
                            {isSelected ?
                        <CheckSquare className={`w-4 h-4 ${isBrutal ? "text-orange-400" : "text-primary"}`} /> :
                        <Square className={`w-4 h-4 ${isBrutal ? "text-zinc-600" : "text-muted-foreground/50"}`} />}
                          </button>

                          <div className="flex-1 min-w-0 flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className={`text-sm font-medium truncate ${isBrutal ? "text-zinc-200" : "text-foreground"}`}>
                                {t.student_name || "Your child"}{t.student_year ? `, ${t.student_year}` : ""}
                              </p>
                              <p className={`text-xs ${isBrutal ? "text-zinc-500" : "text-muted-foreground"}`}>
                                {formatDate(t.created_date)}
                              </p>
                            </div>

                            <div className="flex items-center gap-1 flex-shrink-0">
                              <button
                            onClick={() => handleLoad(t)}
                            className={`p-2 rounded-xl transition-colors ${isBrutal ? "bg-orange-600 hover:bg-orange-700 text-white" : "bg-primary hover:bg-primary/90 text-primary-foreground"}`}>
                            
                                <FileText className="w-4 h-4" />
                              </button>
                              {isSubscribed ?
                          <button
                            onClick={() => handleSingleDownload(t)}
                            disabled={singleDownloadingId === t.id}
                            className={`p-2 rounded-xl transition-colors ${isBrutal ? "bg-zinc-700 hover:bg-zinc-600 text-zinc-200" : "bg-muted hover:bg-border text-foreground"}`}>
                            
                                  {singleDownloadingId === t.id ?
                            <Loader2 className="w-4 h-4 animate-spin" /> :
                            <Download className="w-4 h-4" />}
                                </button> :
                          null}
                              <button
                            onClick={() => handleShare(t)}
                            className={`p-2 rounded-xl transition-colors ${isBrutal ? "bg-zinc-700 hover:bg-zinc-600 text-zinc-200" : "bg-muted hover:bg-border text-foreground"}`}
                            title="Share">
                            
                                {sharedId === t.id ?
                            <Check className="w-4 h-4 text-green-500" /> :
                            <Share2 className="w-4 h-4" />}
                              </button>
                              {!isSubscribed &&
                          <button
                            onClick={onUpgrade}
                            className={`p-2 rounded-xl transition-colors opacity-60 ${isBrutal ? "bg-zinc-800 text-zinc-500" : "bg-muted text-muted-foreground"}`}>
                            
                                  🔒
                                </button>
                          }
                              {deleteConfirmId === t.id ?
                          <div className="flex items-center gap-1">
                                  <span className={`text-xs ${isBrutal ? "text-red-400" : "text-destructive"}`}>Sure?</span>
                                  <button onClick={() => handleDelete(t.id)} className={`p-2 rounded-xl ${isBrutal ? "bg-red-900/30 text-red-400" : "bg-destructive/10 text-destructive"}`}>
                                    <Trash2 className="w-4 h-4" />
                                  </button>
                                  <button onClick={() => setDeleteConfirmId(null)} className={`p-2 rounded-xl text-xs ${isBrutal ? "bg-zinc-800 text-zinc-400" : "bg-muted text-muted-foreground"}`}>✕</button>
                                </div> :

                          <button onClick={() => setDeleteConfirmId(t.id)} className={`p-2 rounded-xl transition-colors ${isBrutal ? "hover:bg-red-900/30 text-red-400" : "hover:bg-destructive/10 text-destructive"}`}>
                                  <Trash2 className="w-4 h-4" />
                                </button>
                          }
                            </div>
                          </div>
                        </div>

                        {/* Inline comments field — full width */}
                        <div className="mt-2 pl-7">
                          <label className={`text-xs font-semibold ${isBrutal ? "text-zinc-400" : "text-muted-foreground"}`}>Your comments</label>
                          {editingCommentId === t.id ? (
                            <div className="flex items-center gap-1 mt-0.5">
                              <input
                                autoFocus
                                value={commentDraft}
                                onChange={(e) => setCommentDraft(e.target.value)}
                                onBlur={() => handleCommentSave(t.id)}
                                onKeyDown={(e) => { if (e.key === 'Enter') handleCommentSave(t.id); if (e.key === 'Escape') setEditingCommentId(null); }}
                                maxLength={80}
                                className={`flex-1 text-xs rounded-lg px-2 py-1 border focus:outline-none focus:ring-1 focus:ring-ring ${isBrutal ? "bg-zinc-700 border-zinc-600 text-white" : "bg-background border-input"}`}
                              />
                            </div>
                          ) : (
                            <button
                              onClick={() => { setEditingCommentId(t.id); setCommentDraft(t.comments || ""); }}
                              className={`mt-0.5 text-xs block w-full text-left rounded-lg py-1 border border-dashed transition-colors px-5 ${
                                t.comments
                                  ? isBrutal ? "border-zinc-600 text-zinc-300" : "border-border text-foreground"
                                  : isBrutal ? "border-zinc-700 text-zinc-600" : "border-border/50 text-muted-foreground/50"
                              }`}
                            >
                              {t.comments || "e.g. semester, teacher"}
                            </button>
                          )}
                        </div>
                      </div>);

              })}
                </div>
            }
            </div>
          </motion.div>
        </motion.div>
      }
      {/* Download format prompt */}
      <AnimatePresence>
        {showDownloadPrompt &&
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          
            <motion.div
            initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.9, opacity: 0 }}
            className={`w-full max-w-sm rounded-3xl p-6 space-y-4 shadow-2xl ${isBrutal ? "bg-zinc-900" : "bg-white"}`}>
            
              <h3 className={`font-fredoka text-lg ${isBrutal ? "text-orange-400" : "text-primary"}`}>Download {selected.size} reports as…</h3>
              <div className="flex flex-col gap-2">
                <button
                onClick={() => handleBulkDownload(true)}
                className={`w-full py-2.5 rounded-2xl font-bold text-sm transition-all ${isBrutal ? "bg-orange-600 hover:bg-orange-700 text-white" : "bg-primary hover:bg-primary/90 text-primary-foreground"}`}>
                
                  One combined PDF
                </button>
                <button
                onClick={() => handleBulkDownload(false)}
                className={`w-full py-2.5 rounded-2xl font-bold text-sm border transition-all ${isBrutal ? "border-zinc-700 text-zinc-300 hover:bg-zinc-800" : "border-border text-foreground hover:bg-muted"}`}>
                
                  Separate files
                </button>
                <button
                onClick={() => setShowDownloadPrompt(false)}
                className={`w-full py-2 rounded-2xl text-sm transition-all ${isBrutal ? "text-zinc-500 hover:text-zinc-300" : "text-muted-foreground hover:text-foreground"}`}>
                
                  Cancel
                </button>
              </div>
            </motion.div>
          </motion.div>
        }
      </AnimatePresence>
    </AnimatePresence>);

}