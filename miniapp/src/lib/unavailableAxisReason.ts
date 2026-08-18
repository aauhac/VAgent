/**
 * Presentation-only: map engine evidence → user-facing unavailable axis reasons.
 * Does not invent thresholds or recompute analysis.
 */

export type AxisUnavailableReason = {
  code: string;
  user_message: string;
  source: string;
};

export type ProfileAxisId = 'contact' | 'breath' | 'effort' | 'register' | 'resonance';

export const PROFILE_AXIS_META: Record<
  ProfileAxisId,
  { label: string; dimId: string; left: string; right: string }
> = {
  contact: { label: '접촉감', dimId: 'glottal_contact_profile', left: '가벼움', right: '단단함' },
  breath: { label: '숨 섞임', dimId: 'air_leakage_breathiness', left: '적음', right: '많음' },
  effort: { label: '힘', dimId: 'vocal_effort_strain', left: '편안', right: '밀어붙임' },
  register: { label: '성구 연결', dimId: 'register_configuration', left: '분리', right: '자연스러움' },
  resonance: { label: '중역 존재감', dimId: 'resonance_formant_strategy', left: '낮음', right: '높음' },
};

const GENERIC: AxisUnavailableReason = {
  code: 'ESTIMATE_UNAVAILABLE',
  user_message: '이번 녹음에서는 이 항목을 안정적으로 확인하기 어려웠어요.',
  source: 'fallback',
};

function asList(dimsInput: any): any[] {
  if (!dimsInput) return [];
  if (Array.isArray(dimsInput)) return dimsInput;
  return Object.values(dimsInput);
}

function indexDims(dimsInput: any): Record<string, any> {
  const out: Record<string, any> = {};
  for (const d of asList(dimsInput)) {
    const id = d?.dimension_id || d?.id;
    if (id) out[String(id)] = d;
  }
  return out;
}

function indexCriteria(matrix: any[] = []): Record<string, any> {
  const out: Record<string, any> = {};
  for (const row of matrix || []) {
    const id = row?.dimension_id || row?.id;
    if (id) out[String(id)] = row;
  }
  return out;
}

function sufficiency(row: any): string {
  return String(row?.measurement_sufficiency || row?.overall || '').toUpperCase();
}

function hasSegmentStarvation(row: any): boolean {
  if (!row) return false;
  const evalN = Number(row.evaluable_segments);
  const total = Number(row.total_segments);
  if (Number.isFinite(evalN) && Number.isFinite(total) && total > 0) {
    if (evalN <= 2 || evalN / total < 0.25) return true;
  }
  const sat = Number(row.required_satisfied);
  const req = Number(row.required_total || row.required_minimum);
  if (Number.isFinite(sat) && Number.isFinite(req) && req > 0 && sat === 0) return true;
  return sufficiency(row) === 'INSUFFICIENT';
}

function criteriaMentions(row: any, needles: string[]): boolean {
  const blob = JSON.stringify(row?.criteria || row || {}).toLowerCase();
  return needles.some((n) => blob.includes(n.toLowerCase()));
}

function contaminationEvidence(ctx?: {
  quality?: any;
  dimensions?: any;
  criteriaRow?: any;
}): boolean {
  const row = ctx?.criteriaRow;
  if (criteriaMentions(row, ['contamination', 'mixed', 'accompaniment', 'noise_dominant'])) {
    return true;
  }
  return false;
}

/** True only when coverage/duration fields themselves say vocal evidence is short. */
export function vocalCoverageInsufficient(quality?: any, criteriaRow?: any): boolean {
  if (hasSegmentStarvation(criteriaRow)) return true;
  if (!quality) return false;
  const code = String(quality.code || quality.quality_code || quality.coverage_code || '').toUpperCase();
  if (['INSUFFICIENT_COVERAGE', 'SHORT_VOCAL', 'NO_VOCAL', 'INSUFFICIENT_VOCAL'].includes(code)) {
    return true;
  }
  if (quality.insufficient_vocal_coverage === true || quality.usable_vocal === false) return true;
  const usable = Number(quality.usable_voiced_duration_sec);
  const minUsable = Number(quality.min_usable_voiced_duration_sec);
  if (Number.isFinite(usable) && Number.isFinite(minUsable) && minUsable > 0 && usable < minUsable) {
    return true;
  }
  return false;
}

function highRangeMissing(ctx?: { highNoteProfile?: any; pitchContext?: any }): boolean {
  const p = ctx?.highNoteProfile || {};
  const availability = String(p.availability || (p.available ? 'FULL' : '')).toUpperCase();
  if (availability === 'UNAVAILABLE') {
    const reason = String(p.reason || '').toUpperCase();
    if (reason.includes('PITCH') || reason.includes('HIGH') || reason.includes('RANGE')) return true;
  }
  const pitch = ctx?.pitchContext || p.pitch_context || {};
  if (pitch.high_range_available === false) return true;
  return false;
}

/**
 * Pick a user-facing reason for one missing profile axis from real evidence only.
 */
const PLANNER_KEY: Record<ProfileAxisId, string> = {
  contact: 'contact',
  breath: 'breathiness',
  effort: 'effort',
  register: 'register',
  resonance: 'resonance',
};

export function getUnavailableAxisReason(
  axisId: ProfileAxisId,
  opts?: {
    dimensions?: any;
    criteriaMatrix?: any[];
    quality?: any;
    highNoteProfile?: any;
    context?: 'song' | 'precision';
    remainingUncertainties?: string[];
  },
): AxisUnavailableReason {
  const meta = PROFILE_AXIS_META[axisId];
  const byId = indexDims(opts?.dimensions);
  const crit = indexCriteria(opts?.criteriaMatrix);
  const dim = byId[meta.dimId];
  const row = crit[meta.dimId];
  const prefix = opts?.context === 'precision' && axisId === 'effort' ? '강약 과제에서 ' : '';
  const remaining = new Set((opts?.remainingUncertainties || []).map((x) => String(x)));

  const starve = hasSegmentStarvation(row);
  const suff = sufficiency(row);
  const coverageShort = vocalCoverageInsufficient(opts?.quality, row);

  if (axisId === 'register') {
    if (
      highRangeMissing({ highNoteProfile: opts?.highNoteProfile })
      || starve
      || remaining.has('register')
    ) {
      return {
        code: 'INSUFFICIENT_RANGE_TRANSITION',
        user_message: opts?.context === 'precision'
          ? '음역이 바뀌는 표준 과제 구간이 충분하지 않아 안정적으로 확인하기 어려웠어요.'
          : '음역이 바뀌는 구간이 충분하지 않아 안정적으로 확인하기 어려웠어요.',
        source: starve ? `criteria_segments:${meta.dimId}` : 'high_note_or_remaining',
      };
    }
  }

  if (axisId === 'effort') {
    if (starve || suff === 'INSUFFICIENT' || remaining.has('effort') || remaining.has('dynamic_response')) {
      return {
        code: 'INSUFFICIENT_DYNAMIC_VARIATION',
        user_message: `${prefix}강약이 달라지는 구간이 충분하지 않아 안정적으로 비교하기 어려웠어요.`,
        source: `criteria:${meta.dimId}:${suff || 'unknown'}`,
      };
    }
  }

  if (axisId === 'contact') {
    if (starve || suff === 'PARTIAL' || suff === 'INSUFFICIENT' || remaining.has('contact')) {
      return {
        code: 'CONTACT_EVIDENCE_UNAVAILABLE',
        user_message: '접촉 특성을 비교할 수 있는 음향 정보가 충분하지 않았어요.',
        source: `criteria:${meta.dimId}:${suff || 'segments'}`,
      };
    }
  }

  if (axisId === 'resonance') {
    if (starve || suff === 'INSUFFICIENT' || suff === 'PARTIAL' || remaining.has('resonance')) {
      return {
        code: 'RESONANCE_EVIDENCE_UNAVAILABLE',
        user_message: '이번 녹음에서는 관련 음향 특성을 안정적으로 구분하기 어려웠어요.',
        source: `criteria:${meta.dimId}:${suff || 'unknown'}`,
      };
    }
  }

  if (axisId === 'breath') {
    if (starve || suff === 'INSUFFICIENT' || remaining.has('breathiness')) {
      return {
        code: 'BREATHINESS_EVIDENCE_UNAVAILABLE',
        user_message: '숨 섞임을 안정적으로 비교할 수 있는 구간이 충분하지 않았어요.',
        source: `criteria:${meta.dimId}:${suff || 'unknown'}`,
      };
    }
  }

  if (contaminationEvidence({ quality: opts?.quality, criteriaRow: row })) {
    return {
      code: 'SIGNAL_CONTAMINATION',
      user_message:
        '반주나 주변 소리가 함께 들어가 일부 발성 특성을 안정적으로 구분하기 어려웠어요.',
      source: `criteria_contamination:${meta.dimId}`,
    };
  }

  if (coverageShort) {
    return {
      code: 'INSUFFICIENT_VOCAL_COVERAGE',
      user_message: '분석 가능한 목소리 구간이 충분하지 않았어요.',
      source: starve ? `evaluable_segments:${meta.dimId}` : `quality_coverage:${meta.dimId}`,
    };
  }

  if (dim?.hidden && String(dim.confidence_label || '').toLowerCase() === 'low') {
    return {
      code: 'DIRECTIONALITY_UNSTABLE',
      user_message: GENERIC.user_message,
      source: `hidden_low_confidence:${meta.dimId}`,
    };
  }

  if (remaining.has(PLANNER_KEY[axisId])) {
    return { ...GENERIC, source: `remaining_uncertainty:${PLANNER_KEY[axisId]}` };
  }

  return { ...GENERIC, source: `unknown:${meta.dimId}` };
}

export function highNoteUnavailableCopy(profile: any): AxisUnavailableReason | null {
  if (!profile) return null;
  const availability = String(profile.availability || (profile.available ? 'FULL' : 'UNAVAILABLE')).toUpperCase();
  if (profile.available !== false && availability !== 'UNAVAILABLE') return null;
  if (highRangeMissing({ highNoteProfile: profile })) {
    return {
      code: 'INSUFFICIENT_HIGH_RANGE',
      user_message: '이번 녹음에서는 고음 구간이 충분하지 않았어요.',
      source: 'high_note_function_profile',
    };
  }
  return {
    code: 'ESTIMATE_UNAVAILABLE',
    user_message: GENERIC.user_message,
    source: 'high_note_function_profile',
  };
}

export function timbreUnavailableCopy(profile: any): AxisUnavailableReason | null {
  if (!profile) return null;
  const availability = String(profile.availability || (profile.available ? 'FULL' : 'UNAVAILABLE')).toUpperCase();
  if (profile.available !== false && availability !== 'UNAVAILABLE') return null;
  const reason = String(profile.reason || '').toUpperCase();
  if (reason.includes('CONTAM') || reason.includes('MIXED') || reason.includes('NOISE')) {
    return {
      code: 'SIGNAL_CONTAMINATION',
      user_message: '반주나 주변 소리가 함께 들어가 일부 발성 특성을 안정적으로 구분하기 어려웠어요.',
      source: `timbre_profile:${reason || 'contamination'}`,
    };
  }
  if (reason.includes('SEGMENT') || reason.includes('COVERAGE') || reason.includes('VOCAL')) {
    return {
      code: 'INSUFFICIENT_VOCAL_COVERAGE',
      user_message: '분석 가능한 목소리 구간이 충분하지 않았어요.',
      source: `timbre_profile:${reason}`,
    };
  }
  return {
    code: 'RESONANCE_EVIDENCE_UNAVAILABLE',
    user_message: '이번 녹음에서는 관련 음향 특성을 안정적으로 구분하기 어려웠어요.',
    source: `timbre_profile:${reason || 'unavailable'}`,
  };
}

/** Short measurement-scope hint for Precision CTA (not training advice). */
export function precisionHintForAxis(axisId: ProfileAxisId): string | null {
  switch (axisId) {
    case 'register':
      return '정밀 발성 진단에서는 사이렌처럼 음역이 변하는 짧은 추가 녹음으로 다시 확인할 수 있어요.';
    case 'contact':
      return '정밀 발성 진단에서는 지속음을 추가로 녹음해 이 항목을 다시 확인할 수 있어요.';
    case 'effort':
      return '정밀 발성 진단에서는 강약이 변하는 추가 녹음으로 다시 확인할 수 있어요.';
    case 'resonance':
      return '정밀 발성 진단에서는 표준 발성 과제로 관련 음향 특성을 다시 확인할 수 있어요.';
    case 'breath':
      return '정밀 발성 진단에서는 지속음·강약 과제로 숨 섞임을 다시 확인할 수 있어요.';
    default:
      return null;
  }
}

export type MissingProfileAxis = {
  id: ProfileAxisId;
  label: string;
  reason: AxisUnavailableReason;
};

export function listMissingProfileAxes(
  availableIds: Set<string> | string[],
  opts?: {
    dimensions?: any;
    criteriaMatrix?: any[];
    quality?: any;
    highNoteProfile?: any;
    context?: 'song' | 'precision';
    remainingUncertainties?: string[];
  },
): MissingProfileAxis[] {
  const have = availableIds instanceof Set ? availableIds : new Set(availableIds);
  const order: ProfileAxisId[] = ['contact', 'breath', 'effort', 'register', 'resonance'];
  return order
    .filter((id) => !have.has(id))
    .map((id) => ({
      id,
      label: PROFILE_AXIS_META[id].label,
      reason: getUnavailableAxisReason(id, opts),
    }));
}
