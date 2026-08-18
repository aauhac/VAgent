import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createAnalysis } from '../api/client';
import AccompanimentToggle, {
  analysisOptsFromAccompaniment,
} from '../components/ui/AccompanimentToggle';
import AudioReadyPanel from '../components/ui/AudioReadyPanel';
import { MIC_PRE_CONSENT, microphoneErrorMessage } from '../lib/userFacingErrors';

const MIN_SEC = 15;
const MAX_SEC = 60;

const MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
];

type Phase = 'idle' | 'recording' | 'ready';

function pickMime(): { mime?: string; ext: string } {
  for (const mime of MIME_CANDIDATES) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(mime)) {
      if (mime.includes('mp4')) return { mime, ext: 'mp4' };
      return { mime, ext: 'webm' };
    }
  }
  return { ext: 'webm' };
}

export default function Record() {
  const nav = useNavigate();
  const [phase, setPhase] = useState<Phase>('idle');
  const [seconds, setSeconds] = useState(0);
  const [levels, setLevels] = useState<number[]>(Array(24).fill(4));
  const [previewLevels, setPreviewLevels] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [hasAccompaniment, setHasAccompaniment] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewDuration, setPreviewDuration] = useState<number | null>(null);
  const [blobMeta, setBlobMeta] = useState<{ blob: Blob; ext: string } | null>(null);

  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const secondsRef = useRef(0);
  const stoppingRef = useRef(false);
  const levelSnapRef = useRef<number[]>([]);

  const previewUrlRef = useRef<string | null>(null);
  previewUrlRef.current = previewUrl;

  useEffect(() => () => {
    stopCapture();
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  function stopCapture() {
    if (timerRef.current) window.clearInterval(timerRef.current);
    timerRef.current = null;
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    mediaRef.current?.stream.getTracks().forEach((t) => t.stop());
    const ctx = audioCtxRef.current;
    if (ctx && ctx.state !== 'closed') {
      void ctx.close().catch(() => undefined);
    }
    audioCtxRef.current = null;
    analyserRef.current = null;
    mediaRef.current = null;
  }

  async function start() {
    setError(null);
    stoppingRef.current = false;
    if (phase === 'recording') return;
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    setBlobMeta(null);
    stopCapture();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;

      const picked = pickMime();
      const rec = picked.mime
        ? new MediaRecorder(stream, { mimeType: picked.mime })
        : new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.start(200);
      mediaRef.current = rec;
      setPhase('recording');
      setSeconds(0);
      secondsRef.current = 0;
      timerRef.current = window.setInterval(() => {
        secondsRef.current += 1;
        setSeconds(secondsRef.current);
        if (secondsRef.current >= MAX_SEC && !stoppingRef.current) {
          stoppingRef.current = true;
          void finishRecording(true);
        }
      }, 1000);

      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        const step = Math.floor(data.length / 24) || 1;
        const next = Array.from({ length: 24 }, (_, i) => {
          const v = data[i * step] || 0;
          return Math.max(4, Math.round((v / 255) * 56));
        });
        setLevels(next);
        levelSnapRef.current = next;
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();
    } catch (e: any) {
      setError(microphoneErrorMessage(e));
      stopCapture();
      setPhase('idle');
    }
  }

  async function finishRecording(auto = false) {
    const rec = mediaRef.current;
    if (!rec) return;
    if (!auto && secondsRef.current < MIN_SEC) {
      setError(`최소 ${MIN_SEC}초 이상 불러 주세요.`);
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
    const mimeType = rec.mimeType || pickMime().mime || 'audio/webm';
    const ext = mimeType.includes('mp4') ? 'mp4' : 'webm';
    const snap = [...levelSnapRef.current];
    stopCapture();
    const blob = new Blob(chunksRef.current, { type: mimeType });
    const url = URL.createObjectURL(blob);
    setPreviewUrl(url);
    setPreviewDuration(recordedSec);
    setPreviewLevels(snap.length ? snap : levels);
    setBlobMeta({ blob, ext });
    setPhase('ready');
    setError(null);
  }

  async function analyze() {
    if (!blobMeta) return;
    setUploading(true);
    setError(null);
    try {
      const opts = analysisOptsFromAccompaniment(hasAccompaniment);
      const { analysis_id } = await createAnalysis(
        blobMeta.blob,
        `recording.${blobMeta.ext}`,
        opts,
      );
      sessionStorage.setItem('vocalfb_last_blob', URL.createObjectURL(blobMeta.blob));
      sessionStorage.setItem('vocalfb_last_filename', `recording.${blobMeta.ext}`);
      sessionStorage.setItem('vocalfb_last_has_accompaniment', hasAccompaniment ? '1' : '0');
      nav(`/analyzing/${analysis_id}`);
    } catch (e: any) {
      setError(e?.message || '업로드 실패');
      setUploading(false);
    }
  }

  function resetToIdle() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setBlobMeta(null);
    setPreviewDuration(null);
    setSeconds(0);
    setPhase('idle');
    setError(null);
  }

  return (
    <main>
      <h1 className="brand" style={{ fontSize: '1.7rem' }}>노래를 불러주세요</h1>
      <p className="lead">
        분석 전에 녹음을 한 번 들어볼 수 있어요. 권장 길이는 15~60초예요.
      </p>

      <div className="panel">
        <AccompanimentToggle
          checked={hasAccompaniment}
          onChange={setHasAccompaniment}
          noun="녹음"
          disabled={phase === 'recording' || uploading}
        />

        {phase === 'idle' && (
          <>
            <ul className="record-idle-tips">
              <li>{MIC_PRE_CONSENT}</li>
              <li>한 구절 정도가 가장 좋아요</li>
              <li>조용한 환경에서 녹음해 주세요</li>
              <li>반주를 틀어 부를 때는 이어폰을 권장해요</li>
            </ul>
            <button className="btn" style={{ width: '100%' }} onClick={start}>
              녹음 시작
            </button>
            <p className="muted" style={{ marginTop: 10, marginBottom: 0, fontSize: '0.82rem' }}>
              마이크를 쓸 수 없으면 <Link to="/upload">음성 파일로 분석</Link>할 수 있어요.
            </p>
          </>
        )}

        {phase === 'recording' && (
          <>
            <div className="record-timer">
              {String(Math.floor(seconds / 60)).padStart(2, '0')}:
              {String(seconds % 60).padStart(2, '0')}
            </div>
            <p className="record-status">녹음 중</p>
            <div className="level-bars" aria-hidden>
              {levels.map((h, i) => (
                <i key={i} style={{ height: h }} />
              ))}
            </div>
            <button className="btn secondary" style={{ width: '100%' }} onClick={() => finishRecording(false)}>
              녹음 종료
            </button>
            <p className="muted" style={{ marginTop: 10, marginBottom: 0, fontSize: '0.82rem' }}>
              최소 {MIN_SEC}초 · 최대 {MAX_SEC}초
            </p>
          </>
        )}

        {phase === 'ready' && previewUrl && (
          <AudioReadyPanel
            src={previewUrl}
            title="녹음 완료"
            subtitle="들어본 뒤 분석하거나 다시 녹음할 수 있어요"
            levels={previewLevels}
            durationSec={previewDuration}
            onClear={resetToIdle}
            clearLabel="다시 녹음"
            onAnalyze={analyze}
            analyzing={uploading}
          />
        )}

        {error && <p className="fail" style={{ marginTop: 12, marginBottom: 0 }}>{error}</p>}
      </div>
    </main>
  );
}
