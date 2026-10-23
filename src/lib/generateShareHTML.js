const LOGO_URL = "https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets/images/public/69fc81cf4f6a0ae5ab617e2b/c7bffff4e_TTLogo01.png";
const APP_URL = "https://teachertranslate.com.au";
const DISCLAIMER = "⚠️ Disclaimer: This translation is AI-generated for informational purposes only. Always consult your child's teacher directly for accurate information.";

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function buildModeBlockHTML(result, m, studentName, studentYear) {
  const name = studentName
    ? `<strong>Student: ${escapeHtml(studentName)} (${escapeHtml(studentYear)})</strong>`
    : `<strong>Year level: ${escapeHtml(studentYear)}</strong>`;

  const kidRef = studentName ? `${escapeHtml(studentName)}'s` : "my child's";
  const header = m === "brutal"
    ? `💥 THE BRUTAL TRUTH ABOUT ${kidRef.toUpperCase()} REPORT`
    : m === "hilarious"
    ? `🤣 THE HILARIOUS REALITY ABOUT ${kidRef.toUpperCase()} REPORT`
    : `😊 DECODING ${kidRef.toUpperCase()} SCHOOL REPORT`;
  const summary = m === "brutal" ? (result.overall_brutal_direct || result.overall_brutal) : m === "hilarious" ? result.overall_brutal : result.overall_honest_helpful;

  let sections = "";
  if (result.sections && result.sections.length > 0) {
    sections = result.sections.map(s => {
      const text = m === "brutal" ? (s.brutal_direct || s.brutal) : m === "hilarious" ? s.brutal : s.honest_helpful;
      const quote = s.original_excerpt
        ? `<blockquote>"${escapeHtml(s.original_excerpt)}"</blockquote>`
        : "";
      return `<div class="section">
        <h3>${escapeHtml(s.subject_or_area || "")}</h3>
        ${quote}
        <p>${escapeHtml(text)}</p>
      </div>`;
    }).join("");
  }

  return `<div class="mode-block">
    <h1>${header}</h1>
    <p class="student-name">${name}</p>
    <p class="summary">${escapeHtml(summary)}</p>
    ${sections}
  </div>`;
}

export function buildFullHTML(result, shareMode, studentName, studentYear) {
  const blocks = [];
  if (shareMode === "honest_helpful" || shareMode === "all") blocks.push(buildModeBlockHTML(result, "honest_helpful", studentName, studentYear));
  if (shareMode === "hilarious" || shareMode === "all") blocks.push(buildModeBlockHTML(result, "hilarious", studentName, studentYear));
  if (shareMode === "brutal" || shareMode === "all") blocks.push(buildModeBlockHTML(result, "brutal", studentName, studentYear));

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Teacher Translate — Decoded Report</title>
  <link rel="icon" type="image/png" href="${LOGO_URL}">
  <style>
    * { box-sizing: border-box; }
    body { font-family: 'Manrope', 'Albert Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 720px; margin: 0 auto; padding: 24px; color: #333; line-height: 1.7; }
    .logo-top, .logo-bottom { text-align: center; margin: 24px 0; }
    .logo-top img, .logo-bottom img { width: 140px; height: auto; }
    h1 { font-size: 26px; font-weight: 700; color: #496b8d; text-align: center; margin: 24px 0 12px; }
    .mode-block { margin: 16px 0; }
    .student-name { font-size: 17px; font-weight: 700; margin: 8px 0 12px; }
    .summary { font-size: 16px; margin: 12px 0; }
    .section { margin: 16px 0; padding: 14px; background: #f8f9fa; border-radius: 12px; }
    .section h3 { font-size: 16px; font-weight: 600; color: #496b8d; margin: 0 0 8px; }
    .section blockquote { border-left: 3px solid #c8d4e0; padding-left: 12px; margin: 8px 0; font-style: italic; color: #666; font-size: 15px; }
    .section p { font-size: 15px; margin: 8px 0; }
    .separator { text-align: center; margin: 24px 0; color: #ccc; letter-spacing: 2px; }
    .disclaimer { font-size: 12px; color: #999; margin: 20px 0; line-height: 1.5; }
    .credit { text-align: center; font-size: 14px; margin: 12px 0; }
    .credit a { color: #496b8d; text-decoration: none; font-weight: 600; }
    .logo-link { display: inline-block; text-decoration: none; }
    .logo-link p { margin: 8px 0 0; font-size: 15px; font-weight: 600; color: #496b8d; }
    .back-bar { position: sticky; top: 0; z-index: 10; background: #496b8d; margin: -24px -24px 16px; padding: 10px 16px; border-radius: 0 0 14px 14px; }
    .back-bar button { background: rgba(255,255,255,0.16); color: #fff; border: none; font-size: 15px; font-weight: 600; padding: 8px 16px; border-radius: 10px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
    .back-bar button:hover { background: rgba(255,255,255,0.26); }
    .credit { display: flex; align-items: center; justify-content: center; gap: 6px; flex-wrap: wrap; }
    .credit a { display: inline-flex; align-items: center; gap: 4px; }
  </style>
</head>
<body>
  <div class="back-bar">
    <button onclick="goBack()">← Back to Teacher Translate</button>
  </div>
  <div class="logo-top">
    <a href="${APP_URL}" target="_blank" rel="noopener" class="logo-link">
      <img src="${LOGO_URL}" alt="Teacher Translate">
      <p>TeacherTranslate.com.au</p>
    </a>
  </div>
  ${blocks.join('<div class="separator">══════════════</div>')}
  <div class="disclaimer">${DISCLAIMER}</div>
  <div class="credit">🍎 Decoded with Teacher Translate · <a href="${APP_URL}" target="_blank" rel="noopener">🔗 www.teachertranslate.com.au</a></div>
  <div class="logo-bottom">
    <a href="${APP_URL}" target="_blank" rel="noopener" class="logo-link">
      <img src="${LOGO_URL}" alt="Teacher Translate">
      <p>TeacherTranslate.com.au</p>
    </a>
  </div>
  <script>
    function goBack(){
      try { window.close(); } catch(e) {}
      if (!window.closed) {
        if (window.history.length > 1) { window.history.back(); }
        else { window.location.href = "${APP_URL}"; }
      }
    }
  </script>
</body>
</html>`;
}

export function openFullResultsHTML(html) {
  const newWindow = window.open("", "_blank");
  if (newWindow) {
    newWindow.document.write(html);
    newWindow.document.close();
  }
}