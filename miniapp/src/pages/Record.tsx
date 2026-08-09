import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createAnalysis } from '../api/client';

const MIN_SEC = 5;

export default function Record() {
  const nav = useNavigate();
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [levels, setLevels] = useState<number[]>(Array(24).fill(4));
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => () => stopAll(), []);

  function stopAll() {
    if (timerRef.current) window.clearInterval(timerRef.current);
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    mediaRef.current?.stream.getTracks().forEach((t) => t.stop());
  }

  async function start() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;

      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';
      const rec = new MediaRecorder(stream, { mimeType: mime });
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.start(200);
      mediaRef.current = rec;
      setRecording(true);
      setSeconds(0);
      timerRef.current = window.setInterval(() => setSeconds((s) => s + 1), 1000);

      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        const step = Math.floor(data.length / 24);
        const next = Array.from({ length: 24 }, (_, i) => {
          const v = data[i * step] || 0;
          return Math.max(4, Math.round((v / 255) * 56));
        });
        setLevels(next);
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();
    } catch (e: any) {
      setError(e?.message || '마이크 권한이 필요해요.');
    }
  }

  async function stopAndUpload() {
    const rec = mediaRef.current;
    if (!rec) return;
    if (seconds < MIN_SEC) {
      setError(`최소 ${MIN_SEC}초 이상 불러 주세요.`);
      return;
    }
    setUploading(true);
    await new Promise<void>((resolve) => {
      rec.onstop = () => resolve();
      rec.stop();
    });
    stopAll();
    setRecording(false);
    const blob = new Blob(chunksRef.current, { type: rec.mimeType || 'audio/webm' });
    try {
      const { analysis_id } = await createAnalysis(blob, 'recording.webm', {
        include_feedback: true,
      });
      sessionStorage.setItem('vocalfb_last_blob', URL.createObjectURL(blob));
      nav(`/analyzing/${analysis_id}`);
    } catch (e: any) {
      setError(e?.message || '업로드 실패');
      setUploading(false);
    }
  }

  return (
    <main>
      <Link className="muted" to="/">← 홈</Link>
      <h1 className="brand" style={{ fontSize: '1.8rem', marginTop: 16 }}>노래를 불러주세요</h1>
      <p className="lead">이어폰을 끼고 목소리 중심으로 녹음하면 더 정확해요. 최소 {MIN_SEC}초.</p>
      <div className="panel">
        <div style={{ fontSize: '2rem', fontWeight: 800 }}>
          {String(Math.floor(seconds / 60)).padStart(2, '0')}:
          {String(seconds % 60).padStart(2, '0')}
        </div>
        <div className="level-bars" aria-hidden>
          {levels.map((h, i) => (
            <i key={i} style={{ height: h }} />
          ))}
        </div>
        {!recording ? (
          <button className="btn" onClick={start} disabled={uploading}>녹음 시작</button>
        ) : (
          <button className="btn" onClick={stopAndUpload} disabled={uploading}>
            {uploading ? '업로드 중…' : '녹음 종료 & 분석'}
          </button>
        )}
        {error && <p className="fail" style={{ marginTop: 12 }}>{error}</p>}
      </div>
    </main>
  );
}
