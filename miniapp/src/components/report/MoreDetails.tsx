import { ReactNode, useState } from 'react';
import {
  buildAdditionalFindings,
  buildConfidenceEvidenceRows,
  formatAnalysisConfidence,
} from '../../lib/reportPresentation';
import { buildCompactReportDisclaimer } from '../../lib/precisionPresentation';

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
}: Props) {
  const ranges = vocalType?.range_profiles || {};
  const hasRanges = !!(ranges.low || ranges.mid || ranges.high);
  const additional = buildAdditionalFindings(dimensions, preserve, observationFocus);
  const confidenceRows = buildConfidenceEvidenceRows(dimensions, criteriaMatrix);
  const perf = (performanceAreas || []).filter(
    (a: any) => a.status !== 'unknown' && a.score != null,
  );

  return (
    <section className="section">
      <h3 className="section-title">더 자세히</h3>

      {hasRanges && (
        <AccordionRow title="음역별 발성 구성">
          {(['low', 'mid', 'high'] as const).map((band) => {
            const r = ranges[band];
            if (!r) return null;
            const label = band === 'low' ? '저음' : band === 'mid' ? '중음' : '고음';
            if (!r.available) return null;
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

      <p className="footer-note report-disclaimer" data-testid="detail-disclaimer">
        <span className="report-disclaimer__label">참고</span>
        {buildCompactReportDisclaimer(disclaimer)}
      </p>
    </section>
  );
}
