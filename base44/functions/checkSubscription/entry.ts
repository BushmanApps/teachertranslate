import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';
import Stripe from 'npm:stripe@14.21.0';

// ── Idempotent UserProfile resolver (inlined — keep in sync) ─────────
function pickPrimaryProfile(profiles) {
  if (!profiles || profiles.length === 0) return null;
  if (profiles.length === 1) return profiles[0];
  const now = Date.now();
  const withConsent = profiles.filter(
    (p) => p.consent_given_date && new Date(p.consent_given_date).getTime() <= now
  );
  if (withConsent.length > 0) {
    return withConsent.find((p) => p.is_subscribed || p.admin_override || p.lifetime_pro) || withConsent[0];
  }
  const granted = profiles.filter((p) => p.is_subscribed || p.admin_override || p.lifetime_pro);
  if (granted.length > 0) return granted[0];
  return profiles[profiles.length - 1];
}

function stripUndefined(obj) {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v !== undefined && v !== null) out[k] = v;
  }
  return out;
}

// Compute the effective Pro status from three independent grants:
// lifetime_pro (permanent admin grant), admin_override ("grant"/"revoke"),
// and the current Stripe subscription state.
function computeSubscribed(stripeActive, adminOverride, lifetimePro) {
  if (lifetimePro) return true;
  if (adminOverride === 'grant') return true;
  if (adminOverride === 'revoke') return false;
  return !!stripeActive;
}

async function resolveUserProfile(base44, userId, userEmail, options = {}) {
  const { createFields = {}, updateFields = {}, alwaysUpdate = false } = options;
  // Profiles created by backend functions are owned by the service account,
  // so match by the user's email as well as by owner.
  const byOwner = await base44.entities.UserProfile.filter({ created_by_id: userId });
  const byEmail = userEmail ? await base44.entities.UserProfile.filter({ email: userEmail }) : [];
  const seen = new Set();
  const existing = [...(byOwner || []), ...(byEmail || [])].filter((p) => !seen.has(p.id) && seen.add(p.id));
  const primary = pickPrimaryProfile(existing || []);
  if (primary) {
    if (existing.length > 1) {
      const others = existing.filter((p) => p.id !== primary.id);
      const now = Date.now();
      const folded = {};
      for (const p of others) {
        if (p.consent_given_date && !folded.consent_given_date) {
          const t = new Date(p.consent_given_date).getTime();
          if (t <= now) folded.consent_given_date = p.consent_given_date;
        }
        // is_subscribed is NOT folded — it is always recomputed from
        // Stripe status + admin_override + lifetime_pro by the caller.
        if (p.lifetime_pro && !folded.lifetime_pro) folded.lifetime_pro = true;
        if (p.admin_override && !folded.admin_override) folded.admin_override = p.admin_override;
        if (p.subscription_renewal && !folded.subscription_renewal) {
          folded.subscription_renewal = p.subscription_renewal;
        }
        if (p.refund_eligible_until && !folded.refund_eligible_until) {
          folded.refund_eligible_until = p.refund_eligible_until;
          folded.refund_eligible = p.refund_eligible;
        }
        if (typeof p.scans_used === "number" && (folded.scans_used ?? 0) < p.scans_used) folded.scans_used = p.scans_used;
        if (p.email && !folded.email) folded.email = p.email;
        if (p.user_name && !folded.user_name) folded.user_name = p.user_name;
      }
      const hasFolded = Object.keys(folded).length > 0;
      if (alwaysUpdate || hasFolded) {
        const merged = { ...folded, ...stripUndefined(updateFields) };
        if (Object.keys(merged).length > 0) {
          await base44.entities.UserProfile.update(primary.id, merged);
          Object.assign(primary, merged);
        }
      }
      for (const p of others) {
        try { await base44.entities.UserProfile.delete(p.id); } catch (e) {
          console.error("Failed to delete duplicate UserProfile:", p.id, e);
        }
      }
    } else if (alwaysUpdate) {
      const updates = stripUndefined(updateFields);
      if (Object.keys(updates).length > 0) {
        await base44.entities.UserProfile.update(primary.id, updates);
        Object.assign(primary, updates);
      }
    }
    return primary;
  }
  // Restore free scans used by a previously deleted account with this email
  const deletedLogs = userEmail
    ? await base44.entities.DeletedAccountLog.filter({ email: userEmail.toLowerCase() })
    : [];
  const priorScans = Math.max(0, ...(deletedLogs || []).map((l) => l.scans_used || 0));

  return await base44.entities.UserProfile.create({
    created_by_id: userId,
    user_name: createFields.user_name || userEmail || "",
    email: createFields.email || userEmail || null,
    scans_used: Math.max(createFields.scans_used ?? 0, priorScans),
    is_subscribed: createFields.is_subscribed ?? false,
    consent_given_date: createFields.consent_given_date ?? null,
    subscription_renewal: createFields.subscription_renewal ?? null,
    ...stripUndefined(updateFields),
  });
}
// ── End resolver ──────────────────────────────────────────────────────

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const stripe = new Stripe(Deno.env.get('STRIPE_SECRET_KEY'));

    // Resolve the canonical profile first (idempotent — no duplicates).
    const profile = await resolveUserProfile(
      base44.asServiceRole,
      user.id,
      user.email,
      { createFields: { email: user.email, user_name: user.email } }
    );

    const adminOverride = profile?.admin_override || null;
    const lifetimePro = !!profile?.lifetime_pro;
    const storedStripeEmail = profile?.email || null;
    const emailToSearch = (storedStripeEmail || user.email).toLowerCase();
    console.log(`Checking subscription for user ${user.id}, searching with email: ${emailToSearch}`);

    let stripeActive = false;
    let expiresDate = null;
    let stripeError = false;

    try {
      const customers = await stripe.customers.list({ email: emailToSearch, limit: 1 });

      if (customers && customers.data.length > 0) {
        const customer = customers.data[0];
        console.log(`Found Stripe customer: ${customer.id}, Email: ${customer.email}`);

        const activeSubs = await stripe.subscriptions.list({ customer: customer.id, status: 'active', limit: 1 });
        const trialingSubs = await stripe.subscriptions.list({ customer: customer.id, status: 'trialing', limit: 1 });

        const sub = (activeSubs?.data?.[0]) || (trialingSubs?.data?.[0]) || null;
        if (sub) {
          stripeActive = true;
          expiresDate = new Date(sub.current_period_end * 1000).toISOString().split('T')[0];
          console.log(`✅ Active/trialing subscription found for ${customer.email}, expires: ${expiresDate}`);
        } else {
          console.log(`No active or trialing subscription for ${customer.email}`);
        }
      } else {
        console.log(`No Stripe customer found for email: ${emailToSearch}`);
      }
    } catch (e) {
      // Transient Stripe outage — don't revoke Pro. Return the stored
      // value so access survives until the next successful check.
      console.error('Stripe API error (non-fatal, returning stored status):', e.message);
      stripeError = true;
    }

    if (stripeError) {
      return Response.json({
        is_subscribed: !!profile?.is_subscribed,
        subscription_renewal: profile?.subscription_renewal || null,
      });
    }

    // Reconcile the effective Pro status from all three sources.
    const isSubscribed = computeSubscribed(stripeActive, adminOverride, lifetimePro);

    // Always persist the reconciled status — even when no active
    // subscription exists — so a lapsed subscription revokes access
    // instead of leaving a stale is_subscribed=true forever.
    await resolveUserProfile(base44.asServiceRole, user.id, user.email, {
      updateFields: {
        is_subscribed: isSubscribed,
        ...(expiresDate ? { subscription_renewal: expiresDate } : {}),
      },
      alwaysUpdate: true,
    });

    console.log(`Reconciled subscription for ${user.email}: is_subscribed=${isSubscribed} (stripeActive=${stripeActive}, adminOverride=${adminOverride}, lifetimePro=${lifetimePro})`);

    return Response.json({ is_subscribed: isSubscribed, subscription_renewal: expiresDate });
  } catch (error) {
    console.error('CheckSubscription error:', error);
    return Response.json({ error: error.message, is_subscribed: false }, { status: 500 });
  }
});