// Returns true only when consent_given_date is present and in the past.
// A future-dated consent (e.g. set by mistake or via the dashboard) is
// treated as "not given" so the user is re-prompted to consent.
export function hasValidConsent(userProfile) {
  if (!userProfile?.consent_given_date) return false;
  return new Date(userProfile.consent_given_date).getTime() <= Date.now();
}