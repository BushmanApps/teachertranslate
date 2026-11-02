import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';
import Stripe from 'npm:stripe@14.21.0';
import { sydneyTimestamp } from '../../shared/sydneyTime.ts';

Deno.serve(async (req) => {
  const stripe = new Stripe(Deno.env.get('STRIPE_SECRET_KEY'));
  const webhookSecret = Deno.env.get('STRIPE_WEBHOOK_SECRET');

  const body = await req.text();
  const sig = req.headers.get('stripe-signature');

  let event;
  try {
    event = await stripe.webhooks.constructEventAsync(body, sig, webhookSecret);
  } catch (err) {
    console.error('Webhook signature verification failed:', err.message);
    return new Response(`Webhook Error: ${err.message}`, { status: 400 });
  }

  const base44 = createClientFromRequest(req);

  try {
    console.log(`Webhook received: ${event.type}`);
    
    if (event.type === 'checkout.session.completed') {
      const session = event.data.object;
      const userId = session.metadata?.user_id;
      console.log(`Checkout session completed. User ID: ${userId}, Session ID: ${session.id}, Subscription: ${session.subscription}`);

      if (!userId) {
        console.error('ERROR: No user_id in session metadata');
      }

      if (userId) {
        // Get the customer email from the session
        const customerEmail = session.customer_email?.toLowerCase();
        console.log(`Customer email from session: ${customerEmail}`);
        
        // Find the user's profile and mark as subscribed
        const profiles = await base44.asServiceRole.entities.UserProfile.filter({ created_by_id: userId });
        console.log(`Found ${profiles?.length || 0} UserProfile(s) for user ${userId}`);
        
        // Get subscription end date from the subscription
        let expiresDate = null;
        if (session.subscription) {
          const sub = await stripe.subscriptions.retrieve(session.subscription);
          expiresDate = new Date(sub.current_period_end * 1000).toISOString().split('T')[0];
          console.log(`Subscription ends: ${expiresDate}`);
        }
        // Set refund eligibility: eligible for 14 days from now, unless blacklisted
        const user = await base44.asServiceRole.entities.User.get(userId);
        const userEmail = user?.email?.toLowerCase();
        console.log(`User email: ${userEmail}`);
        let refundEligible = false;
        let refundEligibleUntil = null;

        if (userEmail) {
          const blacklist = await base44.asServiceRole.entities.RefundBlacklist.filter({ email: userEmail });
          if (!blacklist || blacklist.length === 0) {
            refundEligibleUntil = sydneyTimestamp(new Date(Date.now() + 14 * 24 * 60 * 60 * 1000));
            refundEligible = true;
            console.log('User is refund eligible for 14 days');
          } else {
            console.log('User is blacklisted from refunds');
          }
        }

        // Pick the canonical profile: prefer one with a valid consent date so
        // a race-created duplicate never overrides consent. Then fold any
        // duplicates into it (preserving consent) and delete the leftovers.
        const now = Date.now();
        const withConsent = (profiles || []).filter(
          (p) => p.consent_given_date && new Date(p.consent_given_date).getTime() <= now
        );
        const primary = withConsent[0] || (profiles && profiles.length > 0 ? profiles[0] : null);

        // Compute effective Pro status: a new purchase grants Pro unless
        // an admin has explicitly revoked access (admin_override = "revoke").
        const checkoutAdminOverride = primary?.admin_override || null;
        const checkoutLifetimePro = !!primary?.lifetime_pro;
        const checkoutIsSubscribed = checkoutLifetimePro || checkoutAdminOverride !== 'revoke';

        const updatePayload = {
          is_subscribed: checkoutIsSubscribed,
          subscription_renewal: expiresDate,
          // Use the verified account email, never the Stripe-supplied one
          ...(userEmail ? { email: userEmail } : {}),
          user_name: user?.email || '',
          scans_used: 0,
          ...(refundEligibleUntil ? { refund_eligible: refundEligible, refund_eligible_until: refundEligibleUntil } : {}),
        };

        if (primary) {
          await base44.asServiceRole.entities.UserProfile.update(primary.id, updatePayload);
          const others = (profiles || []).filter((p) => p.id !== primary.id);
          for (const p of others) {
            // Carry the consent date over if the primary lacked one.
            if (p.consent_given_date && !primary.consent_given_date) {
              await base44.asServiceRole.entities.UserProfile.update(primary.id, { consent_given_date: p.consent_given_date });
              primary.consent_given_date = p.consent_given_date;
            }
            try { await base44.asServiceRole.entities.UserProfile.delete(p.id); } catch (e) {
              console.error("Failed to delete duplicate UserProfile:", p.id, e);
            }
          }
          console.log(`✅ SUCCESS: Activated subscription for user ${userId} (profile id: ${primary.id}), refund eligible: ${refundEligible}`);
        } else {
          const newProfile = await base44.asServiceRole.entities.UserProfile.create({
            created_by_id: userId,
            ...updatePayload,
          });
          console.log(`✅ SUCCESS: Created and activated subscription for user ${userId} (profile id: ${newProfile.id}), refund eligible: ${refundEligible}`);
        }
      }
    }

    if (event.type === 'customer.subscription.deleted' || event.type === 'customer.subscription.updated') {
      const sub = event.data.object;
      const customerId = sub.customer;

      // Find session(s) by customer to get user_id
      const sessions = await stripe.checkout.sessions.list({ customer: customerId, limit: 10 });
      const userId = sessions.data.find(s => s.metadata?.user_id)?.metadata?.user_id;

      if (userId) {
        const profiles = await base44.asServiceRole.entities.UserProfile.filter({ created_by_id: userId });
        if (profiles && profiles.length > 0) {
          const profile = profiles[0];
          const stripeActive = sub.status === 'active' || sub.status === 'trialing';
          const expiresDate = new Date(sub.current_period_end * 1000).toISOString().split('T')[0];
          // Reconcile with admin_override and lifetime_pro so a lapsed
          // subscription revokes Pro (unless an admin has granted it).
          const isSubscribed = profile.lifetime_pro
            || profile.admin_override === 'grant'
            || (stripeActive && profile.admin_override !== 'revoke');
          await base44.asServiceRole.entities.UserProfile.update(profile.id, {
            is_subscribed: isSubscribed,
            subscription_renewal: expiresDate,
          });
          console.log(`Updated subscription status for user ${userId}: is_subscribed=${isSubscribed} (stripeActive=${stripeActive}, adminOverride=${profile.admin_override}, lifetimePro=${profile.lifetime_pro}, event=${event.type})`);
        }
      }
    }
  } catch (err) {
    console.error('Webhook handler error:', err);
  }

  return Response.json({ received: true });
});