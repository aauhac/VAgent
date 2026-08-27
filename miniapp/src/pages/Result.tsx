import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  getAnalysis,
  getAnalysisAccess,
  getProducts,
  patchHistory,
  postVocalProgressInsight,
  postVocalSnapshot,
  saveSongDetailUnlock,
} from '../api/client';
import ProgressInsightSheet from '../components/progress/ProgressInsightSheet';
import TodayPhonationSummary from '../components/progress/TodayPhonationSummary';
import VocalTypeHero from '../components/report/VocalTypeHero';
import PremiumProductCard from '../components/ui/PremiumProductCard';
import {
  classifyDiagnosticOffer,
  diagnosticDurationNote,
  diagnosticOfferBullets,
  pickDiagnosticOffer,
} from '../lib/diagnosticOffer';
import { getLocalActiveGoal } from '../lib/localGoalStore';
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
import { presentCoreFinding, sanitizeDisclaimer } from '../lib/reportPresentation';
import { buyProduct } from '../lib/tossIap';
import { PRICE_LOADING_LABEL, PRICE_UNAVAILABLE_LABEL } from '../lib/iapCatalog';
import { useIapProductPrices } from '../lib/useIapProductPrices';
import { useRewardedDetailUnlock } from '../lib/useRewardedDetailUnlock';

export default function Result() {
  const { id } = useParams();
  const nav = useNavigate();
  const location = useLocation();
  const [data, setData] = useState<any>(null);
  const [products, setProducts] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const lastOfferTrace = useRef<string>('');
  const [busyDetail, setBusyDetail] = useState(false);
  const [insight, setInsight] = useState<ProgressInsightPayload | null>(null);
  const [sheetCard, setSheetCard] = useState<ProgressCard | null>(null);
  const { prices: iapPrices, reload: reloadIapPrices, paymentsEnabled } = useIapProductPrices(products);
  const songUnlockedEarly = !!data?.access?.song_detail_unlocked;
  const rewarded = useRewardedDetailUnlock(id, songUnlockedEarly);

  useEffect(() => {
    if (!id) return;
    // The report and the commerce catalog are independent. A catalog outage must not
    // turn a healthy analysis into "분석 기록이 만료됐어요".
    getProducts(id)
      .then((catalog) => setProducts(catalog))
      .catch(() => setProducts(null));
    getAnalysis(id)
      .then((job) => {
        if (!job.result) {
          setExpired(true);
          return;
        }
        setData(job.result);
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
    const st = location.state as { focusOffer?: string } | null;
    if (st?.focusOffer !== 'song_detail' || !data) return;
    const t = window.setTimeout(() => {
      document.getElementById('offer-song-detail')?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }, 120);
    return () => window.clearTimeout(t);
  }, [location.state, data]);

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

      const hist = listLocalVocalSnapshots(id).map((s) => ({
        canonical: s.canonical,
        created_at: s.created_at,
        goal_id: s.goal_id || undefined,
      }));

      if (server?.insight_available) {
        setInsight({
          ...server,
          source: 'server',
          today: server.today?.length ? server.today : today,
          // Cap free progress cards
          improved: (server.improved || []).slice(0, 1),
          changed: (server.changed || []).slice(0, 1),
          maintained: (server.maintained || []).slice(0, 1),
        });
      } else {
        setInsight(
          buildLocalProgressInsight(canonical, hist.map((h) => ({ canonical: h.canonical })), {
            goal: active?.goal_focus || null,
            recentN: 5,
          }),
        );
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [id, data]);

  /** Re-read entitlements from the server and fold them into the rendered access block. */
  async function reloadAccess() {
    if (!id) return;
    const access = await getAnalysisAccess(id).catch(() => null);
    if (!access) return;
    setData((prev: any) =>
      prev
        ? {
            ...prev,
            access: {
              ...(prev.access || {}),
              song_detail_unlocked: Boolean(access.song_detail_unlocked),
              diagnostic_unlocked: Boolean(access.diagnostic_unlocked),
              diagnostic_session_id: access.diagnostic_session_id ?? null,
            },
          }
        : prev,
    );
  }

  async function buySongDetail() {
    if (!id) return;
    if (!iapPrices.song_detail?.canPurchase) {
      reloadIapPrices();
      return;
    }
    setBusyDetail(true);
    setError(null);
    try {
      const iap = await buyProduct({ productId: 'song_detail', resourceId: id });
      if (iap.ok) {
        // Confirm with the server before navigating; a local flag is not a receipt.
        const access = await getAnalysisAccess(id).catch(() => null);
        if (!access?.song_detail_unlocked) {
          setError('결제 상태를 확인하고 있어요. 다시 앱을 열어도 이어서 확인할 수 있어요.');
          setBusyDetail(false);
          return;
        }
        saveSongDetailUnlock(id);
        nav(`/result/${id}/detail`);
        return;
      }
      if (iap.state === 'CANCELLED') {
        // Nothing was granted; re-read so the CTA cannot drift into an unlocked look.
        await reloadAccess();
        setBusyDetail(false);
        return;
      }
      if (!import.meta.env.PROD && (iap.message || '').includes('토스 앱')) {
        const { mockUnlockSongDetail } = await import('../api/devMocks');
        await mockUnlockSongDetail(id);
        saveSongDetailUnlock(id);
        nav(`/result/${id}/detail`);
        return;
      }
      setError(iap.message || '결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.');
      setBusyDetail(false);
    } catch (e: any) {
      setError(e?.message || '결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.');
      setBusyDetail(false);
    }
  }

  async function unlockViaRewardedAd() {
    if (!id) return;
    setError(null);
    const result = await rewarded.watchAndUnlock();
    if (result === 'unlocked') {
      saveSongDetailUnlock(id);
      patchHistory(id, { songDetailUnlocked: true });
      setData((prev: any) =>
        prev
          ? {
              ...prev,
              access: {
                ...(prev.access || {}),
                song_detail_unlocked: true,
              },
            }
          : prev,
      );
      nav(`/result/${id}/detail`);
    }
  }

  const coreAxes = useMemo(() => {
    if (!data) return [];
    return buildTodayHighlights(extractCanonicalFromResult(data)).slice(0, 3);
  }, [data]);

  if (expired) {
    return (
      <main>
        <h1 className="brand" style={{ fontSize: '1.6rem' }}>분석 기록이 만료됐어요</h1>
        <p className="lead">서버에서 결과를 찾을 수 없어요. 다시 녹음해 주세요.</p>
        {id && (
          <Link className="btn secondary" to="/history" style={{ marginBottom: 12, width: '100%' }}>
            분석 기록으로
          </Link>
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
  const diagOfferKey = products?.offers?.diagnostic || 'diagnostic_full';
  const songPrice = iapPrices.song_detail;
  const diagPrice = iapPrices[diagOfferKey];
  const songPriceLabel = songPrice?.label || PRICE_LOADING_LABEL;
  const diagPriceLabel = diagPrice?.label || PRICE_LOADING_LABEL;
  const songCanBuy = paymentsEnabled && !!songPrice?.canPurchase;
  const diagCanBuy = paymentsEnabled && !!diagPrice?.canPurchase;
  const songUnlocked = !!access.song_detail_unlocked;
  const diagUnlocked = !!access.diagnostic_unlocked;
  const sessionId = access.diagnostic_session_id || null;

  // The card and each option are decided separately on purpose. An ad SDK failure or a
  // commerce catalog outage may remove an OPTION, never the offer itself.
  const showLockedSongDetailOffer = !songUnlocked;
  // The ad ACTION is part of the locked-report product contract, so it renders whenever
  // the ad group is configured. `canOffer` decides whether it can be pressed — a runtime
  // SDK problem or an exhausted daily quota disables it, never hides the choice.
  const showRewardedOption = showLockedSongDetailOffer && rewarded.configured;
  const showPaidSongDetailOption = showLockedSongDetailOffer && paymentsEnabled;
  const rewardedExhausted = Boolean(
    rewarded.status && rewarded.status.remaining_today <= 0,
  );
  const rewardedBlocked =
    rewarded.loadState === 'unavailable' || rewardedExhausted || !rewarded.canOffer;
  const rewardedLabel = rewarded.busy || rewarded.loadState === 'showing'
    ? '광고 진행 중…'
    : rewarded.loadState === 'loading'
      ? '광고 준비 중…'
      : rewardedExhausted
        ? '오늘 무료 열람 소진'
        : rewarded.loadState === 'unavailable' || !rewarded.canOffer
          ? '광고 무료 열람 이용 불가'
          : rewarded.loadState === 'error'
            ? '광고 다시 시도'
            : '광고 보고 무료로 열기';

  // Why the offer looks the way it does, for on-device diagnosis. Booleans and states
  // only — never an analysis id, user key, hash, token, or order id.
  const offerTrace = [
    `score_available=${!!score.available}`,
    `song_unlocked=${songUnlocked}`,
    `payments_enabled=${paymentsEnabled}`,
    `song_can_buy=${songCanBuy}`,
    `rewarded_configured=${rewarded.configured}`,
    `rewarded_can_offer=${rewarded.canOffer}`,
    `rewarded_status_loaded=${rewarded.status != null}`,
    `rewarded_server_can_use=${rewarded.status?.can_use_rewarded_ad ?? 'unknown'}`,
    `rewarded_remaining_today=${rewarded.remainingToday ?? 'unknown'}`,
    `rewarded_load_state=${rewarded.loadState}`,
    `load_supported=${rewarded.loadSupported ?? 'unknown'}`,
    `show_supported=${rewarded.showSupported ?? 'unknown'}`,
  ].join(' ');
  if (offerTrace !== lastOfferTrace.current) {
    lastOfferTrace.current = offerTrace;
    try {
      // eslint-disable-next-line no-console
      console.info(`[DETAIL_OFFER] ${offerTrace}`);
    } catch {
      /* ignore */
    }
  }

  const diagOffer = pickDiagnosticOffer(data);
  const needsDiagnostic = classifyDiagnosticOffer(diagOffer) === 'required';
  const diagBullets = diagnosticOfferBullets(diagOffer);
  const diagDuration = diagnosticDurationNote(diagOffer);

  const vocalType =
    data.vocal_type_teaser
    || data.vocal_type_profile
    || null;

  const finding = presentCoreFinding(data);
  const coreTitle = finding.title;
  const coreDetail = finding.detail;

  return (
    <main>
      <h1 className="brand" style={{ fontSize: '1.4rem', marginBottom: 4 }}>
        오늘의 발성
      </h1>

      {!score.available ? (
        <section className="section">
          <h2 className="type-title" style={{ fontSize: '1.35rem' }}>이번 녹음은 안정적으로 분석하기 어려워요</h2>
          <p className="lead">{data.quality?.user_message}</p>
          <Link className="btn" to="/record">다시 녹음하기</Link>
        </section>
      ) : (
        <>
          <VocalTypeHero profile={vocalType || { available: false }} compact />

          <section className="section" data-testid="core-finding">
            <h3 className="section-title">이번 노래 핵심</h3>
            <p className="finding-title" style={{ marginBottom: coreAxes.length || coreDetail ? 14 : 0 }}>
              {coreTitle}
            </p>
            {coreDetail ? (
              <p className="body-text muted" style={{ marginTop: 0 }}>{coreDetail}</p>
            ) : null}
            {coreAxes.length > 0 ? (
              <ul className="progress-today-list" style={{ marginTop: 12 }}>
                {coreAxes.map((row) => (
                  <li key={row.axis} className="progress-today-row">
                    <span className="progress-today-axis">{row.title}</span>
                    <span className="progress-today-label">{row.label}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </section>

          {insight ? (
            <TodayPhonationSummary
              insight={insight}
              onOpenCard={(card) => setSheetCard(card)}
            />
          ) : null}

          <section className="section" style={{ borderBottom: 0 }}>
            <h3 className="section-title">더 알고 싶다면</h3>
            <div className="upsell-stack">
              {!showLockedSongDetailOffer ? (
                <div id="offer-song-detail" data-testid="offer-song-detail">
                  <PremiumProductCard
                    badge="열람 가능"
                    title="상세 리포트"
                    description="이 노래에서 어떤 부분이 잘 되고, 어디에서 변화가 나타나는지 실제 구간과 함께 확인해요."
                    bullets={[
                      '전체 발성 프로필과 고음·음색 분석',
                      '특징이 나타난 실제 노래 구간 듣기',
                      '이번 녹음에서 확인된 발성 특성 정리',
                    ]}
                    ctaLabel="상세 리포트 보기"
                    to={`/result/${id}/detail`}
                  />
                </div>
              ) : (
                <div
                  id="offer-song-detail"
                  data-testid="offer-song-detail"
                  className="premium-card is-purchase"
                >
                  <div className="premium-card-top">
                    <span className="premium-badge">이 노래 더 자세히</span>
                    {paymentsEnabled ? (
                      <span className="premium-price">{songPriceLabel}</span>
                    ) : null}
                  </div>
                  <h3 className="premium-title">상세 리포트</h3>
                  <p className="premium-desc">
                    노래에서 발견된 발성 특징을 더 자세히 확인해보세요.
                  </p>
                  <ul className="premium-bullets">
                    <li>전체 발성 프로필과 고음·음색 분석</li>
                    <li>특징이 나타난 실제 노래 구간 듣기</li>
                    <li>이번 녹음에서 확인된 발성 특성 정리</li>
                  </ul>
                  <div className="premium-cta" data-testid="rewarded-detail-offer">
                    {/* Free and paid options sit in one decision area. Only the messages
                        that explain an unavailable ad live outside it. */}
                    {rewarded.configured && rewarded.status && rewarded.status.remaining_today <= 0 ? (
                      <p className="muted purchase-choice-note">
                        오늘 무료 열람 기회를 모두 사용했어요. 내일 다시 이용할 수 있어요.
                      </p>
                    ) : null}
                    {rewarded.configured && rewarded.loadState === 'unavailable' ? (
                      <p className="muted purchase-choice-note">
                        지금은 광고 무료 열람을 사용할 수 없어요.
                      </p>
                    ) : null}
                    <div className="purchase-choice-actions">
                      {showRewardedOption ? (
                        <button
                          type="button"
                          className="btn"
                          data-testid="rewarded-action"
                          disabled={
                            rewarded.busy ||
                            rewarded.loadState === 'loading' ||
                            rewarded.loadState === 'showing' ||
                            (rewardedBlocked && rewarded.loadState !== 'error')
                          }
                          // A failed preload retries the ad load only. Running the unlock
                          // path here would open a reward session before an ad exists.
                          onClick={
                            rewarded.loadState === 'error'
                              ? () => void rewarded.retryLoad()
                              : unlockViaRewardedAd
                          }
                        >
                          {rewardedLabel}
                        </button>
                      ) : null}
                      {showPaidSongDetailOption ? (
                        songCanBuy ? (
                          <button
                            type="button"
                            className="btn secondary"
                            disabled={busyDetail}
                            onClick={buySongDetail}
                          >
                            {busyDetail
                              ? '준비 중…'
                              : `${songPriceLabel}에 상세 리포트 열기`}
                          </button>
                        ) : songPrice?.retryable ? (
                          <button type="button" className="btn secondary" onClick={reloadIapPrices}>
                            가격 다시 확인하기
                          </button>
                        ) : (
                          <button type="button" className="btn secondary" disabled>
                            {songPriceLabel === PRICE_LOADING_LABEL
                              ? '가격 확인 중…'
                              : PRICE_UNAVAILABLE_LABEL}
                          </button>
                        )
                      ) : null}
                    </div>
                    {showRewardedOption && !rewardedExhausted ? (
                      typeof rewarded.remainingToday === 'number' ? (
                        <p className="muted purchase-choice-note is-after">
                          오늘 무료 열람 {rewarded.remainingToday}회 남음
                        </p>
                      ) : (
                        <p className="muted purchase-choice-note is-after">
                          오늘 무료 열람 {rewarded.dailyLimit}회까지 가능
                        </p>
                      )
                    ) : null}
                    {rewarded.error ? <p className="fail" style={{ marginTop: 8 }}>{rewarded.error}</p> : null}
                  </div>
                </div>
              )}

              {diagUnlocked && sessionId ? (
                <PremiumProductCard
                  badge="이용 가능"
                  title="정밀 발성 진단"
                  description="추가 녹음으로 확인한 발성 특성을 더 정밀하게 볼 수 있어요."
                  bullets={diagBullets.length ? diagBullets : ['정밀 진단 결과 열람']}
                  ctaLabel="정밀 진단 보기"
                  to={`/diagnostic/${sessionId}/report`}
                />
              ) : (
                <PremiumProductCard
                  variant="purchase"
                  badge={needsDiagnostic ? '추가 확인 추천' : '추가 녹음으로 더 정밀하게'}
                  title="정밀 발성 진단"
                  description="짧은 추가 녹음으로 노래만으로 확인하기 어려웠던 발성 특성을 다시 측정하고, 내 고민에 맞춘 발성 피드백을 받아요."
                  priceLabel={paymentsEnabled ? diagPriceLabel : undefined}
                  bullets={
                    diagBullets.length
                      ? diagBullets
                      : [
                          '확인이 필요한 발성 항목을 추가 녹음으로 다시 비교해요',
                          '표준 과제를 통해 발성 특성을 더 정밀하게 비교해요',
                          '선택한 고민과 현재 분석 결과에 맞는 항목을 확인해요',
                        ]
                  }
                  ctaLabel={
                    !paymentsEnabled
                      ? undefined
                      : diagCanBuy
                        ? `${diagPriceLabel}에 정밀 진단 시작하기`
                        : diagPriceLabel === PRICE_LOADING_LABEL
                          ? '정밀 진단 시작하기'
                          : PRICE_UNAVAILABLE_LABEL
                  }
                  to={paymentsEnabled && diagCanBuy ? `/premium?analysis=${id || ''}&product=${diagOfferKey}` : undefined}
                  disabled={!paymentsEnabled || !diagCanBuy}
                  retryable={paymentsEnabled && !!diagPrice?.retryable}
                  onRetry={paymentsEnabled ? reloadIapPrices : undefined}
                  footer={diagDuration || undefined}
                />
              )}
            </div>
            <p className="muted" style={{ marginTop: 14, fontSize: '0.82rem', lineHeight: 1.45 }}>
              상세 리포트는 이 노래의 고음·음색과 발성 프로필을 자세히 보여 줘요.
              <br />
              정밀 진단은 추가 녹음으로 다시 측정하고, 고민에 맞춘 발성 피드백을 드려요.
            </p>
          </section>

          <ProgressInsightSheet
            open={!!sheetCard}
            card={sheetCard}
            onClose={() => setSheetCard(null)}
          />
        </>
      )}

      {error && <p className="fail">{error}</p>}
      <p className="footer-note">{sanitizeDisclaimer(data.disclaimer)}</p>
    </main>
  );
}
