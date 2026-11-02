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

    // Build return URLs from the server-set X-Base44-App-Url header so
    // checkout always returns to the app's real origin (published URL,
    // custom domain, or preview). This is the domain that serves the
    // Android App Links assetlinks.json, so the OS can open the app
    // directly instead of leaving the user in the browser.
    const appUrl = req.headers.get('X-Base44-App-Url');
    if (!appUrl) {
      console.error('Checkout error: missing X-Base44-App-Url header');
      return Response.json({ error: 'Unable to determine app URL' }, { status: 500 });
    }

    const successUrl = `${appUrl}/?subscribed=1`;
    const cancelUrl = `${appUrl}/`;

    const stripe = new Stripe(Deno.env.get('STRIPE_SECRET_KEY'));

    const session = await stripe.checkout.sessions.create({
      mode: 'subscription',
      line_items: [{ price: PRICE_ID, quantity: 1 }],
      discounts: [{ coupon: COUPON_ID }],
      success_url: successUrl,
      cancel_url: cancelUrl,
      customer_email: user.email,
      metadata: {
        base44_app_id: Deno.env.get('BASE44_APP_ID'),
        user_id: user.id,
      },
    });

    return Response.json({ url: session.url });
  } catch (error) {
    console.error('Checkout error:', error);
    return Response.json({ error: error.message }, { status: 500 });
  }
});