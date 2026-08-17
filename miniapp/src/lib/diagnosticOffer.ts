/** Adaptive diagnostic offer helpers — frontend display only, no recompute. */

import { unresolvedLabelKo } from './userFacingLabels';

export type DiagnosticOffer = {
  unresolved_count?: number;
  unresolved_labels?: string[];
  selected_task_count?: number;
  estimated_duration_text?: string;
  required?: boolean;
  required_tasks?: boolean;
};

export type DiagnosticOfferDecision = 'required' | 'not_required' | 'unknown';

export function pickDiagnosticOffer(source: any): DiagnosticOffer | null {
  if (!source || typeof source !== 'object') return null;
  const offer =
    source.diagnostic_offer
    || source.vocal_function_profile?.diagnostic_offer
    || source.report?.diagnostic_offer
    || null;
  if (!offer || typeof offer !== 'object') return null;
  return offer as DiagnosticOffer;
}

export function classifyDiagnosticOffer(
  offer: DiagnosticOffer | null | undefined,
): DiagnosticOfferDecision {
  if (!offer) return 'required';
  if ((offer as any).precision_requires_recording) return 'required';
  return 'required';
}

/** True when planner explicitly requires additional measurement. */
export function diagnosticTasksRequired(offer: DiagnosticOffer | null | undefined): boolean {
  return classifyDiagnosticOffer(offer) === 'required';
}

export function diagnosticOfferBullets(offer: DiagnosticOffer | null | undefined): string[] {
  if (!offer) return [];
  const labels = (offer.unresolved_labels || [])
    .filter(Boolean)
    .slice(0, 3)
    .map((l) => unresolvedLabelKo(String(l)));
  const bullets: string[] = [];
  if (labels.length) {
    bullets.push(`${labels.join('·')}을 추가 녹음으로 더 확인해요`);
  } else {
    bullets.push('확인이 필요한 발성 항목을 추가 녹음으로 다시 비교해요');
  }
  bullets.push('무엇부터 연습할지 우선순위를 정리해요');
  bullets.push('내 결과에 맞는 단계별 연습 방법을 안내해요');
  return bullets.slice(0, 4);
}

export function diagnosticDurationNote(offer: DiagnosticOffer | null | undefined): string | null {
  if (!offer?.estimated_duration_text) return null;
  const t = String(offer.estimated_duration_text);
  if (t.includes('없음')) return null;
  return `약 ${t.replace(/^약\s*/, '')} · 짧은 추가 녹음`;
}
