import { useState } from 'react';
import type { DisplayAxis } from '../../lib/reportPresentation';
import { buildVocalProfileView, useIsDebug } from '../../lib/reportPresentation';
import { helpTextForAxis } from '../../lib/axisHelpText';
import type { MissingProfileAxis } from '../../lib/unavailableAxisReason';
import { precisionHintForAxis } from '../../lib/unavailableAxisReason';
import SpectrumAxis from './SpectrumAxis';

type Props = {
  dimensions: any;
  criteriaMatrix?: any[];
  title?: string;
  axes?: DisplayAxis[];
  showConfidence?: boolean;
  canonicalRegister?: { status?: string; profile_label?: string; title?: string; description?: string } | null;
  canonicalAcoustic?: { axes?: Record<string, any> } | null;
  quality?: any;
  highNoteProfile?: any;
  context?: 'song' | 'precision';
  showPrecisionHints?: boolean;
  remainingUncertainties?: string[];
};

function MissingAxesAccordion({
  missing,
  showPrecisionHints,
  zeroMode,
}: {
  missing: MissingProfileAxis[];
  showPrecisionHints?: boolean;
  zeroMode?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const debug = useIsDebug();
  if (!missing.length) return null;
  const label = zeroMode
    ? '왜 확인하기 어려웠나요?'
    : `확인하기 어려웠던 항목 ${missing.length}개`;

  return (
    <div className="profile-missing" data-testid="profile-missing-axes">
      <button
        type="button"
        className="profile-missing__toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span>{label}</span>
        <span className="chevron" aria-hidden>{open ? '▴' : '›'}</span>
      </button>
      {open ? (
        <ul className="profile-missing__list">
          {missing.map((row) => (
            <li key={row.id} className="profile-missing__item">
              <p className="profile-missing__name">{row.label}</p>
              <p className="profile-missing__reason">{row.reason.user_message}</p>
              {showPrecisionHints && precisionHintForAxis(row.id) ? (
                <p className="profile-missing__hint">{precisionHintForAxis(row.id)}</p>
              ) : null}
              {debug ? (
                <p className="profile-missing__debug" data-testid="profile-missing-debug">
                  {row.reason.code} · {row.reason.source}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default function VocalProfile({
  dimensions,
  criteriaMatrix = [],
  title: titleOverride,
  axes: axesProp,
  showConfidence = true,
  canonicalRegister,
  canonicalAcoustic,
  quality,
  highNoteProfile,
  context = 'song',
  showPrecisionHints = false,
  remainingUncertainties,
}: Props) {
  const view = buildVocalProfileView(
    dimensions,
    criteriaMatrix,
    canonicalRegister,
    canonicalAcoustic,
    { quality, highNoteProfile, context, remainingUncertainties },
  );
  const axes = axesProp || view.axes;
  const missing = view.missing;
  const title = titleOverride || view.title;

  return (
    <section className="section" data-testid="vocal-profile">
      <h3 className="section-title">{title}</h3>
      {axes.length === 0 ? (
        <>
          <p className="body-text muted">{view.zeroMessage}</p>
          <MissingAxesAccordion missing={missing} showPrecisionHints={showPrecisionHints} zeroMode />
        </>
      ) : (
        <>
          {axes.map((ax) => (
            <SpectrumAxis
              key={ax.id}
              label={ax.label}
              leftLabel={ax.left}
              rightLabel={ax.right}
              value={ax.value ?? 0}
              stateLabel={ax.display}
              description={ax.description}
              helpText={helpTextForAxis(ax.id)}
              confidencePercent={ax.confidence_percent}
              confidenceLabel={ax.confidence_label}
              showConfidence={showConfidence}
            />
          ))}
          {view.intro ? <p className="body-text muted profile-available-note">{view.intro}</p> : null}
          <MissingAxesAccordion missing={missing} showPrecisionHints={showPrecisionHints} />
        </>
      )}
    </section>
  );
}
