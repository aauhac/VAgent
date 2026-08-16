import type { UserVocalGoal } from './goalProgress';
import { USER_GOAL_OPTIONS } from './goalProgress';

const KEY = 'vagent_vocal_goals_v1';

type Store = { goals: UserVocalGoal[] };

function read(): Store {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '{"goals":[]}') as Store;
  } catch {
    return { goals: [] };
  }
}

function write(store: Store) {
  localStorage.setItem(KEY, JSON.stringify(store));
}

export function listLocalGoals(): UserVocalGoal[] {
  return read().goals;
}

export function getLocalActiveGoal(): UserVocalGoal | null {
  const goals = listLocalGoals();
  for (let i = goals.length - 1; i >= 0; i -= 1) {
    if (goals[i].status === 'ACTIVE') return goals[i];
  }
  return null;
}

export function setLocalActiveGoal(input: {
  focus: string;
  label?: string;
  source?: string;
  target?: string | null;
  style_id?: string | null;
}): UserVocalGoal {
  const opt = USER_GOAL_OPTIONS.find((o) => o.focus === input.focus);
  const now = new Date().toISOString();
  const store = read();
  for (const g of store.goals) {
    if (g.status === 'ACTIVE') {
      g.status = 'REPLACED';
      (g as any).ended_at = now;
    }
  }
  const row: UserVocalGoal = {
    id: `local_${Date.now()}`,
    goal_focus: input.focus,
    goal_label: input.label || opt?.label || input.focus,
    source: input.source || 'USER_SELECTED',
    status: 'ACTIVE',
    axis: opt?.axis,
    target: input.target ?? opt?.target ?? null,
    style_id: input.style_id ?? opt?.style_id ?? null,
    kind: opt?.kind,
    wording: opt?.kind === 'STYLE' ? 'STYLE_DIRECTION' : undefined,
    started_at: now,
  };
  store.goals.push(row);
  write(store);
  return row;
}

export function completeLocalActiveGoal(): UserVocalGoal | null {
  const store = read();
  const now = new Date().toISOString();
  let active: UserVocalGoal | null = null;
  for (const g of store.goals) {
    if (g.status === 'ACTIVE') {
      g.status = 'COMPLETED';
      (g as any).ended_at = now;
      active = g;
    }
  }
  write(store);
  return active;
}

export function listLocalGoalHistory(): UserVocalGoal[] {
  return listLocalGoals().filter((g) => g.status !== 'ACTIVE');
}
