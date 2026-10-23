import { createClientFromRequest } from 'npm:@base44/sdk@0.8.44';

const ADMIN_COPY_EMAIL = 'reports@teachertranslate.com.au';

// Escape user-controlled values before interpolating them into email HTML
const escapeHtml = (value) =>
  String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

export default async function(req) {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await req.json().catch(() => ({}));
    const event = body?.event || {};

    // Require a real entity_id and fetch the actual stored record — never trust
    // data from the request body, so an external caller cannot send emails to
    // arbitrary addresses by crafting a payload.
    if (!event?.entity_id) {
      return Response.json({ error: 'Forbidden' }, { status: 403 });
    }

    let profile;
    try {
      profile = await base44.asServiceRole.entities.UserProfile.get(event.entity_id);
    } catch (e) {
      return Response.json({ skipped: true, reason: 'profile not found' });
    }

    // The caller must own the profile whose create/update event triggered
    // this run, OR be an admin (e.g. when an admin flips is_subscribed in the
    // dashboard). Otherwise a logged-in user could trigger welcome emails for
    // other users' profiles.
    if (!profile || (profile.created_by_id !== user.id && user.role !== 'admin')) {
      return Response.json({ error: 'Forbidden' }, { status: 403 });
    }

    const eventType = event.type;
    const oldData = body?.old_data || {};

    // Only act when the user is now subscribed
    if (!profile.is_subscribed) {
      return Response.json({ skipped: 'not subscribed' });
    }

    // Skip if already subscribed before (not a new activation), for any event type
    if (eventType !== 'create' && oldData.is_subscribed === true) {
      return Response.json({ skipped: 'was already subscribed' });
    }

    // Send at most once per profile: atomically claim the send via $inc so
    // replayed or concurrent calls can't trigger duplicate emails.
    if ((profile.welcome_email_count || 0) > 0) {
      return Response.json({ skipped: 'welcome already sent' });
    }
    await base44.asServiceRole.entities.UserProfile.updateMany({ id: profile.id }, { $inc: { welcome_email_count: 1 } });
    const claimed = await base44.asServiceRole.entities.UserProfile.get(profile.id);
    if ((claimed?.welcome_email_count || 0) !== 1) {
      return Response.json({ skipped: 'welcome already sent' });
    }

    let userEmail = profile.email;
    let userName = profile.user_name || '';

    // Fallback: get email from User entity if not on the profile
    if (!userEmail) {
      const userRecord = await base44.asServiceRole.entities.User.get(profile.created_by_id);
      userEmail = userRecord?.email;
      userName = userName || userRecord?.full_name || '';
    }

    if (!userEmail) {
      console.error('sendProWelcomeEmail: No email found for profile', profile.id);
      return Response.json({ error: 'No email found' }, { status: 400 });
    }

    const firstName = escapeHtml(userName ? userName.split(' ')[0] : 'there');

    // Both the subscriber email and admin copy use the editable email template.
    await base44.asServiceRole.integrations.Core.SendEmail({
      to: userEmail,
      from_name: 'Teacher Translate',
      template_name: 'ProWelcome',
      variables: { first_name: firstName, copy_notice: '' },
    });

    await base44.asServiceRole.integrations.Core.SendEmail({
      to: ADMIN_COPY_EMAIL,
      from_name: 'Teacher Translate',
      subject: `[Copy] Pro Welcome - ${userEmail}`,
      template_name: 'ProWelcome',
      variables: {
        first_name: firstName,
        copy_notice: `A Pro welcome email was sent to ${escapeHtml(userEmail)}. Below is a copy.`,
      },
    });

    return Response.json({ success: true, sentTo: userEmail });
  } catch (error) {
    console.error('sendProWelcomeEmail error:', error);
    return Response.json({ error: error.message }, { status: 500 });
  }
}