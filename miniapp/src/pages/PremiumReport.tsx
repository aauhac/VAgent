import { useEffect, useState, type ReactNode } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { getDiagnosticReport } from '../api/client';
import VocalProfile from '../components/report/VocalProfile';
import {
  buildDiagnosticHeroText,
  buildTaskResultSummary,
  sanitizeDisclaimer,
  scrubUserText,
  translateDiagnosticAxis,
  translateDiagnosticFinding,
  translateMechanismTitle,
} from '../lib/reportPresentation';

function AccordionRow({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="accordion-item">
      <button type="button" className="detail-row" onClick={() => setOpen((v) => !v)}>
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

export default function PremiumReport() {
  const { sessionId } = useParams();
  const [params] = useSearchParams();
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const showDebug = params.get('debug') === '1';

  useEffect(() => {
    if (!sessionId) return;
    getDiagnosticReport(sessionId, { debug: showDebug })
      .then((r) => {
        if (r.error === 'REPORT_LOCKED') setError('REPORT_LOCKED');
        else setReport(r);
      })
      .catch((e) => setError(e.message));
  }, [sessionId, showDebug]);

  if (error === 'REPORT_LOCKED') {
    return (
      <main>
        <h1 className="brand" style={{ fontSize: '1.5rem' }}>상세 결과 잠금</h1>
        <p className="lead">이 진단 세션이 아직 해제되지 않았어요.</p>
        <Link className="btn" to={`/premium?session=${sessionId}`}>영구 해제하기</Link>
      </main>
    );
  }
  if (error) return <main><p className="fail">{error}</p></main>;
  if (!report) {
    return (
      <main>
        <p className="muted">리포트 불러오는 중…</p>
        <div className="skeleton" style={{ height: 28, width: '50%' }} />
        <div className="skeleton" style={{ height: 100 }} />
      </main>
    );
  }

  const sections = report.sections || {};
  const summary = report.summary || sections.A_summary || {};
  const reliable =
    report.reliable_findings
    || sections.B_reliable?.items
    || [];
  const uncertain =
    report.uncertain_findings
    || sections.B_uncertain?.items
    || [];
  const supporting =
    report.supporting_observations
    || sections.B_supporting?.items
    || sections.B_auxiliary?.items
    || [];
  const vocalType = report.vocal_type_profile || report.baseline_vocal_type;
  const topFindings = reliable.slice(0, 3).map(translateDiagnosticFinding);
  const profileAxes = reliable
    .map(translateDiagnosticAxis)
    .filter(Boolean) as NonNullable<ReturnType<typeof translateDiagnosticAxis>>[];
  const taskSummary = buildTaskResultSummary(reliable, uncertain);
  const hero = buildDiagnosticHeroText(reliable);
  const hc = vocalType?.head_chest;

  return (
    <main>
      <Link className="muted" to="/">‹ 홈</Link>
      <h1 className="brand" style={{ fontSize: '1.4rem', marginTop: 12 }}>
        정밀 발성 진단
      </h1>

      <section className="section">
        {vocalType?.available && vocalType?.display_name ? (
          <>
            <p className="eyebrow">기본 발성 타입</p>
            <h2 className="type-title">{vocalType.display_name}</h2>
            {hc?.available && hc.chest_ratio != null && (
              <p className="body-text" style={{ marginTop: 8 }}>
                흉성 {hc.chest_ratio}% · 두성 {hc.head_ratio}%
              </p>
            )}
          </>
        ) : (
          <>
            <p className="eyebrow">기본 발성 특성</p>
            <p className="body-text" style={{ fontWeight: 600, lineHeight: 1.5 }}>{hero}</p>
          </>
        )}
        {summary.safety_note && (
          <p className="warn" style={{ marginTop: 10 }}>{scrubUserText(summary.safety_note)}</p>
        )}
      </section>

      <section className="section">
        <h3 className="section-title">가장 뚜렷한 특징</h3>
        {topFindings.length === 0 ? (
          <p className="muted body-text">이번 진단에서 특별히 강하게 나타난 특징은 제한적이에요.</p>
        ) : (
          topFindings.map((f: ReturnType<typeof translateDiagnosticFinding>, i: number) => (
            <div key={`${f.title}-${i}`} className="diag-finding">
              <p className="diag-num">{String(i + 1).padStart(2, '0')}</p>
              <div>
                <p className="diag-finding-title">
                  {f.title}
                  <span className="diag-tone">{f.tone}</span>
                </p>
                <p className="body-text muted" style={{ margin: '6px 0 0' }}>{f.body}</p>
                <p className="spectrum-confidence">
                  {f.confidence_percent != null ? `신뢰도 ${f.confidence_percent}%` : null}
                </p>
              </div>
            </div>
          ))
        )}
      </section>

      {profileAxes.length > 0 && (
        <VocalProfile
          dimensions={[]}
          title="정밀 발성 프로필"
          axes={profileAxes}
        />
      )}

      {taskSummary.length > 0 && (
        <section className="section">
          <h3 className="section-title">표준 과제에서 본 결과</h3>
          {taskSummary.map((t) => (
            <div key={t.task} style={{ marginBottom: 16 }}>
              <p style={{ margin: '0 0 8px', fontWeight: 700 }}>{t.task}</p>
              {t.rows.map((r) => (
                <div key={`${t.task}-${r.label}`} className="trait-row">
                  <span>{r.label}</span>
                  <strong>{r.value}</strong>
                </div>
              ))}
            </div>
          ))}
        </section>
      )}

      <section className="section">
        <h3 className="section-title">더 자세히</h3>

        {supporting.length > 0 && (
          <AccordionRow title="추가로 관찰된 특징" meta={`${supporting.length}개`}>
            {supporting.map((m: any) => (
              <div key={m.mechanism_id || m.display_name} style={{ marginBottom: 12 }}>
                <p style={{ margin: '0 0 4px', fontWeight: 600, color: 'var(--text)' }}>
                  {translateMechanismTitle(m.mechanism_id, m.display_name)}
                </p>
                <p className="muted" style={{ margin: 0 }}>
                  {scrubUserText(m.observation || m.summary)
                    || '관련 음향 특성은 관찰됐지만 이번 진단에서는 별도 점수로 표시하지 않아요.'}
                </p>
              </div>
            ))}
          </AccordionRow>
        )}

        {uncertain.length > 0 && (
          <AccordionRow title="추가 확인이 필요한 항목" meta={`${uncertain.length}개`}>
            {uncertain.map((m: any) => (
              <div key={m.mechanism_id || m.display_name} style={{ marginBottom: 12 }}>
                <p style={{ margin: '0 0 4px', fontWeight: 600, color: 'var(--text)' }}>
                  {translateMechanismTitle(m.mechanism_id, m.display_name)}
                </p>
                <p className="muted" style={{ margin: 0 }}>
                  {scrubUserText(m.summary)
                    || '이번 과제에서는 비교할 수 있는 구간이 충분하지 않았어요.'}
                </p>
              </div>
            ))}
          </AccordionRow>
        )}

        <AccordionRow title="분석 방법과 한계">
          <p style={{ marginTop: 0 }}>
            {sanitizeDisclaimer(
              (report.safety || {}).disclaimer
                || sections.H_disclaimer?.text
                || report.disclaimer,
            )}
          </p>
        </AccordionRow>

        {showDebug && report.scientific_debug && (
          <AccordionRow title="[debug] scientific_debug">
            <pre style={{ overflow: 'auto', fontSize: 11 }}>
              {JSON.stringify(report.scientific_debug, null, 2)}
            </pre>
          </AccordionRow>
        )}
      </section>

      <section className="section" style={{ borderBottom: 0 }}>
        <div className="cta-row">
          <Link className="btn" to="/record">새 노래 분석하기</Link>
          <Link className="btn secondary" to="/history">진단 기록 보기</Link>
        </div>
      </section>
    </main>
  );
}
