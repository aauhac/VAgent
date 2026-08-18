/**
 * Presentation-only Vocal Profile completeness fixtures (A–H).
 * Does not invent engine estimates — used by adapter QA.
 */
import type { ProfileAxisId } from '../lib/unavailableAxisReason';

const DIM = {
  contact: 'glottal_contact_profile',
  breath: 'air_leakage_breathiness',
  effort: 'vocal_effort_strain',
  register: 'register_configuration',
  resonance: 'resonance_formant_strategy',
} as const;

function dim(
  id: string,
  opts: {
    status: string;
    hidden?: boolean;
    continuum?: number | null;
    confidence?: string;
    evaluable?: number;
    total?: number;
    sufficiency?: string;
  },
) {
  return {
    dimension_id: id,
    status: opts.status,
    hidden: !!opts.hidden,
    continuum_0_to_1: opts.continuum ?? null,
    confidence_label: opts.confidence || 'medium',
    evaluable_segments: opts.evaluable,
    total_segments: opts.total,
  };
}

function criteria(id: string, sufficiency: string, evaluable = 8, total = 10) {
  return {
    dimension_id: id,
    measurement_sufficiency: sufficiency,
    evaluable_segments: evaluable,
    total_segments: total,
  };
}

const ALL_IDS: ProfileAxisId[] = ['contact', 'breath', 'effort', 'register', 'resonance'];

function allDims(available: Partial<Record<ProfileAxisId, boolean>>) {
  return ALL_IDS.map((id) => {
    const ok = available[id] !== false;
    if (id === 'breath') {
      return dim(DIM.breath, {
        status: ok ? 'LOW' : 'UNKNOWN',
        hidden: !ok,
        confidence: ok ? 'high' : 'low',
        evaluable: ok ? 12 : 1,
        total: 12,
      });
    }
    if (id === 'contact') {
      return dim(DIM.contact, {
        status: ok ? 'MODERATE' : 'UNKNOWN',
        hidden: !ok,
        continuum: ok ? 0.42 : null,
        evaluable: ok ? 10 : 2,
        total: 12,
      });
    }
    if (id === 'effort') {
      return dim(DIM.effort, {
        status: ok ? 'LOW' : 'UNKNOWN',
        hidden: !ok,
        continuum: ok ? 0.3 : null,
        evaluable: ok ? 9 : 1,
        total: 12,
      });
    }
    if (id === 'register') {
      return dim(DIM.register, {
        status: ok ? 'CONNECTED' : 'STABLE_LIKE',
        hidden: !ok,
        confidence: ok ? 'medium' : 'low',
        evaluable: ok ? 8 : 1,
        total: 12,
      });
    }
    return dim(DIM.resonance, {
      status: ok ? 'OBSERVED' : 'UNKNOWN',
      hidden: !ok,
      continuum: ok ? 0.55 : null,
      evaluable: ok ? 8 : 1,
      total: 12,
    });
  });
}

function allCriteria(available: Partial<Record<ProfileAxisId, boolean>>) {
  return ALL_IDS.map((id) => {
    const ok = available[id] !== false;
    return criteria(DIM[id], ok ? 'SUFFICIENT' : 'INSUFFICIENT', ok ? 10 : 1, 12);
  });
}

/** A. Five axes available */
export const fixtureAFiveAxes = {
  id: 'A',
  dimensions: allDims({ contact: true, breath: true, effort: true, register: true, resonance: true }),
  criteriaMatrix: allCriteria({ contact: true, breath: true, effort: true, register: true, resonance: true }),
  expectedAvailable: ['contact', 'breath', 'effort', 'register', 'resonance'],
};

/** B. Three axes available */
export const fixtureBThreeAxes = {
  id: 'B',
  dimensions: allDims({ contact: true, breath: true, effort: true, register: false, resonance: false }),
  criteriaMatrix: allCriteria({ contact: true, breath: true, effort: true, register: false, resonance: false }),
  expectedAvailable: ['contact', 'breath', 'effort'],
};

/** C. One axis available (matches 9dff presentation shape: breathiness only) */
export const fixtureCOneAxis = {
  id: 'C',
  dimensions: [
    dim(DIM.contact, { status: 'UNKNOWN', hidden: true, continuum: null, evaluable: 2, total: 14 }),
    dim(DIM.breath, { status: 'LOW', hidden: false, confidence: 'high', evaluable: 14, total: 14 }),
    dim(DIM.effort, { status: 'UNKNOWN', hidden: true, evaluable: 1, total: 14 }),
    dim(DIM.register, { status: 'STABLE_LIKE', hidden: true, confidence: 'low', evaluable: 1, total: 14 }),
    dim(DIM.resonance, { status: 'OBSERVED', hidden: true, evaluable: 1, total: 14 }),
  ],
  criteriaMatrix: [
    criteria(DIM.contact, 'PARTIAL', 2, 14),
    criteria(DIM.breath, 'SUFFICIENT', 14, 14),
    criteria(DIM.effort, 'INSUFFICIENT', 1, 14),
    criteria(DIM.register, 'INSUFFICIENT', 1, 14),
    criteria(DIM.resonance, 'INSUFFICIENT', 1, 14),
  ],
  quality: {
    duration_sec: 21.8,
    voiced_duration_sec: 12.9,
  },
  expectedAvailable: ['breath'],
  rootCause: 'A+C',
};

/** D. Zero axes */
export const fixtureDZeroAxes = {
  id: 'D',
  dimensions: allDims({ contact: false, breath: false, effort: false, register: false, resonance: false }),
  criteriaMatrix: allCriteria({ contact: false, breath: false, effort: false, register: false, resonance: false }),
  expectedAvailable: [],
};

/** E. Short vocal coverage — duration/segment evidence present */
export const fixtureEShortCoverage = {
  id: 'E',
  dimensions: allDims({ contact: false, breath: false, effort: false, register: false, resonance: false }),
  criteriaMatrix: allCriteria({ contact: false, breath: false, effort: false, register: false, resonance: false }),
  quality: {
    code: 'INSUFFICIENT_COVERAGE',
    insufficient_vocal_coverage: true,
    usable_voiced_duration_sec: 1.2,
    min_usable_voiced_duration_sec: 6,
  },
  expectedReasonCode: 'INSUFFICIENT_VOCAL_COVERAGE',
  expectedAvailable: [],
};

/** F. High-range absent */
export const fixtureFHighRangeAbsent = {
  id: 'F',
  dimensions: allDims({ contact: true, breath: true, effort: true, register: false, resonance: true }),
  criteriaMatrix: allCriteria({ contact: true, breath: true, effort: true, register: false, resonance: true }),
  highNoteProfile: {
    available: false,
    availability: 'UNAVAILABLE',
    reason: 'INSUFFICIENT_HIGH_RANGE',
    pitch_context: { high_range_available: false },
  },
  expectedRegisterReason: 'INSUFFICIENT_RANGE_TRANSITION',
};

/** G. Noise / contamination on a spectral axis */
export const fixtureGContamination = {
  id: 'G',
  dimensions: allDims({ contact: false, breath: true, effort: true, register: true, resonance: false }),
  criteriaMatrix: [
    {
      dimension_id: DIM.contact,
      measurement_sufficiency: 'INSUFFICIENT',
      evaluable_segments: 2,
      total_segments: 12,
      criteria: { contamination: true, accompaniment: 'mixed' },
    },
    criteria(DIM.breath, 'SUFFICIENT', 10, 12),
    criteria(DIM.effort, 'SUFFICIENT', 10, 12),
    criteria(DIM.register, 'SUFFICIENT', 8, 12),
    {
      dimension_id: DIM.resonance,
      measurement_sufficiency: 'INSUFFICIENT',
      evaluable_segments: 2,
      total_segments: 12,
      criteria: { mixed: true },
    },
  ],
  expectedContactReason: 'CONTACT_EVIDENCE_UNAVAILABLE',
};

/** H. Canonical fallback available but raw dimension hidden/unavailable */
export const fixtureHCanonicalFallback = {
  id: 'H',
  dimensions: [
    dim(DIM.contact, { status: 'UNKNOWN', hidden: true, continuum: null, evaluable: 1, total: 10 }),
    dim(DIM.breath, { status: 'LOW', hidden: false, evaluable: 10, total: 10 }),
    dim(DIM.effort, { status: 'UNKNOWN', hidden: true }),
    dim(DIM.register, { status: 'UNKNOWN', hidden: true, confidence: 'low' }),
    dim(DIM.resonance, { status: 'UNKNOWN', hidden: true }),
  ],
  criteriaMatrix: [
    criteria(DIM.contact, 'INSUFFICIENT', 1, 10),
    criteria(DIM.breath, 'SUFFICIENT', 10, 10),
    criteria(DIM.effort, 'INSUFFICIENT', 1, 10),
    criteria(DIM.register, 'INSUFFICIENT', 1, 10),
    criteria(DIM.resonance, 'INSUFFICIENT', 1, 10),
  ],
  canonicalAcoustic: {
    axes: {
      contact: { continuum: 0.52, display: '중간', available: true },
      breathiness: { continuum: 0.28, display: '적음', available: true },
    },
  },
  expectedAvailable: ['contact', 'breath'],
};

export const VOCAL_PROFILE_FIXTURES = {
  A: fixtureAFiveAxes,
  B: fixtureBThreeAxes,
  C: fixtureCOneAxis,
  D: fixtureDZeroAxes,
  E: fixtureEShortCoverage,
  F: fixtureFHighRangeAbsent,
  G: fixtureGContamination,
  H: fixtureHCanonicalFallback,
};
