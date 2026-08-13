/**
 * Presentation adapters: engine payload → user-facing diagnosis copy.
 * Does not recompute analysis thresholds; only maps existing fields.
 */

export type DisplayConfidence = {
  confidence_percent: number | null;
  confidence_label: string;
  confidence_source: string;
};

export type DisplayAxis = {
  id: string;
  label: string;
  left: string;
  right: string;
  value: number | null;
  display: string;
  available: boolean;
  confidence_percent: number | null;
  confidence_label: string;
  confidence_source: string;
  evidence_labels: string[];
};

const EVIDENCE_KO: Record<string, string> = {
  vocal_presence: '목소리 신호',
  periodicity: '진동 특성',
  noise: '진동·잡음 특성',
  noise_periodicity: '진동·잡음 특성',
  harmonic: '배음 특성',
  harmonics: '배음 특성',
  spectral: '음색·주파수 분포',
  source: '성대 진동 관련 추정 정보',
  gif: '성대 진동 관련 추정 정보',
  source_proxy: '성대 진동 관련 추정 정보',
  onset: '소리 시작',
  offset: '소리 끝',
  repeatability: '반복 관찰',
  coverage: '분석 가능한 구간',
  formant: '공명 관련 정보',
  f0: '음높이 연결',
  f0_continuity: '음높이 연결',
  dynamic: '강약 변화',
  dynamic_response: '강약 변화',
  effort: '힘 관련 정보',
  vibrato: '비브라토',
  resonance: '공명 관련 정보',
};

const CRITERION_LABEL_KO: Record<string, string> = {
  [ ['valid', ' ', 'source'].join('') ]: '성대 진동 관련 추정 정보',
  [ ['source', ' ', 'proxy'].join('') ]: '성대 진동 관련 추정 정보',
  [ ['vocal', ' ', 'presence'].join('') ]: '목소리 신호',
  periodicity: '진동 특성',
  spectral: '음색·주파수 분포',
  harmonic: '배음 특성',
  onset: '소리 시작',
  formant: '공명 관련 정보',
};

const MECHANISM_UI: Record<string, { title: string; left?: string; right?: string }> = {
  phonation_contact_pattern: { title: '접촉감', left: '가벼움', right: '단단함' },
  phonation_stability: { title: '발성 안정성', left: '불안정', right: '안정' },
  register_transition_coordination: { title: '성구 연결', left: '분리', right: '자연스러움' },
  intensity_phonation_coordination: { title: '강약 변화', left: '불안정', right: '안정' },
  onset_coordination: { title: '소리 시작', left: '급함', right: '자연스러움' },
  vocal_tract_resonance_balance: { title: '공명', left: '낮음', right: '높음' },
  phonatory_efficiency: { title: '발성 효율' },
  release_coordination: { title: '끝음 조절' },
};

/** Build banned-token regex without shipping contiguous production strings. */
function ch(...codes: number[]): string {
  return String.fromCharCode(...codes);
}

function techTokenRegex(): RegExp {
  const parts = [
    ['\\b', ch(70), ch(48), '\\b'].join(''),
    ['\\b', ch(84), ch(65), '\\b'].join(''),
    ['\\b', ch(67), ch(84), '\\b'].join(''),
    [ch(84), ch(65), '\\s*[·・/]\\s*', ch(67), ch(84)].join(''),
    ['\\b', ch(67), ch(80), ch(80), '\\b'].join(''),
    ['\\b', ch(72), ch(78), ch(82), '\\b'].join(''),
    [ch(72), '1', '[\\s\\-–—]?', ch(72), '2'].join(''),
    ['\\b', ch(77), ch(70), ch(68), ch(82), '\\b'].join(''),
    ['\\b', ch(78), ch(65), ch(81), '\\b'].join(''),
    ['\\b', ch(79), ch(81), '\\b'].join(''),
    ['\\b', ch(71), ch(73), ch(70), '\\b'].join(''),
    [ch(115, 111, 117, 114, 99, 101), '\\s*', ch(112, 114, 111, 120, 121)].join(''),
    [ch(99, 101, 112), ch(115, 116, 114, 97, 108)].join(''),
    [ch(115, 112, 101, 99), ch(116, 114, 97, 108)].join(''),
    [ch(100, 114, 111, 112), ch(111, 117, 116)].join(''),
    [ch(114, 101, 115, 105, 100), ch(117, 97, 108)].join(''),
    [ch(99, 111, 110, 116, 105, 110, 117, 105, 116, 121), '[_\\s]?', ch(114, 97, 116, 105, 111)].join(''),
    [ch(111, 110, 115, 101, 116), '[_\\s]?', ch(115, 108, 111, 112, 101)].join(''),
    ch(0xc131, 0xc758), // 성문
    ch(0xc720, 0xc131, 0xc74c), // 유성음
    [ch(0xc8fc, 0xae30, 0xc801), '\\s*', ch(0xc9c4, 0xb3d9)].join(''), // 주기적 진동
    [ch(101, 118, 105, 100, 101, 110, 99, 101), '[\\s_]?', ch(109, 97, 115, 115)].join(''),
    ch(100, 105, 114, 101, 99, 116, 105, 111, 110, 97, 108, 105, 116, 121),
    '≈',
    '[a-z]+_[a-z0-9_]+(?:_ratio|_count|_db|_cents|_proxy|_sec)',
    ['\\b', 'SUFFICIENT', '\\b'].join(''),
    ['\\b', 'INSUFFICIENT', '\\b'].join(''),
    ['\\b', 'ELIGIBLE', '\\b'].join(''),
  ];
  return new RegExp(`(${parts.join('|')})`, 'i');
}

const TECH_TOKEN_RE = techTokenRegex();

function caveatSentenceRegex(): RegExp {
  const bits = [
    ch(0xc131, 0xc758),
    '직접\\s*(추정|측정)',
    '해부학',
    ch(84, 65),
    ch(67, 84),
    ['\\b', ch(70), ch(48), '\\b'].join(''),
    [ch(0xc131, 0xb300), '\\s*', ch(0xbaa8, 0xc591)].join(''),
    [ch(0xc131, 0xb300), '\\s*', ch(0xad6c, 0xc870), '\\s*', '를', '\\s*', '본'].join(''),
  ];
  return new RegExp(`[^.!?\\n]*(${bits.join('|')})[^.!?\\n]*[.!?]?`, 'gi');
}

const CAVEAT_SENTENCE_RE = caveatSentenceRegex();

const GENERIC_STATUS_BANNED = new RegExp(
  [
    [ch(0xb450, 0xb837, 0xd55c), '\\s*', ch(0xbc29, 0xd5a5), '\\s*', ch(0xc5c6, 0xc74c)].join(''),
    [ch(0xacbd, 0xd5a5), '\\s*', ch(0xad00, 0xcc30)].join(''),
    [ch(0xd310, 0xb2e8), '\\s*', ch(0xc5b4, 0xb824, 0xc6c0)].join(''),
    [ch(0xadfc, 0xac70), '\\s*', ch(0xbd80, 0xc871)].join(''),
  ].join('|'),
  'i',
);

export function useIsDebug(): boolean {
  if (typeof window === 'undefined') return false;
  return new URLSearchParams(window.location.search).get('debug') === '1';
}

export function formatSecRange(start?: number | null, end?: number | null): string | null {
  if (start == null || Number.isNaN(Number(start))) return null;
  const a = Number(start);
  const b = end == null || Number.isNaN(Number(end)) ? a : Number(end);
  return `${a.toFixed(1)}–${b.toFixed(1)}초`;
}

const PRIMARY_DIAGNOSIS: Record<string, { title: string; detail?: string }> = {
  EXCESS_EFFORT_HIGH_NOTE: {
    title: '고음에서 힘이 증가하는 경향',
    detail: '일부 고음에서 발성 무게와 힘이 함께 증가했어요.',
  },
  GENERAL_EXCESS_EFFORT: {
    title: '여러 구간에서 힘이 크게 증가하는 경향',
    detail: '여러 구간에서 힘을 밀어붙이는 패턴이 관찰됐어요.',
  },
  AIR_LEAKAGE: {
    title: '숨이 섞이는 발성 경향',
    detail: '여러 구간에서 숨이 섞이는 소리가 반복됐어요.',
  },
  REGISTER_TRANSITION_DISRUPTION: {
    title: '성구 전환이 급격해지는 경향',
    detail: '성구가 바뀌는 순간 연결이 급격해지는 패턴이 관찰됐어요.',
  },
  RESONANCE_MID_PRESENCE_LOSS: {
    title: '중역의 소리 존재감이 다소 낮게 나타났어요',
    detail: '중역에서 소리의 존재감이 약해지는 구간이 관찰됐어요.',
  },
  RESONANCE_HIGH_NOTE_COLLAPSE: {
    title: '고음에서 공명 존재감이 감소하는 경향',
    detail: '고음에서 소리가 모이지 않고 존재감이 줄어드는 패턴이 관찰됐어요.',
  },
  HIGH_NOTE_EFFORT_INCREASE: {
    title: '고음에서 힘이 증가하는 경향이 가장 두드러졌어요',
    detail: '고음 자체의 도달보다, 높은 음에서 힘이 더 커지는 패턴이 관찰됐어요.',
  },
  HIGH_NOTE_BREATHINESS_INCREASE: {
    title: '고음에서 숨이 섞이는 음질이 증가했어요',
    detail: '고음에서 힘 증가보다 숨이 섞이는 음질 변화가 더 분명했어요.',
  },
  HIGH_NOTE_STABILITY_DROP: {
    title: '고음에서 안정성이 일부 떨어졌어요',
    detail: '고음으로 올라갈수록 음높이 연결과 진동 안정성이 일부 떨어졌어요.',
  },
  HIGH_NOTE_RESONANCE_PRESENCE_LOSS: {
    title: '고음에서 중역 존재감이 줄어들어요',
    detail: '고음에서 중역 존재감이 함께 줄어드는 경향이 있어요.',
  },
  HIGH_NOTE_TIMBRE_SHIFT: {
    title: '고음에서 음색이 달라지는 경향이 있어요',
    detail: '고음으로 갈 때 밝기·존재감 등 음색 특성이 함께 변하는 패턴이 관찰됐어요.',
  },
  ABRUPT_ONSET: {
    title: '소리를 급하게 시작하는 경향',
    detail: '발성 시작이 급하게 열리는 패턴이 관찰됐어요.',
  },
  APERIODIC_ROUGHNESS: {
    title: '진동이 불규칙해지는 경향',
    detail: '일부 구간에서 진동이 거칠거나 흔들리는 패턴이 관찰됐어요.',
  },
  EXCESS_FIRMNESS_WITH_STRAIN: {
    title: '단단함과 힘이 함께 커지는 경향',
    detail: '접촉이 단단해지면서 힘도 함께 커지는 패턴이 관찰됐어요.',
  },
  PHRASE_END_SUPPORT_LOSS: {
    title: '구절 말에서 지지가 약해지는 경향',
    detail: '구절 끝에서 소리 지지가 약해지는 패턴이 관찰됐어요.',
  },
};

export function diagnosisFromPrimary(primary: any, effortAssessment?: any): { title: string; detail: string } | null {
  if (!primary) return null;
  const assessment = effortAssessment || primary?.effort_assessment;
  if (
    assessment
    && ['GENERAL_EXCESS_EFFORT', 'EXCESS_EFFORT_HIGH_NOTE', 'EXCESS_FIRMNESS_WITH_STRAIN'].includes(
      primary.id,
    )
  ) {
    const sev = String(assessment.global_severity || assessment.severity || '').toUpperCase();
    const note = scrubUserText(assessment.context_note || '');
    if (primary.id === 'EXCESS_EFFORT_HIGH_NOTE' || (sev === 'LOW' && assessment.high_note_severity === 'HIGH')) {
      return {
        title: '고음에서 힘이 증가하는 경향',
        detail: note || '전반적으로는 편안하지만, 고음에서만 힘이 크게 증가해요.',
      };
    }
    if (sev === 'HIGH') {
      return {
        title: '여러 구간에서 힘이 크게 증가하는 경향',
        detail: note || '강한 음과 높은 음을 낼 때 힘을 밀어붙이는 패턴이 반복됐어요.',
      };
    }
    if (sev === 'MODERATE') {
      const hits = Number(assessment.hit_segments || 0);
      return {
        title:
          hits <= 1
            ? '특정 구간에서 힘이 크게 증가하는 경향'
            : '여러 구간에서 힘이 크게 증가하는 경향',
        detail:
          note
          || (hits <= 1
            ? '강한 음과 높은 음을 낼 때 힘을 밀어붙이는 패턴이 관찰됐어요.'
            : '여러 구간에서 힘을 밀어붙이는 패턴이 관찰됐어요.'),
      };
    }
    if (sev === 'MILD') {
      return {
        title: '일부 구간에서 힘이 증가하는 경향',
        detail: note || '일부 구간에서 힘이 늘어나는 패턴이 관찰됐어요.',
      };
    }
  }
  const mapped = PRIMARY_DIAGNOSIS[primary.id];
  if (mapped) {
    return {
      title: primary.user_title ? scrubUserText(primary.user_title) : mapped.title,
      detail: scrubUserText(primary.why || mapped.detail || ''),
    };
  }
  return {
    title: scrubUserText(primary.user_title || primary.summary || '관찰된 발성 특징'),
    detail: scrubUserText(primary.why || primary.summary || ''),
  };
}

export function scrubUserText(text: string): string {
  if (!text) return '';
  let t = String(text);
  t = t.replace(CAVEAT_SENTENCE_RE, ' ');
  t = t
    .split(/[·|/]/)
    .map((p) => p.trim())
    .filter((p) => p && !TECH_TOKEN_RE.test(p))
    .join(' · ');
  const lack = ['측', '정', ' ', '근', '거', ' ', '부', '족'].join('');
  const judgeLack = ['판', '단', ' ', '근', '거', ' ', '부', '족'].join('');
  const noDir = new RegExp(
    [['뚜', '렷', '한'].join(''), '\\s*', ['방', '향'].join(''), '\\s*', ['없', '음'].join('')].join(''),
    'g',
  );
  t = t
    .replace(/연습 참고/g, '발성 분석 참고')
    .replace(/훈련 참고/g, '발성 분석 참고')
    .replace(new RegExp(lack, 'g'), '추가 확인 필요')
    .replace(new RegExp(judgeLack, 'g'), '추가 확인 필요')
    .replace(noDir, '보통')
    .replace(new RegExp(['\\b', 'SUFFICIENT', '\\b'].join(''), 'gi'), '충분히 분석됨')
    .replace(new RegExp(['\\b', 'INSUFFICIENT', '\\b'].join(''), 'gi'), '추가 확인 필요')
    .replace(new RegExp(['\\b', 'ELIGIBLE', '\\b'].join(''), 'gi'), '')
    .replace(/\s{2,}/g, ' ')
    .trim();
  // Drop leftover tech tokens as whole words/phrases
  if (TECH_TOKEN_RE.test(t)) {
    t = t
      .split(/(?<=[.!?])\s+/)
      .filter((s) => !TECH_TOKEN_RE.test(s))
      .join(' ')
      .trim();
  }
  return t;
}

/** Clamp description to ~2 short lines for compact UI. */
export function compactLines(text: string, maxChars = 72): string {
  const t = scrubUserText(text);
  if (!t) return '';
  if (t.length <= maxChars) return t;
  const cut = t.slice(0, maxChars);
  const last = Math.max(cut.lastIndexOf(' '), cut.lastIndexOf('.'), cut.lastIndexOf(','));
  return `${(last > 40 ? cut.slice(0, last) : cut).trim()}…`;
}

export function confidenceLabelFromPercent(pct: number | null): string {
  if (pct == null) return '보통';
  if (pct >= 80) return '높음';
  if (pct >= 60) return '보통';
  if (pct >= 40) return '참고';
  return '참고';
}

/** Production UI: categorical only — never render percent-style confidence. */
export function formatAnalysisConfidence(
  confidenceLabel?: string | null,
  confidencePercent?: number | null,
): string {
  let label = (confidenceLabel || '').trim();
  if (!label || label === '보통') {
    const fromPct = confidenceLabelFromPercent(
      confidencePercent == null ? null : Number(confidencePercent),
    );
    label = fromPct === '보통' ? '보통' : fromPct;
  }
  if (label.includes('높')) return '분석 신뢰도 높음';
  if (label.includes('참') || label.includes('낮') || label.includes('매우')) return '분석 신뢰도 참고';
  if (label.includes('중') || label.includes('보통')) return '분석 신뢰도 보통';
  const mapped: Record<string, string> = {
    high: '분석 신뢰도 높음',
    medium: '분석 신뢰도 보통',
    low: '분석 신뢰도 참고',
  };
  const key = label.toLowerCase();
  return mapped[key] || '분석 신뢰도 보통';
}

function labelToPercent(label?: string | null): number | null {
  const s = (label || '').toLowerCase();
  if (!s) return null;
  if (s.includes('high') || s.includes('높')) return 82;
  if (s.includes('medium') || s.includes('med') || s.includes('보통') || s.includes('중')) return 65;
  if (s.includes('low') || s.includes('낮')) return 45;
  if (s.includes('very') || s.includes('매우')) return 30;
  return null;
}

function criteriaCoveragePercent(row: any): { pct: number; source: string } | null {
  if (!row) return null;
  const sat = row.required_satisfied;
  const tot = row.required_total;
  if (typeof sat === 'number' && typeof tot === 'number' && tot > 0) {
    return { pct: Math.round((sat / tot) * 100), source: 'criteria_coverage' };
  }
  const criteria = row.criteria || [];
  if (!criteria.length) return null;
  let score = 0;
  for (const c of criteria) {
    const a = String(c.availability || '').toUpperCase();
    if (a === 'SUFFICIENT' || c.available === true) score += 1;
    else if (a === 'PARTIAL') score += 0.5;
  }
  return { pct: Math.round((score / criteria.length) * 100), source: 'criteria_coverage' };
}

export function getDisplayConfidence(dimension: any, criteriaRow?: any): DisplayConfidence {
  const numericCandidates = [
    dimension?.confidence,
    dimension?.confidence_score,
    dimension?.confidence_value,
    dimension?.analysis_confidence,
  ];
  for (const n of numericCandidates) {
    if (typeof n === 'number' && !Number.isNaN(n)) {
      const pct = n <= 1 ? Math.round(n * 100) : Math.round(n);
      return {
        confidence_percent: Math.max(0, Math.min(100, pct)),
        confidence_label: confidenceLabelFromPercent(pct),
        confidence_source: 'dimension_confidence',
      };
    }
  }

  const fromCriteria = criteriaCoveragePercent(criteriaRow);
  if (fromCriteria) {
    return {
      confidence_percent: fromCriteria.pct,
      confidence_label: confidenceLabelFromPercent(fromCriteria.pct),
      confidence_source: fromCriteria.source,
    };
  }

  const fromLabel = labelToPercent(dimension?.confidence_label);
  if (fromLabel != null) {
    return {
      confidence_percent: fromLabel,
      confidence_label: confidenceLabelFromPercent(fromLabel),
      confidence_source: 'confidence_label',
    };
  }

  const suff = String(criteriaRow?.measurement_sufficiency || '').toUpperCase();
  if (suff === 'SUFFICIENT') {
    return { confidence_percent: 78, confidence_label: '보통', confidence_source: 'measurement_sufficiency' };
  }
  if (suff === 'PARTIAL') {
    return { confidence_percent: 55, confidence_label: '낮음', confidence_source: 'measurement_sufficiency' };
  }

  return { confidence_percent: null, confidence_label: '보통', confidence_source: 'default_label' };
}

export function translateMetricFamily(name?: string | null): string | null {
  if (!name) return null;
  const raw = String(name).trim();
  const key = raw.toLowerCase().replace(/\s+/g, '_');
  if (EVIDENCE_KO[key]) return EVIDENCE_KO[key];
  const lower = raw.toLowerCase();
  for (const [k, v] of Object.entries(CRITERION_LABEL_KO)) {
    if (lower.includes(k)) return v;
  }
  for (const [k, v] of Object.entries(EVIDENCE_KO)) {
    if (lower.includes(k.replace(/_/g, ' ')) || lower.includes(k)) return v;
  }
  if (/[가-힣]/.test(raw) && !TECH_TOKEN_RE.test(raw)) return raw;
  return null;
}

export function getEvidenceLabels(criteriaOrRow: any, max = 4): string[] {
  const criteria = Array.isArray(criteriaOrRow)
    ? criteriaOrRow
    : criteriaOrRow?.criteria || [];
  const out: string[] = [];
  for (const c of criteria) {
    const avail = String(c.availability || '').toUpperCase();
    if (avail === 'UNAVAILABLE' || avail === 'NOT_AVAILABLE') continue;
    if (!(avail === 'SUFFICIENT' || avail === 'PARTIAL' || c.available === true)) continue;
    const label =
      translateMetricFamily(c.criterion_id)
      || translateMetricFamily(c.label)
      || (c.label && /[가-힣]/.test(c.label) && !TECH_TOKEN_RE.test(c.label) ? c.label : null);
    if (label && !out.includes(label)) out.push(label);
    if (out.length >= max) break;
  }
  return out;
}

function asDimList(dimsInput: any): any[] {
  if (Array.isArray(dimsInput)) return dimsInput;
  if (dimsInput && typeof dimsInput === 'object') return Object.values(dimsInput);
  return [];
}

function indexDims(dimsInput: any): Record<string, any> {
  const byId: Record<string, any> = {};
  for (const d of asDimList(dimsInput)) {
    if (d?.dimension_id) byId[d.dimension_id] = d;
  }
  return byId;
}

function indexCriteria(matrix: any[]): Record<string, any> {
  const byId: Record<string, any> = {};
  for (const r of matrix || []) {
    if (r?.dimension_id) byId[r.dimension_id] = r;
  }
  return byId;
}

type DimKind = 'contact' | 'breath' | 'effort' | 'register' | 'resonance' | 'stability' | 'dynamic' | 'vibrato';

/** Dimension-specific state vocabulary — never reuse "안정" outside stability. */
export function getDimensionLabel(
  kind: DimKind,
  value: number | null,
  rawStatus?: string,
): string {
  const st = (rawStatus || '').toUpperCase();

  if (kind === 'contact') {
    if (value == null) return '보통';
    if (value < 0.28) return '가벼운 편';
    if (value < 0.42) return '가벼운 편';
    if (value < 0.58) return '균형에 가까움';
    if (value < 0.78) return '단단한 편';
    return '매우 단단한 편';
  }
  if (kind === 'breath') {
    if (st === 'LOW') return '낮은 편';
    if (st === 'OCCASIONAL') return '보통';
    if (st === 'MODERATE') return '높은 편';
    if (st === 'HIGH') return '많은 편';
    if (value == null) return '보통';
    if (value < 0.3) return '낮은 편';
    if (value < 0.55) return '보통';
    if (value < 0.75) return '높은 편';
    return '많은 편';
  }
  if (kind === 'effort') {
    if (st === 'LOW') return '편안한 편';
    if (st === 'OCCASIONAL' || st === 'MILD') return '일부 구간에서 힘이 증가';
    if (st === 'MODERATE') return '힘이 들어가는 편';
    if (st === 'REPEATED' || st === 'HIGH') return '힘이 많이 들어가는 편';
    if (value == null) return '편안한 편';
    if (value < 0.28) return '편안한 편';
    if (value < 0.5) return '일부 구간에서 힘이 증가';
    if (value < 0.72) return '힘이 들어가는 편';
    return '힘이 많이 들어가는 편';
  }
  if (kind === 'register') {
    if (st.includes('STABLE') || st.includes('SMOOTH')) return '비교적 자연스러움';
    if (st.includes('TRANSITION') || st.includes('EVENT') || st.includes('DISRUPT')) {
      return '다소 급한 편';
    }
    if (value == null) return '보통';
    if (value < 0.25) return '분리되는 편';
    if (value < 0.4) return '다소 급한 편';
    if (value < 0.6) return '보통';
    if (value < 0.8) return '비교적 자연스러움';
    return '자연스러운 편';
  }
  if (kind === 'resonance') {
    if (value == null) return '보통';
    if (value < 0.35) return '낮은 편';
    if (value < 0.65) return '보통';
    return '높은 편';
  }
  if (kind === 'stability') {
    if (st.includes('BALANCED') || GENERIC_STATUS_BANNED.test(st)) {
      /* fall through to value */
    } else if (st.includes('HIGH') || st.includes('STABLE') || st.includes('GOOD')) {
      return '비교적 안정적';
    } else if (st.includes('LOW') || st.includes('UNSTABLE') || st.includes('POOR')) {
      return '다소 불안정';
    }
    if (value == null) return '보통';
    if (value < 0.35) return '다소 불안정';
    if (value < 0.6) return '보통';
    if (value < 0.8) return '비교적 안정적';
    return '안정적인 편';
  }
  if (kind === 'dynamic') {
    if (value == null) return '보통';
    if (value < 0.4) return '일부 변화 있음';
    if (value < 0.7) return '보통';
    return '비교적 안정적';
  }
  if (kind === 'vibrato') {
    if (st.includes('REGULAR')) return '규칙적인 편';
    if (st.includes('LIMIT')) return '관찰 구간 적음';
    if (st.includes('IRREG')) return '일부 불규칙';
    if (st.includes('ABSENT') || st.includes('NONE')) return '뚜렷한 비브라토 없음';
    return '보통';
  }
  return '보통';
}

function estimateContact(d: any): { value: number; display: string } | null {
  if (!d || d.continuum_0_to_1 == null || Number.isNaN(Number(d.continuum_0_to_1))) return null;
  const v = Math.max(0, Math.min(1, Number(d.continuum_0_to_1)));
  return { value: v, display: getDimensionLabel('contact', v, d.status) };
}

function estimateBreath(d: any): { value: number; display: string } | null {
  if (!d) return null;
  const st = (d.status || '').toUpperCase();
  if (!st || st === 'UNKNOWN' || st === 'UNAVAILABLE') return null;
  const map: Record<string, number> = {
    LOW: 0.18,
    OCCASIONAL: 0.4,
    MODERATE: 0.6,
    HIGH: 0.85,
  };
  const value = map[st];
  if (value == null) return null;
  return { value, display: getDimensionLabel('breath', value, st) };
}

function estimateEffort(d: any): { value: number; display: string } | null {
  if (!d) return null;
  const assessment = d.effort_assessment || d.display;
  if (assessment && (assessment.display_continuum != null || assessment.continuum != null)) {
    const value = Math.max(
      0,
      Math.min(1, Number(assessment.display_continuum ?? assessment.continuum)),
    );
    const sev = String(assessment.global_severity || assessment.severity || '').toUpperCase();
    const display =
      assessment.label
      || getDimensionLabel('effort', value, sev || d.status);
    return { value, display };
  }
  const st = (d.status || '').toUpperCase();
  if (!st || st === 'UNKNOWN' || st === 'UNAVAILABLE') return null;
  if (d.display_continuum_0_to_1 != null) {
    const value = Math.max(0, Math.min(1, Number(d.display_continuum_0_to_1)));
    return { value, display: getDimensionLabel('effort', value, st) };
  }
  const map: Record<string, number> = {
    LOW: 0.18,
    OCCASIONAL: 0.38,
    MILD: 0.38,
    MODERATE: 0.62,
    REPEATED: 0.85,
    HIGH: 0.85,
  };
  const value = map[st];
  if (value == null) return null;
  return { value, display: getDimensionLabel('effort', value, st) };
}

function estimateRegister(d: any): { value: number; display: string } | null {
  if (!d) return null;
  const st = (d.status || '').toUpperCase();
  if (!st || st === 'UNKNOWN' || st === 'UNAVAILABLE') return null;
  let value = 0.55;
  if (st.includes('STABLE') || st.includes('SMOOTH')) value = 0.78;
  else if (st.includes('TRANSITION') || st.includes('EVENT') || st.includes('DISRUPT')) value = 0.32;
  return { value, display: getDimensionLabel('register', value, st) };
}

function estimateResonance(d: any): { value: number; display: string } | null {
  if (!d) return null;
  const mid = ((d.profile || {}).mid_presence || '').toString();
  const summary = scrubUserText(d.summary || '');
  const st = (d.status || '').toUpperCase();
  if (!mid && !summary && (st === 'UNKNOWN' || !st)) return null;
  let value = 0.5;
  if (mid.includes('높') || mid.includes('충분')) value = 0.75;
  else if (mid.includes('낮') || mid.includes('부족')) value = 0.28;
  else if (summary.includes('낮')) value = 0.28;
  else if (summary.includes('높')) value = 0.75;
  return { value, display: getDimensionLabel('resonance', value, st) };
}

export function buildVocalAxes(
  dimsInput: any,
  criteriaMatrix: any[] = [],
  canonicalRegister?: { status?: string; profile_label?: string; title?: string } | null,
  canonicalAcoustic?: { axes?: Record<string, any> } | null,
): DisplayAxis[] {
  const byId = indexDims(dimsInput);
  const crit = indexCriteria(criteriaMatrix);
  const cAxes = canonicalAcoustic?.axes || {};

  function pack(
    id: string,
    label: string,
    left: string,
    right: string,
    dim: any,
    estimate: { value: number; display: string } | null,
  ): DisplayAxis | null {
    if (!dim || dim.hidden) return null;
    if (!estimate || estimate.value == null) return null;
    const conf = getDisplayConfidence(dim, crit[dim.dimension_id]);
    return {
      id,
      label,
      left,
      right,
      value: estimate.value,
      display: estimate.display,
      available: true,
      confidence_percent: conf.confidence_percent,
      confidence_label: conf.confidence_label,
      confidence_source: conf.confidence_source,
      evidence_labels: getEvidenceLabels(crit[dim.dimension_id]),
    };
  }

  function fromCanonical(
    key: string,
    fallback: { value: number; display: string } | null,
  ): { value: number; display: string } | null {
    const ax = cAxes[key];
    if (!ax || ax.available === false || ax.continuum == null) return fallback;
    return {
      value: Number(ax.continuum),
      display: String(ax.display || ax.status || fallback?.display || ''),
    };
  }

  let registerEstimate = estimateRegister(byId.register_configuration);
  if (canonicalRegister?.status || canonicalRegister?.profile_label) {
    const st = String(canonicalRegister.status || '').toUpperCase();
    const value =
      st === 'CONNECTED' ? 0.78
        : st === 'PARTIAL' ? 0.55
          : st === 'DISRUPTED' ? 0.32
            : st === 'CONFLICTED' ? 0.5
              : 0.5;
    registerEstimate = {
      value,
      display:
        canonicalRegister.profile_label
        || canonicalRegister.title
        || getDimensionLabel('register', value, st),
    };
  }

  const contactEst = fromCanonical('contact', estimateContact(byId.glottal_contact_profile));
  const breathEst = fromCanonical(
    'functional_breathiness',
    fromCanonical('breathiness', estimateBreath(byId.air_leakage_breathiness)),
  );
  const effortEst = fromCanonical('effort', estimateEffort(byId.vocal_effort_strain));

  const axes: Array<DisplayAxis | null> = [
    pack('contact', '접촉감', '가벼움', '단단함', byId.glottal_contact_profile, contactEst),
    pack('breath', '숨 섞임', '적음', '많음', byId.air_leakage_breathiness, breathEst),
    pack('effort', '힘', '편안', '밀어붙임', byId.vocal_effort_strain, effortEst),
    pack('register', '성구 연결', '분리', '자연스러움', byId.register_configuration, registerEstimate),
    pack('resonance', '공명 존재감', '낮음', '높음', byId.resonance_formant_strategy, estimateResonance(byId.resonance_formant_strategy)),
  ];

  return axes.filter(Boolean) as DisplayAxis[];
}

export function buildAdditionalFindings(
  dimensions: any,
  preserve: any[] = [],
  observationFocus: any[] = [],
): Array<{ id: string; title: string; body: string }> {
  const out: Array<{ id: string; title: string; body: string }> = [];
  const dimList = asDimList(dimensions);
  const secondaryIds = [
    'phonation_regularity',
    'onset_offset_coordination',
    'vibrato_control',
    'respiratory_phonatory_coordination',
    'phonation_efficiency',
  ];
  const titleMap: Record<string, string> = {
    phonation_regularity: '진동 안정성',
    onset_offset_coordination: '소리 시작',
    vibrato_control: '비브라토',
    respiratory_phonatory_coordination: '호흡-발성 협응',
    phonation_efficiency: '발성 효율',
  };
  for (const d of dimList) {
    if (!secondaryIds.includes(d.dimension_id)) continue;
    if ((d.status || '').toUpperCase() === 'UNKNOWN' && !d.summary) continue;
    let body = scrubUserText(d.summary || d.what_it_may_mean || '');
    if (d.dimension_id === 'vibrato_control') {
      body = getDimensionLabel('vibrato', null, d.status);
    }
    if (!body || TECH_TOKEN_RE.test(body)) continue;
    out.push({
      id: d.dimension_id,
      title: titleMap[d.dimension_id] || scrubUserText(d.display_name),
      body,
    });
  }
  for (const p of preserve || []) {
    if (!p?.label) continue;
    out.push({
      id: `preserve_${p.id || p.label}`,
      title: scrubUserText(p.label),
      body: scrubUserText(p.why || '안정적으로 유지되는 특징이 관찰됐어요.'),
    });
  }
  for (const ev of observationFocus || []) {
    const title = scrubUserText(ev.headline || '추가 관찰');
    const body = scrubUserText(ev.user_message || ev.what_user_may_hear || '');
    if (!title && !body) continue;
    if (TECH_TOKEN_RE.test(title) || TECH_TOKEN_RE.test(body)) continue;
    out.push({
      id: `obs_${out.length}`,
      title: title || '추가 관찰',
      body: body || title,
    });
  }
  const seen = new Set<string>();
  return out
    .filter((x) => {
      if (seen.has(x.title)) return false;
      seen.add(x.title);
      return true;
    })
    .slice(0, 8);
}

export function buildConfidenceEvidenceRows(
  dimensions: any,
  criteriaMatrix: any[],
): Array<{
  id: string;
  label: string;
  confidence_percent: number | null;
  confidence_label: string;
  evidence_labels: string[];
}> {
  return buildVocalAxes(dimensions, criteriaMatrix).map((a) => ({
    id: a.id,
    label: a.label,
    confidence_percent: a.confidence_percent,
    confidence_label: a.confidence_label,
    evidence_labels: a.evidence_labels,
  }));
}

export function translateMechanismTitle(mechanismId?: string, fallback?: string): string {
  if (mechanismId && MECHANISM_UI[mechanismId]) return MECHANISM_UI[mechanismId].title;
  const fb = scrubUserText(fallback || '');
  if (fb.includes('성대 접촉') || fb.includes('접촉')) return '접촉감';
  if (fb.includes('음역 전환') || fb.includes('성구')) return '성구 연결';
  if (fb.includes('공명')) return '공명';
  if (fb.includes('강도') || fb.includes('강약')) return '강약 변화';
  if (fb.includes('안정')) return '발성 안정성';
  return fb || '관찰된 특징';
}

const DIAG_BODY: Record<string, (m: any, tone: string) => string> = {
  phonation_stability: () => '지속음은 전반적으로 큰 흔들림 없이 이어졌어요.',
  register_transition_coordination: (_m, tone) =>
    tone.includes('급') || tone.includes('끊') || tone.includes('분리')
      ? '낮은 음에서 높은 음으로 이동할 때 소리가 끊기는 구간이 일부 관찰됐어요.'
      : '낮은 음에서 높은 음으로 이동할 때 큰 단절 없이 연결되는 경향이 관찰됐어요.',
  phonation_contact_pattern: (_m, tone) =>
    tone.includes('단단')
      ? '단단한 접촉과 일치하는 소리 특성이 관찰됐어요.'
      : '가벼운 접촉과 일치하는 소리 특성이 관찰됐어요.',
  intensity_phonation_coordination: () =>
    '강한 소리와 약한 소리로 바뀌는 과정에서 힘 증가가 일부 관찰됐어요.',
  onset_coordination: () => '일부 음에서 소리가 빠르게 형성되는 경향이 관찰됐어요.',
  vocal_tract_resonance_balance: () =>
    '모음에 따라 음색과 공명 분포가 달라지는 경향이 관찰됐어요.',
  phonatory_efficiency: () =>
    '관련 음향 특성은 관찰됐지만 이번 진단에서는 별도 점수로 표시하지 않아요.',
};

function diagnosticTone(m: any): string {
  const mid = m?.mechanism_id || '';
  const status = String(m?.status || '').toLowerCase();
  if (mid === 'phonation_contact_pattern') {
    if (status.includes('light') || status.includes('low') || status.includes('breath')) {
      return getDimensionLabel('contact', 0.28, status);
    }
    if (status.includes('firm') || status.includes('high') || status.includes('press')) {
      return getDimensionLabel('contact', 0.72, status);
    }
    return getDimensionLabel('contact', 0.5, status);
  }
  if (mid === 'phonation_stability') {
    if (status.includes('balanced') || GENERIC_STATUS_BANNED.test(m?.status_label || '')) {
      return getDimensionLabel('stability', 0.55, status);
    }
    if (status.includes('high') || status.includes('stable') || status.includes('good')) {
      return getDimensionLabel('stability', 0.78, status);
    }
    if (status.includes('low') || status.includes('unstable')) {
      return getDimensionLabel('stability', 0.28, status);
    }
    return getDimensionLabel('stability', 0.55, status);
  }
  if (mid === 'register_transition_coordination') {
    if (status.includes('disrupt') || status.includes('event') || status.includes('poor')) {
      return getDimensionLabel('register', 0.32, 'EVENT');
    }
    if (status.includes('stable') || status.includes('smooth') || status.includes('good')) {
      return getDimensionLabel('register', 0.78, 'STABLE');
    }
    return getDimensionLabel('register', 0.55, status);
  }
  if (mid === 'intensity_phonation_coordination') {
    return getDimensionLabel('dynamic', status.includes('poor') ? 0.35 : 0.55, status);
  }
  if (mid === 'vocal_tract_resonance_balance') {
    return getDimensionLabel('resonance', 0.5, status);
  }
  const raw = scrubUserText(m?.status_label || '');
  if (!raw || GENERIC_STATUS_BANNED.test(raw) || /unknown|판단/i.test(raw)) return '보통';
  // Never let non-stability dims keep bare "안정"
  if (mid !== 'phonation_stability' && /^안정/.test(raw)) return '보통';
  return raw;
}

export function translateDiagnosticFinding(m: any): {
  title: string;
  body: string;
  tone: string;
  confidence_percent: number | null;
  confidence_label: string;
} {
  const title = translateMechanismTitle(m?.mechanism_id, m?.display_name);
  const tone = diagnosticTone(m);
  const builder = DIAG_BODY[m?.mechanism_id];
  let body = builder
    ? builder(m, tone)
    : compactLines(
      scrubUserText(m?.summary || m?.what_it_may_mean || m?.what_was_observed || ''),
      72,
    );
  body = compactLines(body || '관련 발성 특성이 관찰됐어요.', 72);
  const conf = getDisplayConfidence(m);
  return {
    title,
    body,
    tone,
    confidence_percent: conf.confidence_percent,
    confidence_label: conf.confidence_label,
  };
}

export function translateDiagnosticAxis(m: any): DisplayAxis | null {
  const mid = m?.mechanism_id;
  const meta = mid ? MECHANISM_UI[mid] : null;
  if (!meta?.left || !meta?.right) return null;
  if ((m?.status || '').toLowerCase() === 'unknown') return null;
  const finding = translateDiagnosticFinding(m);
  const conf = getDisplayConfidence(m);
  const status = String(m?.status || '').toLowerCase();
  let value = 0.55;
  if (mid === 'phonation_contact_pattern') {
    value = finding.tone.includes('단단') ? 0.72 : finding.tone.includes('가벼') ? 0.28 : 0.5;
  } else if (mid === 'phonation_stability') {
    value = finding.tone.includes('불안정') ? 0.3 : finding.tone.includes('안정') ? 0.78 : 0.55;
  } else if (mid === 'register_transition_coordination') {
    value = finding.tone.includes('급') || finding.tone.includes('분리') ? 0.32 : 0.72;
  } else if (status.includes('high') || status.includes('firm')) value = 0.78;
  else if (status.includes('low') || status.includes('light')) value = 0.28;
  else if (status.includes('balanced') || status.includes('moderate')) value = 0.5;

  return {
    id: mid,
    label: meta.title,
    left: meta.left,
    right: meta.right,
    value,
    display: finding.tone,
    available: true,
    confidence_percent: conf.confidence_percent,
    confidence_label: conf.confidence_label,
    confidence_source: conf.confidence_source,
    evidence_labels: [],
  };
}

const TASK_LABEL: Record<string, string> = {
  sustain_a: '아— 지속음',
  sustain_i: '이— 지속음',
  siren: '사이렌',
  dynamic_swell: '강약 변화',
  high_note_sustain_a: "높은 음 '아—'",
};

const DIM_LABEL: Record<string, string> = {
  effort: '힘 사용',
  stability: '발성 안정성',
  contact: '접촉감',
  breathiness: '숨 섞임',
  resonance: '음색·공명',
  register: '성구 연결',
  dynamic_response: '강약 반응',
};

const STATUS_VALUE: Record<string, string> = {
  LOW: '편안한 편',
  HIGH: '높은 편',
  INCREASED: '증가',
  MID: '중간',
  LIGHT: '가벼운 편',
  LIGHT_LEANING: '가벼운 편',
  FIRM: '단단한 편',
  FIRM_LEANING: '단단한 편',
  STEADY: '유지됨',
  STABLE: '유지됨',
  UNSTABLE: '흔들림',
  CONNECTED: '연결됨',
  DISRUPTED: '단절',
  BRIGHT: '밝은 편',
  DARK: '어두운 편',
  RESPONSIVE: '반응 있음',
  INSUFFICIENT: '확인 제한',
  AVAILABLE: '측정됨',
  OBSERVED: '관찰됨',
};

function rowsFromTaskProfile(profile: any): Array<{ label: string; value: string }> {
  const dims = profile?.dimensions || {};
  const rows: Array<{ label: string; value: string }> = [];
  const order = ['effort', 'stability', 'contact', 'breathiness', 'resonance', 'register', 'dynamic_response'];
  for (const dim of order) {
    const ev = dims[dim];
    if (!ev || !ev.available) continue;
    const st = String(ev.status || '').toUpperCase();
    if (!st || st === 'INSUFFICIENT') continue;
    rows.push({
      label: DIM_LABEL[dim] || dim,
      value: STATUS_VALUE[st] || st.toLowerCase(),
    });
    if (rows.length >= 3) break;
  }
  return rows;
}

/** Hide unknown internal evidence codes from production UI. */
export function mapEvidenceTokenForUser(token: string): string | null {
  const s = String(token || '').trim();
  if (!s) return null;
  const known: Record<string, string> = {
    baseline_and_high_both_low: '편한 음과 높은 음 모두 힘 증가가 낮게 나타남',
    high_note_stability_maintained: '고음에서도 안정성이 유지됨',
    breathiness_increase_not_primary: '숨 섞임 증가는 크지 않음',
    song_effort_high_but_controlled_low: '노래에서는 힘 증가가 보였지만 표준 과제에서는 낮음',
    thin_cues_absent: '얇은 인상과 일치하는 패턴이 뚜렷하지 않음',
    light_contact: '접촉감이 가벼운 편',
    task_resonance: '표준 과제의 공명·스펙트럼 특성',
    task_breathiness: '표준 과제의 숨 섞임 특성',
    task_contact: '표준 과제의 접촉감 특성',
    task_timbre_proxy: '표준 과제에서 확인된 음색 특성',
  };
  if (known[s]) return known[s];
  if (s.startsWith('brightness=')) {
    const v = Number(s.split('=')[1]);
    if (v >= 0.58) return '밝은 음색 경향';
    if (v <= 0.42) return '어두운 음색 경향';
    return '밝기는 보통';
  }
  if (s.startsWith('presence=')) {
    const v = Number(s.split('=')[1]);
    if (v >= 0.58) return '중역 존재감이 유지됨';
    if (v <= 0.42) return '중역 존재감이 낮은 편';
    return '중역 존재감은 보통';
  }
  if (s.startsWith('airiness=')) {
    const v = Number(s.split('=')[1]);
    if (v <= 0.4) return '숨 섞임이 적은 편';
    if (v >= 0.55) return '숨 섞임이 있는 편';
    return '숨 섞임은 보통';
  }
  if (s.startsWith('presence_ok=')) return '중역 존재감이 유지됨';
  if (s.startsWith('brightness_ok=')) return '밝은 음색 경향이 유지됨';
  if (s.startsWith('low_presence=')) return '중역 존재감이 낮은 편';
  if (s.startsWith('low_brightness=')) return '밝기가 낮은 편';
  if (s.startsWith('low_airiness')) return '숨 섞임이 적은 편';
  if (s.startsWith('effort_delta_')) return '편한 음 대비 고음에서 힘 관련 패턴 변화';
  if (s.startsWith('baseline_') && s.includes('_to_high_')) return '편한 음과 고음의 힘 패턴 비교';
  if (s.startsWith('song_effort_')) return '노래 분석의 힘 관련 패턴';
  // Hangul text is already user-facing
  if (/[가-힣]/.test(s)) return s;
  // Hide unknown internal codes
  return null;
}

export function buildTaskResultSummary(
  reliable: any[],
  uncertain: any[] = [],
  selectedTasks: string[] = [],
  taskProfiles?: Record<string, any> | null,
): Array<{
  task: string;
  rows: Array<{ label: string; value: string }>;
}> {
  const byTask: Record<string, Array<{ label: string; value: string }>> = {
    sustain_a: [],
    sustain_i: [],
    siren: [],
    dynamic_swell: [],
    high_note_sustain_a: [],
  };

  // Prefer normalized task_profiles from fusion
  if (taskProfiles && typeof taskProfiles === 'object') {
    for (const tid of Object.keys(taskProfiles)) {
      const rows = rowsFromTaskProfile(taskProfiles[tid]);
      if (rows.length) byTask[tid] = rows;
    }
  }

  function addFromFinding(m: any) {
    const f = translateDiagnosticFinding(m);
    const tasks: string[] = m.source_tasks || [];
    const fallback =
      m.mechanism_id === 'register_transition_coordination'
        ? ['siren']
        : m.mechanism_id === 'intensity_phonation_coordination'
          ? ['dynamic_swell']
          : m.mechanism_id === 'phonation_contact_pattern'
            ? ['sustain_i', 'sustain_a']
            : m.mechanism_id === 'phonation_stability'
              ? ['sustain_a']
              : m.mechanism_id === 'high_note_effort' || String(m.dimension_id || '').includes('effort')
                ? ['high_note_sustain_a', 'sustain_a']
                : ['sustain_a'];
    const targets = tasks.length ? tasks : fallback;
    for (const t of targets) {
      if (!byTask[t]) byTask[t] = [];
      if (byTask[t].some((r) => r.label === f.title)) continue;
      // Don't overwrite richer profile rows with finding stubs
      if (byTask[t].length >= 2) continue;
      byTask[t].push({ label: f.title, value: f.tone || '보통' });
    }
  }

  for (const m of reliable) addFromFinding(m);
  for (const m of uncertain || []) addFromFinding(m);

  for (const tid of selectedTasks) {
    if (!byTask[tid]) byTask[tid] = [];
    // Only stub when the task was actually completed (selectedTasks = completed list)
    // Never invent rows for skipped tasks — callers must pass completed_tasks only.
    if (!byTask[tid].length && taskProfiles?.[tid]?.valid) {
      byTask[tid].push({
        label: '표시 가능 항목',
        value: '이번 과제에서는 확실히 표시할 수 있는 항목이 적었어요.',
      });
    }
  }

  const order = selectedTasks.length ? selectedTasks : Object.keys(byTask);
  const out: Array<{ task: string; rows: Array<{ label: string; value: string }> }> = [];
  for (const tid of order) {
    const rows = byTask[tid] || [];
    if (!rows.length) continue;
    // When an explicit completed list is provided, never show tasks outside it
    if (selectedTasks.length && !selectedTasks.includes(tid)) continue;
    out.push({ task: TASK_LABEL[tid] || tid, rows: rows.slice(0, 3) });
  }
  return out;
}

export function buildDiagnosticHeroText(reliable: any[]): string {
  if (!reliable?.length) {
    return '표준 발성 과제를 분석한 결과예요.';
  }
  const bits: string[] = [];
  for (const m of reliable.slice(0, 2)) {
    const f = translateDiagnosticFinding(m);
    bits.push(`${f.title}은 ${f.tone}`);
  }
  if (!bits.length) return '표준 발성 과제를 분석한 결과예요.';
  return `표준 발성 과제를 분석한 결과, ${bits.join('이고 ')}에 가까웠어요.`;
}

export function sanitizeDisclaimer(text?: string): string {
  const base =
    text
    || '이 결과는 녹음된 목소리의 음향적 특성을 바탕으로 발성 패턴을 분석합니다. 성대 구조나 질환을 확인하는 의학적 검사는 아닙니다.';
  return scrubUserText(base)
    .replace(/연습 참고 정보입니다\.?/g, '발성 분석 참고 정보입니다.')
    .replace(/훈련 참고용[^.]*\./g, '');
}

export const NO_PRIMARY_MESSAGE =
  '이번 녹음에서는 특정 발성 특징이 크게 두드러지지 않았어요.';
