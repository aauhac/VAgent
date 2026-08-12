/** Adaptive diagnostic offer helpers — frontend display only, no recompute. */

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
  // Precision product always offers controlled recording — never hide CTA for song-only sufficiency
  if (!offer) return 'required';
  if ((offer as any).precision_requires_recording) return 'required';
  // Legacy fields kept for compatibility but do not skip Precision
  return 'required';
}

/** True when planner explicitly requires additional measurement. */
export function diagnosticTasksRequired(offer: DiagnosticOffer | null | undefined): boolean {
  return classifyDiagnosticOffer(offer) === 'required';
}

export function diagnosticOfferBullets(offer: DiagnosticOffer | null | undefined): string[] {
  if (!offer) return [];
  const labels = (offer.unresolved_labels || []).filter(Boolean).slice(0, 3);
  const bullets: string[] = [];
  if (labels.length) bullets.push(`확인하면 좋은 항목 · ${labels.join(' · ')}`);
  // Do not show provisional exact task counts as final planned recordings
  const planned = (offer as any).planned_task_count;
  if (typeof planned === 'number' && planned > 0) {
    bullets.push(`짧은 추가 녹음 ${planned}개`);
  } else {
    bullets.push('몇 가지 짧은 추가 녹음');
  }
  if (offer.estimated_duration_text && !String(offer.estimated_duration_text).includes('없음')) {
    bullets.push(`예상 시간 · ${offer.estimated_duration_text}`);
  }
  return bullets;
}
