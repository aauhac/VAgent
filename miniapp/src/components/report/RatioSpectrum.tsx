type Props = {
  chest: number;
  head: number;
};

/** Head/Chest as continuum (same visual language as SpectrumAxis). */
export default function RatioSpectrum({ chest, head }: Props) {
  const c = Number(chest);
  const h = Number(head);
  // Marker at chest→head split (= chest%)
  const marker = Math.max(0, Math.min(100, c));
  return (
    <div className="ratio-spectrum">
      <div className="ratio-labels">
        <span>흉성 {c}%</span>
        <span>두성 {h}%</span>
      </div>
      <div className="spectrum-track" aria-hidden>
        <i className="spectrum-dot" style={{ left: `${marker}%` }} />
      </div>
      <div className="spectrum-ends">
        <span>흉성</span>
        <span>두성</span>
      </div>
    </div>
  );
}
