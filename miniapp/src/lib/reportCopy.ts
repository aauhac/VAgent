/** @deprecated Prefer reportPresentation — kept for import compatibility. */
export {
  useIsDebug,
  formatSecRange,
  diagnosisFromPrimary,
  buildVocalAxes,
  getDisplayConfidence,
  getEvidenceLabels,
  translateMetricFamily,
  scrubUserText,
  NO_PRIMARY_MESSAGE,
} from './reportPresentation';

export function sufficiencyLabel(raw?: string): string {
  const s = (raw || '').toUpperCase();
  if (s === 'SUFFICIENT') return '충분히 분석됨';
  if (s === 'PARTIAL') return '일부만 확인됨';
  if (s === 'INSUFFICIENT' || s === 'UNAVAILABLE') return '추가 확인 필요';
  return '추가 확인 필요';
}

export function findingLabel(raw?: string): string {
  const s = (raw || '').toUpperCase();
  if (['OBSERVED', 'HIGH', 'MODERATE', 'OCCASIONAL', 'REPEATED', 'RESTRICTED'].includes(s)) {
    return '관찰됨';
  }
  if (['LOW', 'STABLE', 'NOT_PROMINENT', 'ABSENT'].includes(s)) return '뚜렷하지 않음';
  if (['UNKNOWN', 'UNAVAILABLE', 'INSUFFICIENT', 'UNDETERMINED'].includes(s)) {
    return '추가 확인 필요';
  }
  return raw || '추가 확인 필요';
}

export function preserveLabels(preserve: any[]): string[] {
  return (preserve || [])
    .map((p) => p?.label)
    .filter(Boolean)
    .slice(0, 3);
}
