import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ensureDiagnosticPlan,
  getDiagnosticProtocol,
  getDiagnosticSession,
  skipControlledRecordings,
  skipDiagnosticTask,
  uploadDiagnosticTask,
  waitForDiagnosticCompletion,
} from '../api/client';
import AudioReadyPanel from '../components/ui/AudioReadyPanel';
import {
  classifyTaskPageState,
  resolveTaskMeta,
  taskProgressLabel,
} from '../lib/diagnosticTaskState';

type Phase = 'idle' | 'recording' | 'ready';

export default function DiagnosticTask() {
  const { sessionId, taskId } = useParams();
  const nav = useNavigate();
  const [protocol, setProtocol] = useState<any>(null);
  const [session, setSession] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sessionLoaded, setSessionLoaded] = useState(false);
  const [protocolLoaded, setProtocolLoaded] = useState(false);
  const [phase, setPhase] = useState<Phase>('idle');
  const [seconds, setSeconds] = useState(0);
  const [levels, setLevels] = useState<number[]>(Array(20).fill(4));
  const [previewLevels, setPreviewLevels] = useState<number[]>([]);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewDuration, setPreviewDuration] = useState<number | null>(null);
  const [blobMeta, setBlobMeta] = useState<{ blob: Blob; ext: string } | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmSkip, setConfirmSkip] = useState(false);
  const [confirmSkipRest, setConfirmSkipRest] = useState(false);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const secondsRef = useRef(0);
  const stoppingRef = useRef(false);
  const levelSnapRef = useRef<number[]>([]);

  async function loadPlan(opts?: { replan?: boolean }) {
    if (!sessionId) {
      setLoadError('정밀 진단 세션 정보가 없어요.');
      setLoading(false);
      setSessionLoaded(true);
      setProtocolLoaded(true);
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const [proto, sess0] = await Promise.all([
        getDiagnosticProtocol(),
        getDiagnosticSession(sessionId),
      ]);
      setProtocol(proto);
      setProtocolLoaded(true);

      let sess = sess0;
      const selected = sess?.selected_tasks || [];
      const diagStatus = (sess?.diagnostic_status || '').toUpperCase();
      if (
        selected.length === 0
        && diagStatus !== 'SAFETY_LIMITED'
        && (opts?.replan || !!sess?.diagnostic_mode)
      ) {
        try {
          sess = await ensureDiagnosticPlan(sessionId);
        } catch {
          /* keep sess0; empty handled below */
        }
      } else if (opts?.replan) {
        try {
          sess = await ensureDiagnosticPlan(sessionId);
        } catch {
          /* keep sess0 */
        }
      }

      // Resume unfinished task if URL task is already passed/skipped / missing
      const next = sess?.next_task_id;
      const order: string[] = sess?.selected_tasks || [];
      if (sess?.status === 'READY_FOR_ANALYSIS' && !next) {
        setBusy(true);
        try {
          await waitForDiagnosticCompletion(sessionId, { triggerAnalyze: true });
          nav(`/diagnostic/${sessionId}/report`, { replace: true });
        } catch (e: any) {
          setLoadError(e?.message || '결과 분석에 실패했어요.');
          setBusy(false);
        }
        setSession(sess);
        setSessionLoaded(true);
        setLoading(false);
        return;
      }
      if (next && taskId && next !== taskId && order.includes(taskId)) {
        const st = sess?.tasks?.[taskId];
        if (st?.passed || st?.skipped || st?.safety_blocked) {
          nav(`/diagnostic/${sessionId}/task/${next}`, { replace: true });
          setSession(sess);
          setSessionLoaded(true);
          setLoading(false);
          return;
        }
      }
      if ((!taskId || !order.includes(taskId)) && next) {
        nav(`/diagnostic/${sessionId}/task/${next}`, { replace: true });
      }
      if ((!taskId || !order.includes(taskId)) && !next && sess?.status === 'READY_FOR_ANALYSIS') {
        setBusy(true);
        try {
          await waitForDiagnosticCompletion(sessionId, { triggerAnalyze: true });
          nav(`/diagnostic/${sessionId}/report`, { replace: true });
        } catch (e: any) {
          setLoadError(e?.message || '결과 분석에 실패했어요.');
          setBusy(false);
        }
      }

      setSession(sess);
      setSessionLoaded(true);
      setLoading(false);
    } catch (e: any) {
      const code = String(e?.message || '');
      if (code === 'SESSION_NOT_FOUND') {
        setLoadError('정밀 진단 세션을 찾지 못했어요.');
      } else if (code === 'SESSION_FORBIDDEN') {
        setLoadError('이 정밀 진단에 접근할 수 없어요.');
      } else {
        setLoadError('추가 녹음 계획을 불러오지 못했어요. 다시 시도해주세요.');
      }
      setSessionLoaded(true);
      setProtocolLoaded(true);
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadPlan();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, taskId]);

  function cleanup() {
    if (timerRef.current != null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    try {
      mediaRef.current?.stream.getTracks().forEach((t) => t.stop());
    } catch {
      /* ignore */
    }
    mediaRef.current = null;
    if (ctxRef.current && ctxRef.current.state !== 'closed') {
      void ctxRef.current.close();
    }
    ctxRef.current = null;
  }

  function resetTaskState() {
    cleanup();
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    stoppingRef.current = false;
    setPhase('idle');
    setBusy(false);
    setSeconds(0);
    secondsRef.current = 0;
    setMsg(null);
    setLevels(Array(20).fill(4));
    setPreviewLevels([]);
    setPreviewUrl(null);
    setPreviewDuration(null);
    setBlobMeta(null);
    chunksRef.current = [];
  }

  useEffect(() => {
    resetTaskState();
    return () => cleanup();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, taskId]);

  const pageState = classifyTaskPageState({
    loading,
    error: loadError,
    sessionLoaded,
    protocolLoaded,
    session,
    protocol,
    taskId,
  });

  const order: string[] = (session?.selected_tasks as string[]) || [];
  const task = resolveTaskMeta(taskId, session, protocol) as any;
  const idx = order.indexOf(taskId || '');
  const progressLabel = taskProgressLabel(order, taskId || '');
  const purpose = (task?.purpose_labels || []).join(' · ');
  const unresolvedLabels = session?.diagnostic_offer?.unresolved_labels || [];

  async function start() {
    if (busy || phase === 'recording' || stoppingRef.current) return;
    setMsg(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setBlobMeta(null);
    cleanup();
    chunksRef.current = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext();
      ctxRef.current = ctx;
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      src.connect(analyser);
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';
      const media = new MediaRecorder(stream, { mimeType: mime });
      mediaRef.current = media;
      media.ondataavailable = (ev) => {
        if (ev.data.size) chunksRef.current.push(ev.data);
      };
      media.start(200);
      setPhase('recording');
      secondsRef.current = 0;
      setSeconds(0);
      timerRef.current = window.setInterval(() => {
        secondsRef.current += 1;
        setSeconds(secondsRef.current);
      }, 1000);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        const bars = Array.from({ length: 20 }, (_, i) => {
          const v = data[Math.floor((i / 20) * data.length)] || 0;
          return Math.max(4, Math.round((v / 255) * 36));
        });
        levelSnapRef.current = bars;
        setLevels(bars);
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    } catch {
      setMsg('마이크 권한을 확인해 주세요.');
      cleanup();
    }
  }

  async function finishRecording() {
    if (stoppingRef.current || !mediaRef.current) return;
    stoppingRef.current = true;
    setBusy(true);
    const media = mediaRef.current;
    await new Promise<void>((resolve) => {
      media.onstop = () => resolve();
      try {
        media.stop();
      } catch {
        resolve();
      }
    });
    cleanup();
    const blob = new Blob(chunksRef.current, { type: media.mimeType || 'audio/webm' });
    const url = URL.createObjectURL(blob);
    setPreviewUrl(url);
    setPreviewLevels(levelSnapRef.current.length ? levelSnapRef.current : levels);
    setPreviewDuration(secondsRef.current);
    setBlobMeta({ blob, ext: 'webm' });
    setPhase('ready');
    setBusy(false);
    stoppingRef.current = false;
  }

  async function submitReady() {
    if (!sessionId || !taskId || !blobMeta) return;
    setBusy(true);
    setMsg(null);
    try {
      const res = await uploadDiagnosticTask(
        sessionId,
        taskId,
        blobMeta.blob,
        `task.${blobMeta.ext}`,
      );
      if (!res.attempt?.passed) {
        setMsg(res.attempt?.quality?.user_message || '녹음 품질이 부족해요. 다시 녹음해 주세요.');
        setBusy(false);
        setPhase('idle');
        return;
      }
      const nextOrder = (res.session?.selected_tasks as string[]) || order;
      const nextId = res.session?.next_task_id || (() => {
        const curIdx = nextOrder.indexOf(taskId);
        return curIdx >= 0 ? nextOrder[curIdx + 1] : undefined;
      })();
      setBusy(false);
      if (nextId) {
        nav(`/diagnostic/${sessionId}/task/${nextId}`);
      } else {
        setMsg('분석 중…');
        setBusy(true);
        await waitForDiagnosticCompletion(sessionId!, { triggerAnalyze: true });
        setBusy(false);
        nav(`/diagnostic/${sessionId}/report`);
      }
    } catch (e: any) {
      setMsg(e?.message || '업로드 실패');
      setBusy(false);
    }
  }

  function reRecord() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setBlobMeta(null);
    setPreviewDuration(null);
    setPhase('idle');
    setMsg(null);
  }

  async function goAfterSkip(sess: any) {
    const next = sess?.next_task_id;
    if (next) {
      nav(`/diagnostic/${sessionId}/task/${next}`);
      return;
    }
    setMsg('분석 중…');
    setBusy(true);
    await waitForDiagnosticCompletion(sessionId!, { triggerAnalyze: true });
    setBusy(false);
    nav(`/diagnostic/${sessionId}/report`);
  }

  async function onSkipThisTask() {
    if (!sessionId || !taskId) return;
    setBusy(true);
    setMsg(null);
    try {
      const sess = await skipDiagnosticTask(sessionId, taskId);
      setConfirmSkip(false);
      await goAfterSkip(sess);
    } catch (e: any) {
      setMsg(e?.message || '건너뛰기에 실패했어요.');
      setBusy(false);
    }
  }

  async function onSkipRemaining() {
    if (!sessionId) return;
    setBusy(true);
    setMsg(null);
    try {
      await skipControlledRecordings(sessionId, { remainingOnly: true });
      setConfirmSkipRest(false);
      setMsg('분석 중…');
      await waitForDiagnosticCompletion(sessionId, { triggerAnalyze: true });
      nav(`/diagnostic/${sessionId}/report`);
    } catch (e: any) {
      setMsg(e?.message || '결과로 이어가지 못했어요.');
      setBusy(false);
    }
  }

  if (pageState === 'loading') {
    return (
      <main>
        <p className="muted">Task 불러오는 중…</p>
      </main>
    );
  }

  if (pageState === 'error') {
    return (
      <main>
        <h1 className="brand" style={{ fontSize: '1.4rem' }}>정밀 발성 진단</h1>
        <p className="fail">{loadError}</p>
        <button className="btn" type="button" onClick={() => void loadPlan({ replan: true })}>
          다시 시도
        </button>
      </main>
    );
  }

  if (pageState === 'safety-limited') {
    return (
      <main>
        <h1 className="brand" style={{ fontSize: '1.4rem' }}>안전상 추가 녹음을 진행하지 않아요</h1>
        <p className="lead">
          현재 불편감이 있어 강한 고음·큰 소리 검사는 제한했어요.
          지금까지의 분석으로 리포트를 이어갈 수 있어요.
        </p>
        <button
          className="btn"
          type="button"
          disabled={busy}
          onClick={async () => {
            if (!sessionId) return;
            setBusy(true);
            try {
              await waitForDiagnosticCompletion(sessionId, { triggerAnalyze: true });
              nav(`/diagnostic/${sessionId}/report`);
            } catch (e: any) {
              setLoadError(e?.message || '리포트를 만들지 못했어요.');
              setBusy(false);
            }
          }}
        >
          리포트 보기
        </button>
      </main>
    );
  }

  if (pageState === 'loaded-empty' || pageState === 'loaded-missing-task') {
    return (
      <main>
        <h1 className="brand" style={{ fontSize: '1.4rem' }}>정밀 발성 진단</h1>
        <p className="fail">
          {pageState === 'loaded-missing-task'
            ? '이 추가 녹음 안내를 불러오지 못했어요.'
            : '추가 녹음 계획을 불러오지 못했어요. 다시 시도해주세요.'}
        </p>
        <button className="btn" type="button" onClick={() => void loadPlan({ replan: true })}>
          다시 불러오기
        </button>
        {session?.source_analysis_id ? (
          <p className="muted" style={{ marginTop: 12 }}>
            <Link to={`/result/${session.source_analysis_id}/detail`}>상세 리포트로 돌아가기</Link>
          </p>
        ) : null}
      </main>
    );
  }

  return (
    <main>
      <p className="page-kicker">정밀 진단 · {progressLabel}</p>
      {unresolvedLabels.length > 0 && (
        <p className="muted" style={{ marginTop: 4 }}>이번에 확인할 항목 · {unresolvedLabels.join(' · ')}</p>
      )}
      <h1 className="brand" style={{ fontSize: '1.5rem', marginTop: 8 }}>{task.title}</h1>
      <p className="lead">{task.why}</p>
      {purpose && (
        <p className="body-text muted" style={{ marginBottom: 12 }}>이 녹음으로 확인하는 것 · {purpose}</p>
      )}
      <div className="panel">
        <p className="body-text" style={{ marginTop: 0 }}>{task.instruction}</p>
        <p className="muted">잘하려고 하지 않아도 됩니다. 평소처럼 편하게 수행하면 됩니다.</p>

        {phase === 'idle' && (
          <>
            <button className="btn" style={{ width: '100%', marginTop: 12 }} onClick={start} disabled={busy}>
              녹음 시작
            </button>
            {!confirmSkip ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => setConfirmSkip(true)}
                style={{
                  display: 'block',
                  width: '100%',
                  marginTop: 12,
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--muted, #888)',
                  textDecoration: 'underline',
                  cursor: 'pointer',
                  fontSize: '0.92rem',
                }}
              >
                이 과제 건너뛰기
              </button>
            ) : (
              <div style={{ marginTop: 12 }}>
                <p className="muted" style={{ fontSize: '0.9rem', lineHeight: 1.45 }}>
                  이 과제를 건너뛰면 관련 항목의 판단 근거가 줄어들 수 있어요.
                </p>
                <button className="btn" type="button" disabled={busy} onClick={() => setConfirmSkip(false)} style={{ width: '100%', marginTop: 8 }}>
                  계속 녹음하기
                </button>
                <button className="btn secondary" type="button" disabled={busy} onClick={() => void onSkipThisTask()} style={{ width: '100%', marginTop: 8 }}>
                  이 과제 건너뛰기
                </button>
              </div>
            )}
            {!confirmSkipRest ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => setConfirmSkipRest(true)}
                style={{
                  display: 'block',
                  width: '100%',
                  marginTop: 10,
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--muted, #aaa)',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                }}
              >
                남은 과제 없이 결과 보기
              </button>
            ) : (
              <div style={{ marginTop: 10 }}>
                <p className="muted" style={{ fontSize: '0.88rem' }}>
                  남은 과제를 건너뛰고 지금까지의 결과로 분석할까요?
                </p>
                <button className="btn secondary" type="button" disabled={busy} onClick={() => void onSkipRemaining()} style={{ width: '100%', marginTop: 8 }}>
                  남은 과제 없이 계속
                </button>
                <button type="button" disabled={busy} onClick={() => setConfirmSkipRest(false)} style={{ width: '100%', marginTop: 6, background: 'transparent', border: 'none', color: 'var(--muted)', textDecoration: 'underline' }}>
                  취소
                </button>
              </div>
            )}
          </>
        )}

        {phase === 'recording' && (
          <>
            <div className="record-timer" style={{ marginTop: 12 }}>
              {String(Math.floor(seconds / 60)).padStart(2, '0')}:{String(seconds % 60).padStart(2, '0')}
            </div>
            <p className="record-status">녹음 중</p>
            <div className="level-bars">
              {levels.map((h, i) => <i key={i} style={{ height: h }} />)}
            </div>
            <button className="btn secondary" style={{ width: '100%' }} onClick={finishRecording} disabled={busy}>
              녹음 종료
            </button>
          </>
        )}

        {phase === 'ready' && previewUrl && (
          <div style={{ marginTop: 12 }}>
            <AudioReadyPanel
              src={previewUrl}
              title="과제 녹음 완료"
              subtitle="들어본 뒤 다음 단계로 가거나 다시 녹음할 수 있어요"
              levels={previewLevels}
              durationSec={previewDuration}
              onClear={reRecord}
              clearLabel="다시 녹음"
              onAnalyze={submitReady}
              analyzeLabel={idx >= 0 && idx < order.length - 1 ? '다음 단계' : '제출하고 결과 보기'}
              analyzing={busy}
            />
          </div>
        )}

        {msg && <p className="muted" style={{ marginTop: 12 }}>{msg}</p>}
      </div>
    </main>
  );
}
