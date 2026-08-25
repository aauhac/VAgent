/**
 * Development-only unlock shims.
 *
 * Kept out of api/client.ts so a production build never links them into the shared
 * client chunk. Both endpoints are 403 fail-closed on the server when VAGENT_ENV is
 * production; this module exists so local flows stay testable without the Toss SDK.
 *
 * Import these ONLY behind an `import.meta.env.PROD` guard, and only via dynamic import.
 */

import { apiUrl } from './base';
import { devMockHeaders } from './client';

function assertDev(): void {
  if (import.meta.env.PROD) {
    throw new Error('MOCK_UNLOCK_DISABLED_IN_PRODUCTION');
  }
}

export async function mockUnlockSongDetail(analysisId: string) {
  assertDev();
  const res = await fetch(apiUrl(`/v1/analyses/${analysisId}/mock-unlock-detail`), {
    method: 'POST',
    headers: await devMockHeaders(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function mockPaySession(sessionId: string, productId?: string) {
  assertDev();
  const res = await fetch(apiUrl(`/v1/diagnostic-sessions/${sessionId}/mock-pay`), {
    method: 'POST',
    headers: await devMockHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(productId ? { product_id: productId } : {}),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
