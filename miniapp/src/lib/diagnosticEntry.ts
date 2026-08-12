/** Diagnostic flow entry helpers — URL sessionId is SoT, not localStorage. */

export type DiagnosticSessionLike = {
  session_id?: string;
  status?: string;
  user_concerns?: unknown[] | null;
  diagnostic_mode?: string | null;
  next_task_id?: string | null;
  selected_tasks?: string[] | null;
};

/** Next in-flow route for an existing diagnostic session. Never returns "/". */
export function nextDiagnosticRoute(session: DiagnosticSessionLike | null | undefined): string | null {
  const sid = session?.session_id;
  if (!sid) return null;
  const status = (session.status || '').toUpperCase();
  const mode = session.diagnostic_mode;
  const concerns = session.user_concerns;
  const hasConcerns = Array.isArray(concerns) && concerns.length > 0;
  const intakeDone = !!mode || hasConcerns;

  if (status === 'COMPLETED') {
    return `/diagnostic/${sid}/report`;
  }
  if (status === 'READY_FOR_ANALYSIS' || status === 'ANALYZING') {
    return `/diagnostic/${sid}/report`;
  }
  if (status === 'TASKS_IN_PROGRESS') {
    const next = session.next_task_id || (session.selected_tasks || [])[0];
    if (next) return `/diagnostic/${sid}/task/${next}`;
    return `/diagnostic/${sid}/report`;
  }
  if (!intakeDone) {
    return `/diagnostic/${sid}/concerns`;
  }
  if (status === 'PAID' || status === 'SAFETY_CHECK' || status === 'CREATED') {
    return `/diagnostic/${sid}/safety`;
  }
  return `/diagnostic/${sid}/concerns`;
}

export function concernIntakePath(sessionId: string): string {
  return `/diagnostic/${sessionId}/concerns`;
}

export function premiumEntryPath(analysisId: string, productId: string): string {
  return `/premium?analysis=${encodeURIComponent(analysisId)}&product=${encodeURIComponent(productId)}`;
}
