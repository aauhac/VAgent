import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  getPreviewUrl,
  getProducts,
  getSongDetailedReport,
  patchHistory,
} from '../api/client';

function seekTo(audio: HTMLAudioElement | null, sec?: number | null) {
  if (!audio || sec == null || Number.isNaN(Number(sec))) return;
  audio.currentTime = Math.max(0, Number(sec));
  void audio.play();
}

function ScoreLine({
  score,
  label,
}: {
  score?: number | null;
  label?: string;
}) {
  if (score == null) {
    return (
      <strong>
        — · <span className="muted" style={{ fontWeight: 500 }}>{label || '—'}</span>
      </strong>
    );
  }
  return (
    <strong>
      {Math.round(score)}점
      <span className="muted" style={{ marginLeft: 8, fontWeight: 500 }}>
        · {label}
      </span>
    </strong>
  );
}

/** 0 = light (left), 1 = firm (right) */
export function ContactContinuum({ value }: { value: number }) {
  const c = Math.max(0, Math.min(1, Number(value)));
  const left = Math.max(0, Math.round(c * 6));
  const right = Math.max(0, Math.round((1 - c) * 6));
  return (
    <p className="muted" style={{ margin: '4px 0', fontSize: '0.9rem' }}>
      가벼움 {'─'.repeat(left)}●{'─'.repeat(right)} 단단함
      <br />
      (좋고 나쁨이 아닌 경향 표시)
    </p>
  );
}

function whyText(w: any): string {
  if (w == null) return '';
  if (typeof w === 'string') return w;
  return w.text || '';
}

function whyScope(w: any): string | null {
  if (w && typeof w === 'object' && w.scope) return w.scope;
  return null;
}

function CriterionAvailMark({ availability }: { availability?: string }) {
  if (availability === 'SUFFICIENT') return <span>✓</span>;
  if (availability === 'NOT_AVAILABLE') return <span>—</span>;
  return <span>△</span>;
}

function VocalTypeCard({ profile }: { profile: any }) {
  if (!profile || profile.available === false) {
    return (
      <div className="panel">
        <h3 style={{ marginTop: 0 }}>나의 발성 타입</h3>
        <p className="muted">
          {profile?.description || '이번 녹음에서는 발성 타입을 충분히 구분하지 못했어요.'}
        </p>
      </div>
    );
  }
  const hc = profile.head_chest || {};
  const chest = hc.chest_ratio;
  const head = hc.head_ratio;
  const showRatio = hc.available && chest != null && head != null;
  const traits = profile.key_traits || [];
  const ranges = profile.range_profiles || {};
  const timeline = profile.timeline || [];

  return (
    <div className="panel">
      <h3 style={{ marginTop: 0 }}>나의 발성 타입</h3>
      <p style={{ fontSize: '1.25rem', fontWeight: 800, margin: '8px 0' }}>
        {profile.display_name || profile.headline}
      </p>
      {showRatio ? (
        <>
          <p style={{ margin: '4px 0', fontWeight: 700 }}>
            흉성 {chest}% · 두성 {head}%
          </p>
          <div
            style={{
              display: 'flex',
              height: 10,
              borderRadius: 6,
              overflow: 'hidden',
              background: 'rgba(0,0,0,0.08)',
              marginTop: 8,
              marginBottom: 4,
            }}
          >
            <i style={{ width: `${chest}%`, background: 'currentColor', opacity: 0.85, display: 'block' }} />
            <i style={{ width: `${head}%`, background: 'currentColor', opacity: 0.25, display: 'block' }} />
          </div>
          <p className="muted" style={{ fontSize: '0.8rem', margin: '2px 0 10px' }}>
            흉성 {'─'.repeat(Math.max(1, Math.round(chest / 8)))}●{'─'.repeat(Math.max(1, Math.round(head / 8)))} 두성
          </p>
        </>
      ) : (
        <p className="muted" style={{ margin: '4px 0 10px' }}>
          {hc.broad_label || '비율을 충분히 확정하지 못했어요.'}
        </p>
      )}
      {profile.description && (
        <p style={{ margin: '8px 0' }}>{profile.description}</p>
      )}
      {profile.confidence_label && (
        <p className="muted" style={{ fontSize: '0.85rem' }}>
          발성 타입 분석 신뢰도: {profile.confidence_label}
        </p>
      )}
      {traits.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <p style={{ marginBottom: 6 }}><strong>핵심 특징</strong></p>
          {traits.map((t: any) => (
            <div key={t.key || t.label} className="area-row" style={{ marginBottom: 4 }}>
              <span className="muted">{t.label}</span>
              <strong style={{ fontSize: '0.9rem' }}>{t.value}</strong>
            </div>
          ))}
        </div>
      )}
      {(profile.local_register_events || []).length > 0 && (
        <div style={{ marginTop: 10 }}>
          <p className="muted" style={{ fontSize: '0.8rem', marginBottom: 4 }}>국소 구간</p>
          {(profile.local_register_events || []).slice(0, 4).map((e: any, i: number) => (
            <p key={i} style={{ margin: '2px 0', fontSize: '0.85rem' }}>
              {e.start_sec != null && e.end_sec != null
                ? `${Number(e.start_sec).toFixed(0)}–${Number(e.end_sec).toFixed(0)}초 · `
                : ''}
              {e.type === 'LOCAL_CHEST_PULL'
                ? '흉성 비중을 오래 유지'
                : e.type === 'LOCAL_ABRUPT_BREAK'
                  ? '성구가 급격히 바뀜'
                  : e.type === 'LOCAL_EFFORT_SPIKE'
                    ? '힘 증가'
                    : e.type === 'LOCAL_EARLY_HEAD_SHIFT'
                      ? '두성 전환이 빠름'
                      : (e.type || '')}
            </p>
          ))}
        </div>
      )}
      {profile.coaching_link && (
        <p className="muted" style={{ marginTop: 10, fontSize: '0.9rem' }}>
          {profile.coaching_link}
        </p>
      )}
      {(ranges.low || ranges.mid || ranges.high) && (
        <div style={{ marginTop: 14 }}>
          <p style={{ marginBottom: 6 }}><strong>음역별 발성 구성</strong></p>
          {(['low', 'mid', 'high'] as const).map((band) => {
            const r = ranges[band];
            if (!r) return null;
            const label = band === 'low' ? '저음' : band === 'mid' ? '중음' : '고음';
            if (!r.available) {
              return (
                <p key={band} className="muted" style={{ margin: '2px 0', fontSize: '0.85rem' }}>
                  {label}: 측정 구간 부족
                </p>
              );
            }
            return (
              <p key={band} style={{ margin: '2px 0', fontSize: '0.9rem' }}>
                {label}: 흉성 {r.chest_ratio} / 두성 {r.head_ratio}
              </p>
            );
          })}
        </div>
      )}
      {timeline.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <p className="muted" style={{ fontSize: '0.8rem', marginBottom: 4 }}>시간에 따른 비중</p>
          {timeline.map((t: any, i: number) => {
            const avail = t.available !== false && t.chest_ratio != null && t.head_ratio != null;
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span className="muted" style={{ fontSize: '0.75rem', width: 72 }}>
                  {Number(t.start_sec).toFixed(0)}–{Number(t.end_sec).toFixed(0)}s
                </span>
                {avail ? (
                  <>
                    <div style={{ flex: 1, height: 6, borderRadius: 4, overflow: 'hidden', background: 'rgba(0,0,0,0.08)' }}>
                      <i style={{ display: 'block', height: '100%', width: `${t.chest_ratio}%`, background: 'currentColor', opacity: 0.7 }} />
                    </div>
                    <span style={{ fontSize: '0.75rem', whiteSpace: 'nowrap', minWidth: 88 }}>
                      {t.label === '균형에 가까움'
                        ? '균형에 가까움'
                        : `흉성 ${t.chest_ratio}% · 두성 ${t.head_ratio}%`}
                    </span>
                  </>
                ) : (
                  <span className="muted" style={{ fontSize: '0.75rem' }}>
                    {t.label || '측정 부족'}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function SongDetailReport() {
  const { id } = useParams();
  const nav = useNavigate();
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [diagPrice, setDiagPrice] = useState('—');
  const [diagProduct, setDiagProduct] = useState('diagnostic_upgrade');
  const [openCriteria, setOpenCriteria] = useState<Record<string, boolean>>({});
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const blobUrl = useMemo(() => sessionStorage.getItem('vocalfb_last_blob'), []);
  const previewUrl = id ? getPreviewUrl(id) : '';

  useEffect(() => {
    if (!id) return;
    getSongDetailedReport(id)
      .then((r) => {
        if (r.error === 'SONG_DETAIL_LOCKED') {
          setError('SONG_DETAIL_LOCKED');
          return;
        }
        setReport(r);
        patchHistory(id, { songDetailUnlocked: true });
      })
      .catch((e) => setError(e.message));
    getProducts(id).then((cat) => {
      const offer = cat.offers?.diagnostic || 'diagnostic_full';
      setDiagProduct(offer);
      setDiagPrice(cat.products?.[offer]?.display_amount || '—');
    }).catch(() => undefined);
  }, [id]);

  if (error === 'SONG_DETAIL_LOCKED') {
    return (
      <main>
        <h1 className="brand" style={{ fontSize: '1.5rem' }}>상세 리포트 잠금</h1>
        <p className="lead">이 노래의 상세 리포트가 아직 해제되지 않았어요.</p>
        <Link className="btn" to={`/result/${id}`}>결과로 돌아가기</Link>
      </main>
    );
  }
  if (error) return <main><p className="fail">{error}</p></main>;
  if (!report) return <main><p className="muted">상세 리포트 불러오는 중…</p></main>;

  const summary = report.summary || {};
  const decision = report.coaching_decision || report.vocal_function_profile?.coaching_decision || {};
  const vf = report.vocal_function_profile || {};
  const dims = vf.dimensions || [];
  const focus = report.focus_segments || [];
  const observationFocus = report.observation_segments || [];
  const showProblemFocus = report.show_problem_focus !== false && focus.length > 0;
  const showTraining = report.show_corrective_training !== false && (report.training_plan || []).length > 0;
  const maintenance = report.maintenance_plan || [];
  const supplement = report.performance_supplement || {};
  const suppAreas = supplement.areas || report.areas || [];
  const extraMeasure = report.additional_measurements || [];
  const primary = decision.primary_bottleneck;
  const preserve = decision.preserve || [];
  const modify = decision.modify || [];
  const whyStruct = decision.why_structured || {};
  const why = decision.why || [];
  const measureCands = decision.measurement_candidates || decision.needs_confirmation || extraMeasure || [];
  const bestSelf = decision.best_self_reference;
  const targetEp = decision.target_episode;
  const coreSpan = targetEp?.core_evidence_span;
  const criteriaMatrix = report.criteria_matrix || vf.criteria_matrix || [];
  const candidateComparison = decision.candidate_comparison || [];
  const vocalType = report.vocal_type_profile || vf.vocal_type_profile;

  function playEpisode(ev: any) {
    const raw = Number(ev?.original_start_sec ?? ev?.start_sec);
    if (Number.isNaN(raw)) return;
    seekTo(audioRef.current, Math.max(0, raw - 0.7));
  }

  function toggleCriteria(idKey: string) {
    setOpenCriteria((prev) => ({ ...prev, [idKey]: !prev[idKey] }));
  }

  return (
    <main>
      <Link className="muted" to={`/result/${id}`}>← 무료 결과</Link>
      <h1 className="brand" style={{ fontSize: '1.6rem', marginTop: 12 }}>
        {summary.title || '오늘의 코칭'}
      </h1>
      <p className="lead">{summary.text || decision.headline}</p>
      {(vf.quality_badge || report.quality_badge) && (
        <p className="muted" style={{ fontSize: '0.9rem' }}>
          {vf.quality_badge || report.quality_badge}
        </p>
      )}
      {(vf.quality_badge_note || report.quality_badge_note) && (
        <p className="muted" style={{ fontSize: '0.85rem' }}>
          {vf.quality_badge_note || report.quality_badge_note}
        </p>
      )}
      {vf.separation_note && (
        <p className="muted" style={{ fontSize: '0.85rem' }}>{vf.separation_note}</p>
      )}

      <VocalTypeCard profile={vocalType} />

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>가장 먼저 바꿔볼 부분</h3>
        {!primary && (
          <p className="muted">
            {decision.no_primary_message
              || '이번 녹음에서는 우선적으로 교정해야 할 뚜렷한 기능적 병목은 찾지 못했어요.'}
          </p>
        )}
        {(modify.length ? modify : primary ? [{ label: primary.user_title, why: primary.why }] : []).map(
          (m: any, i: number) => (
            <div key={i} style={{ marginBottom: 12 }}>
              <div className="area-row">
                <span>{m.label || primary?.user_title}</span>
                <strong>MODIFY</strong>
              </div>
              <p className="muted" style={{ margin: '4px 0' }}>{m.why || primary?.why}</p>
            </div>
          ),
        )}
        {primary?.satisfied_criteria?.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <p style={{ marginBottom: 4 }}><strong>이 병목이 선택된 판단 기준</strong></p>
            <ul className="muted" style={{ margin: 0, paddingLeft: 18 }}>
              {primary.satisfied_criteria.map((c: any, i: number) => (
                <li key={i}>✓ {c.label}</li>
              ))}
            </ul>
            {primary.criteria_user_summary && (
              <p className="muted" style={{ fontSize: '0.85rem', marginTop: 6 }}>
                {primary.criteria_user_summary}
              </p>
            )}
          </div>
        )}
      </div>

      {coreSpan && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>
            {coreSpan.label || targetEp?.core_label || '핵심 구간'}
          </h3>
          <p className="muted" style={{ fontSize: '0.9rem' }}>
            문제 phrase 전체보다 실제 evidence가 모인 구간을 먼저 들어보세요.
          </p>
          <div className="area-row">
            <span>
              {Number(coreSpan.original_start_sec ?? coreSpan.start_sec).toFixed(1)}s –{' '}
              {Number(coreSpan.original_end_sec ?? coreSpan.end_sec).toFixed(1)}s
              {targetEp?.start_sec != null && (
                <span className="muted">
                  {' '}
                  (phrase {Number(targetEp.original_start_sec ?? targetEp.start_sec).toFixed(1)}–
                  {Number(targetEp.original_end_sec ?? targetEp.end_sec).toFixed(1)})
                </span>
              )}
            </span>
            <button
              type="button"
              className="btn secondary"
              style={{ fontSize: '0.8rem', padding: '6px 10px' }}
              onClick={() => playEpisode(coreSpan)}
            >
              듣기
            </button>
          </div>
        </div>
      )}

      {showProblemFocus ? (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>문제 구간 듣기</h3>
          <audio ref={audioRef} src={blobUrl || previewUrl} controls style={{ width: '100%' }} />
          {focus.map((ev: any, i: number) => (
            <div key={i} style={{ marginTop: 12 }}>
              <div className="area-row">
                <span>
                  {ev.time_label
                    || (ev.original_start_sec != null
                      ? `${Number(ev.original_start_sec).toFixed(1)}s – ${Number(ev.original_end_sec ?? ev.original_start_sec).toFixed(1)}s`
                      : `${Number(ev.start_sec).toFixed(1)}s – ${Number(ev.end_sec).toFixed(1)}s`)}
                  {ev.headline ? ` · ${ev.headline}` : ''}
                </span>
                <button
                  type="button"
                  className="btn secondary"
                  style={{ fontSize: '0.8rem', padding: '6px 10px' }}
                  onClick={() => playEpisode(ev)}
                >
                  듣기
                </button>
              </div>
              <p className="muted" style={{ margin: '4px 0' }}>
                {ev.user_message || ev.what_user_may_hear}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <audio ref={audioRef} src={blobUrl || previewUrl} controls style={{ width: '100%', marginBottom: 12 }} />
      )}

      {observationFocus.length > 0 && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>참고해서 들어볼 구간</h3>
          <p className="muted" style={{ fontSize: '0.9rem' }}>
            추가로 관찰된 음질 구간이며, 교정 우선순위(문제 구간)가 아닙니다.
          </p>
          {observationFocus.map((ev: any, i: number) => (
            <div key={i} style={{ marginTop: 12 }}>
              <div className="area-row">
                <span>
                  {ev.time_label
                    || `${Number(ev.start_sec).toFixed(1)}s – ${Number(ev.end_sec).toFixed(1)}s`}
                  {ev.headline ? ` · ${ev.headline}` : ''}
                </span>
                <button
                  type="button"
                  className="btn secondary"
                  style={{ fontSize: '0.8rem', padding: '6px 10px' }}
                  onClick={() => playEpisode(ev)}
                >
                  듣기
                </button>
              </div>
              <p className="muted" style={{ margin: '4px 0' }}>
                {ev.user_message || ev.what_user_may_hear}
              </p>
            </div>
          ))}
        </div>
      )}

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>지금 유지할 부분</h3>
        {preserve.length === 0 && <p className="muted">표시할 유지 항목이 없어요.</p>}
        {preserve.map((p: any) => (
          <div key={p.id} style={{ marginBottom: 8 }}>
            <div className="area-row">
              <span>✓ {p.label}</span>
              <strong>PRESERVE</strong>
            </div>
            {p.why && <p className="muted" style={{ margin: '2px 0', fontSize: '0.9rem' }}>{p.why}</p>}
          </div>
        ))}
      </div>

      {bestSelf && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>비교해서 들어볼 잘 된 구간</h3>
          <p className="muted">{bestSelf.coaching_hint}</p>
          <button
            type="button"
            className="btn secondary"
            style={{ fontSize: '0.8rem', padding: '6px 10px' }}
            onClick={() => playEpisode(bestSelf)}
          >
            듣기
          </button>
        </div>
      )}

      {(whyStruct.supporting?.length || why.length > 0) && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>왜 그렇게 판단했나요?</h3>
          {whyStruct.scope_note && (
            <p className="muted" style={{ marginBottom: 8 }}>{whyStruct.scope_note}</p>
          )}
          {whyStruct.supporting?.length ? (
            <>
              <p style={{ marginBottom: 4 }}><strong>문제 근거</strong></p>
              <ul className="muted">
                {whyStruct.supporting.map((w: any, i: number) => (
                  <li key={`s-${i}`}>
                    {whyText(w)}
                    {whyScope(w) ? (
                      <span className="muted" style={{ fontSize: '0.8rem' }}> · {whyScope(w)}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            why.map((w: string, i: number) => (
              <p key={i} className="muted" style={{ margin: '6px 0' }}>{w}</p>
            ))
          )}
          {whyStruct.preserved?.length > 0 && (
            <>
              <p style={{ marginBottom: 4 }}><strong>유지된 부분</strong></p>
              <ul className="muted">
                {whyStruct.preserved.map((w: any, i: number) => (
                  <li key={`p-${i}`}>
                    {whyText(w)}
                    {whyScope(w) ? (
                      <span className="muted" style={{ fontSize: '0.8rem' }}> · {whyScope(w)}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </>
          )}
          {(whyStruct.contradicting?.length || primary?.alternative_explanations?.length) ? (
            <>
              <p style={{ marginBottom: 4 }}><strong>다른 가능성</strong></p>
              <ul className="muted">
                {(whyStruct.contradicting || primary?.alternative_explanations || []).map(
                  (w: any, i: number) => (
                    <li key={`c-${i}`}>{whyText(w)}</li>
                  ),
                )}
              </ul>
            </>
          ) : null}
        </div>
      )}

      {showTraining ? (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>오늘의 연습</h3>
          <ul>
            {(report.training_plan || []).map((x: string, i: number) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
          {(decision.success_criteria || []).length > 0 && (
            <>
              <p className="muted" style={{ marginTop: 8 }}>성공 기준</p>
              <ul className="muted">
                {(decision.success_criteria || []).map((x: string, i: number) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      ) : maintenance.length > 0 ? (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>유지용 루틴</h3>
          <p className="muted" style={{ fontSize: '0.9rem' }}>
            교정 연습이 아니라 유지용 루틴이에요.
          </p>
          <ul>
            {maintenance.map((x: string, i: number) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {measureCands.length > 0 && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>추가로 확인하면 좋은 부분</h3>
          {measureCands.map((m: any, i: number) => (
            <div key={i} style={{ marginBottom: 8 }}>
              <p className="muted" style={{ margin: 0 }}>
                {m.issue || m.title || '추가 측정'} — {m.reason || m.user_message || ''}
              </p>
              {m.recommended_task && (
                <p className="muted" style={{ fontSize: '0.85rem', margin: '2px 0' }}>
                  추천 과제: {m.recommended_task}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>성대 작동 프로필</h3>
        {dims.length === 0 && (
          <p className="muted">메인 카드에 올릴 만큼 충분한 항목이 제한적이에요. 아래 전체 기준표를 보세요.</p>
        )}
        {dims.map((d: any) => {
          const matrixRow = criteriaMatrix.find((r: any) => r.dimension_id === d.dimension_id);
          const open = !!openCriteria[d.dimension_id];
          return (
            <div key={d.dimension_id} style={{ marginBottom: 18 }}>
              <div className="area-row">
                <span>{d.display_name}</span>
                <strong>{d.continuum_label || d.status_label || d.prevalence_label}</strong>
              </div>
              {d.dimension_id === 'glottal_contact_profile' && d.continuum_0_to_1 != null && (
                <ContactContinuum value={d.continuum_0_to_1} />
              )}
              {d.profile && d.dimension_id === 'resonance_formant_strategy' ? (
                <ul className="muted" style={{ margin: '6px 0', paddingLeft: 18 }}>
                  <li>밝기: {d.profile.brightness}</li>
                  <li>중역 존재감: {d.profile.mid_presence}</li>
                </ul>
              ) : (
                <p className="muted" style={{ margin: '4px 0' }}>{d.summary}</p>
              )}
              {d.what_it_may_mean && (
                <p className="muted" style={{ margin: '4px 0', fontSize: '0.9rem' }}>
                  {d.what_it_may_mean}
                </p>
              )}
              {matrixRow && (
                <button
                  type="button"
                  className="btn secondary"
                  style={{ fontSize: '0.75rem', padding: '4px 8px', marginTop: 4 }}
                  onClick={() => toggleCriteria(d.dimension_id)}
                >
                  판단 기준 보기 {open ? '▴' : '▾'}
                </button>
              )}
              {open && matrixRow && (
                <ul className="muted" style={{ marginTop: 8, paddingLeft: 18, fontSize: '0.85rem' }}>
                  {(matrixRow.criteria || []).map((c: any) => (
                    <li key={c.criterion_id}>
                      <CriterionAvailMark availability={c.availability} /> {c.label}
                      {' · '}
                      {c.availability === 'SUFFICIENT' ? '충분'
                        : c.availability === 'NOT_AVAILABLE' ? '측정 불가' : '부족'}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>

      {criteriaMatrix.length > 0 && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>전체 발성 판단 기준</h3>
          <p className="muted" style={{ fontSize: '0.85rem' }}>
            {report.criteria_matrix_note
              || vf.criteria_matrix_note
              || '기준 충족/미충족은 측정 근거 충분 여부이며 발성 좋고 나쁨이 아닙니다.'}
          </p>
          {criteriaMatrix.map((row: any) => {
            const open = !!openCriteria[`matrix:${row.dimension_id}`];
            return (
              <div key={row.dimension_id} style={{ marginBottom: 14, borderTop: '1px solid rgba(0,0,0,0.06)', paddingTop: 10 }}>
                <div className="area-row">
                  <span>{row.display_name}</span>
                  <strong>{row.finding_label}</strong>
                </div>
                <p className="muted" style={{ margin: '4px 0', fontSize: '0.85rem' }}>
                  판단 근거: {row.measurement_sufficiency_label}
                  {' · '}
                  교정 우선순위: {row.coaching_eligibility_label}
                </p>
                <p className="muted" style={{ margin: '2px 0', fontSize: '0.85rem' }}>{row.summary}</p>
                <button
                  type="button"
                  className="btn secondary"
                  style={{ fontSize: '0.75rem', padding: '4px 8px' }}
                  onClick={() => toggleCriteria(`matrix:${row.dimension_id}`)}
                >
                  세부 기준 {open ? '▴' : '▾'}
                </button>
                {open && (
                  <ul className="muted" style={{ marginTop: 8, paddingLeft: 18, fontSize: '0.85rem' }}>
                    {(row.criteria || []).map((c: any) => (
                      <li key={c.criterion_id}>
                        <CriterionAvailMark availability={c.availability} /> {c.label}
                        {' · '}
                        {c.availability === 'SUFFICIENT' ? '충분'
                          : c.availability === 'NOT_AVAILABLE' ? '측정 불가' : '부족'}
                        {c.direction && c.direction !== 'NEUTRAL' ? ` (${c.direction})` : ''}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}

      {candidateComparison.length > 0 && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>Primary 후보 비교</h3>
          <p className="muted" style={{ fontSize: '0.85rem' }}>
            다른 항목이 부족해서 자동으로 1위가 되지 않도록, 각 후보의 기준 충족을 비교합니다.
          </p>
          {candidateComparison.map((c: any, i: number) => (
            <div key={i} className="area-row" style={{ marginBottom: 6 }}>
              <span>
                {c.label || c.bottleneck_id}
                <span className="muted" style={{ fontSize: '0.8rem' }}>
                  {' '}· 기준 {c.criterion_coverage || '—'} · {c.measurement_sufficiency}
                </span>
              </span>
              <strong style={{ fontSize: '0.85rem' }}>
                {c.coaching_eligible ? 'ELIGIBLE' : (c.coaching_eligibility || 'NO')}
              </strong>
            </div>
          ))}
        </div>
      )}

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>{supplement.title || '보조 가창 분석'}</h3>
        <p className="muted">{supplement.note || '가창 참고 정보입니다.'}</p>
        {suppAreas.map((a: any) => (
          <div key={a.area_id} style={{ marginBottom: 12 }}>
            <div className="area-row">
              <span>{a.display_name}</span>
              <ScoreLine score={a.score} label={a.status_label || a.status} />
            </div>
            {a.headline && <p className="muted" style={{ margin: '4px 0' }}>{a.headline}</p>}
          </div>
        ))}
      </div>

      {extraMeasure.length > 0 && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>추가 정밀 측정</h3>
          <ul className="muted">
            {extraMeasure.map((m: any, i: number) => (
              <li key={i}>{m.reason}: {(m.tasks || []).join(', ')}</li>
            ))}
          </ul>
        </div>
      )}

      {/* unknown_footer is included in limitations — avoid double display */}

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>한계</h3>
        <ul className="muted">
          {(report.limitations || []).map((x: string, i: number) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
        <p className="muted" style={{ fontSize: '0.85rem' }}>{report.disclaimer}</p>
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>{report.upgrade?.title || '정밀 진단'}</h3>
        <p className="muted">{report.upgrade?.body}</p>
        <button
          type="button"
          className="btn"
          onClick={() => nav(`/premium?analysisId=${id}&product=${diagProduct}`)}
        >
          {report.upgrade?.cta || '정밀 발성 진단'} ({diagPrice})
        </button>
      </div>
    </main>
  );
}
