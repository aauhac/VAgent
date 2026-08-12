import { useEffect, useRef, useState, type RefObject } from 'react';
import { fetchAuthenticatedPreviewBlobUrl, resolveLocalBlobUrl } from '../../lib/reportAudio';

export type ClipRange = {
  start_sec: number;
  end_sec?: number | null;
  label?: string;
};

type Props = {
  analysisId: string;
  audioRef: RefObject<HTMLAudioElement>;
  clip: ClipRange | null;
  onClipClear?: () => void;
};

function formatTime(sec: number) {
  const s = Math.max(0, Math.floor(sec));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

/** Authenticated preview + optional feature-segment playback with end boundary. */
export default function ReportAudioPlayer({ analysisId, audioRef, clip, onClipClear }: Props) {
  const [src, setSrc] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [duration, setDuration] = useState(0);
  const [current, setCurrent] = useState(0);
  const revokeRef = useRef<(() => void) | null>(null);
  const pendingSeekRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setSrc(null);
    revokeRef.current?.();
    revokeRef.current = null;

    const local = resolveLocalBlobUrl(analysisId);
    if (local) {
      setSrc(local);
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }

    fetchAuthenticatedPreviewBlobUrl(analysisId)
      .then(({ url, revoke }) => {
        if (cancelled) {
          revoke();
          return;
        }
        revokeRef.current = revoke;
        setSrc(url);
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setLoadError('녹음 파일을 불러오지 못했어요. 잠시 후 다시 시도해주세요.');
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
      revokeRef.current?.();
      revokeRef.current = null;
    };
  }, [analysisId]);

  useEffect(() => {
    if (clip == null) return;
    pendingSeekRef.current = Math.max(0, clip.start_sec - 0.35);
    const a = audioRef.current;
    if (a && a.readyState >= 1) {
      try {
        a.currentTime = pendingSeekRef.current;
        void a.play().catch(() => setLoadError('재생을 시작하지 못했어요.'));
      } catch {
        /* wait for loadedmetadata */
      }
      pendingSeekRef.current = null;
    }
  }, [clip, audioRef, src]);

  function onLoadedMetadata(e: React.SyntheticEvent<HTMLAudioElement>) {
    const d = e.currentTarget.duration;
    if (Number.isFinite(d) && d > 0) setDuration(d);
    const seek = pendingSeekRef.current;
    if (seek != null) {
      try {
        e.currentTarget.currentTime = seek;
        void e.currentTarget.play().catch(() => setLoadError('재생을 시작하지 못했어요.'));
      } catch {
        /* ignore */
      }
      pendingSeekRef.current = null;
    }
  }

  function onTimeUpdate(e: React.SyntheticEvent<HTMLAudioElement>) {
    const t = e.currentTarget.currentTime;
    setCurrent(t);
    if (clip?.end_sec != null && t >= Number(clip.end_sec) + 0.15) {
      e.currentTarget.pause();
      try {
        e.currentTarget.currentTime = Math.max(0, clip.start_sec - 0.1);
      } catch {
        /* ignore */
      }
    }
  }

  if (loading) {
    return (
      <div className="sticky-player">
        <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>녹음 불러오는 중…</p>
      </div>
    );
  }

  if (loadError || !src) {
    return (
      <div className="sticky-player">
        <p className="fail" style={{ margin: 0, fontSize: '0.85rem' }}>
          {loadError || '녹음 파일을 불러오지 못했어요. 잠시 후 다시 시도해주세요.'}
        </p>
      </div>
    );
  }

  return (
    <div className="sticky-player">
      {clip?.label ? <div className="sticky-label">{clip.label}</div> : null}
      <audio
        ref={audioRef}
        src={src}
        controls
        preload="metadata"
        onLoadedMetadata={onLoadedMetadata}
        onTimeUpdate={onTimeUpdate}
        onError={() => setLoadError('녹음 파일을 불러오지 못했어요. 잠시 후 다시 시도해주세요.')}
        onEnded={() => {
          if (duration > 0) setCurrent(duration);
        }}
      />
      {duration > 0 ? (
        <p className="muted" style={{ margin: '4px 0 0', fontSize: '0.75rem' }}>
          {formatTime(current)} / {formatTime(duration)}
        </p>
      ) : null}
      {clip && onClipClear ? (
        <button type="button" className="btn ghost" style={{ marginTop: 6, fontSize: '0.8rem' }} onClick={onClipClear}>
          구간 재생 해제
        </button>
      ) : null}
    </div>
  );
}
