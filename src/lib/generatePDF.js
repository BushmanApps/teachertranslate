import { jsPDF } from "jspdf";
import { getAcUrl } from "./acUrl.js";

// Brand colour (#496b8d)
const BRAND = [73, 107, 141];
const BRAND_LIGHT = [235, 241, 247];
const GREY_DARK = [60, 60, 60];
const GREY_MID = [100, 100, 100];
const GREY_LIGHT = [150, 150, 150];
const BLUE_NOTE = [70, 100, 150];
const GREEN_ACT = [50, 120, 80];
const GREEN_LIGHT = [240, 249, 244];
const WHITE = [255, 255, 255];

const LOGO_URL = "https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets/images/public/69fc81cf4f6a0ae5ab617e2b/c7bffff4e_TTLogo01.png";

const DISCLAIMER =
  "Disclaimer: Teacher Translate is designed to help families better understand school reports. " +
  "Translations are AI-generated interpretations and are not literal translations. " +
  "Curriculum references are based on the Australian Curriculum Version 9.0. " +
  "Your local state or territory may use an interpretation or adapted version of this curriculum. " +
  "For any concerns about your child's progress, please speak directly with their teacher.";

function stripEmoji(text) {
  if (!text) return "";
  return String(text)
    .replace(/[\u{1F300}-\u{1FFFF}]/gu, "")
    .replace(/[\u2600-\u27BF]/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

async function loadImageAsDataURL(url) {
  try {
    const res = await fetch(url);
    const blob = await res.blob();
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  } catch {
    return null;
  }
}

function performanceLabel(level) {
  if (!level) return null;
  const map = {
    ahead: "Working Above Year Level",
    average: "Working At Year Level",
    behind: "Working Below Year Level",
    unknown: null,
  };
  return map[level] || null;
}

// Open links in new window — jsPDF annotation flag
const LINK_OPTS = (url) => ({ url, newWindow: true });

export async function buildPDFDoc(translations) {
  const logoDataURL = await loadImageAsDataURL(LOGO_URL);

  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const margin = 15;
  const contentW = pageW - margin * 2;

  const FOOTER_Y = 287;
  let contentBottom = 265; // tightened on last translation to reserve disclaimer space

  let y = 0;

  const checkPage = (needed = 10) => {
    if (y + needed > contentBottom) { doc.addPage(); y = 20; }
  };

  const addText = (text, fontSize, bold, color, maxWidth) => {
    doc.setFontSize(fontSize);
    doc.setFont("helvetica", bold ? "bold" : "normal");
    if (color) doc.setTextColor(...color);
    const safe = stripEmoji(text);
    const lines = doc.splitTextToSize(safe, maxWidth || contentW);
    const lineH = fontSize * 0.45;
    checkPage(lines.length * lineH + 2);
    doc.text(lines, margin, y);
    y += lines.length * lineH + 2;
  };

  const addLabel = (label, color) => {
    doc.setFontSize(8);
    doc.setFont("helvetica", "bold");
    doc.setTextColor(...(color || GREY_LIGHT));
    checkPage(5);
    doc.text(label.toUpperCase(), margin, y);
    y += 5;
  };

  const addSpacer = (h = 4) => { y += h; };

  const addHRule = () => {
    doc.setDrawColor(220, 228, 236);
    checkPage(5);
    doc.line(margin, y, pageW - margin, y);
    y += 5;
  };

  const drawHeader = (t) => {
    doc.setFillColor(...BRAND);
    doc.rect(0, 0, pageW, 34, "F");

    if (logoDataURL) {
      doc.addImage(logoDataURL, "PNG", margin, 4, 24, 24);
    }

    doc.setTextColor(...WHITE);
    doc.setFontSize(20);
    doc.setFont("helvetica", "bold");
    const titleX = logoDataURL ? margin + 28 : margin;
    doc.text("Teacher Translate", titleX, 20);
    doc.link(margin, 2, 165, 30, LINK_OPTS("https://www.teachertranslate.com.au"));

    doc.setFontSize(9);
    doc.setFont("helvetica", "normal");
    doc.text(
      `Generated ${new Date().toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" })}`,
      pageW - margin, 20, { align: "right" }
    );

    y = 42;

    if (t.student_name || t.student_year) {
      doc.setFontSize(11);
      doc.setFont("helvetica", "normal");
      doc.setTextColor(...GREY_MID);
      doc.text(
        `Report for: ${t.student_name || "Your child"}${t.student_year ? `  |  ${t.student_year}` : ""}`,
        margin, y
      );
      y += 7;
    }

    const modeLabel = t.mode === "brutal" ? "Brutal Mode" : t.mode === "hilarious" ? "Hilarious Mode" : "Honest Mode";
    doc.setFontSize(9);
    doc.setFont("helvetica", "bold");
    doc.setTextColor(...BRAND);
    doc.text(modeLabel, margin, y);
    y += 9;
  };

  const getDisclaimerHeight = () => {
    doc.setFontSize(9);
    const lines = doc.splitTextToSize(DISCLAIMER, contentW - 4);
    return lines.length * (9 * 0.45) + 10;
  };

  const drawDisclaimerOnLastPage = (totalPages) => {
    doc.setPage(totalPages);
    const disclaimerH = getDisclaimerHeight();
    const boxY = FOOTER_Y - disclaimerH - 6;

    doc.setFillColor(255, 251, 235);
    doc.rect(margin - 2, boxY, contentW + 4, disclaimerH, "F");
    doc.setDrawColor(251, 191, 36);
    doc.rect(margin - 2, boxY, contentW + 4, disclaimerH, "S");

    doc.setFontSize(9);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(146, 64, 14);
    const lines = doc.splitTextToSize(DISCLAIMER, contentW - 4);
    doc.text(lines, margin, boxY + 5);
  };

  const drawFooter = (totalPages) => {
    for (let p = 1; p <= totalPages; p++) {
      doc.setPage(p);
      doc.setFontSize(8);
      doc.setTextColor(...GREY_LIGHT);
      doc.setFont("helvetica", "normal");
      doc.text("Teacher Translate — teacher-speak, decoded  |  ", margin, FOOTER_Y);
      const labelW = doc.getStringUnitWidth("Teacher Translate — teacher-speak, decoded  |  ") * 8 / doc.internal.scaleFactor;
      doc.setTextColor(...BRAND);
      doc.text("www.teachertranslate.com.au", margin + labelW, FOOTER_Y);
      doc.link(margin + labelW, FOOTER_Y - 4, 62, 5, LINK_OPTS("https://www.teachertranslate.com.au"));
      doc.setTextColor(...GREY_LIGHT);
      doc.text(`Page ${p} of ${totalPages}`, pageW - margin, FOOTER_Y, { align: "right" });
    }
  };

  const disclaimerReserve = getDisclaimerHeight() + 12;

  translations.forEach((t, tIdx) => {
    if (tIdx > 0) { doc.addPage(); }

    // Reserve space for disclaimer on last page
    contentBottom = (tIdx === translations.length - 1)
      ? FOOTER_Y - disclaimerReserve
      : 265;

    drawHeader(t);

    // Overall summary
    addLabel(t.mode === "brutal" ? "The Brutal Truth" : t.mode === "hilarious" ? "The Hilarious Reality" : "The Honest Summary");
    addText(t.mode === "brutal" ? (t.brutal_direct_translation || t.brutal_translation) : t.mode === "hilarious" ? t.brutal_translation : t.honest_helpful_translation, 11, false, GREY_DARK);

    // Overall performance label — field is performance_level on translation records
    const overallPerfLabel = performanceLabel(t.performance_level);
    if (overallPerfLabel) {
      addSpacer(2);
      doc.setFontSize(9);
      doc.setFont("helvetica", "bold");
      doc.setTextColor(...BRAND);
      checkPage(6);
      doc.text(overallPerfLabel, margin, y);
      y += 6;
    }

    if (t.performance_summary) {
      addSpacer(2);
      addLabel("Year Level Assessment");
      addText(t.performance_summary, 10, false, GREY_MID);
    }

    // Sections
    if (t.sections && t.sections.length > 0) {
      addSpacer(7);
      doc.setFontSize(13);
      doc.setFont("helvetica", "bold");
      doc.setTextColor(...GREY_DARK);
      checkPage(10);
      doc.text("Sentence by Sentence Breakdown", margin, y);
      y += 8;

      t.sections.forEach((section) => {
        addSpacer(4);
        checkPage(35);

        // Section subject bar
        doc.setFillColor(...BRAND_LIGHT);
        doc.rect(margin - 2, y - 5, contentW + 4, 10, "F");
        doc.setFontSize(12);
        doc.setFont("helvetica", "bold");
        doc.setTextColor(...BRAND);
        doc.text(stripEmoji(section.subject_or_area || ""), margin, y + 1);
        y += 9;

        // Section performance label
        const sectionPerfLabel = performanceLabel(section.performance_level);
        if (sectionPerfLabel) {
          doc.setFontSize(9);
          doc.setFont("helvetica", "bold");
          doc.setTextColor(...BRAND);
          checkPage(6);
          doc.text(sectionPerfLabel, margin, y);
          y += 6;
        }

        // Teacher comment
        if (section.original_excerpt) {
          addSpacer(2);
          addLabel("Teacher Comment", GREY_LIGHT);
          const excerptText = `"${stripEmoji(section.original_excerpt)}"`;
          const excerptLines = doc.splitTextToSize(excerptText, contentW);
          const lineH = 10 * 0.45;
          const boxH = excerptLines.length * lineH + 6;
          checkPage(boxH + 8);
          doc.setFillColor(248, 249, 250);
          doc.rect(margin - 2, y - 3, contentW + 4, boxH, "F");
          doc.setFontSize(10);
          doc.setFont("helvetica", "italic");
          doc.setTextColor(90, 90, 90);
          doc.text(excerptLines, margin, y + 2);
          y += boxH;
          addSpacer(2);
        }

        // Translation
        const transText = t.mode === "brutal" ? (section.brutal_direct || section.brutal) : t.mode === "hilarious" ? section.brutal : section.honest_helpful;
        if (transText) {
          addLabel("Translation", BLUE_NOTE);
          addText(transText, 11, false, [40, 40, 40]);
          addSpacer(2);
        }

        // Curriculum codes & notes
        const codes = section.curriculum_codes?.length > 0
          ? section.curriculum_codes
          : (section.ac_code && section.ac_code !== "null")
            ? [{ code: section.ac_code, performance_note: section.performance_note, activity_suggestion: section.activity_suggestion }]
            : [];

        if (codes.length === 0 && section.performance_note && section.performance_note !== "null") {
          addLabel("Australian Curriculum v9.0", BLUE_NOTE);
          addText(stripEmoji(section.performance_note), 10, false, BLUE_NOTE);
          addSpacer(2);
        }

        codes.forEach((entry) => {
          if (entry.performance_note && entry.performance_note !== "null") {
            addLabel("Australian Curriculum v9.0", BLUE_NOTE);

            const noteText = stripEmoji(entry.performance_note);
            const sentences = noteText.split(/(?<=\.)\s+/);
            const acUrl = getAcUrl(entry.code);

            sentences.forEach((sentence, si) => {
              if (si > 0) addSpacer(1);
              const codePattern = entry.code && entry.code !== "null" ? `(${entry.code})` : null;
              const codeIdx = codePattern ? sentence.indexOf(codePattern) : -1;

              if (codeIdx !== -1 && acUrl) {
                // Render the whole sentence without the bracketed code
                const before = sentence.slice(0, codeIdx).replace(/\.\s*$/, "");
                const after = sentence.slice(codeIdx + codePattern.length).trim();
                const lineH = 10 * 0.45;
                const fullSentence = `${before}${after ? (before ? " " + after : after) : ""}`;
                const fullLines = doc.splitTextToSize(fullSentence, contentW);
                checkPage(fullLines.length * lineH + 2);
                doc.setFontSize(10);
                doc.setFont("helvetica", "normal");
                doc.setTextColor(...BLUE_NOTE);
                // Render each line; find which line contains the code and underline it
                fullLines.forEach((line, li) => {
                  doc.text(line, margin, y + li * (lineH + 0.5));
                });
                y += fullLines.length * (lineH + 0.5) + 1;
              } else {
                addText(sentence, 10, false, BLUE_NOTE);
              }
            });
            addSpacer(1);
          }

          if (entry.code && entry.code !== "null") {
            const acUrl = getAcUrl(entry.code) || `https://www.australiancurriculum.edu.au/search/?q=${entry.code}`;
            doc.setFontSize(9);
            doc.setFont("helvetica", "bold");
            doc.setTextColor(...BRAND);
            checkPage(6);
            const codeText = `Curriculum Code: ${entry.code}`;
            doc.text(codeText, margin, y);
            const codeW = doc.getStringUnitWidth(codeText) * 9 / doc.internal.scaleFactor;
            doc.link(margin, y - 5, codeW, 6, LINK_OPTS(acUrl));
            y += 6;
          }

          // Supporting activity + Scootle — green box
          // IMPORTANT: measure all content first, then checkPage, THEN draw box so it's never split
          const hasActivity = entry.activity_suggestion && entry.activity_suggestion !== "null";
          const hasScootle = entry.code && entry.code !== "null";

          if (hasActivity || hasScootle) {
            addSpacer(1);
            addLabel("Supporting Activity", GREEN_ACT);

            doc.setFontSize(10);
            const lineH = 10 * 0.45;
            const actLines = hasActivity
              ? doc.splitTextToSize(stripEmoji(entry.activity_suggestion), contentW - 4)
              : [];
            const scootleText = hasScootle ? `Find supporting Scootle resources for ${entry.code}` : null;
            const scootleLines = scootleText
              ? doc.splitTextToSize(scootleText, contentW - 4)
              : [];

            const actH = actLines.length * lineH + (actLines.length > 0 ? 2 : 0);
            const scootleH = scootleLines.length * lineH + (scootleLines.length > 0 ? 2 : 0);
            const innerGap = hasActivity && hasScootle ? 3 : 0;
            const boxH = actH + scootleH + innerGap + 8;

            // checkPage BEFORE drawing the box — ensures box starts on the right page
            checkPage(boxH + 6);
            const boxStartY = y;

            doc.setFillColor(...GREEN_LIGHT);
            doc.rect(margin - 2, boxStartY - 3, contentW + 4, boxH, "F");

            if (hasActivity) {
              doc.setFontSize(10);
              doc.setFont("helvetica", "normal");
              doc.setTextColor(...GREEN_ACT);
              doc.text(actLines, margin, y + 2);
              y += actH;
              if (hasScootle) y += innerGap;
            }

            if (hasScootle) {
              const scootleUrl = `https://www.scootle.edu.au/ec/search?q=${entry.code}&acCode=${entry.code}&v=text&field=title&field=text.all&field=topic`;
              doc.setFontSize(10);
              doc.setFont("helvetica", "bold");
              doc.setTextColor(...GREEN_ACT);
              doc.text(scootleLines, margin, y + 2);
              const scootleW = doc.getStringUnitWidth(scootleLines[0]) * 10 / doc.internal.scaleFactor;
              doc.link(margin, y - 2, Math.min(scootleW, contentW), 6, LINK_OPTS(scootleUrl));
              y += scootleH;
            }

            y += 5; // bottom padding inside box
            addSpacer(2);
          }
        });

        addHRule();
      });
    }
  });

  const totalPages = doc.internal.getNumberOfPages();
  drawDisclaimerOnLastPage(totalPages);
  drawFooter(totalPages);
  return doc;
}

export async function saveSinglePDF(translation, studentName) {
  const doc = await buildPDFDoc([translation]);
  const now = new Date();
  const dd = String(now.getDate()).padStart(2, "0");
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const yy = String(now.getFullYear());
  const namePart = studentName ? ` - ${studentName}` : "";
  doc.save(`Teacher Translate${namePart} - ${dd}_${mm}_${yy}.pdf`);
}

export async function saveCombinedPDF(translations) {
  const doc = await buildPDFDoc(translations);
  const now = new Date();
  const dd = String(now.getDate()).padStart(2, "0");
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const yy = String(now.getFullYear());
  doc.save(`Teacher Translate - ${dd}_${mm}_${yy}.pdf`);
}