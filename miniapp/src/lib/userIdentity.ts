/**
 * User identity for analysis requests.
 * Toss anonymous hash is NOT login userKey and is never payment proof.
 * Production must not silently fall back to demo-user.
 */

import { getAnonymousKey } from '@apps-in-toss/web-framework';

export type UserIdentity = {
  provider: 'DEV' | 'TOSS_ANONYMOUS';
  subject: string;
};

export const IDENTITY_USER_MESSAGE =
  '사용자 정보를 확인하지 못했어요. 앱을 다시 열고 시도해 주세요.';

const IDENTITY_CODES = new Set([
  'USER_IDENTITY_UNAVAILABLE',
  'ANONYMOUS_KEY_UNAVAILABLE',
  'INVALID_CATEGORY',
  'SDK_UNSUPPORTED',
  'ERROR',
]);

export class IdentityUnavailableError extends Error {
  readonly code: string;
  constructor(code: string) {
    super(IDENTITY_USER_MESSAGE);
    this.name = 'IdentityUnavailableError';
    this.code = IDENTITY_CODES.has(code) ? code : 'USER_IDENTITY_UNAVAILABLE';
  }
}

export function isIdentityUnavailableError(err: unknown): err is IdentityUnavailableError {
  if (err instanceof IdentityUnavailableError) return true;
  if (err instanceof Error && err.name === 'IdentityUnavailableError') return true;
  if (err instanceof Error && IDENTITY_CODES.has(err.message)) return true;
  return false;
}

const HEADER_NAME = 'X-VAgent-User-Key';
const CACHE_KEY = 'vagent_user_identity_v1';

let cached: UserIdentity | null = null;

/** Official Apps in Toss getAnonymousKey() result → anonymous hash. */
export function parseAnonymousKeyResult(result: unknown): string {
  if (result === undefined) {
    throw new IdentityUnavailableError('SDK_UNSUPPORTED');
  }
  if (result === null) {
    throw new IdentityUnavailableError('ANONYMOUS_KEY_UNAVAILABLE');
  }
  if (typeof result === 'string') {
    const token = result.trim();
    if (token === 'INVALID_CATEGORY') {
      throw new IdentityUnavailableError('INVALID_CATEGORY');
    }
    if (token === 'ERROR') {
      throw new IdentityUnavailableError('ERROR');
    }
    throw new IdentityUnavailableError('ANONYMOUS_KEY_UNAVAILABLE');
  }
  if (typeof result === 'object') {
    const rec = result as { type?: unknown; hash?: unknown };
    if (rec.type === 'HASH' && typeof rec.hash === 'string' && rec.hash.trim()) {
      return rec.hash.trim();
    }
    if (rec.type === 'INVALID_CATEGORY') {
      throw new IdentityUnavailableError('INVALID_CATEGORY');
    }
    if (rec.type === 'ERROR') {
      throw new IdentityUnavailableError('ERROR');
    }
  }
  throw new IdentityUnavailableError('ANONYMOUS_KEY_UNAVAILABLE');
}

async function resolveTossAnonymousKey(): Promise<string> {
  if (typeof getAnonymousKey !== 'function') {
    throw new IdentityUnavailableError('SDK_UNSUPPORTED');
  }
  let result: unknown;
  try {
    result = await getAnonymousKey();
  } catch {
    throw new IdentityUnavailableError('ANONYMOUS_KEY_UNAVAILABLE');
  }
  return parseAnonymousKeyResult(result);
}

export async function getUserIdentity(): Promise<UserIdentity> {
  if (cached) return cached;
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as UserIdentity;
      if (parsed?.provider === 'TOSS_ANONYMOUS' && parsed.subject) {
        cached = parsed;
        return parsed;
      }
      if (!import.meta.env.PROD && parsed?.provider === 'DEV' && parsed.subject) {
        cached = parsed;
        return parsed;
      }
    }
  } catch {
    /* ignore */
  }

  try {
    const subject = await resolveTossAnonymousKey();
    cached = { provider: 'TOSS_ANONYMOUS', subject };
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify(cached));
    } catch {
      /* ignore */
    }
    return cached;
  } catch (err) {
    const code = isIdentityUnavailableError(err) ? err.code : 'USER_IDENTITY_UNAVAILABLE';
    try {
      console.debug('[vocalfb] identity', code);
    } catch {
      /* ignore */
    }
    if (import.meta.env.PROD) {
      if (isIdentityUnavailableError(err)) throw err;
      throw new IdentityUnavailableError('USER_IDENTITY_UNAVAILABLE');
    }
  }

  if (!import.meta.env.PROD) {
    cached = { provider: 'DEV', subject: 'demo-user' };
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify(cached));
    } catch {
      /* ignore */
    }
    return cached;
  }

  throw new IdentityUnavailableError('USER_IDENTITY_UNAVAILABLE');
}

export function identityHeaders(extra?: HeadersInit): HeadersInit {
  const subject = cached?.subject;
  if (!subject) {
    return { ...(extra || {}) };
  }
  return {
    'X-User-Id': subject,
    [HEADER_NAME]: subject,
    ...(extra || {}),
  };
}

export async function ensureIdentityHeaders(extra?: HeadersInit): Promise<HeadersInit> {
  await getUserIdentity();
  return identityHeaders(extra);
}

export { HEADER_NAME as USER_KEY_HEADER };

export function clearUserIdentity() {
  cached = null;
  try {
    sessionStorage.removeItem(CACHE_KEY);
  } catch {
    /* ignore */
  }
}

/** Test-only: clear in-memory cache. */
export function resetUserIdentityCacheForTests() {
  clearUserIdentity();
}
