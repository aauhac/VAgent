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
      {showConfidence && (confidencePercent != null || confidenceLabel) ? (
        <p className="spectrum-confidence">
          {confidencePercent != null && confidencePercent >= 70
            ? '신뢰도 높음'
            : confidencePercent != null && confidencePercent >= 40
              ? '신뢰도 보통'
              : confidenceLabel?.includes('부족') || confidenceLabel?.includes('낮')
                ? '참고용'
                : confidencePercent != null
                  ? '참고용'
                  : confidenceLabel
                    ? `신뢰도 ${confidenceLabel}`
                    : null}
        </p>
      ) : null}
    </div>
  );
}
