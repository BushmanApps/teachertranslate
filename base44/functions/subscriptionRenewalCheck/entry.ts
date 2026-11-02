import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';
import { escapeEmailText } from '../../shared/emailBranding.ts';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const profiles = await base44.asServiceRole.entities.UserProfile.filter({ auto_renew_disabled: true });
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    let warningSent = 0;

    for (const profile of profiles || []) {
      if (!profile.subscription_renewal || !profile.is_subscribed) continue;
      const renewalDate = new Date(profile.subscription_renewal);
      renewalDate.setHours(0, 0, 0, 0);
      const days = Math.round((renewalDate - today) / 86400000);
      if (days !== 14 || profile.renewal_warning_sent) continue;
      const users = profile.email
        ? await base44.asServiceRole.entities.User.filter({ email: profile.email })
        : await base44.asServiceRole.entities.User.filter({ id: profile.created_by_id });
      const user = users?.[0];
      if (!user?.email) continue;
      await base44.asServiceRole.integrations.Core.SendEmail({
        to: user.email.toLowerCase(),
        template_name: 'SubscriptionEnding',
        variables: {
          name: escapeEmailText(profile.user_name || user.full_name || 'there'),
          renewal_date: renewalDate.toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' }),
        },
        from_name: 'Teacher Translate',
      });
      await base44.asServiceRole.entities.UserProfile.update(profile.id, { renewal_warning_sent: true });
      warningSent++;
    }
    return Response.json({ success: true, warningSent, accountsDeleted: 0 });
  } catch (error) {
    console.error('subscriptionRenewalCheck error:', error);
    return Response.json({ error: error.message }, { status: 500 });
  }
});
