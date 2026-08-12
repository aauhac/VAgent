import { useEffect, useRef, useState, type CSSProperties } from 'react';

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

function finiteDuration(value: number | null | undefined): number {
  if (value == null) return 0;
  if (!Number.isFinite(value) || value <= 0) return 0;
  return value;
}

/** Preview: visual strip + seekable scrubber + play / clear / analyze. */
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
  const wasPlayingBeforeScrubRef = useRef(false);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [dur, setDur] = useState(finiteDuration(durationSec));
  const [isScrubbing, setIsScrubbing] = useState(false);
  const [scrubTime, setScrubTime] = useState(0);
  const [previewError, setPreviewError] = useState(false);

  useEffect(() => {
    setPlaying(false);
    setCurrent(0);
    setScrubTime(0);
    setIsScrubbing(false);
    setPreviewError(false);
    setDur(finiteDuration(durationSec));
    const a = audioRef.current;
    if (a) {
      a.pause();
      try {
        a.currentTime = 0;
      } catch {
        /* ignore */
      }
    }
  }, [src, durationSec]);

  const displayTime = isScrubbing ? scrubTime : current;
  const seekable = dur > 0 && !analyzing && !previewError;
  const progressPct = dur > 0 ? Math.min(100, Math.max(0, (displayTime / dur) * 100)) : 0;
  const bars = levels && levels.length ? levels : Array.from({ length: 28 }, (_, i) => 8 + ((i * 7) % 28));

  function togglePlay() {
    const a = audioRef.current;
    if (!a || analyzing || previewError) return;
    if (a.paused) {
      if (dur > 0 && a.currentTime >= Math.max(0, dur - 0.05)) {
        a.currentTime = 0;
        setCurrent(0);
      }
      void a.play().catch(() => {
        setPreviewError(true);
        setPlaying(false);
      });
      setPlaying(true);
    } else {
      a.pause();
      setPlaying(false);
    }
  }

  function seekTo(next: number) {
    const a = audioRef.current;
    if (!a || dur <= 0) return;
    const clamped = Math.min(dur, Math.max(0, next));
    try {
      a.currentTime = clamped;
    } catch {
      /* ignore */
    }
    setCurrent(clamped);
    setScrubTime(clamped);
  }

  function onScrubStart() {
    const a = audioRef.current;
    wasPlayingBeforeScrubRef.current = !!(a && !a.paused);
    if (a && !a.paused) a.pause();
    setIsScrubbing(true);
  }

  function onScrubInput(value: number) {
    setScrubTime(value);
    seekTo(value);
  }

  function onScrubEnd() {
    setIsScrubbing(false);
    const a = audioRef.current;
    if (wasPlayingBeforeScrubRef.current && a) {
      void a.play().catch(() => {
        setPreviewError(true);
        setPlaying(false);
      });
      setPlaying(true);
    } else {
      setPlaying(false);
    }
    wasPlayingBeforeScrubRef.current = false;
  }

  function handleClear() {
    const a = audioRef.current;
    if (a) {
      a.pause();
      try {
        a.currentTime = 0;
      } catch {
        /* ignore */
      }
    }
    setPlaying(false);
    setCurrent(0);
    setScrubTime(0);
    onClear?.();
  }

  return (
    <div className="audio-ready">
      <div className="audio-ready-head">
        <div>
          <p className="audio-ready-title">{title}</p>
          {subtitle ? <p className="audio-ready-sub">{subtitle}</p> : null}
        </div>
        {dur > 0 ? <span className="audio-ready-meta">{formatTime(dur)}</span> : null}
      </div>

      <div className="audio-ready-visual" aria-hidden>
        <div className="audio-ready-bars">
          {bars.map((h, i) => {
            const barPct = ((i + 0.5) / bars.length) * 100;
            const played = barPct <= progressPct;
            return (
              <i
                key={i}
                className={played ? 'is-played' : undefined}
                style={{ height: Math.max(6, Math.min(40, h)) }}
              />
            );
          })}
        </div>
      </div>

      <div className="audio-ready-scrubber">
        <input
          type="range"
          className="audio-ready-range"
          min={0}
          max={dur > 0 ? dur : 1}
          step={0.1}
          value={seekable ? displayTime : 0}
          disabled={!seekable}
          aria-label="재생 위치"
          aria-valuemin={0}
          aria-valuemax={Math.round(dur)}
          aria-valuenow={Math.round(displayTime)}
          aria-valuetext={
            dur > 0
              ? `${Math.round(displayTime)}초 / ${Math.round(dur)}초`
              : '재생 시간 없음'
          }
          style={{ '--scrub-progress': `${progressPct}%` } as CSSProperties}
          onPointerDown={onScrubStart}
          onTouchStart={onScrubStart}
          onChange={(e) => onScrubInput(Number(e.target.value))}
          onPointerUp={onScrubEnd}
          onTouchEnd={onScrubEnd}
          onKeyUp={onScrubEnd}
        />
        <div className="audio-ready-time-row">
          <span>{formatTime(displayTime)}</span>
          <span>{dur > 0 ? formatTime(dur) : '--:--'}</span>
        </div>
      </div>

      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onLoadedMetadata={(e) => {
          const d = e.currentTarget.duration;
          if (Number.isFinite(d) && d > 0) setDur(d);
        }}
        onTimeUpdate={(e) => {
          if (isScrubbing) return;
          setCurrent(e.currentTarget.currentTime || 0);
        }}
        onEnded={() => {
          setPlaying(false);
          if (dur > 0) setCurrent(dur);
        }}
        onPause={() => {
          if (!isScrubbing) setPlaying(false);
        }}
        onPlay={() => setPlaying(true)}
        onError={() => {
          setPreviewError(true);
          setPlaying(false);
        }}
      />

      {previewError ? (
        <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
          이 브라우저에서는 미리듣기를 지원하지 않아요. 분석은 계속할 수 있어요.
        </p>
      ) : null}

      <div className="audio-ready-actions">
        <button
          type="button"
          className="btn secondary"
          onClick={togglePlay}
          disabled={analyzing || previewError}
        >
          {playing ? '일시정지' : '재생'}
        </button>
        {onClear ? (
          <button type="button" className="btn ghost" onClick={handleClear} disabled={analyzing}>
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
