// AC v9.0 content description fetcher - uses official MRAC JSON-LD data
import { createClientFromRequest } from 'npm:@base44/sdk@0.8.25';

const SUBJECT_URLS = {
  english: 'https://vocabulary.curriculum.edu.au/MRAC/2024/04/LA/ENG/export/MRAC/2024/04/LA/ENG.jsonld',
  maths: 'https://vocabulary.curriculum.edu.au/MRAC/2024/04/LA/MAT/export/MRAC/2024/04/LA/MAT.jsonld',
  mathematics: 'https://vocabulary.curriculum.edu.au/MRAC/2024/04/LA/MAT/export/MRAC/2024/04/LA/MAT.jsonld',
  science: 'https://vocabulary.curriculum.edu.au/MRAC/2024/04/LA/SCI/export/MRAC/2024/04/LA/SCI.jsonld',
  hass: 'https://vocabulary.curriculum.edu.au/MRAC/2024/04/LA/HASS/export/MRAC/2024/04/LA/HASS.jsonld',
  humanities: 'https://vocabulary.curriculum.edu.au/MRAC/2024/04/LA/HASS/export/MRAC/2024/04/LA/HASS.jsonld',
};

// Maps "Year 3" -> "Y3", "Foundation" -> "F", etc.
function getYearTag(studentYear) {
  const lower = studentYear.toLowerCase().trim();
  if (lower.includes('foundation') || lower.includes('prep') || lower.includes('kindergarten')) return 'YF';
  const match = lower.match(/year\s*(\d+)/);
  if (match) return `Y${match[1]}`;
  return null;
}

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { subjects, studentYear } = await req.json();
    if (!subjects || !studentYear) {
      return Response.json({ error: 'Missing subjects or studentYear' }, { status: 400 });
    }

    const yearTag = getYearTag(studentYear);
    if (!yearTag) {
      return Response.json({ error: 'Could not parse year level' }, { status: 400 });
    }

    const results = {};

    for (const subject of subjects) {
      const key = subject.toLowerCase().trim();
      const url = SUBJECT_URLS[key];
      if (!url) continue;

      const res = await fetch(url);
      if (!res.ok) continue;

      const data = await res.json();
      const graph = data[0]?.['@graph'] || [];

      // Content descriptions have:
      // - a statementNotation like "AC9E3LA01" (contains year tag e.g. "3" for Year 3)
      // - a skos:prefLabel or dc:description with the actual text
      // - type includes ASN Statement

      const entries = [];

      for (const node of graph) {
        // Get the notation (code)
        const notations = node['http://purl.org/ASN/schema/core/statementNotation'];
        if (!notations) continue;
        const notation = notations[0]?.['@value'];
        if (!notation || notation === 'root') continue;

        // Check if this code matches our year level
        // AC codes format: AC9[SubjectInitials][YearNum][Strand][Num]
        // e.g. AC9E3LA01 = AC9 + E(English) + 3(Year3) + LA(Language) + 01
        // For Foundation: AC9EFLA01
        const yearInCode = yearTag === 'YF' ? 'F' : yearTag.replace('Y', '');
        // The year appears after the subject initials (1-4 chars) in the code
        const codeYearMatch = notation.match(/^AC9[A-Z]+?(\d+|F)/);
        if (!codeYearMatch || codeYearMatch[1] !== yearInCode) continue;

        // Get the description text - look for prefLabel or description
        const prefLabels = node['http://www.w3.org/2004/02/skos/core#prefLabel'];
        const descriptions = node['http://purl.org/dc/terms/description'];

        let text = null;
        if (prefLabels) {
          text = prefLabels.find(l => l['@language'] === 'en-au')?.['@value'] || prefLabels[0]?.['@value'];
        }
        if (!text && descriptions) {
          text = descriptions.find(l => l['@language'] === 'en-au')?.['@value'] || descriptions[0]?.['@value'];
        }

        if (text && text.length > 15 && !text.includes('</') && text !== notation) {
          // Strip any HTML tags
          const clean = text.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
          if (clean.length > 15) {
            entries.push({ code: notation, description: clean });
          }
        }
      }

      if (entries.length > 0) {
        results[subject] = entries;
      }
    }

    return Response.json({ success: true, results });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});