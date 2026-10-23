import { base44 } from "@/api/base44Client";

export function trackEvent(eventName, properties = {}) {
  try {
    base44.analytics.track({ eventName, properties });
  } catch (e) {
    console.error("Analytics error:", e);
  }
}