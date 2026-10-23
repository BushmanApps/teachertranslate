import { base44 } from "@/api/base44Client";
import { queryClientInstance } from "@/lib/query-client";
import { sydneyTimestamp } from "@/lib/sydneyTime";

// Record the date/time the user consented to the Privacy Policy and Terms
// of Use. Keeps the original date if consent was already given, so a user
// is only ever asked once.
export async function recordConsentGiven(currentUser) {
  try {
    const existing = (await base44.functions.invoke("updateUserProfile", {}))?.data;
    if (existing?.consent_given_date && new Date(existing.consent_given_date).getTime() <= Date.now()) return existing.consent_given_date;

    const consentDate = sydneyTimestamp();
    // Profile writes go through the backend so users can never change
    // their email or subscription status.
    await base44.functions.invoke("updateUserProfile", { consent_given_date: consentDate });
    // Refresh the cached profile so the app immediately sees the consent
    // (Home redirects to the Consent screen while it is missing).
    queryClientInstance.invalidateQueries({ queryKey: ["userProfile"] });
    return consentDate;
  } catch (e) {
    console.error("Failed to record consent:", e);
  }
}