/**
 * Build a direct Australian Curriculum v9 content-description URL from a code.
 *
 * Code format: AC9 + subjectKey + yearNum + strand + itemNum
 * Examples: AC9M3A03, AC9E3LY01, AC9S3U01, AC9HS3K01
 */

const SUBJECT_MAP = {
  // Two-letter subject keys first (longer match wins)
  HS: {
    learningArea: "hass-f-6",
    subjectPrefix: "HASHASHY",
  },
  // Single-letter subject keys
  M: {
    learningArea: "mathematics",
    subjectPrefix: "MATMATY",
  },
  E: {
    learningArea: "english",
    subjectPrefix: "ENGENGY",
  },
  S: {
    learningArea: "science",
    subjectPrefix: "SCISCIY",
  },
  HP: {
    learningArea: "health",
    subjectPrefix: "HPEHPEY",
  },
  T: {
    learningArea: "technologies",
    subjectPrefix: "TECHTEY",
  },
};

// Map year-level strings from the app to curriculum year numbers
const YEAR_ALIAS = {
  F: "F",
  foundation: "F",
  "kindergarten / preparatory": "F",
  prep: "F",
  kindy: "F",
};

/**
 * Parse an AC9 code and return the direct curriculum URL.
 * Returns null if the code can't be parsed.
 */
export function getAcUrl(code) {
  if (!code || code === "null") return null;

  // AC9 codes: AC9 + subjectLetters + yearDigit(s) + strand + itemNum
  // e.g. AC9M3A03, AC9E3LY01, AC9HS3K01, AC9S10U01
  const match = code.match(/^AC9([A-Z]+?)(\d{1,2}|F)([A-Z]+\d{2})$/);
  if (!match) return null;

  const [, subjectKey, yearStr] = match;

  // Try two-letter key first, then one-letter
  const subjectInfo =
    SUBJECT_MAP[subjectKey] ||
    (subjectKey.length > 1 && SUBJECT_MAP[subjectKey.slice(0, 2)]) ||
    null;

  if (!subjectInfo) return null;

  const yearLabel = yearStr === "F" ? "foundation" : `year-${yearStr}`;
  const subjectIdentifier = `${subjectInfo.subjectPrefix}${yearStr}`;

  return (
    `https://www.australiancurriculum.edu.au/f-10-curriculum/learning-areas/${subjectInfo.learningArea}/${yearLabel}/content-description` +
    `?subject-identifier=${subjectIdentifier}` +
    `&content-description-code=${code}` +
    `&detailed-content-descriptions=0&hide-ccp=0&hide-gc=0&load-detailed-content-descriptions=0&side-by-side=1&strands-start-index=0&view=quick`
  );
}