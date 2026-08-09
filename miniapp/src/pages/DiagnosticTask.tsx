import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { analyzeDiagnosticSession, getDiagnosticProtocol, uploadDiagnosticTask } from '../api/client';

const ORDER = ['sustain_a', 'sustain_i', 'siren', 'dynamic_swell'];

export default function DiagnosticTask() {
  const { sessionId, taskId } = useParams();
  const nav = useNavigate();
  const [protocol, setProtocol] = useState<any>(null);
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [levels, setLevels] = useState<number[]>(Array(20).fill(4));
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const secondsRef = useRef(0);

  useEffect(() => {
    getDiagnosticProtocol().then(setProtocol).catch(() => undefined);
    return () => cleanup();
  }, []);

  const task = (protocol?.tasks || []).find((t: any) => t.task_id === taskId);
  const idx = ORDER.indexOf(taskId || '');
  const progressLabel = `${idx + 1} / ${ORDER.length}`;

  function cleanup() {
    if (timerRef.current) clearInterval(timerRef.current);
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    mediaRef.current?.stream.getTracks().forEach((t) => t.stop());
    if (ctxRef.current && ctxRef.current.state !== 'closed') void ctxRef.current.close();
    ctxRef.current = null;
  }

  async function start() {
    setMsg(null);
    cleanup();
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
    setRecording(true);
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
      setLevels(Array.from({ length: 20 }, (_, i) => Math.max(4, Math.round(((data[i * step] || 0) / 255) * 56))));
      rafRef.current = requestAnimationFrame(tick);
    };
    tick();
  }

  async function stopUpload() {
    const rec = mediaRef.current;
    if (!rec || !sessionId || !taskId || !task) return;
    if (secondsRef.current < task.min_sec) {
      setMsg(`최소 ${task.min_sec}초 이상 녹음해 주세요.`);
      return;
    }
    setBusy(true);
    await new Promise<void>((resolve) => {
      rec.onstop = () => resolve();
      rec.stop();
    });
    const mime = rec.mimeType || 'audio/webm';
    const ext = mime.includes('mp4') ? 'mp4' : 'webm';
    cleanup();
    setRecording(false);
    const blob = new Blob(chunksRef.current, { type: mime });
    try {
      const res = await uploadDiagnosticTask(sessionId, taskId, blob, `task.${ext}`);
      if (!res.attempt?.passed) {
        setMsg(res.attempt?.quality?.user_message || '다시 녹음해 주세요.');
        setBusy(false);
        return;
      }
      const nextId = ORDER[idx + 1];
      if (nextId) {
        nav(`/diagnostic/${sessionId}/task/${nextId}`);
      } else {
        setMsg('분석 중…');
        await analyzeDiagnosticSession(sessionId);
        nav(`/diagnostic/${sessionId}/report`);
      }
    } catch (e: any) {
      setMsg(e?.message || '업로드 실패');
      setBusy(false);
    }
  }

  if (!task) {
    return <main><p className="muted">Task 불러오는 중…</p></main>;
  }

  return (
    <main>
      <p className="muted">Task {progressLabel}</p>
      <h1 className="brand" style={{ fontSize: '1.5rem' }}>{task.title}</h1>
      <p className="lead">{task.why}</p>
      <div className="panel">
        <p>{task.instruction}</p>
        <p className="muted">잘하려고 하지 않아도 됩니다. 평소처럼 편하게 수행하면 됩니다.</p>
        <div style={{ fontSize: '1.8rem', fontWeight: 800, marginTop: 12 }}>
          {String(Math.floor(seconds / 60)).padStart(2, '0')}:{String(seconds % 60).padStart(2, '0')}
        </div>
        <div className="level-bars">
          {levels.map((h, i) => <i key={i} style={{ height: h }} />)}
        </div>
        {!recording ? (
          <button className="btn" onClick={start} disabled={busy}>녹음 시작</button>
        ) : (
          <button className="btn" onClick={stopUpload} disabled={busy}>녹음 종료 & 제출</button>
        )}
        {msg && <p className={msg.includes('분석') ? 'muted' : 'warn'} style={{ marginTop: 12 }}>{msg}</p>}
      </div>
      <Link className="muted" to="/">홈</Link>
    </main>
  );
}
