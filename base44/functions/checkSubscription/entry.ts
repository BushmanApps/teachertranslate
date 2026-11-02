import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });
    const body = await req.json().catch(() => ({}));

    if (body?.native === true) {
      const baseUrl = Deno.env.get('BASE_URL');
      const authorization = req.headers.get('authorization');
      if (!baseUrl || !authorization) {
        return Response.json({ error: 'Native subscription service is unavailable' }, { status: 503 });
      }
      const response = await fetch(
        `${baseUrl.replace(/\/$/, '')}/api/apps/${Deno.env.get('BASE44_APP_ID')}/eb44/iap/subscription`,
        { headers: { authorization } }
      );
      return Response.json(await response.json(), { status: response.status });
    }

    const profiles = await base44.asServiceRole.entities.UserProfile.filter({ email: user.email });
    const profile = (profiles || []).find((item) => item.is_subscribed || item.lifetime_pro || item.admin_override) || profiles?.[0];
    return Response.json({
      is_subscribed: !!profile?.is_subscribed,
      subscription_renewal: profile?.subscription_renewal || null,
    });
  } catch (error) {
    console.error('checkSubscription error:', error);
    return Response.json({ error: error instanceof Error ? error.message : 'Subscription check failed' }, { status: 500 });
  }
});
