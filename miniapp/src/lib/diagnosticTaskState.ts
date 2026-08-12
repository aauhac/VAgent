/** Pure diagnostic task recorder state helpers (testable without DOM). */

export type RecorderUiState = {
  recording: boolean;
  busy: boolean;
  seconds: number;
  msg: string | null;
};

export type TaskPageLoadState =
  | 'loading'
  | 'error'
  | 'safety-limited'
  | 'loaded-empty'
  | 'loaded-missing-task'
  | 'loaded-with-tasks';

export function initialRecorderUiState(): RecorderUiState {
  return { recording: false, busy: false, seconds: 0, msg: null };
}

/** Called whenever sessionId/taskId changes — must enable a fresh start. */
export function resetRecorderUiState(): RecorderUiState {
  return initialRecorderUiState();
}

export function canStartRecording(state: RecorderUiState, stopping: boolean): boolean {
  return !state.busy && !state.recording && !stopping;
}

export function afterQualityFail(state: RecorderUiState): RecorderUiState {
  return { ...state, busy: false, recording: false, seconds: 0, msg: state.msg };
}

/** Progress label from adaptive selected_tasks (not a fixed 4-task battery). */
export function taskProgressLabel(selectedTasks: string[], taskId: string): string {
  const order = selectedTasks.length ? selectedTasks : [];
  const idx = order.indexOf(taskId);
  if (!order.length) return '0 / 0';
  if (idx < 0) return `— / ${order.length}`;
  return `${idx + 1} / ${order.length}`;
}

export function nextTaskId(selectedTasks: string[], taskId: string): string | null {
  const idx = selectedTasks.indexOf(taskId);
  if (idx < 0) return null;
  return selectedTasks[idx + 1] || null;
}

export function resolveTaskMeta(
  taskId: string | undefined,
  session: { task_plan?: Array<{ task_id: string }> | null } | null | undefined,
  protocol: { tasks?: Array<{ task_id: string }> | null } | null | undefined,
): { task_id: string } | null {
  if (!taskId) return null;
  const fromPlan = (session?.task_plan || []).find((t) => t.task_id === taskId);
  if (fromPlan) return fromPlan;
  const fromProto = (protocol?.tasks || []).find((t) => t.task_id === taskId);
  return fromProto || null;
}

/**
 * Separate loading from empty/error. Never treat tasks.length===0 as loading
 * after the request finished.
 */
export function classifyTaskPageState(opts: {
  loading: boolean;
  error: string | null;
  sessionLoaded: boolean;
  protocolLoaded: boolean;
  session: {
    selected_tasks?: string[] | null;
    diagnostic_status?: string | null;
    status?: string | null;
    task_plan?: Array<{ task_id: string }> | null;
  } | null;
  protocol: { tasks?: Array<{ task_id: string }> | null } | null;
  taskId?: string;
}): TaskPageLoadState {
  if (opts.loading) return 'loading';
  if (opts.error) return 'error';
  if (!opts.sessionLoaded || !opts.protocolLoaded) return 'loading';

  const status = (opts.session?.diagnostic_status || '').toUpperCase();
  const selected = opts.session?.selected_tasks || [];
  if (status === 'SAFETY_LIMITED' && selected.length === 0) return 'safety-limited';
  if (selected.length === 0) return 'loaded-empty';

  const meta = resolveTaskMeta(opts.taskId, opts.session, opts.protocol);
  if (!meta) return 'loaded-missing-task';
  return 'loaded-with-tasks';
}
