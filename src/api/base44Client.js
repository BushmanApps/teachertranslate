import { createClient } from '@base44/sdk';
import { appParams } from '@/lib/app-params';

const { appId, token, functionsVersion, appBaseUrl } = appParams;

const isPreviewHost =
  typeof window !== 'undefined' &&
  (window.location.hostname === 'localhost' ||
    window.location.hostname.endsWith('.webcontainer-api.io'));

const serverUrl = isPreviewHost
  ? (import.meta.env.VITE_BASE44_BACKEND_URL || 'https://teachertranslate.eb44.app')
  : '';

export const base44 = createClient({
  appId,
  token,
  functionsVersion,
  serverUrl,
  requiresAuth: false,
  appBaseUrl
});
