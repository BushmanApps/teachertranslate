import { getAcUrl } from "@/lib/acUrl.js";

const SAMPLES = [
{
  title: "Honest mode",
  teacher: "Is developing independence in their learning.",
  translation:
  "Tom is making progress in working on his own without constant teacher direction. He's not there yet, but he's heading in the right direction. He may still need reminders to get started or check his work, but he's beginning to take ownership.",
  accent: "bg-[#a8d8c8]/80",
  badge: "bg-primary text-primary-foreground"
},
{
  title: "Hilarious mode",
  teacher: "Needs to apply themselves more consistently.",
  translation:
  "Tom's coasting like a kid on a pool noodle — barely moving and proud of it. He's got the gears but keeps leaving them in neutral. Teacher's being polite; 'lazy' is the word they're too scared to use.",
  accent: "bg-pink-100",
  badge: "bg-pink-500 text-white",
  hilarious: true
},
{
  title: "Brutal Mode",
  teacher: "Has demonstrated a developing understanding of place value.",
  translation:
  "Tom doesn't get place value. He's guessing. The teacher is wrapping 'he's clueless' in a polite bow so you don't storm the front office. He needs help, not another report card that hides it.",
  accent: "bg-zinc-900",
  badge: "bg-orange-600 text-white",
  brutal: true
},
{
  title: "Year Level Assessment (Pro feature)",
  teacher: "Is building multiplication fact fluency.",
  translation:
  "Tom is working on recalling times tables automatically. In Year 4, students are expected to know these — it makes fractions, division, and problem-solving much easier.",
  accent: "bg-[#fde8cb]/90",
  badge: "bg-accent text-accent-foreground",
  pro: true
}];


export default function SampleScreenshots() {
  return (
    <div className="w-full max-w-lg mx-auto">
      <h2 className="font-fredoka text-2xl text-center text-foreground mb-1">
        See it in action
      </h2>
      <p className="text-center text-xs text-muted-foreground mb-4">
        Real examples of how Teacher Translate decodes report comments
      </p>

      <div className="space-y-4">
        {SAMPLES.map((s, i) =>
        <div
          key={i}
          className={`rounded-3xl shadow-lg overflow-hidden ${s.accent} ${
          s.brutal ? "border border-zinc-700" : s.hilarious ? "border border-pink-300" : "border border-border"}`
          }>
          
            {/* Phone-style header bar */}
            <div
            className={`flex items-center justify-between px-4 py-2.5 ${
            s.brutal ? "bg-zinc-800" : s.hilarious ? "bg-pink-50" : "bg-white/60"}`
            }>
            
              <span
              className={`text-xs font-bold px-3 py-1 rounded-full ${s.badge}`}>
              
                {s.title}
              </span>
              <span
              className={`text-xs ${s.brutal ? "text-zinc-500" : s.hilarious ? "text-pink-400" : "text-muted-foreground"}`}>
              
                Year 4
              </span>
            </div>

            {/* Teacher speak */}
            <div className="px-5 pt-4">
              <p
              className={`text-xs font-semibold uppercase tracking-wide ${
              s.brutal ? "text-orange-400/80" : s.hilarious ? "text-pink-500/80" : "text-primary/70"}`
              }>
              
                Teacher wrote
              </p>
              <p
              className={`text-sm mt-1 italic ${
              s.brutal ? "text-zinc-300" : s.hilarious ? "text-pink-900" : "text-foreground"}`
              }>
              
                &ldquo;{s.teacher}&rdquo;
              </p>
            </div>

            {/* Translation */}
            <div className="px-5 py-4">
              <p
              className={`text-xs font-semibold uppercase tracking-wide ${
              s.brutal ? "text-orange-400/80" : s.hilarious ? "text-pink-500/80" : "text-primary/70"}`
              }>
              
                Translation
              </p>
              <p
              className={`text-sm mt-1 leading-relaxed ${
              s.brutal ? "text-zinc-200" : s.hilarious ? "text-pink-900" : "text-foreground"}`
              }>
              
                {s.translation}
              </p>
              {s.pro &&
            <p className="text-xs mt-2 text-green-700">
                  📚 Australian Curriculum:{" "}
                  <a
                href={getAcUrl("AC9M4A02") || "https://www.australiancurriculum.edu.au/search/?q=AC9M4A02"}
                target="_blank"
                rel="noopener noreferrer"
                className="font-bold underline">
                
                    (AC9M4A02)
                  </a>
                </p>
            }
            </div>

            {/* Supporting activity (Pro feature) */}
            {s.pro &&
          <div className="mx-5 mb-5 rounded-2xl bg-green-50 border border-green-200 p-3">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-sm">🏠</span>
                  <p className="text-xs font-bold text-green-700">Try at home</p>
                  <span className="ml-auto text-[10px] font-bold px-2 py-0.5 rounded-full bg-accent text-accent-foreground">PRO</span>
                </div>
                <p className="text-xs text-green-900 leading-relaxed">
                  Roll two dice and multiply the numbers — race against a 30-second timer. Repeat with different pairs to build automatic recall of times tables.
                </p>
              </div>
          }
          </div>
        )}
      </div>
    </div>);

}