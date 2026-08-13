/** Route contract: diagnostic resolver never returns Home. */
function resolveDiagnosticRoute(session) {
  const sid = session?.session_id;
  if (!sid) return null;
  const status = (session.status || '').toUpperCase();
  const mode = session.diagnostic_mode;
  const concerns = session.user_concerns;
  const hasConcerns = Array.isArray(concerns) && concerns.length > 0;
  const intakeDone = !!mode || hasConcerns;
  const selected = session.selected_tasks || [];
  const diagStatus = String(session.diagnostic_status || '').toUpperCase();

  if (status === 'FAILED' || status === 'COMPLETED') return `/diagnostic/${sid}/report`;
  if (status === 'READY_FOR_ANALYSIS' || status === 'ANALYZING') return `/diagnostic/${sid}/report`;
  if (status === 'TASKS_IN_PROGRESS') {
    const next = session.next_task_id || selected[0];
    return next ? `/diagnostic/${sid}/task/${next}` : `/diagnostic/${sid}/report`;
  }
  if (status === 'RECORDING_CHOICE') return `/diagnostic/${sid}/recordings`;
  if (status === 'SAFETY_CHECK') return `/diagnostic/${sid}/safety`;
  if (status === 'PAID') return intakeDone ? `/diagnostic/${sid}/safety` : `/diagnostic/${sid}/concerns`;
  if (status === 'CREATED') return `/diagnostic/${sid}/concerns`;
  if (!intakeDone) return `/diagnostic/${sid}/concerns`;
  if (diagStatus === 'SAFETY_LIMITED' && selected.length === 0) return `/diagnostic/${sid}/report`;
  return `/diagnostic/${sid}/safety`;
}

const sid = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const cases = [
  { status: 'SAFETY_CHECK', expectIncludes: '/safety', extra: { diagnostic_mode: 'CONCERN_FOCUSED' } },
  { status: 'RECORDING_CHOICE', expectIncludes: '/recordings' },
  { status: 'TASKS_IN_PROGRESS', expectIncludes: '/task/', extra: { next_task_id: 'sustain_a', selected_tasks: ['sustain_a'] } },
  { status: 'READY_FOR_ANALYSIS', expectIncludes: '/report' },
  { status: 'ANALYZING', expectIncludes: '/report' },
  { status: 'COMPLETED', expectIncludes: '/report' },
];

let failed = 0;
for (const c of cases) {
  const route = resolveDiagnosticRoute({ session_id: sid, status: c.status, ...(c.extra || {}) });
  if (!route || route === '/' || !route.includes(c.expectIncludes)) {
    failed += 1;
    console.error('FAIL', c.status, route);
  } else {
    console.log('PASS', c.status, '→', route);
  }
}
if (failed) process.exit(1);
console.log('ALL_ROUTE_CONTRACTS_PASS');
