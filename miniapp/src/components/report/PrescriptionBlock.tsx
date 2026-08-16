import { scrubUserText } from '../../lib/reportPresentation';

type Alternate = {
  title?: string;
  instruction?: string;
};

export type Prescription = {
  title?: string;
  instruction?: string;
  repetitions?: string;
  success_cues?: string[];
  alternate?: Alternate | null;
  song_transfer?: string;
};

/** Direct prescription UI — comparison A/B is not shown here. */
export default function PrescriptionBlock({
  prescription,
  testIdPrefix,
}: {
  prescription?: Prescription | null;
  testIdPrefix?: string;
}) {
  if (!prescription?.instruction) return null;
  const prefix = testIdPrefix || 'qa-rx';
  const success = (prescription.success_cues || []).filter(Boolean).slice(0, 4);
  const alt = prescription.alternate;

  return (
    <div data-testid={prefix} style={{ marginTop: 12 }}>
      <p className="body-text" style={{ fontWeight: 700, margin: 0 }} data-testid={`${prefix}-title`}>
        {scrubUserText(prescription.title || '이렇게 해보세요')}
      </p>
      <p
        className="body-text"
        style={{ marginTop: 8, lineHeight: 1.55, whiteSpace: 'pre-line' }}
        data-testid={`${prefix}-instruction`}
      >
        {scrubUserText(prescription.instruction)}
      </p>
      {prescription.repetitions ? (
        <p className="body-text muted" style={{ marginTop: 6, fontSize: '0.92rem' }} data-testid={`${prefix}-reps`}>
          반복 · {scrubUserText(prescription.repetitions)}
        </p>
      ) : null}

      {alt?.instruction ? (
        <div style={{ marginTop: 12 }} data-testid={`${prefix}-alternate`}>
          <p className="eyebrow" style={{ margin: 0 }}>
            {scrubUserText(alt.title || '그래도 잘 안 되면')}
          </p>
          <p className="body-text" style={{ marginTop: 6, lineHeight: 1.5 }}>
            {scrubUserText(alt.instruction)}
          </p>
        </div>
      ) : null}

      {success.length > 0 ? (
        <div style={{ marginTop: 12 }} data-testid={`${prefix}-success`}>
          <p className="eyebrow" style={{ margin: 0 }}>
            잘 되고 있다는 신호
          </p>
          <ul className="body-text" style={{ paddingLeft: 18, margin: '6px 0 0' }}>
            {success.map((c) => (
              <li key={c}>{scrubUserText(c)}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {prescription.song_transfer ? (
        <div style={{ marginTop: 12 }} data-testid={`${prefix}-transfer`}>
          <p className="eyebrow" style={{ margin: 0 }}>
            원곡에서는
          </p>
          <p className="body-text muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
            {scrubUserText(prescription.song_transfer)}
          </p>
        </div>
      ) : null}
    </div>
  );
}
