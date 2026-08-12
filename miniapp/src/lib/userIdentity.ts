/**
 * User identity provider — DEV fallback vs Toss anonymous key.
 * Production must not silently fall back to demo-user.
 */

export type UserIdentity = {
  provider: 'DEV' | 'TOSS_ANONYMOUS';
  subject: string;
};

const HEADER_NAME = 'X-VAgent-User-Key';
const CACHE_KEY = 'vagent_user_identity_v1';

let cached: UserIdentity | null = null;

function isTossRuntime(): boolean {
  try {
    return typeof window !== 'undefined' && !!(window as any).AppsInToss;
  } catch {
    return false;
  }
}

function isProductionBuild(): boolean {
  return !!import.meta.env.PROD;
}

async function resolveTossAnonymousKey(): Promise<string | null> {
  const api = (window as any)?.AppsInToss;
  if (!api?.getAnonymousKey) return null;
  try {
    const key = await api.getAnonymousKey();
    if (typeof key === 'string' && key.trim()) return key.trim();
    if (key && typeof key === 'object' && typeof key.result === 'string') {
      return key.result.trim();
    }
  } catch {
    return null;
  }
  return null;
}

export async function getUserIdentity(): Promise<UserIdentity> {
  if (cached) return cached;
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as UserIdentity;
      if (parsed?.subject) {
        cached = parsed;
        return parsed;
      }
    }
  } catch {
    /* ignore */
  }

  if (isTossRuntime()) {
    const subject = await resolveTossAnonymousKey();
    if (subject) {
      cached = { provider: 'TOSS_ANONYMOUS', subject };
      try {
        sessionStorage.setItem(CACHE_KEY, JSON.stringify(cached));
      } catch {
        /* ignore */
      }
      return cached;
    }
    if (isProductionBuild()) {
      throw new Error('USER_IDENTITY_UNAVAILABLE');
    }
  } else if (isProductionBuild()) {
    // Production web without Toss runtime must not silently become demo-user
    throw new Error('USER_IDENTITY_UNAVAILABLE');
  }

  // Local browser / non-Toss development only
  cached = { provider: 'DEV', subject: 'demo-user' };
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(cached));
  } catch {
    /* ignore */
  }
  return cached;
}

export function identityHeaders(extra?: HeadersInit): HeadersInit {
  const subject = cached?.subject || 'demo-user';
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
