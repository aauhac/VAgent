import type { RefObject } from 'react';

type Props = {
  src: string;
  label?: string | null;
  audioRef: RefObject<HTMLAudioElement>;
  active?: boolean;
};

/** Sticky mini player — hidden until a clip is selected. */
export default function StickyAudioPlayer({ src, label, audioRef, active }: Props) {
  if (!src || !active || !label) return null;
  return (
    <div className="sticky-player">
      <div className="sticky-label">{label}</div>
      <audio ref={audioRef} src={src} controls preload="metadata" />
    </div>
  );
}
