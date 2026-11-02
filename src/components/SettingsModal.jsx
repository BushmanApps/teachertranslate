import { useState, useEffect, useRef } from "react";
import { X, Trash2, LogOut, AlertTriangle, Sun, Moon, ChevronDown, Clock } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useIsMobile } from "@/hooks/use-mobile";
import { base44 } from "@/api/base44Client";
import { useAuth } from "@/lib/AuthContext";
import { clearSetupShown } from "@/lib/setupSession";

const YEAR_LEVELS = [
  "Kindergarten / Preparatory",
  "Year 1", "Year 2", "Year 3", "Year 4", "Year 5", "Year 6",
  "Year 7", "Year 8", "Year 9", "Year 10", "Year 11", "Year 12",
];

export default function SettingsModal({ isOpen, onClose, studentYear, studentName, creatorEmail, students, activeStudentId, onSelectStudent, onAddNewStudent, onSave, onDelete, isBrutal, hasActiveResult, isSubscribed, subscriptionRenewal, onUpgrade, darkMode, onToggleDarkMode }) {
  const [year, setYear] = useState(studentYear || "");
  const [name, setName] = useState(studentName || "");
  const isMobile = useIsMobile();
  const { logout } = useAuth();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmDeleteAccount, setConfirmDeleteAccount] = useState(false);
  const [confirmLogout, setConfirmLogout] = useState(false);
  const [showYearWarning, setShowYearWarning] = useState(false);
  const [nameDropdownOpen, setNameDropdownOpen] = useState(false);
  const [hasUserEditedName, setHasUserEditedName] = useState(false);
  const [, setPickedStudent] = useState(null);
  const nameInputRef = useRef(null);
  const nameDropdownRef = useRef(null);

  const renewalDisplay = subscriptionRenewal
    ? new Date(subscriptionRenewal).toLocaleDateString("en-AU", { day: "numeric", month: "long", year: "numeric" })
    : "your renewal date";

  // Reset confirm dialogs when modal closes
  useEffect(() => {
    if (!isOpen) {
      setConfirmDelete(false);
      setConfirmDeleteAccount(false);
      setDeletingDeferred(false);
      setNameDropdownOpen(false);
      setHasUserEditedName(false);
      setConfirmLogout(false);
      setPickedStudent(null);
    }
  }, [isOpen]);

  // Close name dropdown on outside click
  useEffect(() => {
    if (!nameDropdownOpen) return;
    const handler = (e) => {
      if (nameDropdownRef.current && !nameDropdownRef.current.contains(e.target)) {
        setNameDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [nameDropdownOpen]);

  // Sync inputs when props change
  useEffect(() => {
    setYear(studentYear || "");
    setName(studentName || "");
    setHasUserEditedName(false);
  }, [studentYear, studentName, creatorEmail]);

  // Global Enter key handler
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e) => {
      if (e.key === "Enter" && year && !confirmDelete && !confirmDeleteAccount && !showYearWarning && !confirmLogout) {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, year, name, confirmDelete, confirmDeleteAccount, showYearWarning, confirmLogout]);

  function handleSave() {
    const yearChanged = year !== studentYear;
    if (yearChanged && hasActiveResult) {
      setShowYearWarning(true);
      return;
    }
    onSave({ studentYear: year, studentName: name });
    onClose();
  }

  function handleConfirmYearChange() {
    setShowYearWarning(false);
    onSave({ studentYear: year, studentName: name });
    onClose();
  }

  function handleLogout() {
    setConfirmLogout(false);
    clearSetupShown();
    // Sign out through the shared AuthContext so React auth state and token
    // cleanup stay synchronized — critical on a fresh install or after app
    // data has been cleared, where calling the SDK logout alone can leave
    // the app's in-memory session stale and the redirect silently no-ops.
    logout(true, "/welcome");
  }

  const [deletingAccount, setDeletingAccount] = useState(false);
  const [deletingDeferred, setDeletingDeferred] = useState(false);

  async function handleDeleteAccount(mode) {
    if (mode === "deferred" && window.eb44?.isMobileApp?.()) {
      const platform = window.Capacitor?.getPlatform?.();
      const packageName = "com.base69fc81cf4f6a0ae5ab617e2b.app";
      const url = platform === "ios"
        ? "https://apps.apple.com/account/subscriptions"
        : `https://play.google.com/store/account/subscriptions?package=${packageName}&sku=teacher_translate_pro_users`;
      window.location.assign(url);
      return;
    }
    setDeletingAccount(true);
    try {
      await base44.functions.invoke("deleteAccount", { deleteMode: mode });
      if (mode === "deferred") {
        setDeletingDeferred(true);
        setDeletingAccount(false);
        return;
      }
    } catch (e) {
      console.error("Account deletion error:", e);
    } finally {
      if (mode !== "deferred") {
        clearSetupShown();
        base44.auth.logout("/");
      }
    }
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className={`w-full max-w-lg rounded-3xl p-4 space-y-3 overflow-y-auto mx-4 max-h-[90vh] ${
              isBrutal ? "bg-zinc-900 text-white" : "bg-white"
            }`}
            style={{ paddingBottom: "calc(1rem + env(safe-area-inset-bottom))" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={`flex items-center justify-between sticky top-0 z-20 -mx-4 px-4 -mt-4 pt-4 pb-2 ${isBrutal ? "bg-zinc-900" : "bg-white"}`}>
              <h2 className={`font-fredoka text-xl ${isBrutal ? "text-orange-400" : "text-primary"}`}>
                ⚙️ Settings
              </h2>
              <div className="flex items-center gap-0.5">
                <button
                  onClick={(e) => { e.stopPropagation(); onToggleDarkMode?.(!darkMode); }}
                  type="button"
                  className={`relative z-10 p-2.5 rounded-full hover:bg-muted active:bg-muted cursor-pointer select-none transition-colors ${darkMode && !isBrutal ? "text-amber-400" : "text-muted-foreground"}`}
                  title={darkMode ? "Light mode" : "Dark mode"}
                >
                  {darkMode && !isBrutal ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
                </button>
                <button onClick={(e) => { e.stopPropagation(); onClose(); }} type="button" className="relative z-10 p-3 -mr-1 rounded-full hover:bg-muted active:bg-muted cursor-pointer select-none transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="space-y-3">
              <div className="space-y-1 relative" ref={nameDropdownRef}>
                <label className="text-sm font-bold">Child's first name (optional)</label>
                <div className="relative">
                  <input
                    ref={nameInputRef}
                    value={name}
                    onChange={(e) => { setName(e.target.value.replace(/[<>]/g, "").slice(0, 12)); setNameDropdownOpen(true); setHasUserEditedName(true); }}
                    onFocus={() => { if (!hasUserEditedName) { setName(""); setHasUserEditedName(true); } setNameDropdownOpen(true); }}
                    onKeyDown={(e) => { if (e.key === "Enter" && year) { setNameDropdownOpen(false); handleSave(); } }}
                    maxLength={12}
                    placeholder="e.g. Tom (max 12 characters)"
                    className={`w-full rounded-xl border px-4 py-2 pr-9 text-sm focus:outline-none focus:ring-2 focus:ring-ring ${
                      isBrutal ? "bg-zinc-800 border-zinc-600 text-white" : "bg-background border-input"
                    }`}
                  />
                  {students && students.length > 0 && (
                    <button
                      type="button"
                      onClick={() => { setNameDropdownOpen(!nameDropdownOpen); nameInputRef.current?.focus(); }}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1"
                    >
                      <ChevronDown className={`w-4 h-4 transition-transform ${nameDropdownOpen ? "rotate-180" : ""} ${isBrutal ? "text-zinc-400" : "text-muted-foreground"}`} />
                    </button>
                  )}
                </div>
                <AnimatePresence>
                  {nameDropdownOpen && students && students.length > 0 && (
                    <motion.div
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -4 }}
                      className={`absolute z-30 w-full mt-1 rounded-xl border shadow-lg max-h-48 overflow-y-auto ${
                        isBrutal ? "bg-zinc-800 border-zinc-600" : "bg-white border-border"
                      }`}
                    >
                      {students
                        .filter((s) => {
                          if (!hasUserEditedName) return true;
                          const typed = name.trim().toLowerCase();
                          if (!typed) return true;
                          return (s.student_name || "").toLowerCase().includes(typed);
                        })
                        .map((s) => {
                          const isActive = s.id === activeStudentId;
                          return (
                            <button
                              key={s.id}
                              type="button"
                              onClick={() => {
                                setPickedStudent(s);
                                setName(s.student_name || "");
                                setNameDropdownOpen(false);
                                setHasUserEditedName(false);
                              }}
                              className={`w-full flex items-center justify-between px-4 py-2 text-sm transition-all select-none text-left ${
                                isActive
                                  ? isBrutal ? "bg-orange-600 text-white" : "bg-primary text-primary-foreground"
                                  : isBrutal ? "text-zinc-200 hover:bg-zinc-700" : "text-foreground hover:bg-muted"
                              }`}
                            >
                              <span>{s.student_name || "Unnamed"}</span>
                              <span className={`text-xs font-normal ${isActive ? "opacity-80" : "opacity-50"}`}>{s.student_year}</span>
                            </button>
                          );
                        })}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {creatorEmail && (
                <div className="space-y-1">
                  <label className="text-sm font-bold">Created By</label>
                  <div className={`w-full rounded-xl border px-4 py-2 text-sm ${isBrutal ? "bg-zinc-800 border-zinc-600 text-zinc-400" : "bg-muted border-border text-muted-foreground"}`}>
                    {creatorEmail}
                  </div>
                </div>
              )}

              <div className="space-y-1">
                <label className="text-sm font-bold">Year Level</label>
                <div className="grid grid-cols-3 gap-2">
                  {YEAR_LEVELS.map((y) => {
                    const isKinder = y === "Kindergarten / Preparatory";
                    const isSelected = year === y;
                    return (
                      <button
                        key={y}
                        onClick={() => setYear(y)}
                        className={`${isKinder ? "col-span-3" : ""} py-2.5 px-3 rounded-xl text-xs font-semibold border-2 transition-all text-center select-none ${
                          isSelected
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

            {onDelete && confirmDelete ? (
              <div className="space-y-2">
                <p className="text-xs text-center text-muted-foreground">Are you sure you want to remove this student? This will not delete any translations already made for this student. Please visit the history section to remove previous translations.</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setConfirmDelete(false)}
                    className="flex-1 py-2 rounded-2xl font-bold text-sm border border-border select-none"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={onDelete}
                    className="flex-1 py-2 rounded-2xl font-bold text-sm text-destructive border border-destructive/30 hover:bg-destructive/5 transition-all select-none"
                  >
                    Yes, Remove
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                {onDelete && (
                  <button
                    onClick={() => setConfirmDelete(true)}
                    className="flex-1 py-2.5 rounded-2xl font-bold text-sm text-destructive border border-destructive/30 hover:bg-destructive/5 transition-all select-none"
                  >
                    Remove student
                  </button>
                )}
                <button
                  onClick={handleSave}
                  disabled={!year}
                  className={`flex-[2] py-2.5 rounded-2xl font-bold text-sm transition-all disabled:opacity-40 select-none ${
                    isBrutal
                      ? "bg-orange-600 hover:bg-orange-700 text-white"
                      : "bg-primary hover:bg-primary/90 text-primary-foreground"
                  }`}
                >
                  Save Settings
                </button>
              </div>
            )}

            {!isSubscribed && (
              <button
                onClick={() => { onUpgrade?.(); }}
                className={`w-full py-2.5 rounded-2xl font-bold text-sm transition-all select-none ${
                  isBrutal ? "bg-orange-600 hover:bg-orange-700 text-white" : "bg-primary hover:bg-primary/90 text-primary-foreground"
                }`}
              >
                ✨ Go Pro
              </button>
            )}

            <div className={`border-t pt-3 space-y-2 flex flex-col items-center ${isBrutal ? "border-zinc-700" : "border-border"}`}>
              <button
                onClick={() => setConfirmLogout(true)}
                className={`py-2.5 px-8 rounded-2xl font-bold text-sm flex items-center justify-center gap-2 transition-all select-none border ${
                  isBrutal ? "border-zinc-700 text-zinc-300 hover:bg-zinc-800" : "border-border text-foreground hover:bg-muted"
                }`}
              >
                <LogOut className="w-4 h-4" /> Log Out
              </button>

              <button
                  onClick={() => setConfirmDeleteAccount(true)}
                  className={`w-full py-2.5 rounded-2xl font-bold text-xs flex items-center justify-center gap-2 transition-all select-none ${
                    isBrutal ? "text-zinc-500 hover:text-red-400" : "text-muted-foreground hover:text-destructive"
                  }`}
                >
                  <Trash2 className="w-3.5 h-3.5" /> Delete Account
                </button>

              <div className={`flex items-center justify-center gap-3 pt-1 text-xs ${isBrutal ? "text-zinc-600" : "text-gray-500"}`}>
                <a href="/support" target="_blank" rel="noopener noreferrer" className="underline underline-offset-2 hover:text-gray-800 transition-colors">Support</a>
                <span>·</span>
                <a href="/terms" target="_blank" rel="noopener noreferrer" className="underline underline-offset-2 hover:text-gray-800 transition-colors">Terms of Use</a>
                <span>·</span>
                <a href="/privacy" target="_blank" rel="noopener noreferrer" className="underline underline-offset-2 hover:text-gray-800 transition-colors">Privacy Policy</a>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}

      {/* Delete account confirmation popup */}
      <AnimatePresence>
        {confirmDeleteAccount && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={`fixed inset-0 z-[60] flex ${isMobile ? "items-end" : "items-center"} justify-center bg-black/60 backdrop-blur-sm p-4`}
          >
            <motion.div
              initial={isMobile ? { y: "100%" } : { scale: 0.9, opacity: 0 }}
              animate={isMobile ? { y: 0 } : { scale: 1, opacity: 1 }}
              exit={isMobile ? { y: "100%" } : { scale: 0.9, opacity: 0 }}
              transition={{ type: "spring", damping: 25, stiffness: 300 }}
              className={`w-full ${isMobile ? "max-w-lg rounded-t-3xl" : "max-w-sm rounded-3xl"} p-6 space-y-4 shadow-2xl ${isBrutal ? "bg-zinc-900" : "bg-white"}`}
              style={isMobile ? { paddingBottom: "calc(1rem + env(safe-area-inset-bottom))" } : undefined}
            >
              {deletingDeferred ? (
                <>
                  <div className="flex items-center gap-3">
                    <Clock className="w-6 h-6 flex-shrink-0 text-emerald-500" />
                    <h3 className={`font-fredoka text-lg ${isBrutal ? "text-orange-400" : "text-primary"}`}>
                      Subscription Scheduled to Cancel
                    </h3>
                  </div>
                  <p className={`text-sm leading-relaxed ${isBrutal ? "text-zinc-300" : "text-foreground/80"}`}>
                    Your Pro subscription will stay active until{subscriptionRenewal ? ` ${renewalDisplay}` : " your renewal date"}, then revert to a free account. You won't be charged again. Your account and translations remain intact in the meantime.
                  </p>
                  <button
                    onClick={() => { setConfirmDeleteAccount(false); setDeletingDeferred(false); onClose?.(); }}
                    className={`w-full py-2.5 rounded-2xl font-bold text-sm transition-all select-none ${isBrutal ? "bg-orange-600 hover:bg-orange-700 text-white" : "bg-primary hover:bg-primary/90 text-primary-foreground"}`}
                  >
                    Done
                  </button>
                </>
              ) : (
                <>
                  <div className="flex items-center gap-3">
                    <AlertTriangle className="w-6 h-6 flex-shrink-0 text-red-500" />
                    <h3 className={`font-fredoka text-lg ${isBrutal ? "text-orange-400" : "text-primary"}`}>
                      Delete Account
                    </h3>
                  </div>
                  <p className={`text-sm leading-relaxed ${isBrutal ? "text-zinc-300" : "text-foreground/80"}`}>
                    This will permanently delete your account and all translation data. All translations will be removed. Ensure you have first downloaded all reports that you want to save (if you are a pro user), by going to the History section.
                  </p>

                  {isSubscribed && subscriptionRenewal && (
                    <div className={`rounded-2xl border p-4 space-y-3 ${isBrutal ? "border-zinc-700 bg-zinc-800/50" : "border-emerald-200 bg-emerald-50"}`}>
                      <p className={`text-sm font-bold ${isBrutal ? "text-orange-400" : "text-emerald-700"}`}>
                        Keep access until {renewalDisplay}?
                      </p>
                      <p className={`text-xs leading-relaxed ${isBrutal ? "text-zinc-400" : "text-emerald-800/80"}`}>
                        Cancel your subscription at the end of your current billing period. You'll keep Pro access until {renewalDisplay}, then revert to a free account — no further charges. Your account and translations will stay intact until this date.
                      </p>
                      <button
                        onClick={() => handleDeleteAccount("deferred")}
                        disabled={deletingAccount}
                        className={`w-full py-2.5 rounded-2xl font-bold text-sm transition-all select-none disabled:opacity-60 ${isBrutal ? "bg-orange-600 hover:bg-orange-700 text-white" : "bg-emerald-600 hover:bg-emerald-700 text-white"}`}
                      >
                        Cancel at Renewal Date
                      </button>
                    </div>
                  )}

                  <div className="space-y-2">
                    <p className={`text-xs font-semibold text-center ${isBrutal ? "text-zinc-500" : "text-muted-foreground"}`}>
                      Or delete everything now:
                    </p>
                    <div className="flex gap-3">
                      <button
                        onClick={() => setConfirmDeleteAccount(false)}
                        disabled={deletingAccount}
                        className={`flex-1 py-2.5 rounded-2xl font-bold text-sm border transition-all select-none disabled:opacity-60 ${isBrutal ? "border-zinc-700 text-zinc-300 hover:bg-zinc-800" : "border-border text-foreground hover:bg-muted"}`}
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => handleDeleteAccount("immediate")}
                        disabled={deletingAccount}
                        className="flex-1 py-2.5 rounded-2xl font-bold text-sm bg-red-600 text-white hover:bg-red-700 transition-all select-none disabled:opacity-60"
                      >
                        {deletingAccount ? "Deleting..." : "Delete Now"}
                      </button>
                    </div>
                  </div>
                </>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Logout confirmation popup */}
      <AnimatePresence>
        {confirmLogout && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={`fixed inset-0 z-[60] flex ${isMobile ? "items-end" : "items-center"} justify-center bg-black/60 backdrop-blur-sm p-4`}
          >
            <motion.div
              initial={isMobile ? { y: "100%" } : { scale: 0.9, opacity: 0 }}
              animate={isMobile ? { y: 0 } : { scale: 1, opacity: 1 }}
              exit={isMobile ? { y: "100%" } : { scale: 0.9, opacity: 0 }}
              transition={{ type: "spring", damping: 25, stiffness: 300 }}
              className={`w-full ${isMobile ? "max-w-lg rounded-t-3xl" : "max-w-sm rounded-3xl"} p-6 space-y-4 shadow-2xl ${isBrutal ? "bg-zinc-900" : "bg-white"}`}
              style={isMobile ? { paddingBottom: "calc(1rem + env(safe-area-inset-bottom))" } : undefined}
            >
              <div className="flex items-center gap-3">
                <LogOut className={`w-6 h-6 flex-shrink-0 ${isBrutal ? "text-orange-400" : "text-primary"}`} />
                <h3 className={`font-fredoka text-lg ${isBrutal ? "text-orange-400" : "text-primary"}`}>
                  Log Out?
                </h3>
              </div>
              <p className={`text-sm leading-relaxed ${isBrutal ? "text-zinc-300" : "text-foreground/80"}`}>
                You'll need to sign in again to use Teacher Translate. Your translations and subscription are safely saved.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setConfirmLogout(false)}
                  className={`flex-1 py-2.5 rounded-2xl font-bold text-sm border transition-all select-none ${isBrutal ? "border-zinc-700 text-zinc-300 hover:bg-zinc-800" : "border-border text-foreground hover:bg-muted"}`}
                >
                  Cancel
                </button>
                <button
                  onClick={handleLogout}
                  className={`flex-1 py-2.5 rounded-2xl font-bold text-sm transition-all select-none ${isBrutal ? "bg-orange-600 hover:bg-orange-700 text-white" : "bg-primary hover:bg-primary/90 text-primary-foreground"}`}
                >
                  Log Out
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Year change confirmation dialog */}
      <AnimatePresence>
        {showYearWarning && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={`fixed inset-0 z-[60] flex ${isMobile ? "items-end" : "items-center"} justify-center bg-black/60 backdrop-blur-sm p-4`}
          >
            <motion.div
              initial={isMobile ? { y: "100%" } : { scale: 0.9, opacity: 0 }}
              animate={isMobile ? { y: 0 } : { scale: 1, opacity: 1 }}
              exit={isMobile ? { y: "100%" } : { scale: 0.9, opacity: 0 }}
              transition={{ type: "spring", damping: 25, stiffness: 300 }}
              className={`w-full ${isMobile ? "max-w-lg rounded-t-3xl" : "max-w-sm rounded-3xl"} p-6 space-y-4 shadow-2xl ${isBrutal ? "bg-zinc-900" : "bg-white"}`}
              style={isMobile ? { paddingBottom: "calc(1rem + env(safe-area-inset-bottom))" } : undefined}
            >
              <div className="flex items-center gap-3">
                <AlertTriangle className={`w-6 h-6 flex-shrink-0 ${isBrutal ? "text-orange-400" : "text-amber-500"}`} />
                <h3 className={`font-fredoka text-lg ${isBrutal ? "text-orange-400" : "text-primary"}`}>
                  New Translation Required
                </h3>
              </div>
              <p className={`text-sm leading-relaxed ${isBrutal ? "text-zinc-300" : "text-foreground/80"}`}>
                Changing the year level will re-translate the current report using <strong>{year}</strong> curriculum standards and supporting resources.{!isSubscribed && " This will use up one of your free scans."}
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowYearWarning(false)}
                  className={`flex-1 py-2.5 rounded-2xl font-bold text-sm border transition-all select-none ${isBrutal ? "border-zinc-700 text-zinc-300 hover:bg-zinc-800" : "border-border text-foreground hover:bg-muted"}`}
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirmYearChange}
                  className={`flex-1 py-2.5 rounded-2xl font-bold text-sm transition-all select-none ${isBrutal ? "bg-orange-600 hover:bg-orange-700 text-white" : "bg-primary hover:bg-primary/90 text-primary-foreground"}`}
                >
                  Yes, Re-translate
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </AnimatePresence>
  );
}