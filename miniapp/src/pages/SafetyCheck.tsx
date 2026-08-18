import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getDiagnosticSession, submitSafety, waitForDiagnosticCompletion } from '../api/client';
import { recordingChoicePath, resolveDiagnosticRoute } from '../lib/diagnosticEntry';

const QUESTIONS = [
  { id: 'pain_on_phonation', label: '소리를 낼 때 통증이 있어요' },
  { id: 'severe_discomfort_after', label: '발성 후 심한 불편감·피로감이 있어요' },
  { id: 'sudden_voice_change', label: '갑자기 생긴 뚜렷한 음성 변화' },
  { id: 'persistent_severe_hoarseness', label: '오랫동안 지속되는 심한 쉰 목소리' },
  { id: 'breathing_difficulty', label: '호흡이 어려운 증상' },
];

export default function SafetyCheck() {
  const { sessionId } = useParams();
  const nav = useNavigate();
  const [answers, setAnswers] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);
  const [phase, setPhase] = useState<'form' | 'analyzing'>('form');

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const session = await getDiagnosticSession(sessionId);
        if (cancelled) return;
        const status = String(session?.status || '').toUpperCase();
        // Stale Safety UI: server already past safety → recover without Home
        if (
          status === 'RECORDING_CHOICE'
          || status === 'TASKS_IN_PROGRESS'
          || status === 'READY_FOR_ANALYSIS'
          || status === 'ANALYZING'
          || status === 'COMPLETED'
          || status === 'FAILED'
        ) {
          const route = resolveDiagnosticRoute({ ...session, session_id: sessionId });
          if (route && route !== `/diagnostic/${sessionId}/safety`) {
            nav(route, { replace: true });
            return;
          }
        }
      } catch {
        /* stay on safety; user can still try */
      } finally {
        if (!cancelled) setBooting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, nav]);

  async function recoverFromServer() {
    if (!sessionId) return false;
    try {
      const session = await getDiagnosticSession(sessionId);
      const route = resolveDiagnosticRoute({ ...session, session_id: sessionId });
      if (route && route !== `/diagnostic/${sessionId}/safety`) {
        setError('진단 진행 상태를 다시 확인했어요.');
        nav(route, { replace: true });
        return true;
      }
    } catch {
      /* keep error on page */
    }
    return false;
  }

  async function goSafetyLimitedResult() {
    if (!sessionId) return;
    setPhase('analyzing');
    setBusy(true);
    try {
      await waitForDiagnosticCompletion(sessionId, { triggerAnalyze: true });
      nav(`/diagnostic/${sessionId}/report`, { replace: true });
    } catch (e: any) {
      setError(e?.message || '안전 제한 결과를 준비하지 못했어요. 여기서 다시 시도할 수 있어요.');
      setPhase('form');
      setBusy(false);
    }
  }

  async function next() {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      const payload: Record<string, boolean> = {};
      QUESTIONS.forEach((q) => {
        payload[q.id] = !!answers[q.id];
      });
      const session = await submitSafety(sessionId, payload);
      const selected: string[] = session?.selected_tasks || [];
      const status = String(session?.status || '').toUpperCase();
      const diagStatus = String(session?.diagnostic_status || '').toUpperCase();
      const route = resolveDiagnosticRoute({ ...session, session_id: sessionId });

      if (typeof import.meta !== 'undefined' && (import.meta as any).env?.DEV) {
        // eslint-disable-next-line no-console
        console.info('[DIAG_FLOW]', {
          session: sessionId,
          action: 'submit_safety',
          after: status,
          diagnostic_status: diagStatus,
          selected,
          safety_flags: session?.safety_flags,
          route,
        });
      }

      // A/B: any remaining safe tasks → Recording Choice (never Home)
      if (status === 'RECORDING_CHOICE' || (selected.length > 0 && status !== 'READY_FOR_ANALYSIS')) {
        nav(recordingChoicePath(sessionId), { replace: true });
        return;
      }

      // C: SAFETY_LIMITED + zero tasks → analysis / safety-limited report (never Home)
      if (
        status === 'READY_FOR_ANALYSIS'
        || status === 'ANALYZING'
        || status === 'COMPLETED'
        || (diagStatus === 'SAFETY_LIMITED' && selected.length === 0)
      ) {
        await goSafetyLimitedResult();
        return;
      }

      if (route) {
        nav(route, { replace: true });
        return;
      }
      // Final in-flow fallback — still never Home
      nav(recordingChoicePath(sessionId), { replace: true });
    } catch (e: any) {
      const recovered = await recoverFromServer();
      if (!recovered) {
        setError(
          e?.message || '제출에 실패했어요. 홈으로 이동하지 않고 여기서 다시 시도할 수 있어요.',
        );
        setBusy(false);
      }
    }
  }

  if (booting) {
    return (
      <main>
        <p className="page-kicker">정밀 발성 진단</p>
        <p className="muted">안전 확인 준비 중…</p>
      </main>
    );
  }

  if (phase === 'analyzing') {
    return (
      <main>
        <p className="page-kicker">정밀 발성 진단</p>
        <p className="lead" style={{ marginTop: 10 }}>
          현재 통증이 있다고 답해 주셔서
          추가 발성 녹음은 진행하지 않아요.
          기존 노래에서 확인된 범위만 안내할게요.
        </p>
        <p className="muted" style={{ marginTop: 8 }}>
          통증이 있는 상태에서는 강한 고음이나 반복 발성을 시도하지 마세요.
        </p>
        <p className="muted">결과를 분석하고 있어요…</p>
        {error ? <p className="fail">{error}</p> : null}
      </main>
    );
  }

  return (
    <main>
      <p className="page-kicker">정밀 발성 진단</p>
      <h2 className="brand" style={{ fontSize: '1.35rem' }}>안전 확인</h2>
      <p className="lead">
        정밀 진단 전에 불편한 증상이 있는지만 확인해요.
        통증이 있으면 추가 녹음은 하지 않아요.
      </p>
      <div className="card">
        {QUESTIONS.map((q) => (
          <label key={q.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '10px 0', cursor: 'pointer' }}>
            <span>{q.label}</span>
            <input
              type="checkbox"
              checked={!!answers[q.id]}
              onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.checked }))}
            />
          </label>
        ))}
      </div>
      <p className="muted">
        해당 항목이 있으면 질병명을 추정하지 않고, 분석을 제한하며
        지속되면 전문가 평가를 고려해 달라는 안내만 드려요.
      </p>
      <button className="btn" disabled={busy} onClick={() => void next()}>다음</button>
      {error && <p className="fail">{error}</p>}
    </main>
  );
}
