import { handleUnauthorizedSession } from '../lib/clientSession';
import {
  ANALYSIS_FAILED,
  LOGIN_REQUIRED,
  NETWORK_UNAVAILABLE,
  RESULT_UNAVAILABLE,
  uploadApiErrorMessage,
} from '../lib/userFacingErrors';
import {
  ensureIdentityHeaders,
  IdentityUnavailableError,
  isIdentityUnavailableError,
} from '../lib/userIdentity';
import { getVagentSessionToken, setVagentSessionToken } from '../lib/tossAuth';
import { apiUrl } from './base';

export type AnalysisJob = {
  analysis_id: string;
  status: string;
  stage?: string;
  progress?: number;
  error?: string | null;
  result?: any;
  analysis_status?: string;
  feedback_status?: string;
};

function throwIfAuthLost(res: Response): void {
  if (res.status !== 401) return;
  handleUnauthorizedSession();
  const err = new Error(LOGIN_REQUIRED);
  err.name = 'LOGIN_REQUIRED';
  throw err;
}

async function headers(extra?: HeadersInit): Promise<HeadersInit> {
  try {
    const base = await ensureIdentityHeaders(extra);
    const token = getVagentSessionToken();
    if (!token) return base;
    return {
      ...base,
      Authorization: `Bearer ${token}`,
    };
  } catch (err) {
    if (isIdentityUnavailableError(err)) {
      throw err instanceof IdentityUnavailableError
        ? err
        : new IdentityUnavailableError('USER_IDENTITY_UNAVAILABLE');
    }
    throw err;
  }
}

/** Header builder for the dev-only mock shims in ./devMocks. Not for production paths. */
export async function devMockHeaders(extra?: HeadersInit): Promise<HeadersInit> {
  return headers(extra);
}

export async function createAnalysis(
  file: Blob,
  filename: string,
  opts?: {
    separate?: boolean;
    include_feedback?: boolean;
    analysis_mode?: 'QUICK' | 'FUNCTIONAL' | 'DIAGNOSTIC';
    input_mode?: 'AUTO' | 'MIXED' | 'VOCAL_ONLY';
    pure_vocal?: boolean;
  },
): Promise<{ analysis_id: string }> {
  const form = new FormData();
  form.append('file', file, filename);
  const mode = opts?.analysis_mode || 'FUNCTIONAL';
  const inputMode =
    opts?.input_mode ||
    (opts?.pure_vocal ? 'VOCAL_ONLY' : 'AUTO');
  // Backend is source of truth; FE only declares intent
  const separate =
    mode === 'FUNCTIONAL'
      ? inputMode !== 'VOCAL_ONLY'
      : !!opts?.separate && inputMode !== 'VOCAL_ONLY';
  form.append('separate', String(separate));
  form.append('analysis_mode', mode);
  form.append('input_mode', inputMode);
  form.append('include_feedback', 'false');
  let reqHeaders: HeadersInit;
  try {
    reqHeaders = await headers();
  } catch (e) {
    if (e instanceof Error && e.message === 'API_BASE_NOT_CONFIGURED') throw e;
    if (isIdentityUnavailableError(e)) {
      throw e instanceof IdentityUnavailableError
        ? e
        : new IdentityUnavailableError('USER_IDENTITY_UNAVAILABLE');
    }
    throw e;
  }
  let res: Response;
  try {
    res = await fetch(apiUrl(`/v1/analyses`), {
      method: 'POST',
      headers: reqHeaders,
      body: form,
    });
  } catch (e) {
    if (e instanceof Error && e.message === 'API_BASE_NOT_CONFIGURED') throw e;
    if (isIdentityUnavailableError(e)) {
      throw e instanceof IdentityUnavailableError
        ? e
        : new IdentityUnavailableError('USER_IDENTITY_UNAVAILABLE');
    }
    throw new Error(
      import.meta.env.DEV
        ? '서버에 연결할 수 없어요. 로컬 backend가 실행 중인지 확인해 주세요.'
        : NETWORK_UNAVAILABLE,
    );
  }
  throwIfAuthLost(res);
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    const uploadMsg = uploadApiErrorMessage(res.status, body);
    if (uploadMsg) throw new Error(uploadMsg);
    if (res.status >= 500) {
      throw new Error(
        import.meta.env.DEV
          ? '분석 요청 처리 중 문제가 발생했어요. 로컬 backend 로그를 확인해 주세요.'
          : ANALYSIS_FAILED,
      );
    }
    if (import.meta.env.PROD) {
      throw new Error(ANALYSIS_FAILED);
    }
    throw new Error(body || ANALYSIS_FAILED);
  }
  return res.json();
}

export async function getAnalysis(id: string): Promise<AnalysisJob> {
  const res = await fetch(apiUrl(`/v1/analyses/${id}`), { headers: await headers() });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(RESULT_UNAVAILABLE);
  return res.json();
}

export async function deleteAnalysis(id: string): Promise<void> {
  const res = await fetch(apiUrl(`/v1/analyses/${id}`), {
    method: 'DELETE',
    headers: await headers(),
  });
  throwIfAuthLost(res);
  if (!res.ok) {
    throw new Error('DELETE_FAILED');
  }
}

export function getPreviewUrl(id: string): string {
  return apiUrl(`/v1/analyses/${id}/preview`);
}

export async function getProducts(analysisId?: string) {
  const q = analysisId ? `?analysis_id=${encodeURIComponent(analysisId)}` : '';
  const res = await fetch(apiUrl(`/v1/products${q}`), { headers: await headers() });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export type LatestNotificationResult = {
  found: boolean;
  analysis_id?: string | null;
  sent_at?: string | null;
};

/**
 * Which analysis the completion alert the user just tapped was about.
 * The Smart Message campaign URL is fixed and carries no id, so the deep-link landing
 * asks the server. "Nothing to open" is a normal answer, not an error.
 *
 * Deliberately does NOT run throwIfAuthLost: an expired session must degrade to the
 * anonymous answer, not bounce the deep link to Home mid-redirect.
 */
export async function getLatestNotificationResult(): Promise<LatestNotificationResult> {
  const res = await fetch(apiUrl('/v1/notifications/latest-result'), {
    headers: await headers(),
  });
  if (!res.ok) return { found: false, analysis_id: null, sent_at: null };
  const data = await res.json().catch(() => null);
  const id = data?.analysis_id;
  const analysisId = typeof id === 'string' && id ? id : null;
  return {
    found: Boolean(data?.found) && analysisId != null,
    analysis_id: analysisId,
    sent_at: typeof data?.sent_at === 'string' ? data.sent_at : null,
  };
}

export async function getAnalysisAccess(analysisId: string) {
  const res = await fetch(apiUrl(`/v1/analyses/${analysisId}/access`), {
    headers: await headers(),
  });
  throwIfAuthLost(res);
  if (res.status === 404) {
    const err: any = new Error('ANALYSIS_NOT_FOUND');
    err.code = 'ANALYSIS_NOT_FOUND';
    err.status = 404;
    throw err;
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getServerHistory(limit = 20, offset = 0): Promise<{
  items: Array<{
    analysis_id: string;
    created_at?: string | null;
    filename?: string | null;
    status?: string;
    vocal_type?: string | null;
    song_detail_unlocked?: boolean;
    diagnostic_unlocked?: boolean;
    diagnostic_session_id?: string | null;
    diagnostic_sessions?: Array<{
      session_id: string;
      status?: string | null;
      created_at?: string | null;
      completed_at?: string | null;
    }>;
    artifact_missing?: boolean;
    error_code?: string | null;
  }>;
  unlinked_diagnostics?: Array<{
    session_id: string;
    status?: string | null;
    created_at?: string | null;
    completed_at?: string | null;
  }>;
  has_more?: boolean;
  total_analyses?: number;
}> {
  const res = await fetch(apiUrl(`/v1/history?limit=${limit}&offset=${offset}`), {
    headers: await headers(),
  });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getAuthMe(): Promise<boolean> {
  const token = getVagentSessionToken();
  if (!token) return false;
  try {
    const res = await fetch(apiUrl(`/v1/auth/me`), { headers: await headers() });
    if (res.status === 401) {
      handleUnauthorizedSession();
      return false;
    }
    return res.ok;
  } catch {
    return false;
  }
}

export async function exchangeTossLogin(authorizationCode: string, referrer: string) {
  // Carry the pre-login anonymous identity so the backend can adopt this device's free
  // analyses onto the userKey it verifies. The header is an identifier, never auth proof.
  // Best-effort: a device with no resolvable anonymous key must still be able to log in,
  // it simply has nothing to adopt.
  let loginHeaders: HeadersInit = { 'Content-Type': 'application/json' };
  try {
    loginHeaders = await ensureIdentityHeaders({ 'Content-Type': 'application/json' });
  } catch {
    /* identity unavailable — proceed without adoption */
  }
  const res = await fetch(apiUrl(`/v1/auth/toss/login`), {
    method: 'POST',
    headers: loginHeaders,
    body: JSON.stringify({
      authorization_code: authorizationCode,
      referrer,
    }),
  });
  if (!res.ok) {
    const err: any = new Error('AUTH_FAILED');
    err.code = 'AUTH_FAILED';
    err.status = res.status;
    throw err;
  }
  const data = await res.json();
  if (data?.session_token) setVagentSessionToken(String(data.session_token));
  if (data?.accessToken || data?.refreshToken || data?.access_token || data?.refresh_token) {
    throw new Error('AUTH_FAILED');
  }
  return data;
}

function paymentError(res: Response, payload: any) {
  const code = payload?.error?.code || payload?.detail?.error?.code || `HTTP_${res.status}`;
  const message = payload?.error?.message || payload?.detail?.error?.message || '결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.';
  const err: any = new Error(message);
  err.code = code;
  err.status = res.status;
  return err;
}

export async function createIapIntent(input: {
  product_id: string;
  analysis_id?: string;
  session_id?: string;
}) {
  const res = await fetch(apiUrl(`/v1/payments/iap/intents`), {
    method: 'POST',
    headers: await headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(input),
  });
  const payload = await res.json().catch(() => ({}));
  throwIfAuthLost(res);
  if (!res.ok) throw paymentError(res, payload);
  return payload as {
    intent_id: string;
    sku: string;
    product_id: string;
    resource_id: string;
    expires_in: number;
  };
}

export async function grantIapOrder(input: { intent_id: string; order_id: string }) {
  const res = await fetch(apiUrl(`/v1/payments/iap/grant`), {
    method: 'POST',
    headers: await headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(input),
  });
  const payload = await res.json().catch(() => ({}));
  throwIfAuthLost(res);
  if (!res.ok) throw paymentError(res, payload);
  return payload as { granted: boolean; complete_product_grant?: boolean };
}

export async function recoverIapOrder(input: {
  order_id: string;
  sku?: string;
  /** Binds the order to the intent that produced it. Re-verified server-side. */
  intent_id?: string;
}) {
  const res = await fetch(apiUrl(`/v1/payments/iap/recover`), {
    method: 'POST',
    headers: await headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(input),
  });
  const payload = await res.json().catch(() => ({}));
  throwIfAuthLost(res);
  if (!res.ok) throw paymentError(res, payload);
  return payload as { granted?: boolean };
}

export type RewardedAdStatus = {
  daily_limit: number;
  used_today: number;
  remaining_today: number;
  already_unlocked: boolean;
  can_use_rewarded_ad: boolean;
  reward_type?: string;
};

export async function getRewardedAdStatus(analysisId: string): Promise<RewardedAdStatus> {
  const res = await fetch(apiUrl(`/v1/analyses/${analysisId}/rewarded-ad`), {
    headers: await headers(),
  });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createRewardedAdSession(analysisId: string): Promise<
  RewardedAdStatus & { session_token: string; expires_at?: string }
> {
  const res = await fetch(apiUrl(`/v1/analyses/${analysisId}/rewarded-ad/session`), {
    method: 'POST',
    headers: await headers(),
  });
  throwIfAuthLost(res);
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : await Promise.resolve('');
    throw new Error(detail || `REWARDED_SESSION_${res.status}`);
  }
  return payload;
}

export async function claimRewardedSongDetail(
  analysisId: string,
  sessionToken: string,
): Promise<RewardedAdStatus & { unlocked?: boolean; duplicate?: boolean }> {
  const res = await fetch(apiUrl(`/v1/analyses/${analysisId}/rewarded-ad/claim`), {
    method: 'POST',
    headers: {
      ...(await headers()),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ session_token: sessionToken }),
  });
  throwIfAuthLost(res);
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : '';
    throw new Error(detail || `REWARDED_CLAIM_${res.status}`);
  }
  return payload;
}

export async function getSongDetailedReport(analysisId: string) {
  const res = await fetch(apiUrl(`/v1/analyses/${analysisId}/detailed-report`), {
    headers: await headers(),
  });
  if (res.status === 402) {
    return { error: 'SONG_DETAIL_LOCKED' };
  }
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createDiagnosticSession(sourceAnalysisId?: string) {
  const q = sourceAnalysisId ? `?source_analysis_id=${encodeURIComponent(sourceAnalysisId)}` : '';
  const res = await fetch(apiUrl(`/v1/diagnostic-sessions${q}`), {
    method: 'POST',
    headers: await headers(),
  });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitConcerns(
  sessionId: string,
  userConcerns: Array<{ id: string; source?: string; priority?: number; follow_up?: string }>,
  diagnosticMode?: 'CONCERN_FOCUSED' | 'GENERAL_DISCOVERY',
  timbreGoal?: { id: string; source?: string } | null,
) {
  const res = await fetch(apiUrl(`/v1/diagnostic-sessions/${sessionId}/concerns`), {
    method: 'POST',
    headers: await headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      user_concerns: userConcerns,
      diagnostic_mode: diagnosticMode,
      ...(timbreGoal ? { timbre_goal: timbreGoal } : {}),
    }),
  });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getDiagnosticProtocol() {
  const res = await fetch(apiUrl(`/v1/diagnostic/protocol`), { headers: await headers() });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitSafety(sessionId: string, answers: Record<string, boolean>) {
  const res = await fetch(apiUrl(`/v1/diagnostic-sessions/${sessionId}/safety`), {
    method: 'POST',
    headers: await headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ answers }),
  });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function ensureDiagnosticPlan(sessionId: string) {
  const res = await fetch(apiUrl(`/v1/diagnostic-sessions/${sessionId}/ensure-plan`), {
    method: 'POST',
    headers: await headers(),
  });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getDiagnosticSession(sessionId: string) {
  const res = await fetch(apiUrl(`/v1/diagnostic-sessions/${sessionId}`), {
    headers: await headers(),
  });
  if (res.status === 404) throw new Error('SESSION_NOT_FOUND');
  if (res.status === 403) throw new Error('SESSION_FORBIDDEN');
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadDiagnosticTask(sessionId: string, taskId: string, file: Blob, filename: string) {
  const form = new FormData();
  form.append('file', file, filename);
  const res = await fetch(apiUrl(`/v1/diagnostic-sessions/${sessionId}/tasks/${taskId}`), {
    method: 'POST',
    headers: await headers(),
    body: form,
  });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function skipDiagnosticTask(sessionId: string, taskId: string) {
  const res = await fetch(apiUrl(`/v1/diagnostic-sessions/${sessionId}/tasks/${taskId}/skip`), {
    method: 'POST',
    headers: await headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ reason: 'USER_CHOICE' }),
  });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function startControlledRecordings(sessionId: string) {
  const res = await fetch(apiUrl(`/v1/diagnostic-sessions/${sessionId}/start-controlled-recordings`), {
    method: 'POST',
    headers: await headers(),
  });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function skipControlledRecordings(sessionId: string, opts?: { remainingOnly?: boolean }) {
  const res = await fetch(apiUrl(`/v1/diagnostic-sessions/${sessionId}/skip-controlled-recordings`), {
    method: 'POST',
    headers: await headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ remaining_only: opts?.remainingOnly !== false }),
  });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function analyzeDiagnosticSession(sessionId: string) {
  const res = await fetch(apiUrl(`/v1/diagnostic-sessions/${sessionId}/analyze`), {
    method: 'POST',
    headers: await headers(),
  });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function regenerateDiagnosticReport(sessionId: string) {
  const res = await fetch(apiUrl(`/v1/diagnostic-sessions/${sessionId}/regenerate-report`), {
    method: 'POST',
    headers: await headers(),
  });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getDiagnosticReport(sessionId: string, opts?: { debug?: boolean }) {
  const res = await fetch(apiUrl(`/v1/diagnostic-sessions/${sessionId}/report`), {
    headers: await headers(opts?.debug ? { 'X-VAgent-Debug': '1' } : undefined),
  });
  if (res.status === 402) {
    return { error: 'REPORT_LOCKED' };
  }
  if (res.status === 202) {
    const body = await res.json().catch(() => ({}));
    return { error: 'REPORT_GENERATING', ...(body || {}) };
  }
  throwIfAuthLost(res);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/** Poll session until COMPLETED (or FAILED), optionally triggering analyze when READY. */
export async function waitForDiagnosticCompletion(
  sessionId: string,
  opts?: { triggerAnalyze?: boolean; maxMs?: number },
) {
  const maxMs = opts?.maxMs ?? 120_000;
  const start = Date.now();
  let triggered = false;
  while (Date.now() - start < maxMs) {
    const sess = await getDiagnosticSession(sessionId);
    const status = String(sess?.status || '').toUpperCase();
    if (status === 'COMPLETED') return sess;
    if (status === 'FAILED') {
      throw new Error(sess?.error || '분석에 실패했어요.');
    }
    if (status === 'READY_FOR_ANALYSIS' && opts?.triggerAnalyze !== false && !triggered) {
      triggered = true;
      await analyzeDiagnosticSession(sessionId);
      continue;
    }
    await new Promise((r) => setTimeout(r, 700));
  }
  throw new Error('결과 분석이 지연되고 있어요. 잠시 후 다시 열어주세요.');
}

export function saveHistory(entry: {
  id: string;
  overall?: number | null;
  label?: string;
  filename?: string;
  vocalType?: string;
  at: string;
  sessionId?: string;
  songDetailUnlocked?: boolean;
}) {
  const key = 'vocalfb_history';
  const prev = JSON.parse(localStorage.getItem(key) || '[]');
  const next = [entry, ...prev.filter((x: any) => x.id !== entry.id)].slice(0, 20);
  localStorage.setItem(key, JSON.stringify(next));
}

export function loadHistory() {
  return JSON.parse(localStorage.getItem('vocalfb_history') || '[]');
}

export function patchHistory(id: string, patch: Record<string, unknown>) {
  const key = 'vocalfb_history';
  const prev = JSON.parse(localStorage.getItem(key) || '[]');
  localStorage.setItem(
    key,
    JSON.stringify(prev.map((x: any) => (x.id === id ? { ...x, ...patch } : x))),
  );
}

export function removeHistory(id: string) {
  const key = 'vocalfb_history';
  const prev = JSON.parse(localStorage.getItem(key) || '[]');
  localStorage.setItem(key, JSON.stringify(prev.filter((x: any) => x.id !== id)));
}

export function saveUnlockedSession(sessionId: string) {
  const key = 'vocalfb_sessions';
  const prev = JSON.parse(localStorage.getItem(key) || '[]');
  if (!prev.includes(sessionId)) {
    localStorage.setItem(key, JSON.stringify([sessionId, ...prev].slice(0, 30)));
  }
}

export function loadUnlockedSessions(): string[] {
  return JSON.parse(localStorage.getItem('vocalfb_sessions') || '[]');
}

export function saveSongDetailUnlock(analysisId: string) {
  const key = 'vocalfb_song_details';
  const prev = JSON.parse(localStorage.getItem(key) || '[]');
  if (!prev.includes(analysisId)) {
    localStorage.setItem(key, JSON.stringify([analysisId, ...prev].slice(0, 40)));
  }
  patchHistory(analysisId, { songDetailUnlocked: true });
}

export function loadSongDetailUnlocks(): string[] {
  return JSON.parse(localStorage.getItem('vocalfb_song_details') || '[]');
}

/** Progress Insight — soft-fail when feature disabled or offline. */
export async function getVocalProgressInsight(opts?: {
  recent_n?: number;
  goal?: string;
  exclude_analysis_id?: string;
}): Promise<any | null> {
  const q = new URLSearchParams();
  if (opts?.recent_n) q.set('recent_n', String(opts.recent_n));
  if (opts?.goal) q.set('goal', opts.goal);
  if (opts?.exclude_analysis_id) q.set('exclude_analysis_id', opts.exclude_analysis_id);
  const qs = q.toString();
  try {
    const insightPath = qs
      ? `/v1/me/vocal-progress/insight?${qs}`
      : '/v1/me/vocal-progress/insight';
    const res = await fetch(apiUrl(insightPath), {
      headers: await headers(),
    });
    if (res.status === 404) return null;
    throwIfAuthLost(res);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function postVocalProgressInsight(body: {
  current_canonical: Record<string, string>;
  goal?: any;
  recent_n?: number;
  exclude_analysis_id?: string;
  today_highlights?: { axis: string; title: string; label: string }[];
}): Promise<any | null> {
  try {
    const res = await fetch(apiUrl(`/v1/me/vocal-progress/insight`), {
      method: 'POST',
      headers: await headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    });
    if (res.status === 404) return null;
    throwIfAuthLost(res);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function postVocalSnapshot(body: {
  analysis_id?: string;
  canonical: Record<string, string>;
  analyzer_version?: string | null;
  goal?: any;
  goal_id_at_analysis?: string | null;
  goal_focus_at_analysis?: string | null;
}): Promise<any | null> {
  try {
    const res = await fetch(apiUrl(`/v1/me/vocal-snapshots`), {
      method: 'POST',
      headers: await headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    });
    if (res.status === 404) return null;
    throwIfAuthLost(res);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getVocalGoals(): Promise<{ active: any; history: any[] } | null> {
  try {
    const res = await fetch(apiUrl(`/v1/me/vocal-goals`), { headers: await headers() });
    throwIfAuthLost(res);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function putActiveVocalGoal(body: {
  focus: string;
  label?: string;
  source?: string;
  target?: string | null;
  style_id?: string | null;
}): Promise<any | null> {
  try {
    const res = await fetch(apiUrl(`/v1/me/vocal-goals/active`), {
      method: 'PUT',
      headers: await headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    });
    throwIfAuthLost(res);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getVocalGoalProgress(opts?: {
  recent_n?: number;
  exclude_analysis_id?: string;
}): Promise<any | null> {
  const q = new URLSearchParams();
  if (opts?.recent_n) q.set('recent_n', String(opts.recent_n));
  if (opts?.exclude_analysis_id) q.set('exclude_analysis_id', opts.exclude_analysis_id);
  const qs = q.toString();
  try {
    const goalPath = qs
      ? `/v1/me/vocal-progress/goal?${qs}`
      : '/v1/me/vocal-progress/goal';
    const res = await fetch(apiUrl(goalPath), {
      headers: await headers(),
    });
    throwIfAuthLost(res);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function postVocalGoalProgress(body: {
  current_canonical: Record<string, string>;
  historical: { canonical_json?: Record<string, string>; canonical?: Record<string, string>; created_at?: string; goal_id_at_analysis?: string }[];
  recent_n?: number;
  goal?: any;
}): Promise<any | null> {
  try {
    const res = await fetch(apiUrl(`/v1/me/vocal-progress/goal`), {
      method: 'POST',
      headers: await headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    });
    throwIfAuthLost(res);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function requestCompletionNotification(analysisId: string): Promise<{ ok: boolean }> {
  const res = await fetch(apiUrl(`/v1/analyses/${analysisId}/completion-notification`), {
    method: 'POST',
    headers: await headers({ 'Content-Type': 'application/json' }),
  });
  throwIfAuthLost(res);
  if (!res.ok) throw new Error('NOTIFICATION_OPT_IN_FAILED');
  return res.json();
}
