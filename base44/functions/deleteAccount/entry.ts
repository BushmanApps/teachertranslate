import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';
import Stripe from 'npm:stripe@14.21.0';
import { sydneyTimestamp } from '../../shared/sydneyTime.ts';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const userId = user.id;
    const userEmail = user.email?.toLowerCase();
    const stripe = new Stripe(Deno.env.get('STRIPE_SECRET_KEY'));

    // Parse optional delete mode: "immediate" (default) or "deferred"
    // - immediate: cancel subscription now and delete account + all data
    // - deferred:  schedule subscription to cancel at period end; keep account &
    //             data so the user keeps Pro until their renewal date, after
    //             which the webhook reverts them to a non-subscribed (trial) user.
    let deleteMode = 'immediate';
    try {
      const body = await req.json();
      if (body?.deleteMode === 'deferred') deleteMode = 'deferred';
    } catch (_) { /* no body or invalid JSON — default to immediate */ }

    // 1. Handle Stripe subscription
    let deferredUntil = null;
    try {
      const profiles = await base44.asServiceRole.entities.UserProfile.filter({ email: user.email });
      if (profiles && profiles.length > 0 && profiles[0].is_subscribed) {
        // Find the Stripe customer via checkout sessions
        const sessions = await stripe.checkout.sessions.list({ limit: 100 });
        const userSession = sessions.data.find(s => s.metadata?.user_id === userId);
        if (userSession?.customer) {
          const subscriptions = await stripe.subscriptions.list({ customer: userSession.customer, status: 'active', limit: 10 });
          for (const sub of subscriptions.data) {
            if (deleteMode === 'deferred') {
              // Schedule cancellation at the end of the current period —
              // user keeps Pro access until then.
              await stripe.subscriptions.update(sub.id, { cancel_at_period_end: true });
              deferredUntil = new Date(sub.current_period_end * 1000).toISOString().split('T')[0];
              console.log(`Scheduled subscription ${sub.id} to cancel at period end (${deferredUntil}) for user ${userId}`);
            } else {
              await stripe.subscriptions.cancel(sub.id);
              console.log(`Cancelled Stripe subscription ${sub.id} for user ${userId}`);
            }
          }
        }
      }
    } catch (e) {
      console.error('Stripe cancellation error (non-fatal):', e.message);
    }

    // Deferred mode: stop here — account and data are kept so the user
    // retains Pro until the renewal date, then reverts to a trial user.
    if (deleteMode === 'deferred') {
      try {
        const profiles = await base44.asServiceRole.entities.UserProfile.filter({ email: user.email });
        if (profiles && profiles.length > 0) {
          await base44.asServiceRole.entities.UserProfile.update(profiles[0].id, {
            auto_renew_disabled: true,
            ...(deferredUntil ? { subscription_renewal: deferredUntil } : {}),
          });
        }
      } catch (e) {
        console.error('UserProfile update error (non-fatal):', e.message);
      }
      return Response.json({ success: true, deferred: true, deferredUntil });
    }

    const svc = base44.asServiceRole;

    // 2. Delete all Translations
    const translations = await svc.entities.Translation.filter({ created_by_id: userId });
    for (const t of translations) {
      await svc.entities.Translation.delete(t.id);
    }
    console.log(`Deleted ${translations.length} translations for user ${userId}`);

    // 3. Delete all Students
    const students = await svc.entities.Student.filter({ created_by_id: userId });
    for (const s of students) {
      await svc.entities.Student.delete(s.id);
    }
    console.log(`Deleted ${students.length} students for user ${userId}`);

    // 4. Gather every UserProfile (by owner and by email)
    const byOwner = await svc.entities.UserProfile.filter({ created_by_id: userId });
    const byEmail = await svc.entities.UserProfile.filter({ email: user.email });
    const seen = new Set();
    const profiles = [...(byOwner || []), ...(byEmail || [])].filter((p) => !seen.has(p.id) && seen.add(p.id));
    const scansUsed = Math.max(0, ...profiles.map((p) => p.scans_used || 0));

    // 5. Keep a minimal log (email, scans used, date) so free scans can't be reset
    if (userEmail) {
      const priorLogs = await svc.entities.DeletedAccountLog.filter({ email: userEmail });
      const priorScans = Math.max(0, ...(priorLogs || []).map((l) => l.scans_used || 0));
      await svc.entities.DeletedAccountLog.create({
        email: userEmail,
        scans_used: Math.max(scansUsed, priorScans),
        deleted_date: sydneyTimestamp(),
      });
    }

    // 6. Send confirmation email while the user is still registered
    try {
      const emailVars = { first_name: (user.full_name || "there").split(" ")[0] };
      await svc.integrations.Core.SendEmail({
        to: user.email,
        template_name: "AccountDeleted",
        variables: emailVars,
      });
      // Send a copy to the reports inbox for record-keeping.
      await svc.integrations.Core.SendEmail({
        to: "reports@teachertranslate.com.au",
        subject: `Account deleted: ${user.email}`,
        template_name: "AccountDeleted",
        variables: { ...emailVars, first_name: `${emailVars.first_name} (${user.email})` },
      });
    } catch (e) {
      console.error('Confirmation email error (non-fatal):', e.message);
    }

    // 7. Delete UserProfiles
    for (const p of profiles) {
      await svc.entities.UserProfile.delete(p.id);
    }
    console.log(`Deleted ${profiles.length} UserProfile(s) for user ${userId}`);

    // 5. If the user was ever a Pro subscriber, add their email to the refund blacklist
    if (userEmail) {
      const wasSubscribed = profiles.some(p => p.is_subscribed || p.refund_eligible_until);
      if (wasSubscribed) {
        const existing = await base44.asServiceRole.entities.RefundBlacklist.filter({ email: userEmail });
        if (!existing || existing.length === 0) {
          await base44.asServiceRole.entities.RefundBlacklist.create({
            email: userEmail,
            reason: "Account deleted after Pro subscription"
          });
          console.log(`Added ${userEmail} to refund blacklist`);
        }
      }
    }

    // 8. Delete the user account itself so they cannot log back in
    await svc.entities.User.delete(userId);
    console.log(`Deleted user account ${userId}`);

    return Response.json({ success: true });
  } catch (error) {
    console.error('Delete account error:', error);
    return Response.json({ error: error.message }, { status: 500 });
  }
});