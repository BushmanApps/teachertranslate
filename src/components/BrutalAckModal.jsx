import { motion, AnimatePresence } from "framer-motion";

export default function BrutalAckModal({ isOpen, onClose, onAccept }) {
  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.92, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.92, y: 20 }}
            className="fixed inset-0 z-50 flex items-center justify-center px-6 pointer-events-none"
          >
            <div className="bg-white rounded-3xl shadow-2xl p-6 max-w-sm w-full pointer-events-auto space-y-4 text-center">
              <div className="text-5xl">💥</div>
              <h2 className="font-fredoka text-xl text-orange-600">Brutal Mode</h2>
              <p className="text-sm leading-relaxed text-foreground/80">
                You're about to switch to <strong>Brutal</strong> mode. These translations are very
                direct, succinct and can be confronting — they reflect what a teacher might{" "}
                <em>want</em> to say but isn't allowed to.
              </p>
              <p className="text-xs leading-relaxed text-muted-foreground">
                Translations are AI-generated interpretations, not literal statements. In all
                instances, please seek clarification directly from your child's teacher.
              </p>
              <div className="flex flex-col gap-2 pt-1">
                <button
                  onClick={onAccept}
                  className="w-full py-3 bg-orange-600 hover:bg-orange-700 text-white font-bold rounded-2xl text-sm transition-all"
                >
                  I understand — bring on the truth
                </button>
                <button
                  onClick={onClose}
                  className="w-full py-2.5 text-sm font-semibold text-muted-foreground hover:text-foreground transition-all"
                >
                  No thanks
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}