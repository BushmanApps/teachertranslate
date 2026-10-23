// ── Idempotent UserProfile resolver (inlined — see note below) ─────────
// Every backend function that touches UserProfile inlines this same helper
// because relative imports outside a function folder can't be bundled.
// Keep all copies in sync.
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

// Reuse the best existing profile, fold duplicates into it (preserving
// consent / admin_override / lifetime_pro / scans / email / name), delete
// the leftovers, and create one profile if none exists. is_subscribed is
// NOT folded — it is always recomputed by checkSubscription from Stripe
// status + admin_override + lifetime_pro. Safe to call concurrently.
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
        if (p.lifetime_pro && !folded.lifetime_pro) folded.lifetime_pro = true;
        if (p.admin_override && !folded.admin_override) folded.admin_override = p.admin_override;
        if (p.subscription_renewal && !folded.subscription_renewal) {
          folded.subscription_renewal = p.subscription_renewal;
        }
        if (p.refund_eligible_until && !folded.refund_eligible_until) {
          folded.refund_eligible_until = p.refund_eligible_until;
          folded.refund_eligible = p.refund_eligible;
        }
        if (typeof p.scans_used === "number" && (folded.scans_used ?? 0) < p.scans_used) {
          folded.scans_used = p.scans_used;
        }
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

import { createClientFromRequest } from 'npm:@base44/sdk@0.8.44';

// Safe, user-editable profile fields. email, is_subscribed, admin_override
// and scans_used are deliberately excluded — subscription status is only
// written by the Stripe-backed functions (checkSubscription / webhook),
// admin_override only by the dashboard, and scans_used only by translateReport.
const ALLOWED_FIELDS = ['user_name', 'consent_given_date'];

export default async function (req) {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const body = await req.json().catch(() => ({}));
    const updates = {};
    for (const field of ALLOWED_FIELDS) {
      if (body[field] !== undefined) updates[field] = body[field];
    }

    // Resolve through the idempotent helper so a profile is created or reused
    // — never duplicated. When updates are supplied (e.g. recording consent),
    // always persist them to the canonical profile.
    const profile = await resolveUserProfile(
      base44.asServiceRole,
      user.id,
      user.email,
      {
        createFields: {
          user_name: updates.user_name || user.full_name || user.email,
          email: user.email,
        },
        updateFields: updates,
        alwaysUpdate: Object.keys(updates).length > 0,
      }
    );

    return Response.json({
      id: profile.id,
      scans_used: profile.scans_used,
      user_name: profile.user_name,
      consent_given_date: profile.consent_given_date,
      is_subscribed: profile.is_subscribed,
      admin_override: profile.admin_override || null,
      lifetime_pro: profile.lifetime_pro,
      subscription_renewal: profile.subscription_renewal,
      email: profile.email,
    });
  } catch (error) {
    console.error('updateUserProfile error:', error);
    return Response.json({ error: error.message }, { status: 500 });
  }
}