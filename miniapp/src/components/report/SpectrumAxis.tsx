import { formatAnalysisConfidence } from '../../lib/reportPresentation';

type Props = {
  label: string;
  leftLabel: string;
  rightLabel: string;
  /** 0..1 continuum position */
  value: number;
  stateLabel: string;
  confidencePercent?: number | null;
  confidenceLabel?: string;
  showConfidence?: boolean;
};

/** Shared continuum: thin line + blue marker. */
export default function SpectrumAxis({
  label,
  leftLabel,
  rightLabel,
  value,
  stateLabel,
  confidencePercent,
  confidenceLabel,
  showConfidence = true,
}: Props) {
  const pct = Math.max(0, Math.min(100, Math.round(Number(value) * 100)));
  const confText =
    confidencePercent != null || confidenceLabel
      ? formatAnalysisConfidence(confidenceLabel, confidencePercent)
      : null;
  return (
    <div className="spectrum-axis">
      <div className="spectrum-head">
        <span className="spectrum-label">{label}</span>
        <span className="spectrum-state">{stateLabel}</span>
      </div>
      <div className="spectrum-track" aria-hidden>
        <i className="spectrum-dot" style={{ left: `${pct}%` }} />
      </div>
      <div className="spectrum-ends">
        <span>{leftLabel}</span>
        <span>{rightLabel}</span>
      </div>
      {showConfidence && confText ? <p className="spectrum-confidence">{confText}</p> : null}
    </div>
  );
}
