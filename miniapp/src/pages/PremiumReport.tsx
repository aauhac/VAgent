import { useEffect, useState, type ReactNode } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { getDiagnosticReport, getDiagnosticSession, analyzeDiagnosticSession } from '../api/client';
import VocalProfile from '../components/report/VocalProfile';
import {
  buildDiagnosticHeroText,
  buildTaskResultSummary,
  formatAnalysisConfidence,
  mapEvidenceTokenForUser,
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
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function load(attempt = 0) {
      try {
        const r = await getDiagnosticReport(sessionId!, { debug: showDebug });
        if (cancelled) return;
        if (r.error === 'REPORT_LOCKED') {
          setError('REPORT_LOCKED');
          return;
        }
        if (r.error === 'REPORT_GENERATING') {
          setError(null);
          setReport(null);
          // Ensure analysis is kicked if still READY
          if (attempt === 0) {
            try {
              const sess = await getDiagnosticSession(sessionId!);
              if (String(sess?.status || '').toUpperCase() === 'READY_FOR_ANALYSIS') {
                await analyzeDiagnosticSession(sessionId!);
              }
            } catch {
              /* keep polling */
            }
          }
          timer = setTimeout(() => void load(attempt + 1), 900);
          return;
        }
        setReport(r);
      } catch (e: any) {
        if (cancelled) return;
        const msg = String(e?.message || '');
        if (msg.includes('report not ready') || msg.includes('REPORT_GENERATING')) {
          setError(null);
          timer = setTimeout(() => void load(attempt + 1), 900);
          return;
        }
        setError(msg || '리포트를 불러오지 못했어요.');
      }
    }

    void load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
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
  if (error) {
    return (
      <main>
        <p className="fail">{error}</p>
        <Link className="btn secondary" to={`/diagnostic/${sessionId}/report`} style={{ marginTop: 12 }}>
          다시 시도
        </Link>
      </main>
    );
  }
  if (!report) {
    return (
      <main>
        <p className="muted">결과를 분석하고 있어요…</p>
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
  const vocalStyle = report.vocal_style_profile || vocalType?.vocal_style_profile;
  const topFindings = reliable.slice(0, 3).map(translateDiagnosticFinding);
  const profileAxes = reliable
    .map(translateDiagnosticAxis)
    .filter(Boolean) as NonNullable<ReturnType<typeof translateDiagnosticAxis>>[];
  const taskSummary = buildTaskResultSummary(
    reliable,
    uncertain,
    report.completed_tasks
      || report.final_diagnostic_profile?.task_evidence?.completed_tasks
      || report.final_diagnostic_profile?.task_evidence?.task_ids_present
      || [],
    report.final_diagnostic_profile?.task_profiles || report.personalized_qa?.coaching?.task_profiles,
  );
  const hero = buildDiagnosticHeroText(reliable);
  const pqa = report.personalized_qa || {};
  const coaching = report.coaching || pqa.coaching || {};
  const strengths = coaching.strengths || [];
  const practices =
    coaching.practice_directions
    || report.improvement_priorities
    || pqa.improvement_priorities
    || [];
  const improvements = practices;
  const safetyNote = report.safety_note || summary.safety_note;

  function evidenceLines(qa: {
    user_facing_support?: string[];
    user_facing_against?: string[];
    user_facing_missing?: string[];
    support?: string[];
    against?: string[];
    missing?: string[];
  }) {
    if (showDebug) {
      return {
        support: qa.support || [],
        against: qa.against || [],
        missing: qa.missing || [],
      };
    }
    const mapList = (raw?: string[], pref?: string[]) => {
      if (pref && pref.length) return pref;
      return (raw || []).map(mapEvidenceTokenForUser).filter(Boolean) as string[];
    };
    return {
      support: mapList(qa.support, qa.user_facing_support),
      against: mapList(qa.against, qa.user_facing_against),
      missing: mapList(qa.missing, qa.user_facing_missing),
    };
  }

  return (
    <main>
      <Link className="muted" to="/">‹ 홈</Link>
      {report.source_analysis_id || report.final_diagnostic_profile?.source_analysis_id ? (
        <p className="muted" style={{ marginTop: 8 }}>
          <Link
            to={`/result/${report.source_analysis_id || report.final_diagnostic_profile?.source_analysis_id}/detail`}
          >
            상세 리포트로 돌아가기
          </Link>
        </p>
      ) : null}
      <h1 className="brand" style={{ fontSize: '1.4rem', marginTop: 12 }}>
        {scrubUserText(report.report_title || (report.evidence_mode === 'CONCERN_ONLY' ? '고민 중심 분석' : '정밀 발성 진단'))}
      </h1>
      {report.report_subtitle ? (
        <p className="muted body-text" style={{ marginTop: 8, lineHeight: 1.45 }}>
          {scrubUserText(report.report_subtitle)}
        </p>
      ) : report.evidence_mode === 'PARTIAL_PRECISION' ? (
        <p className="muted body-text" style={{ marginTop: 8, lineHeight: 1.45 }}>
          일부 추가 과제를 건너뛰어 확인 가능한 범위 안에서 분석했어요.
        </p>
      ) : report.evidence_mode === 'CONCERN_ONLY' ? (
        <p className="muted body-text" style={{ marginTop: 8, lineHeight: 1.45 }}>
          기존 노래에서 확인된 발성 특징을 바탕으로 선택한 고민을 분석했어요.
        </p>
      ) : null}
      {coaching.headline ? (
        <p className="body-text" style={{ marginTop: 8, lineHeight: 1.5 }}>
          {scrubUserText(coaching.headline)}
        </p>
      ) : null}

      {(report.song_key_features || pqa.song_key_features || []).length > 0 && (
        <section className="section">
          <h3 className="section-title">이번 노래에서 보이는 핵심 특징</h3>
          <ul className="body-text" style={{ paddingLeft: 18, margin: 0 }}>
            {(report.song_key_features || pqa.song_key_features).slice(0, 3).map((f: string) => (
              <li key={f} style={{ marginBottom: 6 }}>{scrubUserText(f)}</li>
            ))}
          </ul>
        </section>
      )}

      {strengths.length > 0 && (
        <section className="section">
          <h3 className="section-title">현재 잘하고 있는 점</h3>
          <ul className="body-text" style={{ paddingLeft: 18, margin: 0 }}>
            {strengths.slice(0, 3).map((s: any) => (
              <li key={s.id || s.title} style={{ marginBottom: 8 }}>
                {scrubUserText(s.description || s.title)}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(coaching.focus_areas || []).length > 0 && (
        <section className="section">
          <h3 className="section-title">보완하면 좋은 점</h3>
          <ul className="body-text" style={{ paddingLeft: 18, margin: 0 }}>
            {(coaching.focus_areas as any[]).slice(0, 3).map((f) => (
              <li key={f.id || f.title} style={{ marginBottom: 8 }}>
                {scrubUserText(f.description || f.title)}
              </li>
            ))}
          </ul>
        </section>
      )}

      {pqa.show_qa_section !== false && (pqa.questions?.length > 0 || pqa.question) ? (
        <section className="section">
          <h3 className="section-title">당신이 궁금했던 것</h3>
          {(pqa.questions || []).length > 0
            ? (pqa.questions as Array<{
                question: string;
                answer: string;
                takeaway?: string;
                coaching_mode?: string;
                practice_direction?: any;
                support?: string[];
                against?: string[];
                missing?: string[];
                user_facing_support?: string[];
                user_facing_against?: string[];
                user_facing_missing?: string[];
              }>).map((qa, i) => {
                const ev = evidenceLines(qa);
                return (
                  <div key={`${qa.question}-${i}`} style={{ marginBottom: 20 }}>
                    <p className="body-text" style={{ fontWeight: 600 }}>
                      Q{i + 1}. {qa.question}
                    </p>
                    <p className="body-text" style={{ marginTop: 8, lineHeight: 1.55 }}>
                      A. {scrubUserText(qa.answer || '')}
                    </p>
                    {qa.takeaway ? (
                      <p className="body-text muted" style={{ marginTop: 8, lineHeight: 1.5 }}>
                        {scrubUserText(qa.takeaway)}
                      </p>
                    ) : null}
                    {showDebug && (ev.support.length > 0 || ev.against.length > 0 || ev.missing.length > 0) && (
                      <ul className="body-text muted" style={{ marginTop: 8, paddingLeft: 18, fontSize: '0.85rem' }}>
                        {ev.support.slice(0, 3).map((s) => (
                          <li key={`s-${s}`}>✓ {scrubUserText(s)}</li>
                        ))}
                        {ev.against.slice(0, 2).map((s) => (
                          <li key={`a-${s}`}>○ {scrubUserText(s)}</li>
                        ))}
                        {ev.missing.slice(0, 2).map((s) => (
                          <li key={`m-${s}`}>? {scrubUserText(s)}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })
            : (
              <>
                <p className="body-text" style={{ fontWeight: 600 }}>Q. {pqa.question}</p>
                <p className="body-text" style={{ marginTop: 10, lineHeight: 1.55 }}>
                  A. {scrubUserText(pqa.answer_summary || '')}
                </p>
              </>
            )}
          {(pqa.evidence || coaching.evidence_families || []).length > 0 && (
            <>
              <p className="eyebrow" style={{ marginTop: 14 }}>이번 판단에 사용한 근거</p>
              <ul className="body-text" style={{ paddingLeft: 18 }}>
                {(coaching.evidence_families || []).length > 0
                  ? (coaching.evidence_families as string[]).map((t) => (
                      <li key={t}>✓ {scrubUserText(t)}</li>
                    ))
                  : (pqa.evidence as Array<{ source: string; text: string }>).map((ev) => (
                      <li key={`${ev.source}-${ev.text}`}>
                        ✓ {scrubUserText(ev.text)}
                      </li>
                    ))}
              </ul>
            </>
          )}
        </section>
      ) : null}

      {(pqa.show_qa_section === false || report.diagnostic_mode === 'GENERAL_DISCOVERY') && (
        <section className="section">
          <h3 className="section-title">정밀 진단에서 확인된 핵심 특징</h3>
          <p className="muted body-text" style={{ marginBottom: 10 }}>
            현재 노래와 추가 녹음을 함께 분석한 결과예요.
          </p>
          {(pqa.discovered_features || report.discovered_features || []).length > 0 ? (
            <ul className="body-text" style={{ paddingLeft: 18 }}>
              {(pqa.discovered_features || report.discovered_features).map((f: string) => (
                <li key={f}>{scrubUserText(f)}</li>
              ))}
            </ul>
          ) : (
            <p className="body-text">{scrubUserText(pqa.answer_summary || hero)}</p>
          )}
        </section>
      )}

      {improvements.length > 0 && (
        <section className="section">
          <h3 className="section-title">맞춤 연습 방향</h3>
          {improvements.slice(0, 3).map((g: any, i: number) => (
            <div key={g.practice_id || g.goal_id || i} style={{ marginBottom: 16 }}>
              <p style={{ margin: 0, fontWeight: 700 }}>
                {i + 1}. [{g.mode_label || (g.mode === 'MAINTAIN' ? '유지' : g.mode === 'CORRECT' ? '교정' : '연습')}]{' '}
                {scrubUserText(g.title)}
              </p>
              {(g.instruction || g.principle) ? (
                <p className="body-text muted" style={{ margin: '6px 0 0', lineHeight: 1.5 }}>
                  {scrubUserText(g.instruction || g.principle)}
                </p>
              ) : null}
              {(g.success_cues || g.suggested_focus || []).length > 0 && (
                <>
                  <p className="eyebrow" style={{ marginTop: 8 }}>잘 되고 있다는 신호</p>
                  <ul className="body-text" style={{ paddingLeft: 18, margin: 0 }}>
                    {(g.success_cues || g.suggested_focus || []).slice(0, 3).map((f: string) => (
                      <li key={f}>{scrubUserText(f)}</li>
                    ))}
                  </ul>
                </>
              )}
              {(g.avoid || []).length > 0 && (
                <p className="body-text muted" style={{ marginTop: 6, fontSize: '0.92rem' }}>
                  피하기 · {(g.avoid as string[]).map(scrubUserText).join(' / ')}
                </p>
              )}
              {g.safety_note ? <p className="warn" style={{ marginTop: 6 }}>{scrubUserText(g.safety_note)}</p> : null}
            </div>
          ))}
        </section>
      )}

      <section className="section">
        {(vocalStyle?.display_name || vocalType?.available) ? (
          <>
            <p className="eyebrow">내 발성 스타일</p>
            <h2 className="type-title">
              {vocalStyle?.display_name || vocalType?.display_name}
            </h2>
            {vocalStyle?.description ? (
              <p className="body-text" style={{ marginTop: 8, lineHeight: 1.5 }}>
                {scrubUserText(vocalStyle.description)}
              </p>
            ) : null}
            {(vocalStyle?.primary_traits || []).length > 0 ? (
              <ul className="body-text" style={{ paddingLeft: 18, marginTop: 10 }}>
                {(vocalStyle.primary_traits as Array<{ label: string; value: string }>).slice(0, 3).map((t) => (
                  <li key={`${t.label}-${t.value}`}>{t.label} · {t.value}</li>
                ))}
              </ul>
            ) : null}
            {(() => {
              const sb = vocalStyle?.source_balance_presentation || vocalType?.source_balance || {};
              const hc = vocalType?.head_chest || {};
              const show =
                (sb.show_ratio ?? hc.show_ratio ?? true)
                && sb.balance_class !== 'CONFLICTED'
                && (sb.chest_percent ?? hc.chest_ratio) != null;
              return (
                <div style={{ marginTop: 12 }}>
                  <p className="eyebrow">흉성·두성 관련 음향 성향</p>
                  {show ? (
                    <p className="body-text" style={{ marginTop: 6 }}>
                      흉성 쪽 {sb.chest_percent ?? hc.chest_ratio} · 두성 쪽 {sb.head_percent ?? hc.head_ratio}
                    </p>
                  ) : (
                    <p className="body-text muted" style={{ marginTop: 6 }}>
                      {sb.label
                        || '여러 음향 특징이 서로 다른 방향으로 나타났어요.'}
                    </p>
                  )}
                </div>
              );
            })()}
            {(vocalStyle?.canonical_register?.title || vocalType?.register_strategy?.title) ? (
              <p className="body-text muted" style={{ marginTop: 10 }}>
                성구 연결 · {vocalStyle?.canonical_register?.title || vocalType?.register_strategy?.title}
              </p>
            ) : null}
          </>
        ) : (
          <>
            <p className="eyebrow">기본 발성 특성</p>
            <p className="body-text" style={{ fontWeight: 600, lineHeight: 1.5 }}>{hero}</p>
          </>
        )}
        {safetyNote && (
          <p className="warn" style={{ marginTop: 10 }}>{scrubUserText(safetyNote)}</p>
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
                  {formatAnalysisConfidence(f.confidence_label, f.confidence_percent)}
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

        {(report.user_skipped_task_count > 0
          || report.evidence_mode === 'CONCERN_ONLY'
          || report.evidence_mode === 'PARTIAL_PRECISION'
          || report.evidence_mode_label) && (
          <AccordionRow title="분석 범위">
            <p className="body-text muted" style={{ marginTop: 0, lineHeight: 1.5 }}>
              {scrubUserText(
                report.evidence_mode_label
                || (report.evidence_mode === 'CONCERN_ONLY'
                  ? '기존 노래에서 확인된 발성 특징을 바탕으로 선택한 고민을 분석했어요.'
                  : report.evidence_mode === 'PARTIAL_PRECISION'
                    ? '노래와 완료한 추가 발성 과제를 함께 분석했어요.'
                    : '노래와 추가 발성 과제를 함께 분석했어요.'),
              )}
            </p>
            {(report.completed_task_count != null || report.user_skipped_task_count != null) && (
              <p className="muted" style={{ fontSize: '0.9rem' }}>
                노래 분석 사용함
                {report.evidence_mode === 'CONCERN_ONLY'
                  ? ' · 추가 발성 과제 진행하지 않음'
                  : (
                    <>
                      {report.completed_task_count != null
                        ? ` · 추가 발성 과제 ${report.completed_task_count}개 완료`
                        : ''}
                      {report.user_skipped_task_count
                        ? ` · ${report.user_skipped_task_count}개 건너뜀`
                        : ''}
                    </>
                  )}
              </p>
            )}
          </AccordionRow>
        )}

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
