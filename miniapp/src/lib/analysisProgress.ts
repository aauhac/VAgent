/** User-facing analysis progress. Backend stage/progress values stay the source of truth. */

export const ANALYSIS_PROGRESS_HINT = '목소리의 특징을 하나씩 확인하고 있어요.';
export const ANALYSIS_PROGRESS_WAIT = '잠시만 기다려 주세요.';

export const ANALYSIS_INTERRUPTED = '분석이 중단됐어요. 다시 분석해 주세요.';

const STAGE_COPY: Record<string, string> = {
  queued: '분석을 준비하고 있어요',
  start: '분석을 시작하고 있어요',
  load: '음성 파일을 준비하고 있어요',
  preprocess: '목소리 신호를 정리하고 있어요',
  features: '음높이와 음색을 살펴보고 있어요',
  phonation: '발성 특성을 분석하고 있어요',
  quality: '녹음 상태를 확인하고 있어요',
  scoring: '발성 결과를 정리하고 있어요',
  visuals: '결과 화면을 준비하고 있어요',
  feedback: '피드백을 만들고 있어요',
  save: '분석 결과를 저장하고 있어요',
  done: '분석이 완료됐어요',
};

const FALLBACK_COPY = '분석을 진행하고 있어요';

export function analysisStageLabel(stage?: string | null): string {
  const key = String(stage || '').trim().toLowerCase();
  if (!key) return STAGE_COPY.queued;
  return STAGE_COPY[key] || FALLBACK_COPY;
}

export function isInterruptedStage(stage?: string | null, error?: string | null): boolean {
  const key = String(stage || '').trim().toLowerCase();
  const err = String(error || '').toUpperCase();
  return key === 'interrupted_restart' || err === 'INTERRUPTED_RESTART';
}

export function visualAnalysisProgress(input: {
  status?: string | null;
  stage?: string | null;
  progress?: number | null;
}): number {
  const status = String(input.status || '').toLowerCase();
  const stage = String(input.stage || '').toLowerCase();
  if (status === 'completed' || stage === 'done') return 100;
  const n = Number(input.progress);
  const raw = Number.isFinite(n) ? n : 0;
  return Math.max(4, Math.min(raw, 97));
}
