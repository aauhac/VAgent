/**
 * Server-verified Toss login. Toss Access/Refresh tokens never stored on the client.
 */

const SESSION_KEY = 'vagent_session_token_v1';

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

export async function loginWithTossApp(): Promise<boolean> {
  try {
    const mod = await import('@apps-in-toss/web-framework');
    const appLogin = (mod as any).appLogin;
    if (typeof appLogin !== 'function') return false;
    const result = await appLogin();
    const authorizationCode = result?.authorizationCode;
    const referrer = result?.referrer || 'DEFAULT';
    if (!authorizationCode) return false;
    const { exchangeTossLogin } = await import('../api/client');
    await exchangeTossLogin(String(authorizationCode), String(referrer));
    return true;
  } catch {
    return false;
  }
}
