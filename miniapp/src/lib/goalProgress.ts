/**
 * Goal-aware progress presentation — count / dots only, never fake %.
 * Mirrors backend/app/services/goal_progress.py for local fallback.
 */

export type GoalSource = 'USER_SELECTED' | 'CONCERN_DERIVED' | 'COACHING_GOAL' | 'RECOMMENDED';

export type GoalOption = {
  focus: string;
  label: string;
  kind: string;
  axis: string;
  target?: string | null;
  style_id?: string | null;
};

export type UserVocalGoal = {
  id: string;
  goal_focus: string;
  goal_label: string;
  source: GoalSource | string;
  status: string;
  axis?: string;
  target?: string | null;
  style_id?: string | null;
  kind?: string;
  wording?: string;
  started_at?: string;
};

export type GoalProgressPayload = {
  status: string;
  goal?: {
    id?: string;
    focus?: string;
    label?: string;
    source?: string;
    display_title?: string;
    is_recommended?: boolean;
    started_at?: string;
    kind?: string;
    axis?: string;
    target?: string | null;
  } | null;
  window?: {
    size: number;
    recording_count?: number;
    evaluable_count: number;
    goal_aligned_count: number;
  };
  previous_window?: {
    size: number;
    recording_count?: number;
    evaluable_count: number;
    goal_aligned_count: number;
  } | null;
  sequence?: string[];
  dots?: string[];
  current_evidence?: {
    direction?: string;
    evidence?: string;
    reason?: string;
    evaluable?: boolean;
  } | null;
  summary?: string;
  comparison_available?: boolean;
  note?: string;
  uses_fake_percent?: boolean;
};

export const USER_GOAL_OPTIONS: GoalOption[] = [
  {
    focus: 'REGISTER_CONNECTION',
    label: '고음 구간을 더 안정적으로 연결하기',
    kind: 'FUNCTIONAL',
    axis: 'register_connection',
    target: 'CONNECTED',
  },
  {
    focus: 'EFFORT',
    label: '힘을 덜 밀어붙이고 편하게 내기',
    kind: 'EFFORT_REDUCE',
    axis: 'effort',
    target: 'LOWER',
  },
  {
    focus: 'STABILITY',
    label: '음높이 흔들림 줄이기',
    kind: 'FUNCTIONAL',
    axis: 'stability',
    target: 'STABLE',
  },
  {
    focus: 'BREATHINESS',
    label: '숨이 많이 섞이는 느낌 줄이기',
    kind: 'EXPLICIT_DIRECTION',
    axis: 'breathiness',
    target: 'LOWER',
  },
  {
    focus: 'BRIGHTNESS',
    label: '더 밝고 선명한 음색',
    kind: 'STYLE',
    axis: 'brightness',
    target: 'HIGHER',
    style_id: 'BRIGHT_CLEAR',
  },
  {
    focus: 'TIMBRE_STYLE',
    label: '더 부드럽고 감미로운 음색',
    kind: 'STYLE',
    axis: 'brightness',
    target: 'LOWER',
    style_id: 'SOFT_SWEET',
  },
];

const INSUFFICIENT = new Set(['', 'UNKNOWN', 'UNRESOLVED', 'UNAVAILABLE', 'AMBIGUOUS']);

function axisVal(can: Record<string, string>, axis: string): string | null {
  const v = can[axis];
  if (!v) return null;
  const s = String(v).toUpperCase();
  return INSUFFICIENT.has(s) ? null : s;
}

export function evaluateLocalGoalEvidence(
  goal: GoalOption | UserVocalGoal | { focus?: string; goal_focus?: string; kind?: string; target?: string | null; axis?: string },
  canonical: Record<string, string>,
): { evaluable: boolean; direction: string; evidence: string | null } {
  const focus = String((goal as any).goal_focus || (goal as any).focus || '').toUpperCase();
  const kind = String((goal as any).kind || '').toUpperCase();
  const target = (goal as any).target ? String((goal as any).target).toUpperCase() : null;
  const axis =
    (goal as any).axis
    || USER_GOAL_OPTIONS.find((o) => o.focus === focus)?.axis
    || 'register_connection';
  const evidence = axisVal(canonical, axis);
  if (!evidence) {
    return { evaluable: false, direction: 'INSUFFICIENT_EVIDENCE', evidence: null };
  }
  if (focus === 'SAFETY' || focus === 'MAINTAIN') {
    return { evaluable: false, direction: 'INSUFFICIENT_EVIDENCE', evidence };
  }
  if (focus === 'REGISTER_CONNECTION' || focus === 'HIGH_NOTE_ACCESS') {
    return {
      evaluable: true,
      direction: evidence === 'CONNECTED' ? 'GOAL_ALIGNED' : 'NOT_GOAL_ALIGNED',
      evidence,
    };
  }
  if (focus === 'STABILITY' || focus === 'PITCH_STABILITY' || focus === 'PHRASE_ENDURANCE') {
    return {
      evaluable: true,
      direction: evidence === 'STABLE' ? 'GOAL_ALIGNED' : 'NOT_GOAL_ALIGNED',
      evidence,
    };
  }
  if (focus === 'EFFORT' || kind === 'EFFORT_REDUCE') {
    if (evidence === 'LOW') return { evaluable: true, direction: 'GOAL_ALIGNED', evidence };
    if (evidence === 'HIGH' || evidence === 'MODERATE') {
      return { evaluable: true, direction: 'NOT_GOAL_ALIGNED', evidence };
    }
  }
  if (focus === 'BREATHINESS' && (target === 'LOWER' || kind === 'EXPLICIT_DIRECTION')) {
    return {
      evaluable: true,
      direction: evidence === 'LOW' ? 'GOAL_ALIGNED' : 'NOT_GOAL_ALIGNED',
      evidence,
    };
  }
  if ((focus === 'BRIGHTNESS' || kind === 'STYLE') && target === 'HIGHER') {
    return {
      evaluable: true,
      direction: evidence === 'HIGH' ? 'GOAL_ALIGNED' : 'NOT_GOAL_ALIGNED',
      evidence,
    };
  }
  if ((focus === 'TIMBRE_STYLE' || kind === 'STYLE') && target === 'LOWER') {
    return {
      evaluable: true,
      direction: evidence === 'LOW' ? 'GOAL_ALIGNED' : 'NOT_GOAL_ALIGNED',
      evidence,
    };
  }
  return { evaluable: true, direction: 'NEUTRAL', evidence };
}

export function buildLocalGoalProgress(
  goal: UserVocalGoal | null,
  historical: { canonical: Record<string, string>; created_at?: string; goal_id?: string }[],
  opts?: { recentN?: number; current?: Record<string, string> },
): GoalProgressPayload {
  if (!goal) {
    return { status: 'NO_GOAL', uses_fake_percent: false };
  }
  const recentN = opts?.recentN ?? 5;
  const started = goal.started_at;
  const scoped = historical.filter((s) => {
    if (goal.id && s.goal_id && s.goal_id !== goal.id) return false;
    if (started && s.created_at && s.created_at < started) return false;
    return true;
  });
  const recent = scoped.slice(-recentN);
  const prev = scoped.length > recentN ? scoped.slice(-(recentN * 2), -recentN) : [];

  const score = (rows: typeof recent) => {
    const dots: string[] = [];
    let aligned = 0;
    let evaluable = 0;
    const sequence: string[] = [];
    for (const r of rows) {
      const ev = evaluateLocalGoalEvidence(goal, r.canonical);
      sequence.push(ev.direction);
      if (ev.direction === 'GOAL_ALIGNED') {
        aligned += 1;
        evaluable += 1;
        dots.push('ALIGNED');
      } else if (ev.direction === 'NOT_GOAL_ALIGNED' || ev.direction === 'NEUTRAL') {
        evaluable += 1;
        dots.push(ev.direction === 'NEUTRAL' ? 'NEUTRAL' : 'NOT_ALIGNED');
      } else {
        dots.push('INSUFFICIENT');
      }
    }
    return { aligned, evaluable, dots, sequence, size: rows.length };
  };

  const r = score(recent);
  const p = prev.length ? score(prev) : null;
  let status = 'STARTING';
  if (r.evaluable === 0) status = r.size ? 'INSUFFICIENT_EVIDENCE' : 'INSUFFICIENT_HISTORY';
  else if (!p || p.evaluable === 0) {
    status = r.aligned >= r.evaluable && r.evaluable >= 3 ? 'MAINTAINING' : 'STARTING';
  } else if (r.aligned > p.aligned) status = 'IMPROVING';
  else if (r.aligned < p.aligned) status = 'DECLINING_GOAL_DIRECTION';
  else if (r.aligned / Math.max(r.evaluable, 1) >= 0.8) status = 'MAINTAINING';
  else status = 'STABLE';

  const isStyle = goal.kind === 'STYLE' || goal.wording === 'STYLE_DIRECTION';
  let summary = '기록이 조금 더 쌓이면 목표 방향 변화를 보여드릴게요.';
  if (status === 'IMPROVING') {
    summary = isStyle
      ? '원하는 음색 방향이 최근 녹음에서 더 자주 나타났어요.'
      : p
        ? `최근에는 목표 방향 결과가 조금 더 자주 나타났어요. (이전 ${p.aligned}회 → 최근 ${r.aligned}회)`
        : `최근 ${recentN}회 중 목표 방향 결과 ${r.aligned}회`;
  } else if (status === 'MAINTAINING') {
    summary = '최근에는 목표 방향 결과가 안정적으로 유지되고 있어요.';
  } else if (status === 'STABLE') {
    summary = '최근 녹음에서도 비슷한 수준으로 유지되고 있어요.';
  } else if (status === 'DECLINING_GOAL_DIRECTION') {
    summary = '최근에는 목표 방향 결과가 조금 덜 자주 나타났어요.';
  } else if (status === 'INSUFFICIENT_EVIDENCE') {
    summary = '비교 가능한 기록이 아직 충분하지 않아요.';
  }

  const current_evidence = opts?.current
    ? evaluateLocalGoalEvidence(goal, opts.current)
    : null;

  return {
    status,
    goal: {
      id: goal.id,
      focus: goal.goal_focus,
      label: goal.goal_label,
      source: goal.source,
      display_title: goal.source === 'RECOMMENDED' ? '추천 목표' : '이번 목표',
      is_recommended: goal.source === 'RECOMMENDED',
      started_at: goal.started_at,
      kind: goal.kind,
      axis: goal.axis,
      target: goal.target,
    },
    window: {
      size: recentN,
      recording_count: r.size,
      evaluable_count: r.evaluable,
      goal_aligned_count: r.aligned,
    },
    previous_window: p
      ? {
          size: recentN,
          recording_count: p.size,
          evaluable_count: p.evaluable,
          goal_aligned_count: p.aligned,
        }
      : null,
    sequence: r.sequence,
    dots: r.dots,
    current_evidence: current_evidence
      ? {
          direction: current_evidence.direction,
          evidence: current_evidence.evidence || undefined,
          evaluable: current_evidence.evaluable,
        }
      : null,
    summary,
    comparison_available: !!(p && p.evaluable > 0),
    uses_fake_percent: false,
    note: '목표는 달성률(%)이 아니라 최근 기록에서 목표 방향 evidence가 나타난 횟수로 보여드려요.',
  };
}

/** Text for count line — never returns a percent string. */
export function goalCountLabel(gp: GoalProgressPayload): string {
  const w = gp.window;
  if (!w) return '';
  return `목표 방향 결과 ${w.goal_aligned_count} / ${w.size}회`;
}

export function hasFakePercent(text: string): boolean {
  return /\d+\s*%/.test(text) || /\d+점/.test(text);
}
