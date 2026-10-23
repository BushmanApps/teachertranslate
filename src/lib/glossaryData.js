const EARLY = ["Kindergarten / Preparatory", "Year 1", "Year 2"];
const MID_PRIMARY = ["Year 3", "Year 4"];
const UPPER_PRIMARY = ["Year 5", "Year 6"];
const JUNIOR_SEC = ["Year 7", "Year 8", "Year 9"];
const SENIOR_SEC = ["Year 10", "Year 11", "Year 12"];
const ALL = [...EARLY, ...MID_PRIMARY, ...UPPER_PRIMARY, ...JUNIOR_SEC, ...SENIOR_SEC];

export const GLOSSARY_DATA = [
  // ── Universal (all year levels) ──
  {
    teacher_speak: "Is a pleasure to have in class.",
    category: "Effort",
    honest: "This is genuine, wholehearted praise. Your child is cooperative, kind, and contributes positively to the classroom. They follow instructions, treat their peers with respect, and make the teacher's day smoother. Not every child earns this comment — soak it up!",
    hilarious: "Your kid doesn't cause problems. In teacher-speak, that's basically a standing ovation.",
    brutal: "Your kid isn't a nightmare. Congratulations, you've cleared the lowest possible bar."
  },
  {
    teacher_speak: "Needs to apply themselves more consistently.",
    category: "Effort",
    honest: "Your child shows ability in bursts but doesn't sustain it. They might nail a task one week and coast the next. The teacher is politely flagging that your child's effort is intermittent — they're capable of more, but only deliver when they feel like it. This is a gentle way of saying 'could try harder'.",
    hilarious: "Your child is coasting. They could do better but can't be bothered. The teacher is too polite to say 'lazy'.",
    brutal: "Your child is lazy. There, someone finally said it. They do the bare minimum and only try when they feel like it."
  },
  {
    teacher_speak: "Is easily distracted.",
    category: "Focus",
    honest: "Your child struggles to maintain focus during lessons. Their attention wanders — to classmates, to fidgeting, to whatever's happening outside the window. This isn't necessarily a behavioural problem; it may indicate that tasks are too easy, too hard, or that your child needs support with concentration strategies. It's worth a conversation with the teacher about what specifically draws their attention away.",
    hilarious: "Your child has the attention span of a goldfish. Something shiny? Gone.",
    brutal: "Your child cannot focus to save their life. Every speck of dust is more interesting than the lesson and it's becoming a real problem."
  },
  {
    teacher_speak: "Demonstrates leadership qualities.",
    category: "Positive",
    honest: "Your child naturally steps up — whether organising group work, helping peers, or setting a positive example. Other students look to them for direction. This is a genuine strength that will serve them well beyond school. The teacher sees real leadership potential, not just 'being bossy'.",
    hilarious: "Your child bosses other kids around and they actually listen. Future CEO energy.",
    brutal: "Your child tells other kids what to do and they obey. The teacher called it 'leadership' but we both know it's bossiness with better branding."
  },
  {
    teacher_speak: "Requires encouragement to participate.",
    category: "Confidence",
    honest: "Your child tends to hang back in class discussions and group activities. They may know the answer but won't volunteer it without prompting. This could stem from shyness, fear of being wrong, or simply preferring to observe. The teacher is gently saying your child needs a nudge to get involved — it's not a criticism, but it does mean they're missing opportunities to show what they know.",
    hilarious: "Your child is a wallflower. The teacher has to practically drag participation out of them.",
    brutal: "Your child sits there like a bump on a log. The teacher has to beg them to open their mouth and contribute. It's painful to watch."
  },
  {
    teacher_speak: "Shows respect for peers and teachers.",
    category: "Positive",
    honest: "Your child treats others with consideration and courtesy. They listen when others speak, take turns, and handle disagreements without nastiness. This might sound like a basic expectation, but in a classroom of 25+ kids, it genuinely stands out. The teacher appreciates your child's manners.",
    hilarious: "Your child has basic manners. Shockingly, this makes them a standout in today's classrooms.",
    brutal: "Your child manages to not be rude. That's apparently worthy of praise now. The bar is underground."
  },
  {
    teacher_speak: "Needs to develop resilience.",
    category: "Emotional",
    honest: "Your child struggles when things get difficult — they may give up easily, become upset, or avoid challenges altogether. The teacher is saying, very diplomatically, that your child doesn't cope well with failure or frustration. This is worth paying attention to: resilience is a skill that can be built, but it requires practice with manageable challenges and the right support at home.",
    hilarious: "Your child falls to pieces at the first sign of difficulty. They need to toughen up.",
    brutal: "Your child is soft. They crumble the moment something isn't easy and fall apart at the slightest setback. They need a reality check, not a hug."
  },
  {
    teacher_speak: "Is developing independence in their learning.",
    category: "Growth",
    honest: "Your child is making progress in working on their own without constant teacher direction. 'Developing' is key here — they're not there yet, but they're heading in the right direction. They may still need reminders to get started, check their work, or stay on track, but they're beginning to take ownership. Encourage this at home by letting them tackle homework with minimal hand-holding.",
    hilarious: "Your child still needs to be told what to do every five minutes. But hey, it used to be every two minutes, so... progress?",
    brutal: "Your child can't do anything without being told. They're making progress, but at this rate they'll need hand-holding through university."
  },
  {
    teacher_speak: "Can be disruptive at times.",
    category: "Behaviour",
    honest: "Your child occasionally interrupts lessons, distracts classmates, or acts out. 'At times' is the teacher's way of saying it's not constant, but it happens enough to be noted. This could be calling out, making noises, getting out of their seat, or egging others on. The teacher wants you to know because it's affecting the learning environment — both for your child and those around them.",
    hilarious: "Your child is the class clown and it's getting on everyone's nerves.",
    brutal: "Your child won't shut up and sit still. They're ruining it for everyone else and the teacher is sick of it."
  },
  {
    teacher_speak: "Shows great enthusiasm for learning.",
    category: "Positive",
    honest: "Your child genuinely loves learning. They ask questions, get excited about new topics, and throw themselves into activities. This is one of the best comments a teacher can write — enthusiasm drives motivation, and motivation drives achievement. Nurture this at all costs.",
    hilarious: "Your child actually enjoys school. Enjoy it while it lasts.",
    brutal: "Your child is a keener. It's genuinely refreshing, but give it a few years — the system will grind that enthusiasm out of them."
  },
  {
    teacher_speak: "Needs to work on time management.",
    category: "Organisation",
    honest: "Your child struggles to complete tasks within the allotted time. They might spend too long on one part of an activity, get stuck perfecting minor details, or simply not realise how much time has passed. The teacher is saying your child needs help pacing themselves. This is a very common challenge and is worth working on at home with simple routines.",
    hilarious: "Your child has no concept of time. They'd spend an hour colouring the title and then wonder why the work isn't done.",
    brutal: "Your child wastes time like it's unlimited. They faff about on irrelevant details and then act surprised when nothing's finished. It's frustrating to watch."
  },
  {
    teacher_speak: "Is a kind and considerate class member.",
    category: "Positive",
    honest: "Your child looks out for others, includes classmates who are left out, and shows empathy. This is character praise — the teacher sees your child being a genuinely good person, not just a good student. In the grand scheme of things, this matters more than any academic grade.",
    hilarious: "Your child is nice. That's it. That's the comment.",
    brutal: "Your child is nice. Not smart, not hardworking, not talented — just nice. The teacher scraped the barrel for something positive to say."
  },
  {
    teacher_speak: "Struggles to stay on task.",
    category: "Focus",
    honest: "Your child has difficulty maintaining attention on the activity at hand. They might start an activity well but drift off, or they might never fully engage in the first place. This is different from 'easily distracted' (which is about external things pulling focus) — this is more about your child's internal ability to stick with something. It could indicate attention difficulties worth discussing further.",
    hilarious: "Your child starts things and then... ooh, is that a pencil? They've forgotten what they were doing.",
    brutal: "Your child has zero follow-through. They start something and abandon it within minutes. Nothing ever gets finished."
  },
  {
    teacher_speak: "Has formed positive friendships.",
    category: "Social",
    honest: "Your child has built good relationships with classmates. They have friends, play well with others, and navigate social situations well. This might seem like a throwaway line, but social connection is foundational to everything else at school. A child who feels belonging is a child who can learn.",
    hilarious: "Your child has friends. Unlike some kids in the class. (Yes, there's a subtext there.)",
    brutal: "Your child has friends. This is apparently noteworthy enough to put on a report. Draw your own conclusions about the kids who don't get this comment."
  },
  {
    teacher_speak: "Needs to take more responsibility for their learning.",
    category: "Independence",
    honest: "Your child relies heavily on the teacher (or you) to remind them, prompt them, and push them. The teacher wants to see them take more initiative — starting tasks without being told, checking their own work, packing up without reminders, and owning their progress. This is about building self-direction, which becomes critical in high school and beyond.",
    hilarious: "Your child expects everyone else to do the heavy lifting. The teacher is over it.",
    brutal: "Your child expects to be spoon-fed everything. They take zero ownership and the teacher is carrying their weight for them. It needs to stop."
  },
  {
    teacher_speak: "Can be reluctant to ask for help.",
    category: "Confidence",
    honest: "When your child is stuck, they don't put their hand up. They might sit in silence, guess, or copy from a neighbour rather than admit they need support. This can mean they fall behind because gaps aren't picked up. The teacher is gently flagging that your child's reluctance to seek help is holding them back. Encourage them at home that asking questions is smart, not weak.",
    hilarious: "Your child would rather sit in confused silence than admit they don't know something. Stubborn AND struggling — great combo.",
    brutal: "Your child is too proud to admit they're lost. So they sit there in ignorance, falling further behind. Stupid and stubborn — what a combination."
  },
  {
    teacher_speak: "Needs to consider the impact of their words on others.",
    category: "Behaviour",
    honest: "Your child says things — sometimes intentionally, sometimes not — that upset or hurt classmates. The teacher is diplomatically saying your child can be unkind, blunt, or thoughtless with their words. This isn't about swearing or aggression; it's more about empathy and thinking before speaking. It's worth a conversation at home about how words affect people.",
    hilarious: "Your child is a bit of a bully with their words. The teacher is being extremely polite about it.",
    brutal: "Your child is mean. They say hurtful things and don't care who gets hurt. The teacher is too polite to call it what it is, but we're not."
  },
  {
    teacher_speak: "Is a confident contributor to class discussions.",
    category: "Positive",
    honest: "Your child speaks up readily in class — answering questions, sharing ideas, and joining debates. They're not afraid to be wrong or to offer a different perspective. This is a genuine strength: confident contributors tend to be more engaged learners and often help draw out quieter classmates. The teacher values this.",
    hilarious: "Your child never shuts up in class. Fortunately, what they say is usually worth hearing.",
    brutal: "Your child won't stop talking. They dominate every discussion and don't know when to shut up and let someone else speak."
  },

  // ── Early years (Kindergarten / Prep – Year 2) ──
  {
    teacher_speak: "Is developing fine motor skills.",
    category: "Development",
    year_levels: EARLY,
    honest: "Your child is still building the small-muscle control needed for tasks like handwriting, cutting with scissors, and drawing. This is completely normal for this age — fine motor skills develop at different rates. The teacher may suggest activities at home like playdough, threading beads, or drawing to help strengthen these skills. Don't panic if their handwriting looks messy; it will come.",
    hilarious: "Your child's handwriting looks like a spider dipped in ink and tap-danced across the page. Totally normal for their age, but still.",
    brutal: "Your child's handwriting is illegible. It's age-appropriate, sure, but it's still a scribbly mess that needs work."
  },
  {
    teacher_speak: "Plays cooperatively with peers.",
    category: "Social",
    year_levels: EARLY,
    honest: "Your child shares, takes turns, and joins in group play well. In the early years, play IS learning — it's how children build social skills, language, and problem-solving. This comment tells you your child is navigating the social side of school successfully, which is a big deal at this age.",
    hilarious: "Your child can share a toy without starting a war. At this age, that's practically a Nobel Prize.",
    brutal: "Your child can share without throwing a tantrum. That's the bare minimum at this age, but the teacher is impressed anyway."
  },
  {
    teacher_speak: "Is settling into school routines.",
    category: "Adjustment",
    year_levels: EARLY,
    honest: "Your child is adjusting to the structure of school — following instructions, lining up, packing away, and understanding expectations. 'Settling in' is teacher-speak for 'they're getting there but still finding their feet'. This is very common, especially for children who haven't attended long day care or preschool. Give it time.",
    hilarious: "Your child still looks mildly startled every time the bell goes. They'll get the hang of it.",
    brutal: "Your child still doesn't know what's going on half the time. They'll figure it out eventually, but right now they're completely lost."
  },

  {
    teacher_speak: "Is developing phonological awareness and decoding skills.",
    category: "Academic",
    year_levels: EARLY,
    honest: "Your child is building the foundational skills for reading — recognising sounds, blending letters together, and starting to decode simple words. This is the building block of all future literacy. 'Developing' means they're on track but still mastering the basics. Reading together at home every night, pointing out letters and sounds, makes a real difference at this age.",
    hilarious: "Your child is still figuring out that 'c-a-t' makes 'cat'. Normal for their age, but they need the practice.",
    brutal: "Your child can't read yet. It's expected at this age, but they're not exactly setting the world on fire either. They need more practice at home."
  },
  {
    teacher_speak: "Is building early number sense.",
    category: "Academic",
    year_levels: EARLY,
    honest: "Your child is developing an understanding of numbers — counting, recognising quantities, and starting to grasp concepts like 'more' and 'less'. This is the foundation for all future maths learning. 'Building' means they're making progress but it's still early. Counting objects, talking about numbers in everyday life, and playing simple maths games at home all help.",
    hilarious: "Your child can count to 10 but gets a bit shaky after that. It'll click, give it time.",
    brutal: "Your child barely grasps basic counting. It's normal for now, but they need to actually practice, not just coast."
  },

  // ── Mid primary (Year 3 – Year 4) ──
  {
    teacher_speak: "Is developing fluency in reading.",
    category: "Academic",
    year_levels: MID_PRIMARY,
    honest: "Your child is moving from 'learning to read' to 'reading to learn'. They're building reading fluency — the ability to read smoothly, accurately, and with expression — which is a key milestone in Year 3 and 4. 'Developing' means they're on track but still building speed and confidence, particularly with longer or more complex texts. Regular reading at home, both independently and aloud, will help.",
    hilarious: "Your child reads like they're defusing a bomb — slowly and one word at a time. They'll get there.",
    brutal: "Your child reads painfully slowly. It's like watching paint dry. They need way more practice at home."
  },
  {
    teacher_speak: "Is building multiplication fact fluency.",
    category: "Academic",
    year_levels: MID_PRIMARY,
    honest: "In Year 3 and 4, students are expected to recall multiplication facts (times tables) and use them to solve problems. Your child is working on this but hasn't fully mastered them yet. Knowing times tables automatically makes everything in maths — fractions, division, problem-solving — much easier. A few minutes of practice at home each day will make a big difference here.",
    hilarious: "Your child still counts on their fingers for 6 × 7. The teacher is quietly hoping you'll buy some flashcards.",
    brutal: "Your child doesn't know their times tables. At this age, that's a real problem. The teacher can't do your job for you — drill them at home."
  },
  {
    teacher_speak: "Is developing structured writing with paragraphs.",
    category: "Academic",
    year_levels: MID_PRIMARY,
    honest: "Your child is learning to organise their writing into clear paragraphs with a beginning, middle, and end — rather than one long stream of thought. This is a significant step up from early years writing. 'Developing' means they're starting to get the idea but their writing may still be unstructured or jump between ideas. Encourage them to plan before they write at home.",
    hilarious: "Your child's stories are one giant sentence that wanders everywhere and goes nowhere. Structure is coming... eventually.",
    brutal: "Your child can't structure a sentence, let alone a paragraph. Their writing is an incoherent ramble. They need serious help."
  },
  {
    teacher_speak: "Participates well in NAPLAN preparation.",
    category: "Academic",
    year_levels: MID_PRIMARY,
    honest: "Year 3 and Year 5 are NAPLAN years. The teacher is noting that your child has engaged positively with the preparation and practice activities. This comment is less about your child's results (which you'll receive separately) and more about their attitude — they've approached it calmly and cooperatively rather than with anxiety or resistance. This is a good sign.",
    hilarious: "Your child didn't have a meltdown over the practice tests. In the teacher's eyes, that's a win.",
    brutal: "Your child managed to not fall apart during test practice. The bar is so low it's underground, but they cleared it."
  },
  {
    teacher_speak: "Is developing problem-solving strategies in mathematics.",
    category: "Academic",
    year_levels: MID_PRIMARY,
    honest: "In mid-primary, maths shifts from straightforward calculations to worded problems that require thinking about what operation to use and why. Your child is learning strategies like drawing diagrams, making lists, or working backwards — but hasn't fully mastered applying them independently yet. This is a normal part of the learning curve. Encourage them to talk through their thinking at home.",
    hilarious: "Your child sees a worded maths problem and their brain exits stage left. They're learning to stick with it.",
    brutal: "Your child sees a worded maths problem and gives up instantly. They can't think their way out of a paper bag yet."
  },
  {
    teacher_speak: "Works well collaboratively in groups.",
    category: "Social",
    year_levels: MID_PRIMARY,
    honest: "Year 3 and 4 is when group work becomes more structured — projects, investigations, and presentations. Your child contributes to group tasks, listens to others' ideas, and does their fair share. This is more than just 'being social'; it's about academic collaboration — staying focused on the task while working with peers. The teacher sees this as a strength.",
    hilarious: "Your child can work in a group without it turning into a reality TV show. Solid.",
    brutal: "Your child can work with others without it being a disaster. The bar is on the floor, but they cleared it."
  },
  {
    teacher_speak: "Is developing joined (cursive) handwriting.",
    category: "Development",
    year_levels: MID_PRIMARY,
    honest: "In many schools, Year 3 and 4 is when students transition from printing to joined or cursive handwriting. Your child is in this transition phase — their handwriting may look inconsistent as they learn new letter formations and joins. This is a normal developmental stage. Neatness will improve with practice; the focus at this stage is on fluency rather than perfection.",
    hilarious: "Your child's handwriting is caught in an awkward phase between printing and cursive. It's not pretty, but it's normal.",
    brutal: "Your child's handwriting is a mess — half printing, half cursive, all terrible. It's normal, but it's still an eyesore."
  },

  // ── Upper primary (Year 5 – Year 6) ──
  {
    teacher_speak: "Shows strong research and inquiry skills.",
    category: "Academic",
    year_levels: UPPER_PRIMARY,
    honest: "Your child can independently find information, evaluate sources, and present findings — skills that become increasingly important in upper primary as projects and research tasks become more common. The teacher is recognising that your child thinks critically about what they read, not just copies from a textbook. This sets them up well for high school.",
    hilarious: "Your child can actually Google something and not just copy the first result. Ahead of the curve.",
    brutal: "Your child can look something up without plagiarising. Sad that this is noteworthy, but here we are."
  },
  {
    teacher_speak: "Is preparing well for the transition to high school.",
    category: "Transition",
    year_levels: UPPER_PRIMARY,
    honest: "Year 6 teachers pay close attention to readiness for high school — independence, organisation, and emotional maturity. This comment means the teacher sees your child developing the self-management skills they'll need next year: remembering to bring things, managing a timetable, and handling bigger workloads. Keep encouraging that independence at home.",
    hilarious: "Your child can find their own hat and remember a due date. High school might not destroy them after all.",
    brutal: "Your child can find their own hat. That's the benchmark for high school readiness and they've barely scraped past it."
  },

  {
    teacher_speak: "Needs to manage homework and personal organisation independently.",
    category: "Organisation",
    year_levels: UPPER_PRIMARY,
    honest: "In upper primary, the expectation shifts: your child should be remembering their own homework, packing their own bag, and managing their diary or planner without constant reminders. The teacher is flagging that your child still relies on others to keep them on track. This matters because high school will demand it from day one. Now is the time to step back and let them experience natural consequences — forgetting homework once teaches more than ten reminders.",
    hilarious: "Your child still expects you to pack their bag and remind them about homework. The teacher wants them to grow up a bit.",
    brutal: "Your child is a baby. They can't pack a bag or remember homework. The teacher wants you to stop doing everything for them so they can grow up."
  },

  // ── Junior secondary (Year 7 – Year 9) ──
  {
    teacher_speak: "Needs to meet homework and assessment deadlines.",
    category: "Organisation",
    year_levels: JUNIOR_SEC,
    honest: "High school brings multiple teachers, subjects, and competing deadlines — and your child is struggling to keep up. They may be submitting work late, leaving assignments to the last minute, or forgetting tasks entirely. The teacher is flagging that this is now affecting their results. A homework planner or digital calendar could help. This is the time to build habits before the senior years ramp up.",
    hilarious: "Your child treats deadlines as gentle suggestions. The teacher is not amused.",
    brutal: "Your child never hands anything in on time. It's disrespectful, lazy, and the teacher is over it. Sort it out."
  },
  {
    teacher_speak: "Is developing critical thinking and analysis skills.",
    category: "Academic",
    year_levels: JUNIOR_SEC,
    honest: "In high school, the focus shifts from 'remembering facts' to 'explaining why'. Your child is learning to analyse texts, evaluate arguments, and justify their reasoning — not just give the right answer, but explain how they got there. 'Developing' means they're on the way but haven't mastered it yet. Encourage them to explain their thinking at home, even about non-school topics.",
    hilarious: "Your child is learning that 'because I said so' isn't an acceptable answer anymore. It's a process.",
    brutal: "Your child can't think critically. They parrot opinions without backing them up. They're slowly learning to think for themselves and it's painful to watch."
  },
  {
    teacher_speak: "Needs to manage personal device and technology use.",
    category: "Behaviour",
    year_levels: JUNIOR_SEC,
    honest: "Your child is being distracted by their phone, laptop, or other devices during class time. In high school, where students often have 1:1 devices, this is one of the most common issues teachers raise. It might be messaging friends, scrolling socials, or off-task browsing. The teacher is asking for your support in reinforcing that devices are learning tools during school hours, not entertainment.",
    hilarious: "Your child is glued to their screen. The teacher is competing with TikTok for attention and losing.",
    brutal: "Your child is addicted to their phone. They can't go five minutes without checking it. It's ruining their education and the teacher can't fix your parenting."
  },

  {
    teacher_speak: "Is developing the ability to construct evidence-based arguments.",
    category: "Academic",
    year_levels: JUNIOR_SEC,
    honest: "In high school, your child is learning to back up their claims with evidence — sourcing information, evaluating reliability, and structuring a logical argument. This spans across subjects, from English essays to science reports to history inquiries. 'Developing' means they're starting to do this but still tend toward opinion over evidence. Encourage them at home to justify their opinions: 'Why do you think that? What's your evidence?'",
    hilarious: "Your child is learning that 'because' isn't a complete argument. They're getting there, slowly.",
    brutal: "Your child can't string together a logical argument. Everything is opinion, nothing is backed up. They need to learn that thinking isn't the same as having a hot take."
  },

  // ── Senior secondary (Year 10 – Year 12) ──
  {
    teacher_speak: "Needs to consider post-school pathways and subject selections.",
    category: "Careers",
    year_levels: SENIOR_SEC,
    honest: "The teacher is flagging that your child hasn't yet engaged with planning for life after school — whether that's university, TAFE, an apprenticeship, or work. In the senior years, subject choices and results directly affect post-school options. The teacher wants to see your child thinking ahead and making informed choices. The school's careers advisor is a great resource to tap into now, not later.",
    hilarious: "Your child is sleepwalking towards graduation with no plan. The teacher is trying to tell you before it's too late.",
    brutal: "Your child has no plan for after school. They're drifting aimlessly towards graduation. The teacher is telling you to wake up before your kid becomes a statistic."
  },
  {
    teacher_speak: "Is developing effective independent study habits.",
    category: "Academic",
    year_levels: SENIOR_SEC,
    honest: "Senior years demand a big step up in self-directed learning — revision, note-taking, and exam preparation without a teacher checking over their shoulder. 'Developing' means your child is building these habits but hasn't fully mastered them yet. Strong study routines now will directly impact ATAR and final results. The teacher sees potential but wants to see more consistency.",
    hilarious: "Your child is realising that staring at a textbook isn't the same as studying. Growth, technically.",
    brutal: "Your child has no idea how to study. They stare at a textbook and call it revision. At this age, that's a serious problem that will tank their ATAR."
  },
  {
    teacher_speak: "Is developing sophisticated analytical writing for assessment.",
    category: "Academic",
    year_levels: SENIOR_SEC,
    honest: "Senior years demand a big step up in writing quality — essays and reports need depth of analysis, precise vocabulary, and structured argumentation, not just summary. 'Developing' means your child is producing work of increasing sophistication but hasn't yet mastered the level expected in Year 12. Reading exemplar responses and practising timed writing will accelerate this. Strong analytical writing is the single biggest differentiator in ATAR humanities and science subjects.",
    hilarious: "Your child's essays are getting fancier, but 'big words' and 'good argument' aren't the same thing. They're learning the difference.",
    brutal: "Your child throws big words at a page and hopes they stick. The writing sounds fancy but says nothing. Vocabulary isn't a substitute for actual thought."
  },
  {
    teacher_speak: "Needs to balance academic workload with wellbeing.",
    category: "Wellbeing",
    year_levels: SENIOR_SEC,
    honest: "The teacher has noticed your child is showing signs of stress, fatigue, or burnout — or that their schoolwork is suffering because they're overloaded with part-time work, co-curriculars, or social pressures. This is the teacher's gentle way of saying your child needs to slow down and look after themselves. In the senior years, wellbeing and academic performance are deeply linked. Take this one seriously.",
    hilarious: "Your child is running on caffeine and panic. The teacher is politely telling you they're about to crack.",
    brutal: "Your child is a mess. They're overworked, stressed, and heading for a breakdown. The teacher is telling you to step in before they implode."
  }
];

export function getGlossaryForYear(year) {
  return GLOSSARY_DATA.filter(entry =>
    !entry.year_levels || entry.year_levels.includes(year)
  );
}