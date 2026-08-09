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

export async function createAnalysis(
  file: Blob,
  filename: string,
  opts?: { separate?: boolean; include_feedback?: boolean },
): Promise<{ analysis_id: string }> {
  const form = new FormData();
  form.append('file', file, filename);
  form.append('separate', String(!!opts?.separate));
  form.append('include_feedback', String(!!opts?.include_feedback));
  const res = await fetch(`${API_BASE}/v1/analyses`, { method: 'POST', body: form });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || 'upload failed');
  }
  return res.json();
}

export async function getAnalysis(id: string): Promise<AnalysisJob> {
  const res = await fetch(`${API_BASE}/v1/analyses/${id}`);
  if (!res.ok) throw new Error('not found');
  return res.json();
}

export function saveHistory(entry: { id: string; overall?: number | null; label?: string; at: string }) {
  const key = 'vocalfb_history';
  const prev = JSON.parse(localStorage.getItem(key) || '[]');
  const next = [entry, ...prev.filter((x: any) => x.id !== entry.id)].slice(0, 20);
  localStorage.setItem(key, JSON.stringify(next));
}

export function loadHistory(): Array<{ id: string; overall?: number | null; label?: string; at: string }> {
  return JSON.parse(localStorage.getItem('vocalfb_history') || '[]');
}
