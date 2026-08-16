import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  getAnalysis,
  getProducts,
  mockUnlockSongDetail,
  patchHistory,
  postVocalGoalProgress,
  postVocalProgressInsight,
  postVocalSnapshot,
  putActiveVocalGoal,
  removeHistory,
  saveSongDetailUnlock,
} from '../api/client';
import GoalSelectorSheet from '../components/progress/GoalSelectorSheet';
import ProgressInsightSheet from '../components/progress/ProgressInsightSheet';
import TodayPhonationSummary from '../components/progress/TodayPhonationSummary';
import VocalTypeHero from '../components/report/VocalTypeHero';
import VocalProfile from '../components/report/VocalProfile';
import PremiumProductCard from '../components/ui/PremiumProductCard';
import {
  classifyDiagnosticOffer,
  diagnosticOfferBullets,
  pickDiagnosticOffer,
} from '../lib/diagnosticOffer';
import {
  buildLocalGoalProgress,
  type GoalProgressPayload,
} from '../lib/goalProgress';
import {
  getLocalActiveGoal,
  setLocalActiveGoal,
} from '../lib/localGoalStore';
import {
  listLocalVocalSnapshots,
  upsertLocalVocalSnapshot,
} from '../lib/localVocalHistory';
import {
  buildLocalProgressInsight,
  buildTodayHighlights,
  extractCanonicalFromResult,
  type ProgressCard,
  type ProgressInsightPayload,
} from '../lib/progressPresentation';
import { diagnosisFromPrimary, NO_PRIMARY_MESSAGE, sanitizeDisclaimer } from '../lib/reportPresentation';

export default function Result() {
  const { id } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState<any>(null);
  const [products, setProducts] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const [busyDetail, setBusyDetail] = useState(false);
  const [insight, setInsight] = useState<ProgressInsightPayload | null>(null);
  const [sheetCard, setSheetCard] = useState<ProgressCard | null>(null);
  const [goalProgress, setGoalProgress] = useState<GoalProgressPayload | null>(null);
  const [sheetMode, setSheetMode] = useState<'card' | 'goal'>('card');
  const [goalPickerOpen, setGoalPickerOpen] = useState(false);
  const [goalTick, setGoalTick] = useState(0);

  useEffect(() => {
    if (!id) return;
    Promise.all([getAnalysis(id), getProducts(id)])
      .then(([job, catalog]) => {
        if (!job.result) {
          setExpired(true);
          return;
        }
        setData(job.result);
        setProducts(catalog);
        const access = job.result.access || {};
        if (access.song_detail_unlocked) {
          patchHistory(id, { songDetailUnlocked: true });
        }
        if (access.diagnostic_session_id) {
          patchHistory(id, { sessionId: access.diagnostic_session_id });
        }
        const vt = job.result.vocal_type_teaser || job.result.vocal_type_profile;
        if (vt?.display_name) {
          patchHistory(id, { vocalType: vt.display_name });
        }
      })
      .catch(() => {
        setExpired(true);
        setError('분석 기록이 만료됐어요.');
      });
  }, [id]);

  useEffect(() => {
    if (!id || !data?.score?.available) return;
    const canonical = extractCanonicalFromResult(data);
    if (!Object.keys(canonical).length) {
      setInsight({
        status: 'NO_BASELINE',
        insight_available: false,
        today: [],
        improved: [],
        changed: [],
        maintained: [],
        note: '이번 녹음의 핵심 축을 아직 충분히 읽지 못했어요.',
      });
      setGoalProgress({ status: 'NO_GOAL', uses_fake_percent: false });
      return;
    }

    const active = getLocalActiveGoal();
    upsertLocalVocalSnapshot({
      analysis_id: id,
      created_at: new Date().toISOString(),
      canonical,
      analyzer_version: data.analysis_version || data.score?.version || null,
      goal: active?.goal_focus || null,
      goal_id: active?.id || null,
      goal_focus: active?.goal_focus || null,
    });

    let cancelled = false;
    (async () => {
      const today = buildTodayHighlights(canonical);
      void postVocalSnapshot({
        analysis_id: id,
        canonical,
        analyzer_version: data.analysis_version || null,
        goal: active || null,
        goal_id_at_analysis: active?.id || null,
        goal_focus_at_analysis: active?.goal_focus || null,
      });

      const server = await postVocalProgressInsight({
        current_canonical: canonical,
        goal: active
          ? {
              focus: active.goal_focus,
              label: active.goal_label,
              source: active.source,
              target: active.target,
              style_id: active.style_id,
              kind: active.kind,
              id: active.id,
              started_at: active.started_at,
            }
          : null,
        recent_n: 5,
        exclude_analysis_id: id,
        today_highlights: today,
      });
      if (cancelled) return;

      const histSnaps = listLocalVocalSnapshots(id);
      const hist = histSnaps.map((s) => ({
        canonical: s.canonical,
        created_at: s.created_at,
        goal_id: s.goal_id || undefined,
      }));

      if (server?.insight_available) {
        setInsight({ ...server, source: 'server', today: server.today?.length ? server.today : today });
      } else {
        setInsight(
          buildLocalProgressInsight(canonical, hist.map((h) => ({ canonical: h.canonical })), {
            goal: active?.goal_focus || null,
            recentN: 5,
          }),
        );
      }

      const serverGp = server?.goal_progress;
      if (serverGp && serverGp.status !== 'NO_GOAL' && serverGp.window) {
        setGoalProgress(serverGp);
      } else if (active) {
        const posted = await postVocalGoalProgress({
          current_canonical: canonical,
          historical: histSnaps.map((s) => ({
            canonical_json: s.canonical,
            created_at: s.created_at,
            goal_id_at_analysis: s.goal_id || undefined,
          })),
          recent_n: 5,
          goal: active,
        });
        setGoalProgress(
          posted && posted.status !== 'NO_GOAL'
            ? posted
            : buildLocalGoalProgress(active, hist, { recentN: 5, current: canonical }),
        );
      } else {
        setGoalProgress({ status: 'NO_GOAL', uses_fake_percent: false });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [id, data, goalTick]);

  async function onSelectGoal(
    focus: string,
    label: string,
    extra?: { target?: string; style_id?: string; kind?: string },
  ) {
    setLocalActiveGoal({
      focus,
      label,
      source: 'USER_SELECTED',
      target: extra?.target,
      style_id: extra?.style_id,
    });
    void putActiveVocalGoal({
      focus,
      label,
      source: 'USER_SELECTED',
      target: extra?.target,
      style_id: extra?.style_id,
    });
    setGoalTick((n) => n + 1);
  }

  async function buySongDetail() {
    if (!id) return;
    setBusyDetail(true);
    setError(null);
    try {
      await mockUnlockSongDetail(id);
      saveSongDetailUnlock(id);
      nav(`/result/${id}/detail`);
    } catch (e: any) {
      setError(e?.message || '상세 리포트 해제 실패');
      setBusyDetail(false);
    }
  }

  const freeDims = useMemo(() => {
    if (!data) return null;
    return (
      data.vocal_function_teaser_dimensions
      || data.vocal_function_profile?.dimensions
      || data.dimensions
      || null
    );
  }, [data]);

  if (expired) {
    return (
      <main>
        <h1 className="brand" style={{ fontSize: '1.6rem' }}>분석 기록이 만료됐어요</h1>
        <p className="lead">서버에서 결과를 찾을 수 없어요. 다시 녹음해 주세요.</p>
        {id && (
          <button
            className="btn secondary"
            style={{ marginBottom: 12, width: '100%' }}
            onClick={() => {
              removeHistory(id);
              window.location.href = '/history';
            }}
          >
            기록에서 삭제
          </button>
        )}
        <Link className="btn" to="/record">다시 녹음</Link>
      </main>
    );
  }

  if (error && !data) {
    return (
      <main>
        <p className="fail">{error}</p>
        <Link to="/">홈</Link>
      </main>
    );
  }
  if (!data) {
    return (
      <main>
        <p className="muted">불러오는 중…</p>
        <div className="skeleton" />
        <div className="skeleton" style={{ height: 72 }} />
      </main>
    );
  }

  const score = data.score || {};
  const access = data.access || {};
  const prodMap = products?.products || {};
  const songPrice = prodMap.song_detail?.display_amount || '₩1,000';
  const diagOfferKey = products?.offers?.diagnostic || 'diagnostic_full';
  const diagPrice = prodMap[diagOfferKey]?.display_amount || '₩2,000';
  const songUnlocked = !!access.song_detail_unlocked;
  const diagUnlocked = !!access.diagnostic_unlocked;
  const sessionId = access.diagnostic_session_id || null;

  const diagOffer = pickDiagnosticOffer(data);
  const diagDecision = classifyDiagnosticOffer(diagOffer);
  const needsDiagnostic = diagDecision === 'required';
  const diagBullets = diagnosticOfferBullets(diagOffer);

  const vocalType =
    data.vocal_type_teaser
    || data.vocal_type_profile
    || null;

  const findingTeaser = data.main_finding_teaser || null;
  const primaryForUi =
    findingTeaser && !findingTeaser.none && (findingTeaser.id || findingTeaser.user_title)
      ? findingTeaser
      : null;

  const mapped = diagnosisFromPrimary(primaryForUi);
  const noPrimaryTitle =
    findingTeaser?.none
      ? (findingTeaser.title || '이번 녹음에서는 두드러진 발성 문제는 보이지 않았어요.')
      : null;

  let fallbackFinding: { title: string; detail: string } | null = null;
  if (!mapped && !noPrimaryTitle) {
    const teaser = (data.vocal_function_teaser || data.vocal_quality_teaser || [])[0];
    if (teaser) {
      fallbackFinding = {
        title: String(teaser).replace(/^먼저 살펴볼 후보:\s*/, '').replace(/\.$/, ''),
        detail: '',
      };
    }
  }

  return (
    <main>
      <Link className="muted" to="/">‹ 홈</Link>
      <p className="page-kicker" style={{ marginTop: 14 }}>무료 보컬 리포트</p>
      <h1 className="brand" style={{ fontSize: '1.4rem', marginBottom: 4 }}>
        오늘의 발성
      </h1>
      <p className="lead" style={{ marginBottom: 8 }}>
        현재 상태를 보고, 이전과 달라진 점과 다음 연습을 이어가요.
      </p>

      {!score.available ? (
        <section className="section">
          <h2 className="type-title" style={{ fontSize: '1.35rem' }}>이번 녹음은 안정적으로 분석하기 어려워요</h2>
          <p className="lead">{data.quality?.user_message}</p>
          <Link className="btn" to="/record">다시 녹음하기</Link>
        </section>
      ) : (
        <>
          <VocalTypeHero profile={vocalType || { available: false }} compact />

          {mapped || fallbackFinding ? (
            <section className="section">
              <h3 className="section-title">가장 두드러진 특징</h3>
              <div className="card">
                <p className="finding-title">
                  {(mapped || fallbackFinding)!.title}
                </p>
                {(mapped || fallbackFinding)!.detail ? (
                  <p className="body-text muted">{(mapped || fallbackFinding)!.detail}</p>
                ) : null}
              </div>
            </section>
          ) : (
            <section className="section">
              <h3 className="section-title">가장 두드러진 특징</h3>
              <div className="card">
                <p className="finding-title" style={{ fontSize: '1.05rem' }}>
                  {noPrimaryTitle || NO_PRIMARY_MESSAGE}
                </p>
              </div>
            </section>
          )}

          {insight ? (
            <TodayPhonationSummary
              insight={insight}
              onOpenCard={(card) => {
                setSheetMode('card');
                setSheetCard(card);
              }}
              goalProgress={goalProgress}
              onOpenGoalInsight={() => {
                setSheetMode('goal');
                setSheetCard(null);
              }}
              onSetGoal={() => setGoalPickerOpen(true)}
              onChangeGoal={() => setGoalPickerOpen(true)}
            />
          ) : null}

          {freeDims ? (
            <VocalProfile
              dimensions={freeDims}
              criteriaMatrix={data.criteria_matrix || []}
              title="발성 프로필"
              showConfidence={false}
            />
          ) : null}

          <section className="section" style={{ borderBottom: 0 }}>
            <h3 className="section-title">더 자세히 볼까요?</h3>
            <div className="upsell-stack">
              {songUnlocked ? (
                <PremiumProductCard
                  badge="이용 가능"
                  title="상세 리포트"
                  description="이미 분석된 노래를 더 자세히 살펴봅니다."
                  bullets={['5축 발성 프로필', '추가 관찰 특징', '직접 들어볼 주요 구간']}
                  ctaLabel="상세 리포트 보기"
                  to={`/result/${id}/detail`}
                />
              ) : (
                <PremiumProductCard
                  badge="상세 분석"
                  title="상세 리포트"
                  description="이미 분석된 노래를 더 자세히 살펴봅니다."
                  priceLabel={songPrice}
                  bullets={['5축 발성 프로필', '추가 관찰 특징', '직접 들어볼 주요 구간']}
                  ctaLabel={`상세 리포트 보기 · ${songPrice}`}
                  onClick={buySongDetail}
                  busy={busyDetail}
                />
              )}

              {diagUnlocked && sessionId ? (
                <PremiumProductCard
                  badge="이용 가능"
                  featured={needsDiagnostic}
                  title="정밀 발성 진단"
                  description="추가 녹음으로 확인한 정밀 진단 결과를 볼 수 있어요."
                  bullets={diagBullets.length ? diagBullets : ['정밀 진단 결과 열람']}
                  ctaLabel="정밀 진단 보기"
                  to={`/diagnostic/${sessionId}/report`}
                />
              ) : (
                <PremiumProductCard
                  badge="가장 정밀한 분석"
                  featured={needsDiagnostic}
                  title="정밀 발성 진단"
                  description="현재 노래와 짧은 추가 녹음을 함께 분석해 발성 특성을 더 정밀하게 확인해요."
                  priceLabel={diagPrice}
                  bullets={
                    diagBullets.length
                      ? diagBullets
                      : [
                          '몇 가지 짧은 추가 녹음',
                          '고민이 있으면 고민 중심, 없으면 전체 발성 특성',
                          diagOfferKey === 'diagnostic_upgrade'
                            ? '상세 리포트 보유 시 업그레이드'
                            : '상세 리포트 포함',
                        ]
                  }
                  ctaLabel={`정밀 진단 시작 · ${diagPrice}`}
                  to={`/premium?analysis=${id || ''}&product=${diagOfferKey}`}
                  footer="상세 리포트는 이 노래만의 분석이에요. 정밀 진단은 추가 녹음이 포함됩니다."
                />
              )}
            </div>
          </section>

          <ProgressInsightSheet
            open={sheetMode === 'goal' ? !!goalProgress?.goal : !!sheetCard}
            card={sheetCard}
            goalProgress={goalProgress}
            mode={sheetMode}
            onClose={() => {
              setSheetCard(null);
              setSheetMode('card');
            }}
          />
          <GoalSelectorSheet
            open={goalPickerOpen}
            onClose={() => setGoalPickerOpen(false)}
            onSelect={onSelectGoal}
          />
        </>
      )}

      {error && <p className="fail">{error}</p>}
      <p className="footer-note">{sanitizeDisclaimer(data.disclaimer)}</p>
    </main>
  );
}
