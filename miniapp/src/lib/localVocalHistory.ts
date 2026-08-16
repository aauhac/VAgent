/**
 * Local Personal Vocal History — soft fallback when server baseline flag is off.
 * Never stores embeddings. Canonical categorical labels only.
 */

const KEY = 'vagent_vocal_snapshots_v1';

export type LocalVocalSnapshot = {
  analysis_id: string;
  created_at: string;
  canonical: Record<string, string>;
  analyzer_version?: string | null;
  goal?: string | null;
  goal_id?: string | null;
  goal_focus?: string | null;
};

function readAll(): LocalVocalSnapshot[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '[]') as LocalVocalSnapshot[];
  } catch {
    return [];
  }
}

function writeAll(rows: LocalVocalSnapshot[]) {
  localStorage.setItem(KEY, JSON.stringify(rows.slice(-40)));
}

export function upsertLocalVocalSnapshot(entry: LocalVocalSnapshot) {
  if (!entry.analysis_id || !entry.canonical || !Object.keys(entry.canonical).length) return;
  const prev = readAll().filter((x) => x.analysis_id !== entry.analysis_id);
  writeAll([...prev, entry]);
}

export function listLocalVocalSnapshots(excludeAnalysisId?: string): LocalVocalSnapshot[] {
  const rows = readAll();
  if (!excludeAnalysisId) return rows;
  return rows.filter((x) => x.analysis_id !== excludeAnalysisId);
}

export function clearLocalVocalSnapshots() {
  localStorage.removeItem(KEY);
}
