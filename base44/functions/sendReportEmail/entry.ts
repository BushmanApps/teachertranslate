import { createClientFromRequest } from 'npm:@base44/sdk@0.8.25';

import { fontEmailHtml } from '../../shared/emailBranding.ts';
const DISCLAIMER = "⚠️ Disclaimer: This translation is AI-generated for informational purposes only. Always consult your child's teacher directly for accurate information.";
const SHARE_MODES = ["honest_helpful", "hilarious", "brutal", "all"];

const escapeHtml = (v) =>
  typeof v === "string"
    ? v
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;")
    : "";

// Coerce an untrusted value to a bounded plain string.
const boundedStr = (v, max) => (typeof v === "string" ? v.slice(0, max) : "");

// Whitelist and bound the client-supplied report data — nothing else
// from the request body reaches the email.
function cleanReport(raw) {
  const sections = Array.isArray(raw?.sections) ? raw.sections.slice(0, 50) : [];
  return {
    overall_honest_helpful: boundedStr(raw?.overall_honest_helpful, 20000),
    overall_brutal: boundedStr(raw?.overall_brutal, 20000),
    overall_brutal_direct: boundedStr(raw?.overall_brutal_direct, 20000),
    sections: sections.map((s) => ({
      subject_or_area: boundedStr(s?.subject_or_area, 200),
      original_excerpt: boundedStr(s?.original_excerpt, 2000),
      honest_helpful: boundedStr(s?.honest_helpful, 5000),
      brutal: boundedStr(s?.brutal, 5000),
      brutal_direct: boundedStr(s?.brutal_direct, 5000),
    })),
  };
}

function buildModeBlock(report, m, studentName, studentYear) {
  const name = studentName
    ? `Student: ${escapeHtml(studentName)} (${escapeHtml(studentYear)})`
    : `Year level: ${escapeHtml(studentYear)}`;
  const kidRef = studentName ? `${escapeHtml(studentName)}'s` : "my child's";
  const header = m === "brutal"
    ? `💥 THE BRUTAL TRUTH ABOUT ${kidRef.toUpperCase()} REPORT`
    : m === "hilarious"
    ? `🤣 THE HILARIOUS REALITY ABOUT ${kidRef.toUpperCase()} REPORT`
    : `😊 DECODING ${kidRef.toUpperCase()} SCHOOL REPORT`;
  const summary = m === "brutal" ? (report.overall_brutal_direct || report.overall_brutal) : m === "hilarious" ? report.overall_brutal : report.overall_honest_helpful;

  let sectionRows = "";
  if (report.sections && report.sections.length > 0) {
    sectionRows = report.sections.map((s) => {
      const text = m === "brutal" ? (s.brutal_direct || s.brutal) : m === "hilarious" ? s.brutal : s.honest_helpful;
      const quote = s.original_excerpt
        ? `<tr><td style="padding:6px 0 8px;border-left:3px solid #c8d4e0;padding-left:10px;"><p style="font-size:14px;font-style:italic;color:#666;margin:0;line-height:1.6;">"${escapeHtml(s.original_excerpt)}"</p></td></tr>`
        : "";
      return `<tr><td style="padding:12px;background:#f8f9fa;border-radius:8px;">
          <p style="font-size:15px;font-weight:bold;color:#496b8d;margin:0 0 8px;">${escapeHtml(s.subject_or_area || "")}</p>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">${quote}</table>
          <p style="font-size:14px;line-height:1.7;margin:0;">${escapeHtml(text)}</p>
        </td></tr>
        <tr><td style="height:12px;line-height:12px;font-size:1px;">&nbsp;</td></tr>`;
    }).join("");
  }

  return `<tr><td style="padding:0 24px;">
      <p style="font-size:24px;font-weight:bold;color:#496b8d;text-align:center;margin:0 0 12px;">${escapeHtml(header)}</p>
      <p style="font-size:16px;font-weight:bold;margin:0 0 12px;">${escapeHtml(name)}</p>
      <p style="font-size:15px;line-height:1.7;margin:0 0 16px;">${escapeHtml(summary)}</p>
    </td></tr>
    ${sectionRows ? `<tr><td style="padding:0 24px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">${sectionRows}</table></td></tr>` : ""}`;
}

// Server-built report content; the editable ReportShare template supplies the branding.
function buildReportBlocks(report, shareMode, studentName, studentYear) {
  const sep = `<tr><td style="padding:16px 24px;" align="center"><span style="color:#ccc;letter-spacing:2px;">══════════════</span></td></tr>`;
  const blocks = [];
  if (shareMode === "honest_helpful" || shareMode === "all") blocks.push(buildModeBlock(report, "honest_helpful", studentName, studentYear));
  if (shareMode === "hilarious" || shareMode === "all") {
    if (blocks.length > 0) blocks.push(sep);
    blocks.push(buildModeBlock(report, "hilarious", studentName, studentYear));
  }
  if (shareMode === "brutal" || shareMode === "all") {
    if (blocks.length > 0) blocks.push(sep);
    blocks.push(buildModeBlock(report, "brutal", studentName, studentYear));
  }

  return fontEmailHtml(blocks.join("\n"));
}

function buildReportEmailHtml(report, shareMode, studentName, studentYear, copyNotice = '') {
  const copy = copyNotice
    ? `<p style="font-size:13px;line-height:1.6;color:#73738c;margin:0 0 16px;">${escapeHtml(copyNotice)}</p>`
    : '';
  const blocks = buildReportBlocks(report, shareMode, studentName, studentYear);
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Your Teacher Translate report</title></head><body style="margin:0;padding:0;background:#f8f6f2;font-family:Helvetica,Arial,sans-serif;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8f6f2;"><tr><td align="center" style="padding:24px 12px;"><table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:600px;background:#fff;border:1px solid #dad7ea;border-radius:20px;overflow:hidden;"><tr><td style="padding:28px 32px;background:#496b8d;color:#fff;"><a href="https://teachertranslate.com.au" style="color:#fff;text-decoration:none;font-size:26px;font-weight:700;">Teacher Translate</a></td></tr><tr><td style="padding:28px 24px;"><h1 style="margin:0 0 10px;color:#496b8d;font-size:26px;line-height:1.2;">Your translated school report</h1><p style="margin:0 0 16px;color:#73738c;font-size:16px;line-height:1.6;">A school report decoded into plain English with Teacher Translate.</p>${copy}<table role="presentation" width="100%" cellpadding="0" cellspacing="0">${blocks}</table><p style="margin:24px 0 0;color:#73738c;font-size:12px;line-height:1.6;">${escapeHtml(DISCLAIMER)}</p></td></tr><tr><td style="padding:20px 24px;text-align:center;background:#f8f6f2;color:#73738c;font-size:13px;line-height:1.5;">Decoded with Teacher Translate<br><a href="https://teachertranslate.com.au" style="color:#496b8d;">teachertranslate.com.au</a></td></tr></table></td></tr></table></body></html>`;
}


export default async function(req) {
  try {
    const base44 = createClientFromRequest(req);
    let user;
    try {
      user = await base44.auth.me();
    } catch (_) {
      user = null;
    }
    if (!user) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { translationId, shareMode, to } = await req.json();
    if (!translationId || typeof translationId !== 'string') {
      return Response.json({ error: 'Missing translation ID' }, { status: 400 });
    }
    if (!SHARE_MODES.includes(shareMode)) {
      return Response.json({ error: 'Invalid share mode' }, { status: 400 });
    }

    // Look up the translation from the database and verify ownership —
    // never trust client-supplied report content for the email body.
    let translation;
    try {
      translation = await base44.entities.Translation.get(translationId);
    } catch (_) {
      return Response.json({ error: 'Translation not found' }, { status: 404 });
    }
    if (!translation || translation.created_by_id !== user.id) {
      return Response.json({ error: 'Translation not found' }, { status: 404 });
    }

    // Build the report from stored translation data (server-verified)
    const report = {
      overall_honest_helpful: boundedStr(translation.honest_helpful_translation, 20000),
      overall_brutal: boundedStr(translation.brutal_translation, 20000),
      overall_brutal_direct: boundedStr(translation.brutal_direct_translation, 20000),
      sections: Array.isArray(translation.sections) ? translation.sections.slice(0, 50).map(s => ({
        subject_or_area: boundedStr(s?.subject_or_area, 200),
        original_excerpt: boundedStr(s?.original_excerpt, 2000),
        honest_helpful: boundedStr(s?.honest_helpful, 5000),
        brutal: boundedStr(s?.brutal, 5000),
        brutal_direct: boundedStr(s?.brutal_direct, 5000),
      })) : [],
    };
    const name = boundedStr(translation.student_name, 64);
    const year = boundedStr(translation.student_year, 64);
    const reportHtml = buildReportEmailHtml(report, shareMode, name, year);

    // Sending to a custom recipient ("email the report to someone") is a Pro
    // feature and must be the user's own email otherwise — never an open relay.
    const profiles = await base44.asServiceRole.entities.UserProfile.filter({ email: user.email });
    const isPro = Array.isArray(profiles) && profiles.some((p) => p?.is_subscribed === true || p?.lifetime_pro === true);

    const isEmail = (v) => typeof v === "string" && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
    const customRecipient = isPro && isEmail(to) && to.length <= 254 ? to.trim().toLowerCase() : null;

    if (customRecipient) {
      // ── Cap: max 20 unique recipients per report (translation) ──
      const existingLogs = await base44.asServiceRole.entities.ReportShareLog.filter(
        { sender_user_id: user.id, translation_id: translationId },
        '-created_date',
        500
      );
      const uniqueRecipients = new Set(
        (Array.isArray(existingLogs) ? existingLogs : []).map(l => (l.recipient_email || '').toLowerCase())
      );
      if (!uniqueRecipients.has(customRecipient.toLowerCase()) && uniqueRecipients.size >= 20) {
        return Response.json({ error: 'You can share this report with at most 20 different email addresses.' }, { status: 429 });
      }

      // ── Per-account caps across ALL reports (not resettable via new translations) ──
      const dayAgoISO = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
      const sentToday = await base44.asServiceRole.entities.ReportShareLog.filter(
        { sender_user_id: user.id, created_date: { $gte: dayAgoISO } },
        '-created_date',
        10
      );
      if (Array.isArray(sentToday) && sentToday.length >= 10) {
        return Response.json({ error: 'You can share up to 10 reports per day. Please try again tomorrow.' }, { status: 429 });
      }
      const monthAgoISO = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
      const priorToRecipient = await base44.asServiceRole.entities.ReportShareLog.filter(
        { sender_user_id: user.id, recipient_email: customRecipient, created_date: { $gte: monthAgoISO } },
        '-created_date',
        1
      );
      if (!Array.isArray(priorToRecipient) || priorToRecipient.length === 0) {
        const monthLogs = await base44.asServiceRole.entities.ReportShareLog.filter(
          { sender_user_id: user.id, created_date: { $gte: monthAgoISO } },
          '-created_date',
          500
        );
        const uniqueMonthlyRecipients = new Set(
          (Array.isArray(monthLogs) ? monthLogs : [])
            .map((log) => (log.recipient_email || '').toLowerCase())
            .filter(Boolean)
        );
        if (uniqueMonthlyRecipients.size >= 20) {
          return Response.json({ error: 'You can share reports with at most 20 different email addresses per month.' }, { status: 429 });
        }
      }

      // Send the report to the chosen recipient...
      await base44.asServiceRole.integrations.Core.SendEmail({
        to: customRecipient,
        subject: 'A school report decoded with Teacher Translate',
        html: reportHtml,
        from_name: "Teacher Translate",
      });
      // ...and send a copy to the logged-in user noting who it went to.
      const copyNotice = `This is a copy of a report you sent to ${customRecipient} via Teacher Translate.`;
      await base44.asServiceRole.integrations.Core.SendEmail({
        to: user.email,
        subject: `Copy: A school report decoded with Teacher Translate`,
        html: buildReportEmailHtml(report, shareMode, name, year, copyNotice),
        from_name: "Teacher Translate",
      });

      // ── Log the custom-recipient send ──
      await base44.asServiceRole.entities.ReportShareLog.create({
        sender_email: user.email,
        sender_user_id: user.id,
        recipient_email: customRecipient,
        translation_id: translationId,
        share_mode: shareMode,
      });

      // ── Alert: if user has sent ≥10 reports to others in ≤4 months,
      //    email a summary to reports@teachertranslate.com.au ──
      const fourMonthsAgo = new Date();
      fourMonthsAgo.setMonth(fourMonthsAgo.getMonth() - 4);
      const fourMonthsAgoISO = fourMonthsAgo.toISOString();

      const recentLogs = await base44.asServiceRole.entities.ReportShareLog.filter(
        { sender_user_id: user.id, created_date: { $gte: fourMonthsAgoISO } },
        '-created_date',
        500
      );
      const recentCount = Array.isArray(recentLogs) ? recentLogs.length : 0;

      if (recentCount >= 10) {
        const existingAlerts = await base44.asServiceRole.entities.ShareAlert.filter(
          { sender_user_id: user.id, created_date: { $gte: fourMonthsAgoISO } },
          '-created_date',
          1
        );
        if (!existingAlerts || existingAlerts.length === 0) {
          const recipientRows = (Array.isArray(recentLogs) ? recentLogs : [])
            .map(l => `<tr><td style="padding:6px 12px;border-bottom:1px solid #eee;">${escapeHtml(l.recipient_email || '')}</td><td style="padding:6px 12px;border-bottom:1px solid #eee;color:#666;">${l.created_date ? new Date(l.created_date).toLocaleString('en-AU', { timeZone: 'Australia/Sydney' }) : ''}</td></tr>`)
            .join('');

          await base44.asServiceRole.integrations.Core.SendEmail({
            to: 'reports@teachertranslate.com.au',
            template_name: 'SharingActivityAlert',
            variables: {
              user_email: escapeHtml(user.email),
              report_count: recentCount,
              recipient_rows: fontEmailHtml(recipientRows),
            },
            from_name: "Teacher Translate",
          });

          await base44.asServiceRole.entities.ShareAlert.create({
            sender_email: user.email,
            sender_user_id: user.id,
            report_count: recentCount,
            recipient_summary: (Array.isArray(recentLogs) ? recentLogs : []).map(l => `${l.recipient_email} (${l.created_date || ''})`).join('; '),
          });
        }
      }
    } else {
      await base44.asServiceRole.integrations.Core.SendEmail({
        to: user.email,
        subject: 'Your Teacher Translate report',
        html: reportHtml,
        from_name: "Teacher Translate",
      });
    }

    return Response.json({ success: true });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
}