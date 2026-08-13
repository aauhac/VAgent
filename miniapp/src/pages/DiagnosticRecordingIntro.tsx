import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  getDiagnosticSession,
  skipControlledRecordings,
  startControlledRecordings,
  waitForDiagnosticCompletion,
} from '../api/client';
import { resolveDiagnosticRoute } from '../lib/diagnosticEntry';

/**
 * Post-safety choice: start controlled recordings OR concern-only analysis.
 */
export default function DiagnosticRecordingIntro() {
  const { sessionId } = useParams();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmSkip, setConfirmSkip] = useState(false);
  const [planned, setPlanned] = useState(0);
  const [painNote, setPainNote] = useState(false);
  const [phase, setPhase] = useState<'choice' | 'analyzing'>('choice');

  useEffect(() => {
    if (!sessionId) return;
    getDiagnosticSession(sessionId)
      .then((s) => {
        const n = (s?.selected_tasks || []).length;
        setPlanned(n);
        setPainNote(Boolean(s?.safety_flag_pain) || (s?.safety_flags || []).length > 0);
        const status = String(s?.status || '').toUpperCase();
        const diagStatus = String(s?.diagnostic_status || '').toUpperCase();

        if (status === 'TASKS_IN_PROGRESS') {
          const first = s?.next_task_id || (s?.selected_tasks || [])[0];
          if (first) {
            nav(`/diagnostic/${sessionId}/task/${first}`, { replace: true });
            return;
          }
        }
        if (status === 'SAFETY_CHECK' || status === 'PAID' || status === 'CREATED') {
          const route = resolveDiagnosticRoute({ ...s, session_id: sessionId });
          if (route && !route.includes('/recordings')) {
            nav(route, { replace: true });
            return;
          }
        }
        if (status === 'READY_FOR_ANALYSIS' || status === 'COMPLETED' || status === 'ANALYZING') {
          const route = resolveDiagnosticRoute({ ...s, session_id: sessionId });
          if (route) nav(route, { replace: true });
          return;
        }
        if (diagStatus === 'SAFETY_LIMITED' && n === 0) {
          setPhase('analyzing');
          setBusy(true);
          waitForDiagnosticCompletion(sessionId, { triggerAnalyze: true })
            .then(() => nav(`/diagnostic/${sessionId}/report`, { replace: true }))
            .catch((e) => {
              setError(e?.message || '분석을 시작하지 못했어요.');
              setBusy(false);
              setPhase('choice');
            });
        }
      })
      .catch((e) => setError(e?.message || '세션을 불러오지 못했어요.'));
  }, [sessionId, nav]);

  async function startRecordings() {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      const s = await startControlledRecordings(sessionId);
      const first = s?.next_task_id || (s?.selected_tasks || [])[0];
      if (first) {
        nav(`/diagnostic/${sessionId}/task/${first}`);
        return;
      }
      setPhase('analyzing');
      await waitForDiagnosticCompletion(sessionId, { triggerAnalyze: true });
      nav(`/diagnostic/${sessionId}/report`);
    } catch (e: any) {
      setError(e?.message || '시작하지 못했어요. 홈으로 이동하지 않고 여기서 다시 시도할 수 있어요.');
      setBusy(false);
    }
  }

  async function skipAll() {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      await skipControlledRecordings(sessionId, { remainingOnly: true });
      setPhase('analyzing');
      await waitForDiagnosticCompletion(sessionId, { triggerAnalyze: true });
      nav(`/diagnostic/${sessionId}/report`);
    } catch (e: any) {
      setError(e?.message || '결과로 이어가지 못했어요. 홈으로 이동하지 않고 여기서 다시 시도할 수 있어요.');
      setBusy(false);
      setConfirmSkip(false);
      setPhase('choice');
    }
  }

  if (phase === 'analyzing') {
    return (
      <main>
        <h1 className="brand" style={{ fontSize: '1.5rem' }}>정밀 발성 진단</h1>
        <p className="lead" style={{ marginTop: 10 }}>
          안전을 위해 추가 녹음 없이
          현재 노래에서 확인된 범위를 중심으로 안내해요.
        </p>
        <p className="muted">결과를 분석하고 있어요…</p>
        {error ? <p className="fail">{error}</p> : null}
      </main>
    );
  }

  return (
    <main>
      <h1 className="brand" style={{ fontSize: '1.5rem' }}>정밀 발성 진단</h1>
      <p className="lead" style={{ marginTop: 10 }}>
        선택한 고민을 더 정확히 확인하기 위해
        몇 가지 짧은 발성 과제를 진행해요.
      </p>
      <p className="muted">약 2~3분 · {planned > 0 ? `${planned}개 과제` : '추가 과제'}</p>
      {painNote ? (
        <p className="body-text" style={{ marginTop: 8 }}>
          불편감을 고려해 강한 과제는 제외했어요.
        </p>
      ) : null}
      <p className="body-text muted" style={{ marginTop: 8 }}>
        고음 · 안정성 · 성구 연결 · 음색 변화 등을 확인할 수 있어요.
      </p>

      {!confirmSkip ? (
        <>
          <button className="btn" type="button" disabled={busy} onClick={() => void startRecordings()} style={{ width: '100%', marginTop: 20 }}>
            추가 녹음 시작
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => setConfirmSkip(true)}
            style={{
              display: 'block',
              width: '100%',
              marginTop: 14,
              background: 'transparent',
              border: 'none',
              color: 'var(--muted, #888)',
              textDecoration: 'underline',
              cursor: 'pointer',
              fontSize: '0.95rem',
            }}
          >
            추가 녹음 없이 결과 보기
          </button>
          <p className="muted" style={{ marginTop: 10, fontSize: '0.88rem', lineHeight: 1.45 }}>
            추가 녹음을 건너뛰면 일부 항목의 확인 범위와 분석 신뢰도가 낮아질 수 있어요.
          </p>
        </>
      ) : (
        <div className="panel" style={{ marginTop: 18 }}>
          <p className="body-text" style={{ fontWeight: 600, marginTop: 0 }}>
            추가 녹음 없이 계속할까요?
          </p>
          <p className="body-text muted" style={{ lineHeight: 1.5 }}>
            기존 노래와 선택한 고민을 바탕으로 결과를 알려드려요.
            추가 녹음으로 확인하는 고음·성구 연결·힘 변화 등의 정보는 제한될 수 있어요.
          </p>
          <button className="btn" type="button" disabled={busy} onClick={() => void startRecordings()} style={{ width: '100%', marginTop: 12 }}>
            추가 녹음하기
          </button>
          <button
            type="button"
            className="btn secondary"
            disabled={busy}
            onClick={() => void skipAll()}
            style={{ width: '100%', marginTop: 10 }}
          >
            추가 녹음 없이 계속
          </button>
        </div>
      )}
      {error && <p className="fail">{error}</p>}
    </main>
  );
}
