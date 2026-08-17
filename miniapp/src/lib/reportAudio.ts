import { ensureIdentityHeaders } from './userIdentity';
import { apiUrl } from '../api/base';

/** Fetch preview WAV with auth headers — `<audio src>` cannot send identity headers. */
export async function fetchAuthenticatedPreviewBlobUrl(
  analysisId: string,
): Promise<{ url: string; revoke: () => void }> {
  const res = await fetch(apiUrl(`/v1/analyses/${analysisId}/preview`), {
    headers: await ensureIdentityHeaders(),
  });
  if (!res.ok) {
    throw new Error(res.status === 404 ? 'PREVIEW_NOT_FOUND' : `PREVIEW_HTTP_${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  return { url, revoke: () => URL.revokeObjectURL(url) };
}

/** Session blob is only valid for the analysis that created it. */
export function resolveLocalBlobUrl(analysisId: string | undefined): string | null {
  if (!analysisId) return null;
  const blob = sessionStorage.getItem('vocalfb_last_blob');
  const blobAid = sessionStorage.getItem('vocalfb_last_analysis_id');
  if (!blob) return null;
  if (blobAid && blobAid !== analysisId) return null;
  return blob;
}

export function rememberLocalBlob(analysisId: string, blobUrl: string) {
  try {
    sessionStorage.setItem('vocalfb_last_blob', blobUrl);
    sessionStorage.setItem('vocalfb_last_analysis_id', analysisId);
  } catch {
    /* ignore quota */
  }
}
