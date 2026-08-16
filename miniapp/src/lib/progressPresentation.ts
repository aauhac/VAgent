/**
 * Progress Insight presentation — client mirror of product rules.
 * No fake % for categorical axes. Brightness / source_balance never auto-improvement.
 */

export type ProgressCardKind = 'IMPROVED' | 'CHANGED' | 'MAINTAINED' | 'NEEDS_PRACTICE';

export type ProgressHowMuch = {
  type: 'COUNT_IN_WINDOW';
  window: number;
  label: string;
  previous_count: number;
  recent_count: number;
  current_counts_as_hit?: boolean;
  summary: string;
};

export type ProgressCard = {
  axis: string;
  title: string;
  current_raw: string;
  current_label: string;
  baseline_modal_raw: string;
  baseline_modal_label: string;
  recent_sequence?: { raw: string; label: string }[];
  how_much?: ProgressHowMuch | null;
  interpretation?: string;
  kind: ProgressCardKind;
  headline: string;
  detail: string;
  why_improvement?: string | null;
};

export type ProgressInsightPayload = {
  status: string;
  insight_available: boolean;
  history_count?: number;
  goal_aware?: boolean;
  today: { axis: string; title: string; label: string }[];
  improved: ProgressCard[];
  changed: ProgressCard[];
  maintained: ProgressCard[];
  practice_hint?: string | null;
  note?: string;
  source?: 'server' | 'local';
};

const AXIS_TITLE: Record<string, string> = {
  register_connection: '성구 연결',
  effort: '힘 사용',
  contact: '접촉감',
  breathiness: '숨 섞임',
  stability: '발성 안정성',
  brightness: '밝기',
  source_balance: '소스 밸런스',
  presence: '중역 존재감',
};

const USER_LABEL: Record<string, string> = {
  CONNECTED: '자연스럽게 연결되는 편',
  PARTIAL: '일부 구간만 연결되는 편',
  DISRUPTED: '연결이 끊기는 구간이 있는 편',
  UNRESOLVED: '판단이 어려운 편',
  LOW: '낮은 편',
  MODERATE: '보통',
  HIGH: '높은 편',
  STABLE: '안정적인 편',
  UNSTABLE: '흔들림이 있는 편',
  FIRM: '단단한 편',
  LIGHT: '가벼운 편',
  MID: '중간 편',
  AMBIGUOUS: '애매한 편',
  UNKNOWN: '확인이 어려운 편',
  UNAVAILABLE: '이번엔 확인이 어려워요',
  CHEST_LEANING: '흉성 쪽',
  HEAD_LEANING: '두성 쪽',
  BALANCED: '균형 쪽',
};

const DESCRIPTIVE = new Set(['brightness', 'source_balance', 'timbre', 'presence', 'breathiness', 'contact']);

function userLabel(raw: string): string {
  return USER_LABEL[raw] || raw;
}

function axisTitle(axis: string): string {
  return AXIS_TITLE[axis] || axis;
}

/** Pull categorical labels from free/premium result payload. */
export function extractCanonicalFromResult(data: any): Record<string, string> {
  const out: Record<string, string> = {};
  const axes =
    data?.vocal_type_teaser?.vocal_style_profile?.axes
    || data?.vocal_function_profile?.canonical_acoustic_axes?.axes
    || data?.vocal_function_profile?.axes
    || data?.canonical_acoustic_axes?.axes
    || data?.canonical?.axes
    || {};

  const pick = (axis: string, ...keys: string[]) => {
    for (const k of keys) {
      const node = axes[k];
      if (!node || node.available === false) continue;
      const v = node.value || node.status;
      if (v && String(v).toUpperCase() !== 'UNRESOLVED') {
        out[axis] = String(v).toUpperCase();
        return;
      }
    }
  };

  pick('effort', 'effort');
  pick('contact', 'contact');
  pick('breathiness', 'breathiness', 'functional_breathiness');
  pick('register_connection', 'register_connection');
  pick('stability', 'stability');
  pick('brightness', 'brightness');
  pick('source_balance', 'source_balance');
  pick('presence', 'presence', 'resonance_presence');

  const reg =
    data?.vocal_type_teaser?.vocal_style_profile?.canonical_register
    || data?.vocal_function_profile?.canonical_register;
  if (reg?.status && String(reg.status).toUpperCase() !== 'UNRESOLVED' && !out.register_connection) {
    out.register_connection = String(reg.status).toUpperCase();
  }

  // key_traits display fallback (Korean) — skip; need raw codes for comparison
  return out;
}

export function buildTodayHighlights(canonical: Record<string, string>): ProgressInsightPayload['today'] {
  const order = ['register_connection', 'effort', 'contact', 'stability', 'breathiness'];
  const today: ProgressInsightPayload['today'] = [];
  for (const axis of order) {
    if (!canonical[axis]) continue;
    today.push({
      axis,
      title: axisTitle(axis),
      label: userLabel(canonical[axis]),
    });
    if (today.length >= 3) break;
  }
  return today;
}

function modalOf(labels: string[]): string | null {
  if (!labels.length) return null;
  const counts: Record<string, number> = {};
  for (const l of labels) counts[l] = (counts[l] || 0) + 1;
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
}

function registerImprovement(current: string, dist: Record<string, number>): boolean | null {
  const unstable = (dist.PARTIAL || 0) + (dist.DISRUPTED || 0) + (dist.UNRESOLVED || 0);
  if (current === 'CONNECTED' && unstable >= 0.5) return true;
  if ((current === 'DISRUPTED' || current === 'PARTIAL') && (dist.CONNECTED || 0) >= 0.5) return false;
  return null;
}

/** Build insight from local vocal history snapshots (current excluded). */
export function buildLocalProgressInsight(
  current: Record<string, string>,
  historical: { canonical: Record<string, string> }[],
  opts?: { goal?: string | null; recentN?: number },
): ProgressInsightPayload {
  const today = buildTodayHighlights(current);
  if (!historical.length) {
    return {
      status: 'NO_BASELINE',
      insight_available: false,
      today,
      improved: [],
      changed: [],
      maintained: [],
      source: 'local',
      note: '몇 번 더 부르면, 이전보다 달라진 점을 보여드려요.',
    };
  }

  const recentN = opts?.recentN ?? 5;
  const recent = historical.slice(-recentN);
  const goal = (opts?.goal || '').toUpperCase();
  const goalRegister = goal.includes('REGISTER') || goal.includes('성구');

  const improved: ProgressCard[] = [];
  const changed: ProgressCard[] = [];
  const maintained: ProgressCard[] = [];

  const axes = Object.keys(current);
  for (const axis of axes) {
    const labels = recent
      .map((s) => s.canonical[axis])
      .filter(Boolean) as string[];
    if (!labels.length) continue;
    const dist: Record<string, number> = {};
    for (const l of labels) dist[l] = (dist[l] || 0) + 1 / labels.length;
    const modal = modalOf(labels)!;
    const currentRaw = current[axis];
    const unchanged = currentRaw === modal;

    let improvement: boolean | null = null;
    if (DESCRIPTIVE.has(axis) || axis === 'effort') {
      improvement = null;
    } else if (axis === 'register_connection' && goalRegister) {
      improvement = registerImprovement(currentRaw, dist);
    } else if (axis === 'stability' && goal.includes('STABIL')) {
      improvement = currentRaw === 'STABLE' && (dist.STABLE || 0) < 0.5 ? true : null;
    }

    const seq = recent.map((s) => {
      const raw = s.canonical[axis] || 'UNKNOWN';
      return { raw, label: userLabel(raw) };
    });

    let howMuch: ProgressHowMuch | null = null;
    if (axis === 'register_connection' || axis === 'stability') {
      const target = axis === 'register_connection' ? 'CONNECTED' : 'STABLE';
      const recentCount = labels.filter((l) => l === target).length;
      howMuch = {
        type: 'COUNT_IN_WINDOW',
        window: recentN,
        label: '안정적으로 나타난 기록',
        previous_count: recentCount,
        recent_count: recentCount,
        current_counts_as_hit: currentRaw === target,
        summary: `최근 ${recentN}회 중 안정적인 결과 ${recentCount}회`,
      };
    }

    const base: ProgressCard = {
      axis,
      title: axisTitle(axis),
      current_raw: currentRaw,
      current_label: userLabel(currentRaw),
      baseline_modal_raw: modal,
      baseline_modal_label: userLabel(modal),
      recent_sequence: seq,
      how_much: howMuch,
      kind: 'CHANGED',
      headline: '',
      detail: '',
      why_improvement: null,
    };

    if (improvement === true) {
      improved.push({
        ...base,
        kind: 'IMPROVED',
        headline: '목표 방향으로 개선되고 있어요',
        detail:
          axis === 'register_connection'
            ? '최근 녹음보다 안정적으로 이어지는 구간이 늘었어요'
            : '목표 방향과 맞는 변화예요',
        why_improvement:
          axis === 'register_connection'
            ? '현재 목표가 성구 연결 안정화 방향과 일치하는 변화입니다.'
            : '등록된 목표 방향과 일치합니다.',
      });
    } else if (unchanged) {
      maintained.push({
        ...base,
        kind: 'MAINTAINED',
        headline: '잘 유지하고 있어요',
        detail: '최근 개인 범위와 비슷해요',
      });
    } else if (axis === 'brightness') {
      changed.push({
        ...base,
        kind: 'CHANGED',
        headline: '달라진 부분',
        detail: `최근보다 ${userLabel(currentRaw)}으로 이동했어요`,
      });
    } else if (axis === 'source_balance') {
      changed.push({
        ...base,
        kind: 'CHANGED',
        headline: '달라진 부분',
        detail: `소스 밸런스가 ${userLabel(currentRaw)} 쪽으로 변화했어요`,
      });
    } else if (improvement === false) {
      changed.push({
        ...base,
        kind: 'NEEDS_PRACTICE',
        headline: '조금 더 연습할 부분',
        detail: '최근보다 목표와 멀어진 편이에요',
      });
    } else {
      changed.push({
        ...base,
        kind: 'CHANGED',
        headline: '달라진 부분',
        detail: `${axisTitle(axis)}이(가) ${userLabel(currentRaw)}으로 변화했어요`,
      });
    }
  }

  return {
    status: historical.length <= 2 ? 'LIMITED_HISTORY' : 'AVAILABLE',
    insight_available: true,
    history_count: historical.length,
    goal_aware: goalRegister,
    today,
    improved: improved.slice(0, 2),
    changed: changed.slice(0, 2),
    maintained: maintained.slice(0, 2),
    source: 'local',
    note: '개선은 목표 방향과 맞을 때만 표시합니다. 밝기·밸런스 변화는 개선으로 부르지 않습니다.',
  };
}
