import { useEffect, useId, useRef, useState } from 'react';
import { formatAnalysisConfidence } from '../../lib/reportPresentation';

type Props = {
  label: string;
  leftLabel: string;
  rightLabel: string;
  /** 0..1 continuum position */
  value: number;
  /** Short state label (never a long paragraph) */
  stateLabel: string;
  /** Optional longer explanation under the bar */
  description?: string;
  helpText?: string;
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
  description,
  helpText,
  confidencePercent,
  confidenceLabel,
  showConfidence = true,
}: Props) {
  const pct = Math.max(0, Math.min(100, Math.round(Number(value) * 100)));
  const confText =
    confidencePercent != null || confidenceLabel
      ? formatAnalysisConfidence(confidenceLabel, confidencePercent)
      : null;
  const tipId = useId();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    function onPointer(e: MouseEvent | TouchEvent) {
      const el = wrapRef.current;
      if (el && e.target instanceof Node && !el.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('touchstart', onPointer);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('touchstart', onPointer);
    };
  }, [open]);

  return (
    <div className="spectrum-axis">
      <div className="spectrum-head">
        <div className="spectrum-label-row" ref={wrapRef}>
          <span className="spectrum-label">{label}</span>
          {helpText ? (
            <span className="spectrum-help-wrap">
              <button
                type="button"
                className="spectrum-help-btn"
                aria-label={`${label} 설명`}
                aria-expanded={open}
                aria-controls={tipId}
                onClick={() => setOpen((v) => !v)}
              >
                ?
              </button>
              {open ? (
                <span id={tipId} role="tooltip" className="spectrum-help-tip">
                  {helpText}
                </span>
              ) : null}
            </span>
          ) : null}
        </div>
        <span className="spectrum-state">{stateLabel}</span>
      </div>
      <div className="spectrum-track" aria-hidden>
        <i className="spectrum-dot" style={{ left: `${pct}%` }} />
      </div>
      <div className="spectrum-ends">
        <span>{leftLabel}</span>
        <span>{rightLabel}</span>
      </div>
      {description ? <p className="spectrum-description">{description}</p> : null}
      {showConfidence && confText ? <p className="spectrum-confidence">{confText}</p> : null}
    </div>
  );
}
