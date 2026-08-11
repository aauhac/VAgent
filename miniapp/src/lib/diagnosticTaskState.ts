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
