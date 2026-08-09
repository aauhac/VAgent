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
  opts?: { separate?: boolean; include_feedback?: boolean },
): Promise<{ analysis_id: string }> {
  const form = new FormData();
  form.append('file', file, filename);
  form.append('separate', String(!!opts?.separate));
  form.append('include_feedback', 'false');
  const res = await fetch(`${API_BASE}/v1/analyses`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getAnalysis(id: string): Promise<AnalysisJob> {
  const res = await fetch(`${API_BASE}/v1/analyses/${id}`);
  if (!res.ok) throw new Error('not found');
  return res.json();
}

export function getPreviewUrl(id: string): string {
  return `${API_BASE}/v1/analyses/${id}/preview`;
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

export async function mockPaySession(sessionId: string) {
  const res = await fetch(`${API_BASE}/v1/diagnostic-sessions/${sessionId}/mock-pay`, {
    method: 'POST',
    headers: headers(),
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

export function saveHistory(entry: { id: string; overall?: number | null; label?: string; at: string; sessionId?: string }) {
  const key = 'vocalfb_history';
  const prev = JSON.parse(localStorage.getItem(key) || '[]');
  const next = [entry, ...prev.filter((x: any) => x.id !== entry.id)].slice(0, 20);
  localStorage.setItem(key, JSON.stringify(next));
}

export function loadHistory() {
  return JSON.parse(localStorage.getItem('vocalfb_history') || '[]');
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
