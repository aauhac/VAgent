/** Pause miniapp audio/video before IAP or other overlays. Never auto-resume. */

export function pauseAllMediaPlayback(): void {
  if (typeof document === 'undefined') return;
  const nodes = document.querySelectorAll('audio, video');
  nodes.forEach((node) => {
    const media = node as HTMLMediaElement;
    try {
      media.pause();
    } catch {
      /* ignore */
    }
  });
}
