// Swaps a student's name inside already-translated report text (in state and
// in saved records) without re-running the translation.

const escapeRegex = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// Replace matches while keeping the capitalisation of the original word.
const applyWithCase = (text, regex, newName) =>
  text.replace(regex, (match) => {
    const isCapital = match[0] !== match[0].toLowerCase();
    return isCapital
      ? newName.charAt(0).toUpperCase() + newName.slice(1)
      : newName;
  });

function replaceInString(str, oldName, newName) {
  if (!str || typeof str !== "string") return str;
  if (oldName) {
    return applyWithCase(str, new RegExp(`\\b${escapeRegex(oldName)}\\b`, "gi"), newName);
  }
  if (newName) {
    // Name added from blank: the translation refers to the child generically.
    return applyWithCase(str, /\byour child\b/gi, newName);
  }
  return str;
}

// Keys holding the teacher's original words are never modified.
const SKIP_KEYS = ["original_excerpt", "original_text", "original_comments"];

export function renameStudentInValue(value, oldName, newName) {
  if (typeof value === "string") return replaceInString(value, oldName, newName);
  if (Array.isArray(value)) return value.map((v) => renameStudentInValue(v, oldName, newName));
  if (value && typeof value === "object") {
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      out[k] = SKIP_KEYS.includes(k) ? v : renameStudentInValue(v, oldName, newName);
    }
    return out;
  }
  return value;
}

export default function renameStudentInResult(result, oldName, newName) {
  return renameStudentInValue(result, (oldName || "").trim(), (newName || "").trim());
}