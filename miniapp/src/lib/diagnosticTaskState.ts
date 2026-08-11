/** Pure diagnostic task recorder state helpers (testable without DOM). */

export type RecorderUiState = {
  recording: boolean;
  busy: boolean;
  seconds: number;
  msg: string | null;
};

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
