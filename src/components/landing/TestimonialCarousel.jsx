import { useState, useRef } from "react";
import { ChevronLeft, ChevronRight, Star } from "lucide-react";

const TESTIMONIALS = [
{
  quote:
  "I read my son's reports again and again and still couldn't really figure out how he was doing. Teacher Translate turned a daunting day of report decoding and emailing into something I actually understood. Thank you!!",
  name: "Aja",
  detail: "Mum of a Year 5 boy",
  rating: 5
},
{
  quote:
  "The Hilarious mode had me laughing out loud — but underneath the jokes it was genuinely useful. I finally understood what 'needs to apply themselves' really meant.",
  name: "James",
  detail: "Dad of a Year 6 boy",
  rating: 5
},
{
  quote:
  "As a parent who dreads report season, this is a game-changer. The year-level expectations were the part I needed most. Now I know whether my child is actually on track. Many thanks!",
  name: "Sheridan",
  detail: "Mum of two boys",
  rating: 5
},
{
  quote:
  "The Write Back feature saved me twenty minutes of agonising over an email to one of my son's teachers. It sounded professional and warm at the same time.",
  name: "Daniel",
  detail: "Dad of a Year 8 student",
  rating: 5
},
{
  quote:
  "I'm a teacher myself and even I found the translations helpful for my own kids' reports. The curriculum activities are spot on for their year levels. Brutal mode is also absolutely brilliant and eerily accurate.",
  name: "Sara",
  detail: "Teacher & mum of a Year 3 & 6 student",
  rating: 5
}];


export default function TestimonialCarousel() {
  const [index, setIndex] = useState(0);
  const touchStartX = useRef(null);

  const goPrev = () => setIndex((i) => i === 0 ? TESTIMONIALS.length - 1 : i - 1);
  const goNext = () => setIndex((i) => i === TESTIMONIALS.length - 1 ? 0 : i + 1);

  const handleTouchStart = (e) => {
    touchStartX.current = e.touches[0].clientX;
  };

  const handleTouchEnd = (e) => {
    if (touchStartX.current === null) return;
    const delta = e.changedTouches[0].clientX - touchStartX.current;
    if (Math.abs(delta) > 40) {
      if (delta > 0) goPrev();else
      goNext();
    }
    touchStartX.current = null;
  };

  const t = TESTIMONIALS[index];

  return (
    <div className="w-full max-w-lg mx-auto">
      <h2 className="font-fredoka text-2xl text-center text-foreground mb-1">
        What parents are saying
      </h2>
      <p className="text-center text-xs text-muted-foreground mb-4">
        Swipe through real parent reviews
      </p>

      <div
        className="relative bg-[#a8d8c8]/80 backdrop-blur-sm rounded-3xl shadow-lg p-6 select-none"
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}>
        
        <div className="flex gap-1 justify-center mb-4">
          {Array.from({ length: t.rating }).map((_, i) =>
          <Star key={i} className="w-4 h-4 fill-accent text-[hsl(var(--accent-foreground))]" />
          )}
        </div>

        <p className="text-sm text-foreground leading-relaxed text-center italic mx-8">
          &ldquo;{t.quote}&rdquo;
        </p>

        <div className="mt-4 text-center">
          <p className="font-bold text-sm text-foreground">{t.name}</p>
          <p className="text-xs text-muted-foreground">{t.detail}</p>
        </div>

        {/* Desktop arrows */}
        <button
          onClick={goPrev}
          className="hidden sm:flex absolute left-2 top-1/2 -translate-y-1/2 p-2 rounded-full bg-white/70 hover:bg-white text-foreground shadow-sm transition-all"
          aria-label="Previous testimonial">
          
          <ChevronLeft className="w-5 h-5" />
        </button>
        <button
          onClick={goNext}
          className="hidden sm:flex absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-full bg-white/70 hover:bg-white text-foreground shadow-sm transition-all"
          aria-label="Next testimonial">
          
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>

      {/* Dots */}
      <div className="flex gap-2 justify-center mt-4">
        {TESTIMONIALS.map((_, i) =>
        <button
          key={i}
          onClick={() => setIndex(i)}
          className={`h-2 rounded-full transition-all ${
          i === index ? "w-6 bg-primary" : "w-2 bg-primary/30"}`
          }
          aria-label={`Go to testimonial ${i + 1}`} />

        )}
      </div>
    </div>);

}