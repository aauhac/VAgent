import { useEffect, useState } from 'react';
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
  const songPrice = prodMap.song_detail?.display_amount || '—';
  const songUnlocked = !!access.song_detail_unlocked;

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
      <h1 className="brand" style={{ fontSize: '1.35rem', marginTop: 12, marginBottom: 0 }}>
        내 보컬 리포트
      </h1>

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

          <section className="section">
            <p className="muted body-text" style={{ marginBottom: 12 }}>
              발성 프로필 · 특징 구간 · 음역별 구성은 상세 리포트에서 확인할 수 있어요.
            </p>
            {songUnlocked ? (
              <Link className="btn" to={`/result/${id}/detail`} style={{ width: '100%' }}>
                상세 발성 리포트 보기
              </Link>
            ) : (
              <button
                className="btn"
                disabled={busyDetail}
                onClick={buySongDetail}
                style={{ width: '100%' }}
              >
                {busyDetail ? '준비 중…' : `상세 발성 리포트 보기 · ${songPrice}`}
              </button>
            )}
          </section>
        </>
      )}

      {error && <p className="fail">{error}</p>}
      <p className="footer-note">{sanitizeDisclaimer(data.disclaimer)}</p>
    </main>
  );
}
