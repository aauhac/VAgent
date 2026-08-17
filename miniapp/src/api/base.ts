/**
 * API origin for the Toss-hosted miniapp.
 *
 * Development: empty VITE_API_BASE uses the Vite proxy (same-origin /v1).
 * Production: VITE_API_BASE must be the public backend HTTPS origin.
 * Local fallbacks are development-only and are rejected at production build time.
 */

const RAW = (import.meta.env.VITE_API_BASE || '').trim().replace(/\/$/, '');

export function getApiBase(): string {
  if (!RAW) {
    return '';
  }
  if (import.meta.env.PROD && !RAW.toLowerCase().startsWith('https://')) {
    return '';
  }
  return RAW;
}

export function apiUrl(path: string): string {
  const p = path.startsWith('/') ? path : `/${path}`;
  const base = getApiBase();
  if (import.meta.env.PROD && !base) {
    throw new Error('API_BASE_NOT_CONFIGURED');
  }
  return `${base}${p}`;
}
