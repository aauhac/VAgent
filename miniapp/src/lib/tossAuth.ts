/**
 * Server-verified Toss login. Toss Access/Refresh tokens never stored on the client.
 * Free analysis uses anonymous identity and must not call appLogin.
 */

import { appLogin, getIsTossLoginIntegratedService } from '@apps-in-toss/web-framework';
import { clearClientUserData } from './clientSession';
import {
  LOGIN_BACKEND_FAILED,
  LOGIN_START_FAILED,
} from './userFacingErrors';

const SESSION_KEY = 'vagent_session_token_v1';

export type TossLoginStage =
  | 'OK'
  | 'APP_LOGIN_FUNCTION_UNAVAILABLE'
  | 'APP_LOGIN_CANCELLED'
  | 'APP_LOGIN_FAILED'
  | 'AUTHORIZATION_CODE_MISSING'
  | 'BACKEND_LOGIN_FAILED';

export type TossLoginResult = {
  ok: boolean;
  stage: TossLoginStage;
};

function loginWarn(event: string) {
  try {
    console.warn(`[TOSS_LOGIN] ${event}`);
  } catch {
    /* ignore */
  }
}

export function getVagentSessionToken(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

export function setVagentSessionToken(token: string) {
  try {
    sessionStorage.setItem(SESSION_KEY, token);
  } catch {
    /* ignore */
  }
}

export function clearVagentSessionToken() {
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

function isCancelLike(error: unknown): boolean {
  const rec = error as { message?: string; code?: string; name?: string };
  const text = `${rec?.code || ''} ${rec?.name || ''} ${rec?.message || ''}`.toLowerCase();
  return /user_cancel|cancelled|canceled|cancel\b|취소|닫기/.test(text);
}

export function tossLoginUserMessage(stage: TossLoginStage): string | null {
  switch (stage) {
    case 'OK':
    case 'APP_LOGIN_CANCELLED':
    case 'AUTHORIZATION_CODE_MISSING':
      return null;
    case 'BACKEND_LOGIN_FAILED':
      return LOGIN_BACKEND_FAILED;
    case 'APP_LOGIN_FUNCTION_UNAVAILABLE':
    case 'APP_LOGIN_FAILED':
    default:
      return LOGIN_START_FAILED;
  }
}

async function readLoginIntegration(): Promise<boolean | undefined> {
  if (typeof getIsTossLoginIntegratedService !== 'function') return undefined;
  try {
    return await getIsTossLoginIntegratedService();
  } catch {
    return undefined;
  }
}

let loginInFlight: Promise<TossLoginResult> | null = null;

export async function loginWithTossApp(): Promise<TossLoginResult> {
  if (loginInFlight) return loginInFlight;
  const pending: Promise<TossLoginResult> = (async (): Promise<TossLoginResult> => {
    loginWarn('app_login_start');
    if (typeof appLogin !== 'function') {
      loginWarn('app_login_failed');
      return { ok: false, stage: 'APP_LOGIN_FUNCTION_UNAVAILABLE' };
    }

    let result: { authorizationCode?: unknown; referrer?: unknown } | null | undefined;
    try {
      result = await appLogin();
    } catch (error) {
      if (isCancelLike(error)) {
        loginWarn('app_login_failed');
        return { ok: false, stage: 'APP_LOGIN_CANCELLED' };
      }
      loginWarn('app_login_failed');
      return { ok: false, stage: 'APP_LOGIN_FAILED' };
    }

    const authorizationCode = result?.authorizationCode;
    if (typeof authorizationCode !== 'string' || !authorizationCode) {
      loginWarn('app_login_failed');
      return { ok: false, stage: 'AUTHORIZATION_CODE_MISSING' };
    }

    loginWarn('authorization_code_received');
    loginWarn('backend_exchange_start');
    try {
      const { exchangeTossLogin } = await import('../api/client');
      await exchangeTossLogin(authorizationCode, String(result?.referrer || 'DEFAULT'));
    } catch {
      loginWarn('backend_exchange_failed');
      return { ok: false, stage: 'BACKEND_LOGIN_FAILED' };
    }
    loginWarn('success');
    return { ok: true, stage: 'OK' };
  })().finally(() => {
    loginInFlight = null;
  });
  loginInFlight = pending;
  return pending;
}

/** Login only when a server-verified Toss userKey is required. */
export async function ensureTossLogin(): Promise<TossLoginResult> {
  const token = getVagentSessionToken();
  if (token) {
    const { getAuthMe } = await import('../api/client');
    const alive = await getAuthMe();
    if (alive) return { ok: true, stage: 'OK' };
  }
  return loginWithTossApp();
}

let bootstrapInFlight: Promise<void> | null = null;

export async function bootstrapTossSession(): Promise<void> {
  if (bootstrapInFlight) return bootstrapInFlight;
  bootstrapInFlight = (async () => {
    const integrated = await readLoginIntegration();
    const hadSession = !!getVagentSessionToken();
    if (integrated === false && hadSession) {
      clearClientUserData();
      return;
    }
    if (!hadSession) return;
    const { getAuthMe } = await import('../api/client');
    const alive = await getAuthMe();
    if (!alive) return;
  })().finally(() => {
    bootstrapInFlight = null;
  });
  return bootstrapInFlight;
}

export async function resumeTossSession(): Promise<void> {
  const integrated = await readLoginIntegration();
  if (integrated === false && getVagentSessionToken()) {
    clearClientUserData();
  }
}
