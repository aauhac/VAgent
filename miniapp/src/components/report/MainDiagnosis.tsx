import {
  diagnosisFromPrimary,
  formatSecRange,
  NO_PRIMARY_MESSAGE,
} from '../../lib/reportPresentation';

type Props = {
  primary: any;
  coreSpan?: any;
  onPlay?: (ev: any) => void;
  showAudio?: boolean;
};

export default function MainDiagnosis({
  primary,
  coreSpan,
  onPlay,
  showAudio = true,
}: Props) {
  const diag = diagnosisFromPrimary(primary);
  const range = formatSecRange(
    coreSpan?.original_start_sec ?? coreSpan?.start_sec,
    coreSpan?.original_end_sec ?? coreSpan?.end_sec,
  );

  return (
    <section className="section">
      <h3 className="section-title">가장 두드러진 특징</h3>

      {!diag ? (
        <p className="body-text finding-title" style={{ fontWeight: 600 }}>
          {NO_PRIMARY_MESSAGE}
        </p>
      ) : (
        <>
          <p className="finding-title">{diag.title}</p>
          {showAudio && range && onPlay && (
            <div className="audio-chip-row" style={{ margin: '12px 0' }}>
              <button type="button" className="btn chip secondary" onClick={() => onPlay(coreSpan)}>
                ▶ {range}
              </button>
            </div>
          )}
          {diag.detail && <p className="body-text muted">{diag.detail}</p>}
        </>
      )}
    </section>
  );
}
