import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { getDiagnosticReport } from '../api/client';

function StatusBadge({ status, label }: { status: string; label?: string }) {
  const text = label || status;
  const isUnknown = status === 'unknown';
  return (
    <strong style={{ opacity: isUnknown ? 0.75 : 1 }}>
      {isUnknown ? '판단 어려움' : text}
    </strong>
  );
}

function FindingCard({ m, expandable }: { m: any; expandable?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="panel" style={{ marginBottom: 12 }}>
      <div className="area-row" style={{ marginBottom: 8 }}>
        <span>{m.display_name}</span>
        <span>
          <StatusBadge status={m.status} label={m.status_label} />
          {' '}
          {m.confidence_label && (
            <span className="muted">신뢰도 {m.confidence_label}</span>
          )}
        </span>
      </div>
      <p style={{ marginTop: 0 }}>{m.summary}</p>
      {m.what_was_observed && (
        <p className="muted">관찰: {m.what_was_observed}</p>
      )}
      {m.what_it_may_mean && m.what_it_may_mean !== m.summary && (
        <p className="muted">해석 후보: {m.what_it_may_mean}</p>
      )}
      {m.what_we_cannot_know && (
        <p className="muted">알 수 없는 것: {m.what_we_cannot_know}</p>
      )}
      {m.motor_cue && <p><strong>몸 사용</strong> {m.motor_cue}</p>}
      {m.exercise?.duration && <p><strong>연습</strong> {m.exercise.duration}</p>}
      {expandable && (
        <>
          <button
            type="button"
            className="btn secondary"
            style={{ marginTop: 8, fontSize: '0.85rem' }}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? '닫기' : '왜 이렇게 판단했나요?'}
          </button>
          {open && (
            <div style={{ marginTop: 8 }}>
              <p className="muted">{m.why_this_judgment || '관련 관측이 모였어요.'}</p>
              {(m.alternative_explanations || []).length > 0 && (
                <p className="muted">
                  다른 가능성: {(m.alternative_explanations || []).slice(0, 3).join(' · ')}
                </p>
              )}
            </div>
          )}
        </>
      )}
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
  if (!report) return <main><p className="muted">리포트 불러오는 중…</p></main>;

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
  const training = report.training_plan || sections.F_training_routine || {};
  const retry = report.retry_recommendation || {};
  const retryTasks = retry.tasks || sections.G_next_compare?.items || [];

  return (
    <main>
      <p className="muted">상세 발성 진단 · 영구 보관</p>
      <h1 className="brand" style={{ fontSize: '1.6rem' }}>
        {summary.title || '정밀 발성 분석 완료'}
      </h1>
      <p className="lead">
        {summary.lead || '이번 진단에서 신뢰할 수 있는 특징을 중심으로 알려드릴게요.'}
      </p>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>오늘의 핵심</h3>
        <p>{summary.headline || summary.text}</p>
        {summary.coverage_note && <p className="muted">{summary.coverage_note}</p>}
        {summary.safety_note && <p className="warn">{summary.safety_note}</p>}
        <p className="muted" style={{ fontSize: '0.85rem' }}>
          항목을 억지로 채우지 않습니다. 근거가 부족하면 판단하지 않습니다.
        </p>
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>신뢰할 수 있게 본 항목</h3>
        {reliable.length === 0 && (
          <p className="muted">이번 녹음에서는 충분한 근거가 있는 핵심 항목이 없어요.</p>
        )}
      </div>
      {reliable.map((m: any) => (
        <FindingCard key={m.mechanism_id || m.display_name} m={m} expandable />
      ))}

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>이번에는 판단하기 어려운 항목</h3>
        {uncertain.length === 0 && (
          <p className="muted">판단이 보류된 항목이 없어요.</p>
        )}
        {uncertain.map((m: any) => (
          <div key={m.mechanism_id} style={{ marginBottom: 14 }}>
            <div className="area-row">
              <span>{m.display_name}</span>
              <span className="muted">판단 어려움</span>
            </div>
            <p className="muted" style={{ marginBottom: 4 }}>{m.summary}</p>
            {(m.why_not_judged || []).length > 0 && (
              <ul style={{ margin: '4px 0', paddingLeft: 18 }}>
                {(m.why_not_judged || []).map((w: string, i: number) => (
                  <li key={i} className="muted">{w}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
        <p className="muted" style={{ marginTop: 12, fontSize: '0.85rem' }}>
          판단하지 않은 것은 오류가 아니라 보수적 판단이에요.
        </p>
      </div>

      {supporting.length > 0 && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>보조 관찰</h3>
          {supporting.map((m: any) => (
            <div key={m.mechanism_id} style={{ marginBottom: 12 }}>
              <strong>{m.display_name}</strong>
              <p className="muted">{m.observation || m.summary}</p>
              {m.note && <p className="muted" style={{ fontSize: '0.85rem' }}>{m.note}</p>}
            </div>
          ))}
        </div>
      )}

      {(training.motor_cues || []).length > 0 && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>몸 사용 가이드</h3>
          {(training.motor_cues || []).map((c: any) => (
            <p key={c.mechanism_id}>
              {c.cue}
              {c.duration ? <span className="muted"> · {c.duration}</span> : null}
            </p>
          ))}
        </div>
      )}

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>{training.title || '오늘의 3분 연습'}</h3>
        <ul>
          {(training.items || []).map((x: string, i: number) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
        {training.stop_conditions && (
          <p className="warn">{training.stop_conditions}</p>
        )}
      </div>

      {(retryTasks.length > 0 || retry.message) && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>다시 확인할 항목</h3>
          {retry.message && <p className="muted">{retry.message}</p>}
          <ul>
            {(Array.isArray(retryTasks) ? retryTasks : []).map((t: string, i: number) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>안내</h3>
        <p className="muted">
          {(report.safety || {}).disclaimer
            || sections.H_disclaimer?.text
            || report.disclaimer}
        </p>
      </div>

      {showDebug && report.scientific_debug && (
        <pre className="panel" style={{ overflow: 'auto', fontSize: 11 }}>
          {JSON.stringify(report.scientific_debug, null, 2)}
        </pre>
      )}

      <Link className="btn secondary" to="/" style={{ display: 'block' }}>홈으로</Link>
    </main>
  );
}
