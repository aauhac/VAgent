/**
 * Progress Insight presentation — client mirror of product rules.
 * No fake %; no raw English enums; natural Korean change copy.
 */

import {
  axisLabelKo,
  buildAxisChangeCopy,
  buildAxisMaintainedCopy,
  howMuchStableSummary,
  recentWindowLabel,
  stateChipKo,
  stateLabelKo,
} from './userFacingLabels';

export type ProgressCardKind = 'IMPROVED' | 'CHANGED' | 'MAINTAINED' | 'NEEDS_PRACTICE';

export type ProgressHowMuch = {
  type: 'COUNT_IN_WINDOW';
  window: number;
  actual_count: number;
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
  recent_sequence?: { raw: string; label: string; chip: string }[];
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

const DESCRIPTIVE = new Set(['brightness', 'source_balance', 'timbre', 'presence', 'breathiness', 'contact']);

function userLabel(raw: string): string {
  return stateLabelKo(raw);
}

function axisTitle(axis: string): string {
  return axisLabelKo(axis);
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
      history_count: 0,
      today,
      improved: [],
      changed: [],
      maintained: [],
      source: 'local',
      note: '몇 번 더 부르면 이전 기록과 비교해드릴게요.',
    };
  }

  const requestedN = opts?.recentN ?? 5;
  const recent = historical.slice(-requestedN);
  const actualWindow = recent.length;
  const older =
    historical.length > actualWindow
      ? historical.slice(-(actualWindow * 2), -actualWindow)
      : [];
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
      return {
        raw,
        label: userLabel(raw),
        chip: stateChipKo(raw),
      };
    });

    let howMuch: ProgressHowMuch | null = null;
    if (axis === 'register_connection' || axis === 'stability') {
      const target = axis === 'register_connection' ? 'CONNECTED' : 'STABLE';
      const recentCount = labels.filter((l) => l === target).length;
      const prevLabels = older.map((s) => s.canonical[axis]).filter(Boolean) as string[];
      const prevCount = prevLabels.filter((l) => l === target).length;
      howMuch = {
        type: 'COUNT_IN_WINDOW',
        window: actualWindow,
        actual_count: actualWindow,
        label: '안정적으로 나타난 기록',
        previous_count: older.length ? prevCount : recentCount,
        recent_count: recentCount,
        current_counts_as_hit: currentRaw === target,
        summary: howMuchStableSummary(actualWindow, recentCount, requestedN),
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
        headline: '목표 방향으로 좋아지고 있어요',
        detail:
          axis === 'register_connection'
            ? '이전보다 성구가 자연스럽게 이어지는 쪽으로 나타났어요.'
            : '목표 방향과 맞는 변화예요.',
        why_improvement:
          axis === 'register_connection'
            ? '현재 목표인 성구 연결 안정화 방향과 일치하는 변화예요.'
            : '등록된 목표 방향과 일치해요.',
      });
    } else if (unchanged) {
      maintained.push({
        ...base,
        kind: 'MAINTAINED',
        headline: '잘 유지하고 있어요',
        detail: buildAxisMaintainedCopy(axis, currentRaw),
      });
    } else if (improvement === false) {
      changed.push({
        ...base,
        kind: 'NEEDS_PRACTICE',
        headline: '조금 더 연습할 부분',
        detail: '최근보다 목표와 멀어진 편이에요.',
      });
    } else {
      changed.push({
        ...base,
        kind: 'CHANGED',
        headline: '달라진 부분',
        detail: buildAxisChangeCopy(axis, modal, currentRaw),
      });
    }
  }

  return {
    status: historical.length <= 2 ? 'LIMITED_HISTORY' : 'AVAILABLE',
    insight_available: true,
    history_count: historical.length,
    goal_aware: goalRegister,
    today,
    // Free Result: max 1 per bucket (salience)
    improved: improved.slice(0, 1),
    changed: changed.slice(0, 1),
    maintained: maintained.slice(0, 1),
    source: 'local',
    note: historical.length === 1
      ? undefined
      : undefined,
  };
}

export { recentWindowLabel, howMuchStableSummary };
