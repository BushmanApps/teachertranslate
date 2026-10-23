import { createClientFromRequest } from 'npm:@base44/sdk@0.8.25';

const SUBJECT_URLS = {
  english: 'https://vocabulary.curriculum.edu.au/MRAC/2024/04/LA/ENG/export/MRAC/2024/04/LA/ENG.jsonld',
  maths: 'https://vocabulary.curriculum.edu.au/MRAC/2024/04/LA/MAT/export/MRAC/2024/04/LA/MAT.jsonld',
  science: 'https://vocabulary.curriculum.edu.au/MRAC/2024/04/LA/SCI/export/MRAC/2024/04/LA/SCI.jsonld',
  hass: 'https://vocabulary.curriculum.edu.au/MRAC/2024/04/LA/HASS/export/MRAC/2024/04/LA/HASS.jsonld',
};

const FREE_SCAN_LIMIT = 3;

// Module-level cache: yearInCode -> [{ code, description, subject }]
// Pre-processes raw JSON-LD into compact entries ("mini-curriculum"), reused across requests.
const curriculumCache = new Map();

const STOPWORDS = new Set([
  'the','and','for','are','with','this','that','have','has','was','were',
  'been','from','they','their','them','there','what','when','will','would',
  'could','should','about','into','just','like','some','than','then','these',
  'those','which','while','your','also','such','very','more','most','many',
  'much','each','both','all','any','can','may','his','her','its','our','who',
  'how','why','not','but','nor','yet','does','done','said','year','student',
  'students','child','children','school','teacher','class','grade','report',
  'work','working','able','level','area','term','semester','show','shows',
  'shown','showing','demonstrates','demonstrate','understanding','understand',
  'developing','develop','consistently','consistent','continue','continues',
  'support','supports','encourage','encourages','pleasure','delight','positive',
  'learning','learn','practice','practise','progress','achievement','achieve',
  'expectation','expected','standard','curriculum','knowledge','skill','skills',
  'task','activity','activities','complete','participate','engage','focus',
  'apply','using','used'
]);

function getYearInCode(studentYear) {
  const lower = studentYear.toLowerCase().trim();
  if (lower.includes('foundation') || lower.includes('prep') || lower.includes('kindergarten')) return 'F';
  const match = lower.match(/year\s*(\d+)/);
  if (match) return match[1];
  return null;
}

// Extract 4-char word stems from text, filtering stopwords.
// Handles morphological variants (reading/reads -> "read").
function extractStems(text) {
  const words = text.toLowerCase().match(/[a-z]{4,}/g) || [];
  const stems = new Set();
  for (const w of words) {
    if (!STOPWORDS.has(w)) {
      stems.add(w.slice(0, 4));
    }
  }
  return stems;
}

function extractSubjectEntries(data, yearInCode, subject) {
  const graph = data[0]?.['@graph'] || [];
  const entries = [];

  for (const node of graph) {
    const notations = node['http://purl.org/ASN/schema/core/statementNotation'];
    if (!notations) continue;
    const notation = notations[0]?.['@value'];
    if (!notation || notation === 'root') continue;
    if (notation.includes('_')) continue;

    const codeMatch = notation.match(/^AC9[A-Z]{1,4}(\d+|F)[A-Z]/);
    if (!codeMatch || codeMatch[1] !== yearInCode) continue;

    const prefLabels = node['http://www.w3.org/2004/02/skos/core#prefLabel'];
    const descriptions = node['http://purl.org/dc/terms/description'];

    let text = null;
    if (prefLabels) {
      text = prefLabels.find(l => l['@language'] === 'en-au')?.['@value'] || prefLabels[0]?.['@value'];
    }
    if (!text && descriptions) {
      text = descriptions.find(l => l['@language'] === 'en-au')?.['@value'] || descriptions[0]?.['@value'];
    }
    if (text && text.length > 15) {
      const clean = text.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
      if (clean.length > 15 && clean !== notation) {
        entries.push({ code: notation, description: clean, subject });
      }
    }
  }
  return entries;
}

// Fetch and cache curriculum entries for a year level.
// Returns compact array of { code, description, subject } — the "mini-curriculum".
async function fetchACEntries(studentYear) {
  const yearInCode = getYearInCode(studentYear);
  if (!yearInCode) return [];

  if (curriculumCache.has(yearInCode)) {
    return curriculumCache.get(yearInCode);
  }

  const subjects = ['english', 'maths', 'science', 'hass'];

  const results = await Promise.all(subjects.map(async (subject) => {
    try {
      const res = await fetch(SUBJECT_URLS[subject], { signal: AbortSignal.timeout(8000) });
      if (!res.ok) return [];
      const data = await res.json();
      return extractSubjectEntries(data, yearInCode, subject);
    } catch (e) {
      console.error(`Failed to fetch AC for ${subject}:`, e.message);
      return [];
    }
  }));

  const allEntries = results.flat();

  // Only cache if we got data (don't cache transient failures)
  if (allEntries.length > 0) {
    curriculumCache.set(yearInCode, allEntries);
  }

  return allEntries;
}

// Keyword search: find curriculum entries most relevant to the report text.
// Uses 4-char stem overlap scoring to handle morphological variants.
function findRelevantEntries(entries, reportText, maxEntries = 20) {
  if (entries.length === 0) return [];

  const reportStems = extractStems(reportText);
  if (reportStems.size === 0) return [];

  const scored = entries.map(entry => {
    const entryStems = extractStems(entry.description);
    let score = 0;
    for (const s of reportStems) {
      if (entryStems.has(s)) score++;
    }
    return { entry, score };
  });

  return scored
    .filter(s => s.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, maxEntries)
    .map(s => s.entry);
}

function buildCurriculumContext(entries, studentYear) {
  if (entries.length === 0) return '';

  const bySubject = {};
  for (const e of entries) {
    if (!bySubject[e.subject]) bySubject[e.subject] = [];
    const desc = e.description;
    bySubject[e.subject].push(`${e.code}: ${desc}`);
  }

  const lines = [];
  for (const [subject, items] of Object.entries(bySubject)) {
    lines.push(`\n=== ${subject.toUpperCase()} ===`);
    lines.push(...items);
  }

  return `\nAUSTRALIAN CURRICULUM v9.0 CONTENT DESCRIPTIONS FOR ${studentYear}:\n${lines.join('\n')}\n`;
}

// ── Completeness check helpers ──────────────────────────────────────
// Split report text into individual teacher sentences so we can verify
// the LLM included every one.  Splits on newlines first (reports often
// have one comment per line) then on sentence-ending punctuation.
const END_PUNCT = /[.!?]["'”’)]?$/;

// A leading line of a chunk that is a heading / grade table row / footer
// (e.g. "Teacher Comment", "Number and Algebra D", "Page 21 of 50").
function isNoiseLine(line) {
  if (END_PUNCT.test(line)) return false;
  return line.split(/\s+/).length < 7 || /\d$/.test(line) || /\b[A-Z]$/.test(line) || /:\s*\S+$/.test(line);
}

// Deterministically split the report into complete sentences, joining
// PDF line-wraps back together and dropping headings/table rows.
function splitIntoSentences(text) {
  const chunks = text.replace(/\r/g, '').replace(/[*#_]{1,3}/g, '').split(/(?<=[.!?]["'”’)]?)\s+/);
  const out = [];
  for (const chunk of chunks) {
    const lines = chunk.split('\n').map((l) => l.trim()).filter(Boolean);
    while (lines.length > 1 && isNoiseLine(lines[0])) lines.shift();
    const s = lines.join(' ').replace(/\s+/g, ' ').trim();
    if (s.split(' ').length >= 4 && END_PUNCT.test(s)) out.push(s);
  }
  return out;
}

const BATCH_SIZE = 6;
const CONCURRENCY = 3;

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { reportText, studentYear, studentName } = await req.json();
    if (!reportText || !studentYear) {
      return Response.json({ error: 'Missing reportText or studentYear' }, { status: 400 });
    }

    // ── Server-side quota: free users get FREE_SCAN_LIMIT scans; Pro unlimited ──
    const svc = base44.asServiceRole;
    const byOwner = await svc.entities.UserProfile.filter({ created_by_id: user.id });
    const byEmail = await svc.entities.UserProfile.filter({ email: user.email });
    const seen = new Set();
    const profiles = [...(byOwner || []), ...(byEmail || [])].filter((p) => !seen.has(p.id) && seen.add(p.id));
    if (profiles.length === 0) {
      return Response.json({ error: 'Profile not found' }, { status: 409 });
    }
    const isSubscribed = profiles.some((p) => p.is_subscribed || p.lifetime_pro);
    const quotaProfile = profiles.reduce((a, b) => ((b.scans_used || 0) > (a.scans_used || 0) ? b : a));
    let scansBefore = quotaProfile.scans_used || 0;
    if (!isSubscribed && scansBefore >= FREE_SCAN_LIMIT) {
      return Response.json({ error: 'Free scan limit reached' }, { status: 402 });
    }
    // Atomically reserve the scan before the paid LLM call (refunded below if
    // it fails). $inc is atomic, so concurrent requests each get a distinct
    // count; any request that lands past the limit is reverted and rejected.
    if (!isSubscribed) {
      await svc.entities.UserProfile.updateMany({ id: quotaProfile.id }, { $inc: { scans_used: 1 } });
      const fresh = await svc.entities.UserProfile.get(quotaProfile.id);
      const scansAfter = fresh?.scans_used || 0;
      if (scansAfter > FREE_SCAN_LIMIT) {
        await svc.entities.UserProfile.updateMany({ id: quotaProfile.id }, { $inc: { scans_used: -1 } });
        return Response.json({ error: 'Free scan limit reached' }, { status: 402 });
      }
      scansBefore = scansAfter - 1;
    }
    try {

    const studentRef = studentName || "Your child";

    // Fetch cached curriculum entries, then keyword-filter to relevant subset only
    const allEntries = await fetchACEntries(studentYear);
    const relevantEntries = findRelevantEntries(allEntries, reportText);
    const acContext = buildCurriculumContext(relevantEntries, studentYear);

    const prompt = `You decode "teacher speak" in Australian school reports into plain English for parents. Use Australian English spelling (colour, organise, centre, behaviour, favourite, practise/practice, programme) and subject names ("Maths" not "Math", "English", "Science", "HASS", "Health and Physical Education", "The Arts", "Technologies").

Student: ${studentRef}, Year Level: ${studentYear} (Australian Curriculum v9.0)

REPORT TEXT:
"""
${reportText}
"""
${acContext}
NAMING RULES (apply to every translation you write):
- If the report refers to the student by a first name, use that exact name.
- If the report contains no student name${studentName ? `, use "${studentName}" throughout` : ''}.
- If no name is provided and none appears in the report, use "Your child" (or the pronouns he/she/they exactly as the report uses them) — never invent a name.
- Never replace a name found in the report with a different one.

TASK:
1. Process ONLY teacher-written comments — ignore any student self-reflections, goals, or feedback.
2. INCLUDE EVERY teacher sentence — never skip, combine, or paraphrase. Each sentence = one section with the exact original text.
3. For each section:
   - subject_or_area: subject name or "General/Behaviour"
   - original_excerpt: exact original sentence
   - honest_helpful: 3-5 sentence compassionate plain-English translation. Decode euphemisms ("working on"=struggling, "developing"=below expected, "consistently" vs "sometimes"=frequency). For behaviour, unpack subtext: what trait, why the teacher framed it this way, what it means for the child's learning/social experience, what the parent should do. If behind year level, say so kindly.
   - brutal: hilariously savage translation — funny about the situation, never mean about the child.
   - brutal_direct: 1-3 sentence blunt, slightly offensive truth the teacher wants to say but can't (e.g. "won't shut up", "disrupts the class", "is disrespectful"). No threats, slurs, or physical punishment references.
   - performance_level: "ahead", "average", "behind", or "unknown"
   - curriculum_codes: For academic content, identify ALL matching codes from the list above. For each: code (exact AC code from list only), performance_note ("AC v9.0 [Subject] ${studentYear}: Students learn to [full curriculum content description, never truncated or abbreviated with '..' or '...'] ([code])" + one sentence (no leading punctuation) comparing student to standard), plain_english (1-2 sentences, what ${studentRef} should be able to do), brutal_plain_english (1-2 sentence blunt version), activity_suggestion (specific at-home activity, age-appropriate). For behaviour/no match: empty array []. Never invent codes.
   - performance_note, ac_code, activity_suggestion: legacy fields — set to first curriculum_codes entry's values (or null).

4. Provide overall summary.

Return JSON with sections array and overall fields as per the schema.`;

    const responseSchema = {
      type: "object",
      properties: {
        sections: {
          type: "array",
          items: {
            type: "object",
            properties: {
              subject_or_area: { type: "string" },
              original_excerpt: { type: "string" },
              honest_helpful: { type: "string" },
              brutal: { type: "string" },
              brutal_direct: { type: "string" },
              performance_level: { type: "string" },
              performance_note: { type: "string" },
              ac_code: { type: "string" },
              activity_suggestion: { type: "string" },
              curriculum_codes: {
                type: "array",
                items: {
                  type: "object",
                  properties: {
                    code: { type: "string" },
                    performance_note: { type: "string" },
                    plain_english: { type: "string" },
                    brutal_plain_english: { type: "string" },
                    activity_suggestion: { type: "string" }
                  },
                  required: ["code", "performance_note", "plain_english", "brutal_plain_english", "activity_suggestion"]
                }
              }
            }
          }
        },
        overall_performance_level: { type: "string" },
        overall_performance_summary: { type: "string" },
        overall_honest_helpful: { type: "string" },
        overall_brutal: { type: "string" },
        overall_brutal_direct: { type: "string" }
      }
    };

    // ── Sentence-by-sentence translation ──
    // The report is split into numbered sentences on the server, translated
    // in small parallel batches (one long call was silently truncating), and
    // every number is verified; any missing sentence is retried.
    const sentences = splitIntoSentences(reportText);
    const sectionSchema = responseSchema.properties.sections.items;
    const batchSchema = {
      type: "object",
      properties: {
        sections: {
          type: "array",
          items: {
            ...sectionSchema,
            properties: { sentence_number: { type: "number" }, is_teacher_comment: { type: "boolean" }, ...sectionSchema.properties },
            required: ["sentence_number", "original_excerpt", "honest_helpful", "brutal", "brutal_direct"]
          }
        }
      }
    };
    const translateBatch = (nums) => base44.asServiceRole.integrations.Core.InvokeLLM({
      prompt: `${prompt.split('TASK:')[0]}
SENTENCES TO TRANSLATE NOW (use the full report above only for context, e.g. to work out the subject each sentence belongs to):
${nums.map((n) => `[${n}] ${sentences[n]}`).join('\n')}

Return EXACTLY ${nums.length} section(s), one per numbered sentence above, with sentence_number set to its number and original_excerpt set to the exact sentence. Set is_teacher_comment false only for student self-reflections/goals.
${prompt.split('TASK:')[1].split('3. For each section:')[1].split('4. Provide overall summary.')[0]}`,
      model: "gemini_3_flash",
      response_json_schema: batchSchema
    }).then((r) => r?.sections || []).catch((e) => { console.error('Batch failed:', e.message); return []; });

    const byNumber = new Map();
    const collect = (secs, nums) => {
      for (const s of secs) {
        const n = Number(s.sentence_number);
        if (nums.includes(n) && !byNumber.has(n)) byNumber.set(n, { ...s, original_excerpt: sentences[n] });
      }
    };
    const allNums = sentences.map((_, i) => i);
    const batches = [];
    for (let i = 0; i < allNums.length; i += BATCH_SIZE) batches.push(allNums.slice(i, i + BATCH_SIZE));

    const overallPromise = base44.asServiceRole.integrations.Core.InvokeLLM({
      prompt: `${prompt.split('TASK:')[0]}
TASK: Give only the overall summary of this whole report: overall_performance_level ("ahead", "average", "behind" or "unknown"), overall_performance_summary, overall_honest_helpful, overall_brutal (funny), overall_brutal_direct (blunt). Return JSON.`,
      model: "gemini_3_flash",
      response_json_schema: { type: "object", properties: { ...responseSchema.properties, sections: undefined } }
    });

    // Run batches a few at a time so the AI service doesn't reject a burst
    // of parallel calls (rejected batches were silently dropping sentences).
    const runLimited = async (list) => {
      for (let i = 0; i < list.length; i += CONCURRENCY) {
        const group = list.slice(i, i + CONCURRENCY);
        const res = await Promise.all(group.map(translateBatch));
        group.forEach((nums, j) => collect(res[j], nums));
      }
    };
    await runLimited(batches);

    // Completeness check: retry any sentence that is still missing
    for (let pass = 0; pass < 3; pass++) {
      const missing = allNums.filter((n) => !byNumber.has(n));
      if (missing.length === 0) break;
      console.log(`Completeness check pass ${pass + 1}: ${missing.length} sentence(s) missing, retrying`);
      await new Promise((r) => setTimeout(r, 1500 * (pass + 1)));
      const retryBatches = [];
      for (let i = 0; i < missing.length; i += 3) retryBatches.push(missing.slice(i, i + 3));
      await runLimited(retryBatches);
    }
    const stillMissing = allNums.filter((n) => !byNumber.has(n));
    console.log(`Sentences: ${sentences.length}, translated: ${byNumber.size}, missing: ${stillMissing.length}`);

    const overall = await overallPromise;
    const result = {
      ...overall,
      sections: allNums.filter((n) => byNumber.has(n)).map((n) => byNumber.get(n)).filter((s) => s.is_teacher_comment !== false)
    };

    // Guarantee every curriculum code (and its outcome + activity) belongs to
    // this student's year level and came from the fetched AC v9.0 list.
    const validCodes = new Set(allEntries.map((e) => e.code));
    const yearInCode = getYearInCode(studentYear);
    for (const s of result?.sections || []) {
      s.curriculum_codes = (s.curriculum_codes || []).filter((c) => {
        const m = c?.code?.match(/^AC9[A-Z]{1,4}(\d+|F)[A-Z]/);
        return m && m[1] === yearInCode && (validCodes.size === 0 || validCodes.has(c.code));
      });
      if (s.ac_code && !s.curriculum_codes.some((c) => c.code === s.ac_code)) {
        s.ac_code = null;
        s.performance_note = null;
        s.activity_suggestion = null;
      }
    }


    // ── Trial limiting: first 3 sentences per subject area ──
    // For non-subscribed users, keep only the first 3 sections per subject
    // area and insert a lock marker after the 3rd so the frontend can show
    // an upgrade prompt.  Pro users see all sections.
    if (!isSubscribed) {
      const subjectCounts = {};
      const lockedSubjects = {};
      for (const section of (result?.sections || [])) {
        const subject = section.subject_or_area || "General";
        subjectCounts[subject] = (subjectCounts[subject] || 0) + 1;
        if (subjectCounts[subject] > 3) {
          lockedSubjects[subject] = (lockedSubjects[subject] || 0) + 1;
        }
      }

      const limitedSections = [];
      const seenCounts = {};
      for (const section of (result?.sections || [])) {
        const subject = section.subject_or_area || "General";
        seenCounts[subject] = (seenCounts[subject] || 0) + 1;
        if (seenCounts[subject] <= 3) {
          limitedSections.push(section);
          // After the 3rd in a subject that has more, insert a lock marker
          if (seenCounts[subject] === 3 && lockedSubjects[subject] > 0) {
            limitedSections.push({
              _trial_lock: true,
              subject_or_area: subject,
              hidden_count: lockedSubjects[subject]
            });
          }
        }
      }
      result.sections = limitedSections;
      result.trial_limited = true;
    }

    return Response.json({ success: true, result, scans_used: isSubscribed ? scansBefore : scansBefore + 1 });
    } catch (llmError) {
      if (!isSubscribed) {
        await svc.entities.UserProfile.updateMany({ id: quotaProfile.id }, { $inc: { scans_used: -1 } });
      }
      throw llmError;
    }
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});