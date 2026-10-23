import { useState } from "react";
import { motion } from "framer-motion";
import { PenLine } from "lucide-react";

const YEAR_LEVELS = [
"Kindergarten / Prep",
"Year 1", "Year 2", "Year 3", "Year 4", "Year 5", "Year 6",
"Year 7", "Year 8", "Year 9", "Year 10", "Year 11", "Year 12"];



export default function OnboardingScreen({ onComplete, onSkip, onConsent, startAtStep = 1 }) {
  const [step, setStep] = useState(startAtStep);
  const [studentName, setStudentName] = useState("");
  const [studentYear, setStudentYear] = useState("");
  const [consented, setConsented] = useState(false);

  const handleComplete = () => {
    onComplete({ studentName, studentYear });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-600 via-pink-500 to-orange-400 flex items-center justify-center p-2 sm:p-4 overflow-y-auto">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-white rounded-3xl p-5 sm:p-6 w-full max-w-sm md:max-w-md shadow-2xl space-y-4 max-h-[95svh] overflow-y-auto">
        
        {step === 1 &&
        <motion.div
          key="step1"
          initial={{ opacity: 0, x: 30 }}
          animate={{ opacity: 1, x: 0 }}
          className="space-y-6 text-center">
          
            <img
            src="https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets/images/public/69fc81cf4f6a0ae5ab617e2b/c7bffff4e_TTLogo01.png"
            alt="Teacher Translate"
            className="w-24 h-24 object-contain mx-auto" />
          
            <div>
              <h1 className="font-fredoka text-3xl text-purple-700 leading-tight">
                Teacher Translate
              </h1>
              <p className="text-muted-foreground text-sm mt-2">
                Decode what your child's teacher is <em>actually</em> trying to tell you.
              </p>
            </div>
            <div className="space-y-3 md:space-y-0 md:grid md:grid-cols-2 md:gap-3 text-left">
              <div className="flex gap-3 items-start">
                <span className="text-2xl">😊</span>
                <div>
                  <p className="font-bold text-sm">Honest Mode</p>
                  <p className="text-xs text-muted-foreground">Clear, kind translation of teacher-speak.</p>
                </div>
              </div>
              <div className="flex gap-3 items-start">
                <span className="text-2xl">🤣</span>
                <div>
                  <p className="font-bold text-sm">Hilarious Mode</p>
                  <p className="text-xs text-muted-foreground">Funny, savage but never mean.</p>
                </div>
              </div>
              <div className="flex gap-3 items-start">
                <span className="text-2xl">💥</span>
                <div>
                  <p className="font-bold text-sm">Brutal Mode</p>
                  <p className="text-xs text-muted-foreground">No filter. The raw, unfiltered truth.</p>
                </div>
              </div>
              <div className="flex gap-3 items-start">
                <span className="text-2xl">📊</span>
                <div>
                  <p className="font-bold text-sm">Year Level Assessment</p>
                  <p className="text-xs text-muted-foreground">Know if your child is ahead, on track, or behind.</p>
                </div>
              </div>
            </div>
            <div className="bg-purple-50 border border-purple-100 rounded-xl p-3 space-y-1.5 text-left">
              <p className="text-xs text-muted-foreground leading-relaxed">
                <span className="font-bold text-purple-700">📷 Camera:</span> Enable camera permission to use the "Scan with Camera" feature. You can still upload files or paste text manually without it.
              </p>
              <p className="text-xs text-muted-foreground leading-relaxed">
                <span className="font-bold text-purple-700">🔔 Notifications:</span> Push notifications can be safely disabled — Teacher Translate does not use this feature.
              </p>
            </div>
            <label className="flex items-start gap-2.5 text-left cursor-pointer">
              <input
              type="checkbox"
              checked={consented}
              onChange={(e) => setConsented(e.target.checked)}
              className="mt-0.5 w-4 h-4 accent-purple-600 shrink-0" />
            
              <span className="text-xs text-muted-foreground leading-relaxed">
                I have read and agree to the{" "}
                <a href="/privacy?from=consent" target="_blank" rel="noopener noreferrer" className="font-semibold text-purple-700 underline underline-offset-2">Privacy Policy</a>{" "}
                and{" "}
                <a href="/terms?from=consent" target="_blank" rel="noopener noreferrer" className="font-semibold text-purple-700 underline underline-offset-2">Terms of Use</a>, which include reasonable use of the app.
              </span>
            </label>
            <button
            onClick={() => {onConsent?.();setStep(2);}}
            disabled={!consented}
            className="w-full py-3 bg-purple-600 text-white font-bold rounded-2xl hover:bg-purple-700 transition-all disabled:bg-gray-300 disabled:text-gray-500 disabled:cursor-not-allowed">
            
              Let's Go! →
            </button>
          </motion.div>
        }

        {step === 2 &&
        <motion.div
          key="step2"
          initial={{ opacity: 0, x: 30 }}
          animate={{ opacity: 1, x: 0 }}
          className="space-y-3">
          
            <div className="text-center">
              <div className="text-3xl mb-1">🎒</div>
              <h2 className="font-fredoka text-xl text-purple-700">About Your Child</h2>
              <p className="text-xs text-muted-foreground mt-0.5">This helps us give accurate assessments</p>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-bold text-foreground">Child's first name (optional)</label>
              <input
              value={studentName}
              onChange={(e) => setStudentName(e.target.value.replace(/[<>]/g, "").slice(0, 12))}
              maxLength={12}
              placeholder="e.g. Emma"
              className="w-full rounded-xl border border-input px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400" />
            
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-bold text-foreground">What year are they in?</label>
              <button
              onClick={() => setStudentYear("Kindergarten / Prep")}
              className={`w-full py-2.5 px-3 rounded-xl text-sm font-semibold border-2 transition-all text-center ${
              studentYear === "Kindergarten / Prep" ?
              "border-purple-600 bg-purple-600 text-white" :
              "border-border text-foreground hover:border-purple-300"}`
              }>
              
                Kindergarten / Prep
              </button>
              <div className="grid grid-cols-3 gap-2">
                {YEAR_LEVELS.filter((y) => y !== "Kindergarten / Prep").map((y) =>
              <button
                key={y}
                onClick={() => setStudentYear(y)}
                className={`py-2.5 px-1 rounded-xl text-sm font-semibold border-2 transition-all ${
                studentYear === y ?
                "border-purple-600 bg-purple-600 text-white" :
                "border-border text-foreground hover:border-purple-300"}`
                }>
                
                    {y}
                  </button>
              )}
              </div>
            </div>

            <div className="space-y-2 pt-1">
              <button
              onClick={handleComplete}
              disabled={!studentYear}
              className="w-full py-3 bg-purple-600 text-white font-bold rounded-2xl hover:bg-purple-700 transition-all disabled:opacity-40 disabled:cursor-not-allowed">
              
                Start Translating! <PenLine className="inline w-5 h-5 ml-1" />
              </button>
              <button
              onClick={onSkip}
              className="w-full py-2 text-sm font-semibold text-muted-foreground hover:text-purple-700 transition-all">
              
                Skip and go to main console
              </button>
            </div>
          </motion.div>
        }
      </motion.div>
    </div>);

}