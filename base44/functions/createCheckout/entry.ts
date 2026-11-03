import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';
import Stripe from 'npm:stripe@14.21.0';

const PRICE_ID = 'price_1TiDipGLIYQ3HYn0xIAK3pHa';
// Pre-created fixed coupon: $15 AUD off the first year
const COUPON_ID = 'TT_FIRST_YEAR_15';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const appUrl = Deno.env.get('BASE_URL')?.replace(/\/$/, '');
    if (!appUrl || !/^https:\/\/[^/]+$/i.test(appUrl)) {
      console.error('Checkout error: BASE_URL is missing or invalid');
      return Response.json({ error: 'Checkout is not configured' }, { status: 503 });
    }

    const successUrl = `${appUrl}/?subscribed=1`;
    const cancelUrl = `${appUrl}/`;

    const stripeSecret = Deno.env.get('STRIPE_SECRET_KEY');
    const appId = Deno.env.get('BASE44_APP_ID');
    if (!stripeSecret || !appId) {
      console.error('Checkout error: Stripe configuration is incomplete');
      return Response.json({ error: 'Checkout is not configured' }, { status: 503 });
    }

    const stripe = new Stripe(stripeSecret);
    const session = await stripe.checkout.sessions.create({
      mode: 'subscription',
      line_items: [{ price: PRICE_ID, quantity: 1 }],
      discounts: [{ coupon: COUPON_ID }],
      success_url: successUrl,
      cancel_url: cancelUrl,
      customer_email: user.email || undefined,
      metadata: {
        base44_app_id: appId,
        user_id: user.id,
      },
    });

    return Response.json({ url: session.url });
  } catch (error) {
    console.error('Checkout error:', error);
    const message = error instanceof Error ? error.message : 'Unable to create checkout session';
    return Response.json({ error: message }, { status: 500 });
  }
});
