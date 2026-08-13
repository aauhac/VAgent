/** Diagnostic flow entry helpers — URL sessionId is SoT, not localStorage. */

export type DiagnosticSessionLike = {
  session_id?: string;
  status?: string;
  user_concerns?: unknown[] | null;
  diagnostic_mode?: string | null;
  diagnostic_status?: string | null;
  next_task_id?: string | null;
  selected_tasks?: string[] | null;
  error?: string | null;
};

function diagLog(tag: string, payload: Record<string, unknown>) {
  try {
    if (typeof import.meta !== 'undefined' && (import.meta as any).env?.DEV) {
      // eslint-disable-next-line no-console
      console.info(`[DIAG_${tag}]`, payload);
    }
  } catch {
    /* ignore */
  }
}

/**
 * Canonical next in-flow route for an existing diagnostic session.
 * Never returns "/" — callers must keep the user in the diagnostic flow.
 */
export function resolveDiagnosticRoute(
  session: DiagnosticSessionLike | null | undefined,
): string | null {
  const sid = session?.session_id;
  if (!sid) return null;
  const status = (session.status || '').toUpperCase();
  const mode = session.diagnostic_mode;
  const concerns = session.user_concerns;
  const hasConcerns = Array.isArray(concerns) && concerns.length > 0;
  const intakeDone = !!mode || hasConcerns;
  const selected = session.selected_tasks || [];
  const diagStatus = String(session.diagnostic_status || '').toUpperCase();

  let route: string | null = null;

  if (status === 'FAILED') {
    route = `/diagnostic/${sid}/report`;
  } else if (status === 'COMPLETED') {
    route = `/diagnostic/${sid}/report`;
  } else if (status === 'READY_FOR_ANALYSIS' || status === 'ANALYZING') {
    route = `/diagnostic/${sid}/report`;
  } else if (status === 'TASKS_IN_PROGRESS') {
    const next = session.next_task_id || selected[0];
    route = next ? `/diagnostic/${sid}/task/${next}` : `/diagnostic/${sid}/report`;
  } else if (status === 'RECORDING_CHOICE') {
    route = `/diagnostic/${sid}/recordings`;
  } else if (status === 'SAFETY_CHECK') {
    route = `/diagnostic/${sid}/safety`;
  } else if (status === 'PAID') {
    route = intakeDone ? `/diagnostic/${sid}/safety` : `/diagnostic/${sid}/concerns`;
  } else if (status === 'CREATED') {
    route = `/diagnostic/${sid}/concerns`;
  } else if (!intakeDone) {
    route = `/diagnostic/${sid}/concerns`;
  } else if (diagStatus === 'SAFETY_LIMITED' && selected.length === 0) {
    route = `/diagnostic/${sid}/report`;
  } else {
    // Unknown but in-flow — prefer safety/recordings over Home
    route = `/diagnostic/${sid}/safety`;
  }

  diagLog('ROUTE', {
    session: sid,
    status,
    diagnostic_status: diagStatus,
    selected_count: selected.length,
    route,
  });
  return route;
}

/** @deprecated prefer resolveDiagnosticRoute */
export function nextDiagnosticRoute(
  session: DiagnosticSessionLike | null | undefined,
): string | null {
  return resolveDiagnosticRoute(session);
}

export function concernIntakePath(sessionId: string): string {
  return `/diagnostic/${sessionId}/concerns`;
}

export function premiumEntryPath(analysisId: string, productId: string): string {
  return `/premium?analysis=${encodeURIComponent(analysisId)}&product=${encodeURIComponent(productId)}`;
}

export function recordingChoicePath(sessionId: string): string {
  return `/diagnostic/${sessionId}/recordings`;
}
