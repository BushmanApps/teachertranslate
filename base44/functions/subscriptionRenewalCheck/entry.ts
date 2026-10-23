import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';
import Stripe from 'npm:stripe@14.21.0';
import { escapeEmailText } from '../../shared/emailBranding.ts';
import { sydneyTimestamp } from '../../shared/sydneyTime.ts';

// Scheduled daily function:
// - Sends a warning email 14 days before renewal_date if auto_renew_disabled
// - Deletes the account 1 day after renewal_date if auto_renew_disabled

export default async function(req) {
  try {
    const base44 = createClientFromRequest(req);
    // Scheduled/admin-only task: verify an admin caller before performing
    // destructive subscription cancellation and account deletion.
    const user = await base44.auth.me();
    if (!user || user.role !== 'admin') {
      return Response.json({ error: 'Forbidden' }, { status: 403 });
    }
    const stripe = new Stripe(Deno.env.get('STRIPE_SECRET_KEY'));

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // Get all profiles with auto_renew_disabled and a renewal date
    const profiles = await base44.asServiceRole.entities.UserProfile.filter({ auto_renew_disabled: true });

    let warningSent = 0;
    let accountsDeleted = 0;

    for (const profile of profiles) {
      // Note: is_subscribed is not required — the Stripe webhook flips it to
      // false once the period ends, which is exactly when we must delete.
      if (!profile.subscription_renewal) continue;

      const renewalDate = new Date(profile.subscription_renewal);
      renewalDate.setHours(0, 0, 0, 0);

      const daysUntilRenewal = Math.round((renewalDate - today) / (1000 * 60 * 60 * 24));

      // Get the user record for email
      // Profiles may be owned by the service account, so match by email too
      let users = profile.email ? await base44.asServiceRole.entities.User.filter({ email: profile.email }) : [];
      if (!users?.length) users = await base44.asServiceRole.entities.User.filter({ id: profile.created_by_id });
      const user = users?.[0];
      if (!user?.email) continue;

      const userEmail = user.email.toLowerCase();
      const userName = profile.user_name || user.full_name || 'there';
      const renewalDateStr = renewalDate.toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' });

      // --- Send warning email 14 days before renewal ---
      if (daysUntilRenewal === 14 && !profile.renewal_warning_sent) {
        await base44.asServiceRole.integrations.Core.SendEmail({
          to: userEmail,
          template_name: 'SubscriptionEnding',
          variables: {
            name: escapeEmailText(userName),
            renewal_date: renewalDateStr,
          },
          from_name: 'Teacher Translate'
        });

        await base44.asServiceRole.entities.UserProfile.update(profile.id, { renewal_warning_sent: true });
        warningSent++;
        console.log(`Sent renewal warning to ${userEmail}, renewal on ${renewalDateStr}`);
      }

      // --- Delete account 1 day after renewal date ---
      if (daysUntilRenewal < -1) {
        try {
          // Cancel Stripe subscription
          try {
            const sessions = await stripe.checkout.sessions.list({ limit: 100 });
            const userSession = sessions.data.find(s => s.metadata?.user_id === user.id);
            if (userSession?.customer) {
              const subscriptions = await stripe.subscriptions.list({ customer: userSession.customer, status: 'active', limit: 10 });
              for (const sub of subscriptions.data) {
                await stripe.subscriptions.cancel(sub.id);
                console.log(`Cancelled Stripe subscription ${sub.id} for user ${profile.created_by_id}`);
              }
            }
          } catch (e) {
            console.error('Stripe cancellation error (non-fatal):', e.message);
          }

          const svc = base44.asServiceRole;

          // Delete Translations
          const translations = await svc.entities.Translation.filter({ created_by_id: user.id });
          for (const t of translations) {
            await svc.entities.Translation.delete(t.id);
          }

          // Delete Students
          const students = await svc.entities.Student.filter({ created_by_id: user.id });
          for (const s of students) {
            await svc.entities.Student.delete(s.id);
          }

          // Gather every UserProfile for this user (by owner and by email)
          const byOwner = await svc.entities.UserProfile.filter({ created_by_id: user.id });
          const byEmail = await svc.entities.UserProfile.filter({ email: user.email });
          const seen = new Set();
          const allProfiles = [profile, ...(byOwner || []), ...(byEmail || [])].filter((p) => !seen.has(p.id) && seen.add(p.id));
          const scansUsed = Math.max(0, ...allProfiles.map((p) => p.scans_used || 0));

          // Keep a minimal log (email, scans used, date) so free scans can't be reset
          const priorLogs = await svc.entities.DeletedAccountLog.filter({ email: userEmail });
          const priorScans = Math.max(0, ...(priorLogs || []).map((l) => l.scans_used || 0));
          await svc.entities.DeletedAccountLog.create({
            email: userEmail,
            scans_used: Math.max(scansUsed, priorScans),
            deleted_date: sydneyTimestamp(),
          });

          // Confirmation email while the user is still registered
          try {
            await svc.integrations.Core.SendEmail({
              to: userEmail,
              template_name: 'AccountDeleted',
              variables: { first_name: escapeEmailText(userName.split(' ')[0]) },
            });
          } catch (e) {
            console.error('Confirmation email error (non-fatal):', e.message);
          }

          // Delete UserProfiles
          for (const p of allProfiles) {
            await svc.entities.UserProfile.delete(p.id);
          }

          // Blacklist email (ineligible for refund)
          const existing = await base44.asServiceRole.entities.RefundBlacklist.filter({ email: userEmail });
          if (!existing || existing.length === 0) {
            await base44.asServiceRole.entities.RefundBlacklist.create({
              email: userEmail,
              reason: 'Account auto-deleted after non-renewal subscription expiry'
            });
          }

          // Delete user record
          await base44.asServiceRole.entities.User.delete(user.id);
          accountsDeleted++;
          console.log(`Auto-deleted account for ${userEmail}`);
        } catch (e) {
          console.error(`Failed to delete account for ${userEmail}:`, e.message);
        }
      }
    }

    return Response.json({ success: true, warningSent, accountsDeleted });
  } catch (error) {
    console.error('subscriptionRenewalCheck error:', error);
    return Response.json({ error: error.message }, { status: 500 });
  }
}