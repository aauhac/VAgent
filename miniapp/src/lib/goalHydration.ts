/**
 * Explicit goal load state — loading is never treated as "no goal".
 */
import type { UserVocalGoal } from './goalProgress';
import { getLocalActiveGoal } from './localGoalStore';
import { getVocalGoals } from '../api/client';

export type GoalLoadState =
  | { status: 'loading' }
  | { status: 'none' }
  | { status: 'ready'; goal: UserVocalGoal };

export function goalFromLocalSync(): GoalLoadState {
  const g = getLocalActiveGoal();
  return g ? { status: 'ready', goal: g } : { status: 'loading' };
}

/** Resolve active goal: prefer local immediately when present; confirm via server. */
export async function resolveActiveGoalLoadState(): Promise<GoalLoadState> {
  const local = getLocalActiveGoal();
  if (local) {
    // Still try server in background consumer; return ready now to avoid flash
    return { status: 'ready', goal: local };
  }
  try {
    const remote = await getVocalGoals();
    const active = remote?.active;
    if (active && (active.status === 'ACTIVE' || active.goal_focus || active.focus)) {
      const goal: UserVocalGoal = {
        id: String(active.id || `remote_${Date.now()}`),
        goal_focus: String(active.goal_focus || active.focus || ''),
        goal_label: String(active.goal_label || active.label || active.goal_focus || ''),
        source: String(active.source || 'USER_SELECTED'),
        status: 'ACTIVE',
        axis: active.axis,
        target: active.target ?? null,
        style_id: active.style_id ?? null,
        kind: active.kind,
        started_at: active.started_at || new Date().toISOString(),
      };
      if (goal.goal_focus) return { status: 'ready', goal };
    }
  } catch {
    /* offline */
  }
  return { status: 'none' };
}
