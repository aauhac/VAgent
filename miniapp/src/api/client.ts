const API_BASE = import.meta.env.VITE_API_BASE || '';
const USER_ID = 'demo-user';

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

function headers(extra?: HeadersInit): HeadersInit {
  return { 'X-User-Id': USER_ID, ...(extra || {}) };
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
  const res = await fetch(`${API_BASE}/v1/analyses`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getAnalysis(id: string): Promise<AnalysisJob> {
  const res = await fetch(`${API_BASE}/v1/analyses/${id}`, { headers: headers() });
  if (!res.ok) throw new Error('not found');
  return res.json();
}

export function getPreviewUrl(id: string): string {
  return `${API_BASE}/v1/analyses/${id}/preview`;
}

export async function getProducts(analysisId?: string) {
  const q = analysisId ? `?analysis_id=${encodeURIComponent(analysisId)}` : '';
  const res = await fetch(`${API_BASE}/v1/products${q}`, { headers: headers() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getAnalysisAccess(analysisId: string) {
  const res = await fetch(`${API_BASE}/v1/analyses/${analysisId}/access`, {
    headers: headers(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function mockUnlockSongDetail(analysisId: string) {
  const res = await fetch(`${API_BASE}/v1/analyses/${analysisId}/mock-unlock-detail`, {
    method: 'POST',
    headers: headers(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSongDetailedReport(analysisId: string) {
  const res = await fetch(`${API_BASE}/v1/analyses/${analysisId}/detailed-report`, {
    headers: headers(),
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
    headers: headers(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function mockPaySession(sessionId: string, productId?: string) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/mock-pay`, {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(productId ? { product_id: productId } : {}),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitSafety(sessionId: string, answers: Record<string, boolean>) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/safety`, {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ answers }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadDiagnosticTask(sessionId: string, taskId: string, file: Blob, filename: string) {
  const form = new FormData();
  form.append('file', file, filename);
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/tasks/${taskId}`, {
    method: 'POST',
    headers: headers(),
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function analyzeDiagnosticSession(sessionId: string) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/analyze`, {
    method: 'POST',
    headers: headers(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getDiagnosticReport(sessionId: string, opts?: { debug?: boolean }) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/report`, {
    headers: headers(opts?.debug ? { 'X-VAgent-Debug': '1' } : undefined),
  });
  if (res.status === 402) {
    return { error: 'REPORT_LOCKED' };
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getDiagnosticProtocol() {
  const res = await fetch(`${API_BASE}/v1/diagnostic/protocol`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function saveHistory(entry: {
  id: string;
  overall?: number | null;
  label?: string;
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
