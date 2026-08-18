/** User-facing Korean errors. Never include tokens, keys, or stack traces. */

export const MIC_PRE_CONSENT = '노래를 분석하려면 마이크 사용 권한이 필요해요.';

export const MIC_DENIED =
  '마이크 사용이 허용되지 않았어요. 설정에서 허용하거나, 음성 파일로 분석할 수 있어요.';

export const MIC_NOT_FOUND =
  '마이크를 찾지 못했어요. 음성 파일로 분석할 수 있어요.';

export const MIC_UNAVAILABLE =
  '마이크를 시작하지 못했어요. 음성 파일로 분석할 수 있어요.';

export const LOGIN_CANCELLED = '로그인을 취소했어요.';
export const LOGIN_FAILED = '로그인을 완료하지 못했어요. 다시 시도해 주세요.';
export const LOGIN_START_FAILED = '토스 로그인을 시작하지 못했어요. 다시 시도해 주세요.';
export const LOGIN_BACKEND_FAILED = '로그인 정보를 확인하지 못했어요. 다시 시도해 주세요.';
export const LOGIN_REQUIRED = '로그인이 필요해요.';

export const NETWORK_UNAVAILABLE = '서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.';
export const ANALYSIS_FAILED = '분석 요청 처리 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요.';
export const RESULT_UNAVAILABLE = '결과를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.';

export const UPLOAD_UNSUPPORTED =
  '지원하지 않는 파일 형식이에요. mp3, wav, m4a, flac, ogg, aac, webm, mp4만 올릴 수 있어요.';
export const UPLOAD_TOO_LARGE = '파일이 너무 커요. 30MB 이하 파일만 올릴 수 있어요.';

export const PAYMENT_CANCELLED = '결제가 취소됐어요.';
export const PAYMENT_FAILED = '결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.';

export function microphoneErrorMessage(err: unknown): string {
  const name = String((err as { name?: string })?.name || '');
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || name === 'SecurityError') {
    return MIC_DENIED;
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') {
    return MIC_NOT_FOUND;
  }
  return MIC_UNAVAILABLE;
}

export function uploadApiErrorMessage(status: number, body: string): string | null {
  const text = (body || '').toLowerCase();
  if (status === 413 || text.includes('too large') || text.includes('file too large')) {
    return UPLOAD_TOO_LARGE;
  }
  if (text.includes('unsupported') || text.includes('file type') || text.includes('allowed:')) {
    return UPLOAD_UNSUPPORTED;
  }
  return null;
}
