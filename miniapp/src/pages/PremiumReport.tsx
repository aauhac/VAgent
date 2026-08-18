import { useEffect, useState, type ReactNode } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { getDiagnosticReport, getDiagnosticSession, analyzeDiagnosticSession, regenerateDiagnosticReport } from '../api/client';
import VocalProfile from '../components/report/VocalProfile';
import QAComparisonBlock from '../components/report/QAComparisonBlock';
import PrescriptionBlock from '../components/report/PrescriptionBlock';
import CoachingProtocolCard from '../components/report/CoachingProtocolCard';
import {
  buildCompactReportDisclaimer,
  buildUncertainUserCopy,
  presentAnalysisScope,
  presentCoreFinding,
  presentSupportingList,
} from '../lib/precisionPresentation';
import {
  buildDiagnosticHeroText,
  buildTaskResultSummary,
  mapEvidenceTokenForUser,
  scrubUserText,
  translateDiagnosticFinding,
} from '../lib/reportPresentation';
import { QA_GUIDANCE_VERSION } from '../lib/reportVersions';

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

export default function PremiumReport() {
  const { sessionId } = useParams();
  const [params] = useSearchParams();
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [regenBusy, setRegenBusy] = useState(false);
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

  useEffect(() => {
    if (!report || !import.meta.env.DEV) return;
    const stored = report.qa_guidance_version;
    if (stored !== QA_GUIDANCE_VERSION) {
      console.warn('[DIAG_STALE_REPORT]', {
        stored: stored || null,
        current: QA_GUIDANCE_VERSION,
        sessionId,
      });
    }
  }, [report, sessionId]);

  async function regenerateWithCurrentLogic() {
    if (!sessionId || regenBusy) return;
    setRegenBusy(true);
    try {
      await regenerateDiagnosticReport(sessionId);
      const r = await getDiagnosticReport(sessionId, { debug: showDebug });
      setReport(r);
    } catch (e: any) {
      setError(String(e?.message || '결과를 다시 생성하지 못했어요.'));
    } finally {
      setRegenBusy(false);
    }
  }

  if (error === 'REPORT_LOCKED') {
    return (
      <main>
        <h2 className="brand" style={{ fontSize: '1.35rem', marginTop: 12 }}>상세 결과 잠금</h2>
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
  const completedTasks =
    report.completed_tasks
    || report.final_diagnostic_profile?.task_evidence?.completed_tasks
    || [];
  const taskSummary = buildTaskResultSummary(
    reliable,
    uncertain,
    completedTasks,
    report.final_diagnostic_profile?.task_profiles || report.personalized_qa?.coaching?.task_profiles,
  );
  const hero = buildDiagnosticHeroText(reliable);
  const pqa = report.personalized_qa || {};
  const songKeyFeatures: string[] = report.song_key_features || pqa.song_key_features || [];
  type DistinctFinding = ReturnType<typeof translateDiagnosticFinding>;
  type DistinctFeature =
    | { kind: 'finding'; finding: DistinctFinding }
    | { kind: 'canonical'; text: string };
  const distinctFeatures: DistinctFeature[] =
    topFindings.length > 0
      ? topFindings.map((f: DistinctFinding) => ({ kind: 'finding' as const, finding: f }))
      : songKeyFeatures.slice(0, 3).map((text: string) => ({ kind: 'canonical' as const, text }));
  const analysisScope = presentAnalysisScope(report);
  const supportingShown = presentSupportingList(supporting, 3);
  const uncertainShown: { title: string; body: string }[] = (uncertain || []).map((m: any) =>
    buildUncertainUserCopy(m.mechanism_id, m.summary || m.why_not_judged?.[0], m),
  );
  const compactDisclaimer = buildCompactReportDisclaimer(
    (report.safety || {}).disclaimer
      || sections.H_disclaimer?.text
      || report.disclaimer,
  );
  const hasMoreExplore =
    analysisScope.visible || supportingShown.length > 0 || uncertainShown.length > 0;
  const coaching = report.coaching || pqa.coaching || {};
  const goal = report.coaching_goal || pqa.coaching_goal || {};
  const rawProtocol = report.coaching_protocol || goal.coaching_protocol || pqa.coaching_protocol;
  const coachingProtocol =
    rawProtocol && Array.isArray(rawProtocol.steps) && rawProtocol.steps.length > 0
      ? rawProtocol
      : null;
  const hasProtocolSteps = Boolean(coachingProtocol);
  const timbreGoal = report.timbre_goal || pqa.timbre_goal;
  const desired = goal.desired_outcome || (timbreGoal?.id ? timbreGoal : null);
  const showDesiredTimbre = desired?.type === 'TIMBRE' || Boolean(timbreGoal?.id && timbreGoal.id !== 'RECOMMEND_FOR_ME') || desired?.source === 'SYSTEM_RECOMMENDED';
  const practices =
    (goal.practices && goal.practices.length ? goal.practices : null)
    || coaching.practice_directions
    || report.improvement_priorities
    || pqa.improvement_priorities
    || [];
  const safetyNote = report.safety_note || summary.safety_note;
  const preserveLabels: string[] = goal.preserve_labels || [];
  const canonicalRegister =
    report.canonical_register
    || vocalStyle?.canonical_register
    || vocalType?.canonical_register
    || vocalType?.register_strategy
    || report.canonical_song_evidence?.register;
  const canonicalAcoustic =
    report.canonical_acoustic_axes
    || vocalStyle?.canonical_acoustic_axes;
  const dims =
    report.dimensions
    || report.vocal_function_profile?.dimensions
    || [];
  const criteriaMatrix =
    report.criteria_matrix
    || report.vocal_function_profile?.criteria_matrix
    || [];
  const dimCount = Array.isArray(dims) ? dims.length : Object.keys(dims || {}).length;
  const remainingRaw =
    report.unresolved_dimensions
    || report.final_diagnostic_profile?.remaining_uncertainties
    || [];
  const remainingUncertainties = Array.isArray(remainingRaw)
    ? remainingRaw
    : Object.keys(remainingRaw || {});

  function qaAnswerOnly(answer: string) {
    let text = answer;
    const arrow = text.indexOf('\n\n→');
    if (arrow >= 0) text = text.slice(0, arrow);
    // Prefer structured comparison UI — strip embedded block from prose
    const compareIdx = text.indexOf('\n\n비교해보기');
    if (compareIdx >= 0) text = text.slice(0, compareIdx);
    const circled = text.indexOf('\n\n①');
    if (circled >= 0) text = text.slice(0, circled);
    return text.trim();
  }

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

  const reportTitle = scrubUserText(
    report.report_title || (report.evidence_mode === 'CONCERN_ONLY' ? '고민 중심 분석' : '정밀 발성 진단'),
  );

  return (
    <main>
      {reportTitle && reportTitle !== '정밀 발성 진단' ? (
        <h2 className="brand" style={{ fontSize: '1.25rem', marginTop: 12 }}>
          {reportTitle}
        </h2>
      ) : null}
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
      {safetyNote && (
        <p className="warn" style={{ marginTop: 10 }}>{scrubUserText(safetyNote)}</p>
      )}
      {import.meta.env.DEV && showDebug ? (
        <p style={{ marginTop: 10 }}>
          <button
            type="button"
            className="btn secondary"
            data-testid="dev-regenerate-report"
            disabled={regenBusy}
            onClick={() => void regenerateWithCurrentLogic()}
          >
            {regenBusy ? '다시 생성 중…' : '최신 로직으로 결과 다시 생성'}
          </button>
        </p>
      ) : null}

      {showDesiredTimbre && (desired?.label || timbreGoal?.label) ? (
        <section className="section" data-testid="desired-timbre">
          <h3 className="section-title">원하는 음색</h3>
          <p className="body-text" style={{ fontWeight: 700, margin: 0 }}>
            {scrubUserText(desired?.label || timbreGoal?.label)}
          </p>
          {(desired?.description || timbreGoal?.description) ? (
            <p className="body-text muted" style={{ marginTop: 8, lineHeight: 1.5 }}>
              {scrubUserText(desired?.description || timbreGoal?.description)}
            </p>
          ) : null}
          {desired?.recommendation_reason ? (
            <p className="body-text muted" style={{ marginTop: 8, lineHeight: 1.5 }}>
              {scrubUserText(desired.recommendation_reason)}
            </p>
          ) : null}
        </section>
      ) : null}

      {showDebug && goal.goal_title ? (
        <section className="section" data-testid="coaching-goal">
          <h3 className="section-title">먼저 연습할 부분</h3>
          <p className="body-text" style={{ fontWeight: 700, margin: 0, lineHeight: 1.5 }}>
            {scrubUserText(goal.goal_title)}
          </p>
          {goal.goal_description ? (
            <p className="body-text muted" style={{ marginTop: 8, lineHeight: 1.5 }}>
              {scrubUserText(goal.goal_description)}
            </p>
          ) : null}
        </section>
      ) : null}

      {showDebug && (goal.primary_focus_label || goal.primary_focus) ? (
        <section className="section" data-testid="priority-change">
          <p className="body-text muted" style={{ margin: 0, fontSize: '0.95rem' }}>
            우선 포인트 · {scrubUserText(goal.primary_focus_label || goal.primary_focus)}
          </p>
        </section>
      ) : null}

      {showDebug && goal.why_this_first ? (
        <section className="section" data-testid="why-this-first">
          <h3 className="section-title">왜 이 연습?</h3>
          <p className="body-text" style={{ margin: 0, lineHeight: 1.55 }}>
            {scrubUserText(goal.why_this_first)}
          </p>
        </section>
      ) : null}

      {showDebug ? <CoachingProtocolCard protocol={coachingProtocol} /> : null}

      {pqa.show_qa_section !== false && (pqa.questions?.length > 0 || pqa.question) ? (
        <section className="section" data-testid="qa-section">
          <h3 className="section-title">당신이 궁금했던 것</h3>
          {(pqa.questions || []).length > 0
            ? (pqa.questions as Array<{
                question: string;
                answer: string;
                takeaway?: string;
                what_to_change?: string;
                working_direction?: string;
                prescription?: {
                  title?: string;
                  instruction?: string;
                  repetitions?: string;
                  success_cues?: string[];
                  alternate?: { title?: string; instruction?: string } | null;
                  song_transfer?: string;
                };
                comparison?: {
                  baseline_label?: string;
                  baseline_instruction?: string;
                  variant_label?: string;
                  variant_instruction?: string;
                  success_condition?: string;
                  if_better?: string;
                  if_not_better?: string;
                  A?: string;
                  B?: string;
                  success?: string;
                };
                comparison_protocol?: {
                  baseline_instruction?: string;
                  variant_instruction?: string;
                  success_condition?: string;
                  if_better?: string;
                  A?: string;
                  B?: string;
                  success?: string;
                };
                coaching_mode?: string;
                support?: string[];
                against?: string[];
                missing?: string[];
                user_facing_support?: string[];
                user_facing_against?: string[];
                user_facing_missing?: string[];
              }>).map((qa, i) => {
                const ev = evidenceLines(qa);
                const body = scrubUserText(qaAnswerOnly(qa.answer || ''));
                const nextStep = scrubUserText(qa.what_to_change || '');
                const prescription = qa.prescription;
                const showNext =
                  showDebug
                  && Boolean(nextStep)
                  && !body.includes(nextStep)
                  && !prescription?.instruction;
                const comparison = qa.comparison || qa.comparison_protocol;
                return (
                  <div key={`${qa.question}-${i}`} data-testid={`qa-item-${i}`} style={{ marginBottom: 20 }}>
                    <p className="body-text" style={{ fontWeight: 600 }} data-testid={`qa-question-${i}`}>
                      Q{i + 1}. {qa.question}
                    </p>
                    <p
                      className="body-text"
                      style={{ marginTop: 8, lineHeight: 1.55, whiteSpace: 'pre-line' }}
                      data-testid={`qa-answer-${i}`}
                    >
                      A. {body}
                    </p>
                    {showDebug ? (
                      <PrescriptionBlock prescription={prescription} testIdPrefix={`qa-rx-${i}`} />
                    ) : null}
                    {showDebug ? (
                      <QAComparisonBlock comparison={comparison} testIdPrefix={`qa-compare-${i}`} />
                    ) : null}
                    {showNext ? (
                      <p className="muted body-text" style={{ marginTop: 8, lineHeight: 1.5 }} data-testid={`qa-next-${i}`}>
                        {nextStep}
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
                  A. {scrubUserText(qaAnswerOnly(pqa.answer_summary || ''))}
                </p>
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

      {showDebug && practices.filter((g: any) => g && (g.mode || '') !== 'MAINTAIN').length > 0 && !hasProtocolSteps ? (
        <section className="section" data-testid="practice-section">
          <h3 className="section-title">맞춤 연습 방향</h3>
          {practices
            .filter((g: any) => g && (g.mode || '') !== 'MAINTAIN')
            .slice(0, 2)
            .map((g: any, i: number) => (
            <div key={g.practice_id || g.goal_id || i} style={{ marginBottom: 16 }}>
              <p style={{ margin: 0, fontWeight: 700 }}>
                {i + 1}. {scrubUserText(g.title)}
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
      ) : null}

      {preserveLabels.length > 0 && (
        <section className="section" data-testid="maintain-section">
          <h3 className="section-title">유지하면 좋은 점</h3>
          <ul className="body-text" style={{ paddingLeft: 18, margin: 0 }}>
            {preserveLabels.map((s: string) => (
              <li key={s} style={{ marginBottom: 6 }}>{scrubUserText(s)}</li>
            ))}
          </ul>
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
          </>
        ) : (
          <>
            <p className="eyebrow">기본 발성 특성</p>
            <p className="body-text" style={{ fontWeight: 600, lineHeight: 1.5 }}>{hero}</p>
          </>
        )}
      </section>

      {taskSummary.length > 0 && (
        <section className="section" data-testid="task-result-section">
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

      {(canonicalRegister?.status || (canonicalAcoustic?.axes && Object.keys(canonicalAcoustic.axes).length > 0) || dimCount > 0 || remainingUncertainties.length > 0) ? (
        <VocalProfile
          dimensions={dims}
          criteriaMatrix={criteriaMatrix}
          canonicalRegister={canonicalRegister}
          canonicalAcoustic={canonicalAcoustic}
          context="precision"
          remainingUncertainties={remainingUncertainties}
          quality={report.quality}
        />
      ) : null}

      <section className="section" data-testid="precision-core-findings">
        <h3 className="section-title">가장 뚜렷한 특징</h3>
        {distinctFeatures.length === 0 ? (
          <p className="muted body-text">이번 진단에서 특별히 강하게 나타난 특징은 제한적이에요.</p>
        ) : (
          distinctFeatures.map((item, i) => {
            if (item.kind === 'finding') {
              const shown = presentCoreFinding(item.finding);
              return (
                <div key={`${shown.title}-${i}`} className="diag-finding" style={{ marginBottom: 12 }}>
                  <p className="diag-finding-title" style={{ margin: 0 }}>{shown.title}</p>
                  {shown.body ? (
                    <p className="muted body-text" style={{ margin: '6px 0 0', lineHeight: 1.45 }}>
                      {shown.body}
                    </p>
                  ) : null}
                </div>
              );
            }
            return (
              <div key={`${item.text}-${i}`} className="diag-finding" style={{ marginBottom: 12 }}>
                <p className="diag-finding-title" style={{ margin: 0 }}>
                  {scrubUserText(item.text)}
                </p>
              </div>
            );
          })
        )}
      </section>

      {hasMoreExplore || compactDisclaimer || (showDebug && report.scientific_debug) ? (
        <section className="section" data-testid="precision-more-explore">
          <h3 className="section-title">더 살펴보기</h3>

          {analysisScope.visible ? (
            <AccordionRow title={analysisScope.title}>
              <p className="body-text muted" style={{ marginTop: 0, lineHeight: 1.5 }}>
                {analysisScope.body}
              </p>
              {analysisScope.detail ? (
                <p className="muted" style={{ fontSize: '0.9rem', lineHeight: 1.45 }}>
                  {analysisScope.detail}
                </p>
              ) : null}
            </AccordionRow>
          ) : null}

          {supportingShown.length > 0 ? (
            <AccordionRow title="추가 관찰" meta={`${supportingShown.length}개`}>
              {supportingShown.map((m) => (
                <div key={m.mechanismId || m.title} style={{ marginBottom: 12 }}>
                  <p style={{ margin: '0 0 4px', fontWeight: 600, color: 'var(--text)' }}>
                    {m.title}
                  </p>
                  <p className="muted" style={{ margin: 0, lineHeight: 1.45 }}>
                    {m.body}
                  </p>
                </div>
              ))}
            </AccordionRow>
          ) : null}

          {uncertainShown.length > 0 ? (
            <AccordionRow title="추가 확인이 필요한 항목" meta={`${uncertainShown.length}개`}>
              {uncertainShown.map((m) => (
                <div key={m.title} style={{ marginBottom: 12 }}>
                  <p style={{ margin: '0 0 4px', fontWeight: 600, color: 'var(--text)' }}>
                    {m.title}
                  </p>
                  <p className="muted" style={{ margin: 0, lineHeight: 1.45 }}>
                    {m.body}
                  </p>
                </div>
              ))}
              <p className="muted" style={{ marginTop: 8, fontSize: '0.85rem', lineHeight: 1.45 }}>
                정보가 부족하거나 결과가 서로 다를 때는 억지로 한 방향으로 판단하지 않아요.
              </p>
            </AccordionRow>
          ) : null}

          {compactDisclaimer ? (
            <AccordionRow title="분석 방법과 한계">
              <p className="body-text muted" style={{ marginTop: 0, lineHeight: 1.5 }}>
                {compactDisclaimer}
              </p>
            </AccordionRow>
          ) : null}

          {showDebug && report.scientific_debug ? (
            <AccordionRow title="[debug] scientific_debug">
              <pre style={{ overflow: 'auto', fontSize: 11 }}>
                {JSON.stringify(report.scientific_debug, null, 2)}
              </pre>
            </AccordionRow>
          ) : null}
        </section>
      ) : null}

      <p className="footer-note report-disclaimer" data-testid="precision-disclaimer">
        <span className="report-disclaimer__label">참고</span>
        {compactDisclaimer}
      </p>

      <section className="section" style={{ borderBottom: 0 }}>
        <div className="cta-row">
          <Link className="btn" to="/record">새 노래 분석하기</Link>
          <Link className="btn secondary" to="/history">진단 기록 보기</Link>
        </div>
      </section>
    </main>
  );
}
