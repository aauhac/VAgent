import { useEffect, useRef, useState } from 'react';

type Props = {
  src: string;
  title?: string;
  subtitle?: string;
  levels?: number[];
  durationSec?: number | null;
  onClear?: () => void;
  clearLabel?: string;
  onAnalyze: () => void;
  analyzeLabel?: string;
  analyzing?: boolean;
};

function formatTime(sec: number) {
  const s = Math.max(0, Math.floor(sec));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

/** Preview strip: waveform/progress + play + clear + analyze. */
export default function AudioReadyPanel({
  src,
  title = '준비된 음원',
  subtitle,
  levels,
  durationSec,
  onClear,
  clearLabel = '다시 선택',
  onAnalyze,
  analyzeLabel = '분석하기',
  analyzing,
}: Props) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [dur, setDur] = useState(durationSec ?? 0);

  useEffect(() => {
    setPlaying(false);
    setCurrent(0);
    setDur(durationSec ?? 0);
  }, [src, durationSec]);

  function togglePlay() {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) {
      void a.play();
      setPlaying(true);
    } else {
      a.pause();
      setPlaying(false);
    }
  }

  const bars = levels && levels.length ? levels : Array.from({ length: 28 }, (_, i) => 8 + ((i * 7) % 28));
  const progress = dur > 0 ? Math.min(100, (current / dur) * 100) : 0;

  return (
    <div className="audio-ready">
      <div className="audio-ready-head">
        <div>
          <p className="audio-ready-title">{title}</p>
          {subtitle ? <p className="audio-ready-sub">{subtitle}</p> : null}
        </div>
        {dur > 0 ? <span className="audio-ready-meta">{formatTime(dur)}</span> : null}
      </div>

      <button type="button" className="audio-ready-wave" onClick={togglePlay} aria-label={playing ? '일시정지' : '재생'}>
        <div className="audio-ready-bars" aria-hidden>
          {bars.map((h, i) => (
            <i key={i} style={{ height: Math.max(6, Math.min(40, h)) }} />
          ))}
        </div>
        <div className="audio-ready-progress" aria-hidden>
          <span style={{ width: `${progress}%` }} />
        </div>
        <div className="audio-ready-times">
          <span>{formatTime(current)}</span>
          <span>{dur > 0 ? formatTime(dur) : '--:--'}</span>
        </div>
      </button>

      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onLoadedMetadata={(e) => {
          const d = e.currentTarget.duration;
          if (Number.isFinite(d) && d > 0) setDur(d);
        }}
        onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime || 0)}
        onEnded={() => setPlaying(false)}
        onPause={() => setPlaying(false)}
        onPlay={() => setPlaying(true)}
      />

      <div className="audio-ready-actions">
        <button type="button" className="btn secondary" onClick={togglePlay} disabled={analyzing}>
          {playing ? '일시정지' : '재생'}
        </button>
        {onClear ? (
          <button type="button" className="btn ghost" onClick={onClear} disabled={analyzing}>
            {clearLabel}
          </button>
        ) : null}
      </div>
      <button type="button" className="btn" style={{ width: '100%' }} onClick={onAnalyze} disabled={analyzing}>
        {analyzing ? '분석 준비 중…' : analyzeLabel}
      </button>
    </div>
  );
}
