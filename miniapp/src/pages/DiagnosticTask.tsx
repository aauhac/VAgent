import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  analyzeDiagnosticSession,
  getDiagnosticProtocol,
  getDiagnosticSession,
  uploadDiagnosticTask,
} from '../api/client';
import AudioReadyPanel from '../components/ui/AudioReadyPanel';

const FALLBACK_ORDER = ['sustain_a', 'sustain_i', 'siren', 'dynamic_swell'];

type Phase = 'idle' | 'recording' | 'ready';

export default function DiagnosticTask() {
  const { sessionId, taskId } = useParams();
  const nav = useNavigate();
  const [protocol, setProtocol] = useState<any>(null);
  const [session, setSession] = useState<any>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [seconds, setSeconds] = useState(0);
  const [levels, setLevels] = useState<number[]>(Array(20).fill(4));
  const [previewLevels, setPreviewLevels] = useState<number[]>([]);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewDuration, setPreviewDuration] = useState<number | null>(null);
  const [blobMeta, setBlobMeta] = useState<{ blob: Blob; ext: string } | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const secondsRef = useRef(0);
  const stoppingRef = useRef(false);
  const levelSnapRef = useRef<number[]>([]);

  useEffect(() => {
    getDiagnosticProtocol().then(setProtocol).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    getDiagnosticSession(sessionId).then(setSession).catch(() => undefined);
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

  const order: string[] =
    (session?.selected_tasks && session.selected_tasks.length
      ? session.selected_tasks
      : FALLBACK_ORDER) as string[];
  const task =
    (session?.task_plan || []).find((t: any) => t.task_id === taskId) ||
    (protocol?.tasks || []).find((t: any) => t.task_id === taskId);
  const idx = order.indexOf(taskId || '');
  const progressLabel = idx >= 0 ? `${idx + 1} / ${order.length}` : `— / ${order.length}`;
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
        : MediaRecorder.isTypeSupported('audio/mp4')
          ? 'audio/mp4'
          : undefined;
      const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size) chunksRef.current.push(e.data);
      };
      rec.start(200);
      mediaRef.current = rec;
      setPhase('recording');
      setBusy(false);
      setSeconds(0);
      secondsRef.current = 0;
      timerRef.current = window.setInterval(() => {
        secondsRef.current += 1;
        setSeconds(secondsRef.current);
      }, 1000);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        const step = Math.floor(data.length / 20) || 1;
        const next = Array.from({ length: 20 }, (_, i) =>
          Math.max(4, Math.round(((data[i * step] || 0) / 255) * 56)),
        );
        setLevels(next);
        levelSnapRef.current = next;
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();
    } catch (e: any) {
      setPhase('idle');
      setBusy(false);
      cleanup();
      setMsg(e?.message || '마이크 권한을 확인해 주세요.');
    }
  }

  async function finishRecording() {
    const rec = mediaRef.current;
    if (!rec || !task) return;
    if (secondsRef.current < task.min_sec) {
      setMsg(`최소 ${task.min_sec}초 이상 녹음해 주세요.`);
      return;
    }
    const recordedSec = secondsRef.current;
    await new Promise<void>((resolve) => {
      rec.onstop = () => resolve();
      try {
        rec.stop();
      } catch {
        resolve();
      }
    });
    const mime = rec.mimeType || 'audio/webm';
    const ext = mime.includes('mp4') ? 'mp4' : 'webm';
    const snap = [...levelSnapRef.current];
    cleanup();
    const blob = new Blob(chunksRef.current, { type: mime });
    chunksRef.current = [];
    const url = URL.createObjectURL(blob);
    setPreviewUrl(url);
    setPreviewDuration(recordedSec);
    setPreviewLevels(snap.length ? snap : levels);
    setBlobMeta({ blob, ext });
    setPhase('ready');
    setMsg(null);
  }

  async function submitReady() {
    if (!blobMeta || !sessionId || !taskId) return;
    setBusy(true);
    setMsg(null);
    try {
      const res = await uploadDiagnosticTask(sessionId, taskId, blobMeta.blob, `task.${blobMeta.ext}`);
      if (!res.attempt?.passed) {
        setMsg(res.attempt?.quality?.user_message || '다시 녹음해 주세요.');
        setBusy(false);
        return;
      }
      const nextOrder = (res.session?.selected_tasks as string[]) || order;
      const curIdx = nextOrder.indexOf(taskId);
      const nextId = curIdx >= 0 ? nextOrder[curIdx + 1] : undefined;
      setBusy(false);
      if (nextId) {
        nav(`/diagnostic/${sessionId}/task/${nextId}`);
      } else {
        setMsg('분석 중…');
        setBusy(true);
        await analyzeDiagnosticSession(sessionId);
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

  if (!task) {
    return <main><p className="muted">Task 불러오는 중…</p></main>;
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
          <button className="btn" style={{ width: '100%', marginTop: 12 }} onClick={start} disabled={busy}>
            녹음 시작
          </button>
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
