/**
 * Progress page navigation helpers — safe returnTo, CTA destinations.
 * No external URL back. Presentation/navigation only.
 */

const INTERNAL_PREFIXES = [
  '/',
  '/result/',
  '/history',
  '/record',
  '/upload',
  '/progress',
  '/premium',
  '/diagnostic/',
  '/analyzing/',
  '/quality',
];

export type ProgressLocationState = {
  returnTo?: string;
};

export type GoalCtaKind = 'SET_GOAL' | 'VIEW_DETAIL' | 'ANALYZE';

export type GoalEmptyCta = {
  kind: GoalCtaKind;
  label: string;
  to: string;
  state?: Record<string, unknown>;
};

function readJsonArray(key: string): unknown[] {
  try {
    if (typeof localStorage === 'undefined') return [];
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/** Reject external / javascript / protocol-relative return targets. */
export function isSafeInternalReturnTo(raw: unknown): raw is string {
  if (typeof raw !== 'string') return false;
  const s = raw.trim();
  if (!s.startsWith('/')) return false;
  if (s.startsWith('//')) return false;
  if (/^[a-z]+:/i.test(s)) return false;
  if (s.includes('://')) return false;
  if (s.toLowerCase().includes('javascript:')) return false;
  // Allow exact "/" or known app prefixes
  if (s === '/') return true;
  return INTERNAL_PREFIXES.some((p) => p !== '/' && (s === p || s.startsWith(p)));
}

export function sanitizeReturnTo(raw: unknown, fallback = '/'): string {
  return isSafeInternalReturnTo(raw) ? raw : fallback;
}

export function progressLinkState(returnTo: string): ProgressLocationState {
  return { returnTo: sanitizeReturnTo(returnTo, '/') };
}

/**
 * Resolve back destination for /progress.
 * Prefer explicit returnTo; else in-app PUSH/REPLACE history; else Home.
 * Direct URL / reload (POP without returnTo) → Home — never trust external history.
 */
export function resolveProgressBackTarget(
  locationState: unknown,
  opts?: { navigationType?: 'POP' | 'PUSH' | 'REPLACE' },
): { mode: 'path'; path: string } | { mode: 'history' } | { mode: 'home' } {
  const st = (locationState || {}) as ProgressLocationState;
  if (isSafeInternalReturnTo(st.returnTo)) {
    // Avoid bouncing to /progress itself
    if (st.returnTo === '/progress' || st.returnTo.startsWith('/progress?')) {
      return { mode: 'home' };
    }
    return { mode: 'path', path: st.returnTo };
  }
  const navType = opts?.navigationType;
  if (navType === 'PUSH' || navType === 'REPLACE') {
    return { mode: 'history' };
  }
  return { mode: 'home' };
}

/** Latest analysis from local history + unlock map. */
export function resolveLatestAnalysisForGoalCta(): {
  analysisId: string | null;
  detailUnlocked: boolean;
} {
  const history = readJsonArray('vocalfb_history') as {
    id?: string;
    songDetailUnlocked?: boolean;
  }[];
  const unlocks = new Set(
    readJsonArray('vocalfb_song_details').filter((x): x is string => typeof x === 'string'),
  );
  for (const h of history) {
    const id = h?.id;
    if (!id || typeof id !== 'string') continue;
    const unlocked = !!h.songDetailUnlocked || unlocks.has(id);
    return { analysisId: id, detailUnlocked: unlocked };
  }
  return { analysisId: null, detailUnlocked: false };
}

export function buildNoGoalCta(): GoalEmptyCta {
  const { analysisId, detailUnlocked } = resolveLatestAnalysisForGoalCta();
  if (!analysisId) {
    return {
      kind: 'ANALYZE',
      label: '노래 분석하기',
      to: '/record',
    };
  }
  if (detailUnlocked) {
    return {
      kind: 'SET_GOAL',
      label: '목표 정하러 가기',
      to: `/result/${analysisId}/detail`,
      state: { focusGoalSetting: true },
    };
  }
  return {
    kind: 'VIEW_DETAIL',
    label: '상세 리포트 보기',
    to: `/result/${analysisId}`,
    state: { focusOffer: 'song_detail' },
  };
}

export function noGoalCopy(kind: GoalCtaKind): { title: string; body: string } {
  if (kind === 'ANALYZE') {
    return {
      title: '아직 변화 기록이 없어요',
      body: '먼저 노래를 분석하면 이후 녹음부터 변화 과정을 확인할 수 있어요.',
    };
  }
  if (kind === 'SET_GOAL') {
    return {
      title: '아직 연습 목표가 없어요',
      body: '상세 리포트에서 앞으로 집중할 목표를 정해보세요. 다음 녹음부터 목표 방향의 변화를 추적해드려요.',
    };
  }
  return {
    title: '아직 연습 목표가 없어요',
    body: '상세 리포트에서 발성 분석을 더 자세히 보고 앞으로 집중할 연습 목표를 정할 수 있어요.',
  };
}
