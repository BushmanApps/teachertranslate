import { Heart, GraduationCap } from "lucide-react";

export default function AboutDeveloper() {
  return (
    <div className="w-full max-w-lg mx-auto">
      <h2 className="font-fredoka text-2xl text-center text-foreground mb-1">
        About the developers
      </h2>
      <p className="text-center text-xs text-muted-foreground mb-4">
        Built by people who've sat on both sides of the desk
      </p>

      <div className="bg-[#fde8cb]/90 backdrop-blur-sm rounded-3xl shadow-lg p-6 space-y-4">
        <div className="flex justify-center gap-6">
          <div className="flex flex-col items-center gap-1">
            <div className="p-3 rounded-2xl bg-primary text-primary-foreground">
              <GraduationCap className="w-6 h-6" />
            </div>
            <span className="text-xs font-bold text-foreground">Teachers</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <div className="p-3 rounded-2xl bg-accent text-accent-foreground">
              <Heart className="w-6 h-6" />
            </div>
            <span className="text-xs font-bold text-foreground">Parents</span>
          </div>
        </div>

        <div className="space-y-3 text-sm text-foreground leading-relaxed">
          <p>
            Teacher Translate was created by a team of ex and current Australian
            classroom teachers — who are also parents themselves.
          </p>
          <p>Combined, we've spent decades writing report card comments and know parents squint at them, nod politely, and file it away while being none the wiser.



          </p>
          <p>
            The truth is, teachers choose their words very carefully
            — sometimes <em>too</em> carefully. What looks like a simple sentence
            often carries a whole lot of context, hedging, and professional
            restraint that only another teacher would fully decode.
          </p>
          <p>
            We built this app because parents deserve to genuinely understand
            how their child is tracking at school — not just the polished,
            parent-friendly version. Every parent should have access to
            the same insights a teacher brings to the nuance of a school report -
            without needing years of classroom experience to get there.
          </p>
          <p>
            And honestly, it also gives us the chance to say the things we
            really want you to know — the helpful, hopeful, occasionally
            hilarious truths that don't fit neatly into a report card comment
            box. We've been wanting to tell you this stuff for years.
          </p>
          <p className="font-semibold text-primary pt-1">We hope it makes you (and your child) laugh, but more importantly, that it helps.
          </p>
        </div>
      </div>
    </div>);

}