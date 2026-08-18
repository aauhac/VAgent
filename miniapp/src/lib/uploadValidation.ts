/** Client-side upload checks matching backend AnalysisService. */

export const UPLOAD_MAX_BYTES = 30 * 1024 * 1024;

export const UPLOAD_SUPPORTED_EXT = [
  '.mp3',
  '.wav',
  '.m4a',
  '.flac',
  '.ogg',
  '.aac',
  '.webm',
  '.mp4',
  '.m4v',
] as const;

export type UploadValidation = { ok: true } | { ok: false; reason: 'unsupported' | 'too_large' };

export function fileExtension(name: string): string {
  const trimmed = name.trim();
  const dot = trimmed.lastIndexOf('.');
  if (dot <= 0 || dot === trimmed.length - 1) return '';
  return trimmed.slice(dot).toLowerCase();
}

export function validateUploadFile(file: { name: string; size: number }): UploadValidation {
  const ext = fileExtension(file.name);
  if (!ext || !(UPLOAD_SUPPORTED_EXT as readonly string[]).includes(ext)) {
    return { ok: false, reason: 'unsupported' };
  }
  if (file.size > UPLOAD_MAX_BYTES) {
    return { ok: false, reason: 'too_large' };
  }
  return { ok: true };
}
