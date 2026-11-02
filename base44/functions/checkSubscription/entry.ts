import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const baseUrl = Deno.env.get('BASE_URL');
    const authorization = req.headers.get('authorization');
    if (!baseUrl || !authorization) {
      return Response.json({ error: 'Native subscription service is unavailable' }, { status: 503 });
    }
    const response = await fetch(
      `${baseUrl.replace(/\/$/, '')}/api/apps/${Deno.env.get('BASE44_APP_ID')}/eb44/iap/subscription`,
      { headers: { authorization } }
    );
    const body = await response.json();
    return Response.json(body, { status: response.status });
  } catch (error) {
    console.error('checkSubscription error:', error);
    return Response.json({ error: error.message }, { status: 500 });
  }
});
