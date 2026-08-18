import { ReactNode, useState } from 'react';
import {
  buildAdditionalFindings,
  buildConfidenceEvidenceRows,
  formatAnalysisConfidence,
} from '../../lib/reportPresentation';
import { buildCompactReportDisclaimer } from '../../lib/precisionPresentation';
import {
  highNoteUnavailableCopy,
  timbreUnavailableCopy,
} from '../../lib/unavailableAxisReason';
import HighNoteFunctionSection from './HighNoteFunctionSection';
import TimbreProfileSection from './TimbreProfileSection';

function AccordionRow({
  title,
  meta,
  children,
  defaultOpen = false,
}: {
  title: string;
  meta?: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="accordion-item">
      <button
        type="button"
        className="detail-row"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="detail-label">{title}</span>
        <span className="detail-meta">
          {meta ? <span className="meta-count">{meta}</span> : null}
          <span className="chevron">{open ? '▴' : '›'}</span>
        </span>
      </button>
      {open && <div className="detail-panel">{children}</div>}
    </div>
  );
}

type Props = {
  vocalType: any;
  criteriaMatrix: any[];
  dimensions: any;
  observationFocus?: any[];
  preserve?: any[];
  performanceAreas?: any[];
  disclaimer?: string;
  debug?: boolean;
  candidateComparison?: any[];
  highNoteProfile?: any;
  timbreProfile?: any;
};

export default function MoreDetails({
  vocalType,
  criteriaMatrix,
  dimensions,
  observationFocus = [],
  preserve = [],
  performanceAreas = [],
  disclaimer,
  debug,
  candidateComparison = [],
  highNoteProfile,
  timbreProfile,
}: Props) {
  const ranges = vocalType?.range_profiles || {};
  const visibleBands = (['low', 'mid', 'high'] as const).filter((band) => ranges[band]?.available);
  const hasVisibleRanges = visibleBands.length > 0;
  const additional = buildAdditionalFindings(dimensions, preserve, observationFocus);
  const confidenceRows = buildConfidenceEvidenceRows(dimensions, criteriaMatrix);
  const perf = (performanceAreas || []).filter(
    (a: any) => a.status !== 'unknown' && a.score != null,
  );
  const highNoteUnavailable = highNoteUnavailableCopy(highNoteProfile);
  const timbreUnavailable = timbreUnavailableCopy(timbreProfile);
  const highNoteAvailable = !!highNoteProfile && !highNoteUnavailable;
  const timbreAvailable = !!timbreProfile && !timbreUnavailable;
  const hiddenExtras = [
    highNoteUnavailable ? { id: 'high_note', label: '고음 수행', reason: highNoteUnavailable } : null,
    timbreUnavailable ? { id: 'timbre', label: '음색 프로필', reason: timbreUnavailable } : null,
  ].filter(Boolean) as Array<{ id: string; label: string; reason: { user_message: string; code: string; source: string } }>;

  return (
    <section className="section">
      <h3 className="section-title">더 자세히</h3>

      {hasVisibleRanges && (
        <AccordionRow title="음역별 발성 구성">
        {visibleBands.map((band) => {
            const r = ranges[band];
            const label = band === 'low' ? '저음' : band === 'mid' ? '중음' : '고음';
            return (
              <p key={band} style={{ margin: '6px 0', color: 'var(--text)' }}>
                {label}
                <br />
                <span className="muted">
                  흉성 {r.chest_ratio}% · 두성 {r.head_ratio}%
                </span>
              </p>
            );
          })}
        </AccordionRow>
      )}

      {additional.length > 0 && (
        <AccordionRow title="추가로 관찰된 특징" meta={`${additional.length}개`}>
          {additional.map((f) => (
            <div key={f.id} style={{ marginBottom: 14 }}>
              <p style={{ margin: '0 0 4px', fontWeight: 700, color: 'var(--text)' }}>{f.title}</p>
              <p className="muted" style={{ margin: 0 }}>{f.body}</p>
            </div>
          ))}
        </AccordionRow>
      )}

      {perf.length > 0 && (
        <AccordionRow title="가창 참고 분석">
          <p className="muted" style={{ marginTop: 0 }}>
            발성 진단과 별개의 가창 참고 점수예요.
          </p>
          {perf.map((a: any) => (
            <div key={a.area_id} className="area-row" style={{ padding: '8px 0' }}>
              <span>{a.display_name}</span>
              <strong>{Math.round(a.score)}점</strong>
            </div>
          ))}
        </AccordionRow>
      )}

      {highNoteAvailable && (
        <AccordionRow title="고음 수행">
          <HighNoteFunctionSection profile={highNoteProfile} embedded />
        </AccordionRow>
      )}

      {timbreAvailable && (
        <AccordionRow title="음색 프로필">
          <TimbreProfileSection profile={timbreProfile} omitPresence embedded />
        </AccordionRow>
      )}

      {hiddenExtras.length > 0 && (
        <AccordionRow title="이번 녹음에서 확인하기 어려웠던 항목" meta={`${hiddenExtras.length}개`}>
          {hiddenExtras.map((row) => (
            <div key={row.id} style={{ marginBottom: 14 }}>
              <p style={{ margin: '0 0 4px', fontWeight: 700, color: 'var(--text-secondary)' }}>{row.label}</p>
              <p className="muted" style={{ margin: 0 }}>{row.reason.user_message}</p>
              {debug ? (
                <p className="muted" style={{ margin: '6px 0 0', fontSize: '0.75rem' }}>
                  {row.reason.code} · {row.reason.source}
                </p>
              ) : null}
            </div>
          ))}
        </AccordionRow>
      )}

      {confidenceRows.length > 0 && (
        <AccordionRow title="분석 신뢰도와 근거">
          {confidenceRows.map((row) => (
            <div key={row.id} style={{ marginBottom: 16 }}>
              <p style={{ margin: '0 0 4px', fontWeight: 700, color: 'var(--text)' }}>{row.label}</p>
              <p className="muted" style={{ margin: '0 0 6px' }}>
                {formatAnalysisConfidence(row.confidence_label, row.confidence_percent)}
              </p>
              {row.evidence_labels.length > 0 && (
                <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
                  확인된 정보
                  <br />
                  {row.evidence_labels.join(' · ')}
                </p>
              )}
            </div>
          ))}
        </AccordionRow>
      )}

      {debug && candidateComparison.length > 0 && (
        <AccordionRow title="[debug] candidate comparison" defaultOpen>
          <pre style={{ overflow: 'auto', fontSize: 11 }}>
            {JSON.stringify(candidateComparison, null, 2)}
          </pre>
        </AccordionRow>
      )}

      {debug && (criteriaMatrix || []).length > 0 && (
        <AccordionRow title="[debug] criteria matrix">
          <pre style={{ overflow: 'auto', fontSize: 11 }}>
            {JSON.stringify(criteriaMatrix, null, 2)}
          </pre>
        </AccordionRow>
      )}

      <AccordionRow title="분석 방법과 한계">
        <p className="muted" style={{ marginTop: 0 }} data-testid="detail-disclaimer">
          {buildCompactReportDisclaimer(disclaimer)}
        </p>
      </AccordionRow>
    </section>
  );
}
