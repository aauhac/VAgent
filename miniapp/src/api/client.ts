import { ensureIdentityHeaders } from '../lib/userIdentity';

const API_BASE = import.meta.env.VITE_API_BASE || '';

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

async function headers(extra?: HeadersInit): Promise<HeadersInit> {
  return ensureIdentityHeaders(extra);
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
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/v1/analyses`, {
      method: 'POST',
      headers: await headers(),
      body: form,
    });
  } catch {
    throw new Error(
      '서버에 연결할 수 없어요. backend(http://127.0.0.1:8000)가 실행 중인지 확인해 주세요.',
    );
  }
  if (!res.ok) {
    if (res.status >= 500) {
      throw new Error(
        '분석 요청이 서버에서 실패했어요. backend 로그와 Vite proxy(/v1 → :8000)를 확인해 주세요.',
      );
    }
    throw new Error(await res.text());
  }
  return res.json();
}

export async function getAnalysis(id: string): Promise<AnalysisJob> {
  const res = await fetch(`${API_BASE}/v1/analyses/${id}`, { headers: await headers() });
  if (!res.ok) throw new Error('not found');
  return res.json();
}

export function getPreviewUrl(id: string): string {
  return `${API_BASE}/v1/analyses/${id}/preview`;
}

export async function getProducts(analysisId?: string) {
  const q = analysisId ? `?analysis_id=${encodeURIComponent(analysisId)}` : '';
  const res = await fetch(`${API_BASE}/v1/products${q}`, { headers: await headers() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getAnalysisAccess(analysisId: string) {
  const res = await fetch(`${API_BASE}/v1/analyses/${analysisId}/access`, {
    headers: await headers(),
  });
  if (res.status === 404) {
    const err: any = new Error('ANALYSIS_NOT_FOUND');
    err.code = 'ANALYSIS_NOT_FOUND';
    err.status = 404;
    throw err;
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getServerHistory(limit = 50): Promise<{
  items: Array<{
    analysis_id: string;
    created_at?: string | null;
    filename?: string | null;
    status?: string;
    vocal_type?: string | null;
    song_detail_unlocked?: boolean;
    diagnostic_unlocked?: boolean;
    diagnostic_session_id?: string | null;
    artifact_missing?: boolean;
    error_code?: string | null;
  }>;
}> {
  const res = await fetch(`${API_BASE}/v1/history?limit=${limit}`, {
    headers: await headers(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function mockUnlockSongDetail(analysisId: string) {
  const res = await fetch(`${API_BASE}/v1/analyses/${analysisId}/mock-unlock-detail`, {
    method: 'POST',
    headers: await headers(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSongDetailedReport(analysisId: string) {
  const res = await fetch(`${API_BASE}/v1/analyses/${analysisId}/detailed-report`, {
    headers: await headers(),
  });
  if (res.status === 402) {
    return { error: 'SONG_DETAIL_LOCKED' };
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createDiagnosticSession(sourceAnalysisId?: string) {
  const q = sourceAnalysisId ? `?source_analysis_id=${encodeURIComponent(sourceAnalysisId)}` : '';
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions${q}`, {
    method: 'POST',
    headers: await headers(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function mockPaySession(sessionId: string, productId?: string) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/mock-pay`, {
    method: 'POST',
    headers: await headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(productId ? { product_id: productId } : {}),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitConcerns(
  sessionId: string,
  userConcerns: Array<{ id: string; source?: string; priority?: number; follow_up?: string }>,
  diagnosticMode?: 'CONCERN_FOCUSED' | 'GENERAL_DISCOVERY',
  timbreGoal?: { id: string; source?: string } | null,
) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/concerns`, {
    method: 'POST',
    headers: await headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      user_concerns: userConcerns,
      diagnostic_mode: diagnosticMode,
      ...(timbreGoal ? { timbre_goal: timbreGoal } : {}),
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getDiagnosticProtocol() {
  const res = await fetch(`${API_BASE}/v1/diagnostic/protocol`, { headers: await headers() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitSafety(sessionId: string, answers: Record<string, boolean>) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/safety`, {
    method: 'POST',
    headers: await headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ answers }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function ensureDiagnosticPlan(sessionId: string) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/ensure-plan`, {
    method: 'POST',
    headers: await headers(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getDiagnosticSession(sessionId: string) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}`, {
    headers: await headers(),
  });
  if (res.status === 404) throw new Error('SESSION_NOT_FOUND');
  if (res.status === 403) throw new Error('SESSION_FORBIDDEN');
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadDiagnosticTask(sessionId: string, taskId: string, file: Blob, filename: string) {
  const form = new FormData();
  form.append('file', file, filename);
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/tasks/${taskId}`, {
    method: 'POST',
    headers: await headers(),
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function skipDiagnosticTask(sessionId: string, taskId: string) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/tasks/${taskId}/skip`, {
    method: 'POST',
    headers: await headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ reason: 'USER_CHOICE' }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function startControlledRecordings(sessionId: string) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/start-controlled-recordings`, {
    method: 'POST',
    headers: await headers(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function skipControlledRecordings(sessionId: string, opts?: { remainingOnly?: boolean }) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/skip-controlled-recordings`, {
    method: 'POST',
    headers: await headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ remaining_only: opts?.remainingOnly !== false }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function analyzeDiagnosticSession(sessionId: string) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/analyze`, {
    method: 'POST',
    headers: await headers(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function regenerateDiagnosticReport(sessionId: string) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/regenerate-report`, {
    method: 'POST',
    headers: await headers(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getDiagnosticReport(sessionId: string, opts?: { debug?: boolean }) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/report`, {
    headers: await headers(opts?.debug ? { 'X-VAgent-Debug': '1' } : undefined),
  });
  if (res.status === 402) {
    return { error: 'REPORT_LOCKED' };
  }
  if (res.status === 202) {
    const body = await res.json().catch(() => ({}));
    return { error: 'REPORT_GENERATING', ...(body || {}) };
  }
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
