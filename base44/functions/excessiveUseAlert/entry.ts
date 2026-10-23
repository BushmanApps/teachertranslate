import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';
import { escapeEmailText } from '../../shared/emailBranding.ts';
import { sydneyTimestamp } from '../../shared/sydneyTime.ts';

// Triggered on Translation create: flags users who scan more than 19 reports
// within a rolling 21-day window and emails the admin once per window.

const ALERT_THRESHOLD = 19;
const WINDOW_DAYS = 21;
const ADMIN_EMAIL = 'reports@teachertranslate.com.au';

export default async function(req) {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await req.json().catch(() => ({}));

    const event = body?.event || {};

    // Only accept legitimate entity-automation events: require a real entity_id
    // and derive the creator_email from the actual stored record (never from the
    // request body), so external callers cannot query arbitrary users' activity.
    if (!event?.entity_id) {
      return Response.json({ error: 'Forbidden' }, { status: 403 });
    }

    let fetched;
    try {
      fetched = await base44.asServiceRole.entities.Translation.get(event.entity_id);
    } catch (e) {
      return Response.json({ skipped: true, reason: 'entity not found' });
    }

    // The caller must own the translation whose create event triggered this run,
    // so a logged-in user cannot probe another user's activity by passing their ID.
    if (!fetched || fetched.created_by_id !== user.id) {
      return Response.json({ error: 'Forbidden' }, { status: 403 });
    }
    const creatorEmail = fetched?.creator_email;

    if (!creatorEmail) {
      return Response.json({ skipped: true, reason: 'no creator_email' });
    }

    const now = new Date();
    const windowStart = new Date(now.getTime() - WINDOW_DAYS * 24 * 60 * 60 * 1000);

    // Load this user's translations (service role bypasses RLS)
    const userTranslations = await base44.asServiceRole.entities.Translation.filter({ creator_email: creatorEmail });

    const recentCount = userTranslations.filter((t) => {
      if (!t.created_date) return false;
      return new Date(t.created_date) >= windowStart;
    }).length;

    if (recentCount <= ALERT_THRESHOLD) {
      return Response.json({ skipped: true, recentCount, reason: 'below threshold' });
    }

    // Avoid duplicate alerts within the same 21-day window
    const existingAlerts = await base44.asServiceRole.entities.UsageAlert.filter({ email: creatorEmail });
    const alreadyAlerted = existingAlerts.some((a) => {
      if (!a.alert_date) return false;
      return new Date(a.alert_date) >= windowStart;
    });

    if (alreadyAlerted) {
      return Response.json({ skipped: true, recentCount, reason: 'already alerted recently' });
    }

    const windowStartStr = windowStart.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
    const nowStr = now.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });

    await base44.asServiceRole.integrations.Core.SendEmail({
      to: ADMIN_EMAIL,
      template_name: 'ExcessiveUsageAlert',
      variables: {
        user_email: escapeEmailText(creatorEmail),
        scan_count: recentCount,
        window_days: WINDOW_DAYS,
        window_start: windowStartStr,
        window_end: nowStr,
        threshold: ALERT_THRESHOLD,
      },
      from_name: 'Teacher Translate'
    });

    await base44.asServiceRole.entities.UsageAlert.create({
      email: creatorEmail,
      alert_date: sydneyTimestamp(now),
      scan_count: recentCount
    });

    console.log(`Excessive usage alert sent for ${creatorEmail}: ${recentCount} scans in ${WINDOW_DAYS} days`);
    return Response.json({ success: true, alerted: true });
  } catch (error) {
    console.error('excessiveUseAlert error:', error);
    return Response.json({ error: error.message }, { status: 500 });
  }
}