import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { base44 } from "@/api/base44Client";

export function useUserData() {
  const queryClient = useQueryClient();

  const { data: currentUser, isLoading: userLoading } = useQuery({
    queryKey: ["currentUser"],
    queryFn: () => base44.auth.me(),
    staleTime: 5 * 60 * 1000,
  });

  const { data: userProfile, isLoading: profileLoading } = useQuery({
    queryKey: ["userProfile", currentUser?.id],
    queryFn: async () => {
      if (!currentUser) return null;

      // checkSubscription resolves/creates the canonical profile idempotently
      // (folding any duplicates), so run it first and then re-read to get the
      // single reconciled record — instead of deciding from an earlier read
      // that could race with the profile creation.
      const subCheck = (await base44.functions.invoke("checkSubscription", { native: Boolean(window.eb44?.isMobileApp?.()) }))?.data;

      // Read the single canonical profile from the backend (profiles are
      // owned by the backend, so the app can't read them directly).
      const res = await base44.functions.invoke("updateUserProfile", {});
      const existingProfile = res?.data || null;

      const lifetimePro = !!existingProfile?.lifetime_pro;

      // checkSubscription is the single source of truth — it reconciles
      // is_subscribed from native store status + admin_override + lifetime_pro
      // and persists the result. The stored existingProfile.is_subscribed
      // is NOT trusted as a fallback (it could be stale from a lapsed sub).
      let profile;
      if (subCheck?.is_subscribed) {
        profile = {
          is_subscribed: true,
          subscription_renewal: subCheck.subscription_renewal || existingProfile?.subscription_renewal,
          email: existingProfile?.email || currentUser.email,
          scans_used: existingProfile?.scans_used || 0,
          user_name: existingProfile?.user_name || currentUser?.full_name || ""
        };
      } else {
        profile = {
          is_subscribed: false,
          scans_used: existingProfile?.scans_used || 0,
          user_name: existingProfile?.user_name || currentUser?.full_name || ""
        };
      }

      // Lifetime Pro (admin-only grant) gives full Pro access with no
      // native subscription or renewal date.
      profile.lifetime_pro = lifetimePro;
      profile.is_subscribed = profile.is_subscribed || lifetimePro;

      // Include the stored consent date so the app can check at login
      // whether the user has previously given consent.
      profile.consent_given_date = existingProfile?.consent_given_date || null;

      return profile;
    },
    enabled: !!currentUser,
    staleTime: 5 * 60 * 1000,
  });

  const setUserProfile = useCallback((updater) => {
    queryClient.setQueryData(["userProfile", currentUser?.id], updater);
  }, [queryClient, currentUser]);

  const refresh = useCallback(async () => {
    await Promise.all([
      queryClient.refetchQueries({ queryKey: ["currentUser"] }),
      queryClient.refetchQueries({ queryKey: ["userProfile"] }),
    ]);
  }, [queryClient]);

  return {
    currentUser,
    userProfile,
    setUserProfile,
    isLoading: userLoading || profileLoading,
    refresh,
  };
}