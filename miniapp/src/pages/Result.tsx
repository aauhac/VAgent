import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  getAnalysis,
  getProducts,
  mockUnlockSongDetail,
  patchHistory,
  removeHistory,
  saveSongDetailUnlock,
} from '../api/client';
import VocalTypeHero from '../components/report/VocalTypeHero';
import VocalProfile from '../components/report/VocalProfile';
import PremiumProductCard from '../components/ui/PremiumProductCard';
import { diagnosisFromPrimary, NO_PRIMARY_MESSAGE, sanitizeDisclaimer } from '../lib/reportPresentation';

export default function Result() {
  const { id } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState<any>(null);
  const [products, setProducts] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const [busyDetail, setBusyDetail] = useState(false);

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
        핵심만 먼저 확인해요
      </h1>
      <p className="lead" style={{ marginBottom: 8 }}>
        더 자세한 프로필과 정밀 확인은 아래에서 이어갈 수 있어요.
      </p>

      {!score.available ? (
        <section className="section">
          <h2 className="type-title" style={{ fontSize: '1.35rem' }}>정확한 분석이 어려운 녹음</h2>
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
                  badge="UNLOCKED"
                  title="상세 리포트"
                  description="발성 프로필 · 관찰 특징 · 들어볼 구간을 더 자세히 확인해요."
                  bullets={['상세 발성 프로필', '관찰된 특징', '비교해서 들어볼 구간']}
                  ctaLabel="상세 리포트 보기"
                  to={`/result/${id}/detail`}
                />
              ) : (
                <PremiumProductCard
                  badge="PREMIUM"
                  title="상세 리포트"
                  description="발성 타입 외에 더 자세한 발성 프로필과 관찰 특징을 확인합니다."
                  priceLabel={songPrice}
                  bullets={['상세 발성 프로필', '관찰된 특징', '비교해서 들어볼 구간']}
                  ctaLabel={`상세 리포트 보기 · ${songPrice}`}
                  onClick={buySongDetail}
                  busy={busyDetail}
                />
              )}

              {diagUnlocked && sessionId ? (
                <PremiumProductCard
                  badge="UNLOCKED"
                  featured
                  title="정밀 발성 진단"
                  description="추가 녹음으로 확인한 정밀 진단 결과를 볼 수 있어요."
                  bullets={['불확실 항목 정밀 확인', '짧은 표준 과제']}
                  ctaLabel="정밀 진단 보기"
                  to={`/diagnostic/${sessionId}/report`}
                />
              ) : (
                <PremiumProductCard
                  badge="가장 정확한 분석"
                  featured
                  title="정밀 발성 진단"
                  description="추가 녹음으로 불확실한 항목을 더 정확하게 확인합니다."
                  priceLabel={diagPrice}
                  bullets={[
                    '노래만으로 알기 어려운 항목만 추가 확인',
                    '필요한 짧은 과제만 진행',
                    diagOfferKey === 'diagnostic_upgrade'
                      ? '상세 리포트 보유 시 업그레이드'
                      : '상세 리포트 포함',
                  ]}
                  ctaLabel={`정밀 진단 시작 · ${diagPrice}`}
                  to={`/premium?analysis=${id || ''}&product=${diagOfferKey}`}
                  footer="더 비싼 상품이 아니라, 더 정확한 검사를 위한 단계예요."
                />
              )}
            </div>
          </section>
        </>
      )}

      {error && <p className="fail">{error}</p>}
      <p className="footer-note">{sanitizeDisclaimer(data.disclaimer)}</p>
    </main>
  );
}
