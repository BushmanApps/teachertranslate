import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

// Scheduled function: runs periodically to expire refund eligibility after 14 days
Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (user?.role !== 'admin') {
      return Response.json({ error: 'Forbidden' }, { status: 403 });
    }

    const now = new Date().toISOString();
    // Find all profiles that are still marked eligible but have passed their eligibility date
    const profiles = await base44.asServiceRole.entities.UserProfile.filter({ refund_eligible: true });
    let expiredCount = 0;

    for (const profile of profiles) {
      if (profile.refund_eligible_until && profile.refund_eligible_until < now) {
        await base44.asServiceRole.entities.UserProfile.update(profile.id, { refund_eligible: false });
        expiredCount++;
      }
    }

    console.log(`Expired refund eligibility for ${expiredCount} users`);
    return Response.json({ success: true, expired: expiredCount });
  } catch (error) {
    console.error('expireRefundEligibility error:', error);
    return Response.json({ error: error.message }, { status: 500 });
  }
});