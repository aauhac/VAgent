import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  createDiagnosticSession,
  getAnalysis,
  getAnalysisAccess,
  getDiagnosticSession,
  getProducts,
  mockPaySession,
  patchHistory,
  saveSongDetailUnlock,
  saveUnlockedSession,
} from '../api/client';
import PremiumProductCard from '../components/ui/PremiumProductCard';
import { nextDiagnosticRoute } from '../lib/diagnosticEntry';
import {
  diagnosticOfferBullets,
  pickDiagnosticOffer,
  type DiagnosticOffer,
} from '../lib/diagnosticOffer';
import { buyProduct } from '../lib/tossIap';

/**
 * Diagnostic unlock — after mock pay / existing entitlement → ConcernIntake.
 * Precision always continues to concern/general intake; task count is planned after that.
 */
export default function PremiumUnlock() {
  const [params] = useSearchParams();
  const analysisId = params.get('analysis') || undefined;
  const existingSession = params.get('session') || undefined;
  const productHint = params.get('product') || undefined;
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [displayAmount, setDisplayAmount] = useState<string>('—');
  const [productId, setProductId] = useState<string>('diagnostic_full');
  const [offer, setOffer] = useState<DiagnosticOffer | null>(null);
  const [offerLoading, setOfferLoading] = useState(!!analysisId);
  const [offerFailed, setOfferFailed] = useState(false);
  const [resolving, setResolving] = useState(!!analysisId || !!existingSession);

  useEffect(() => {
    getProducts(analysisId)
      .then((cat) => {
        const next = productHint || cat.offers?.diagnostic || 'diagnostic_full';
        setProductId(next);
        setDisplayAmount(cat.products?.[next]?.display_amount || '—');
      })
      .catch(() => undefined);
  }, [analysisId, productHint]);

  useEffect(() => {
    if (!analysisId) {
      setOffer(null);
      setOfferLoading(false);
      setOfferFailed(false);
      return;
    }
    setOfferLoading(true);
    setOfferFailed(false);
    getAnalysis(analysisId)
      .then((job) => {
        setOffer(pickDiagnosticOffer(job.result));
        setOfferLoading(false);
      })
      .catch(() => {
        setOffer(null);
        setOfferFailed(true);
        setOfferLoading(false);
      });
  }, [analysisId]);

  // Existing entitlement / session → resume flow (never Home)
  useEffect(() => {
    let cancelled = false;
    async function resume() {
      try {
        if (existingSession) {
          const session = await getDiagnosticSession(existingSession);
          if (cancelled) return;
          if (session?.unlocked === false) {
            setResolving(false);
            return;
          }
          const next = nextDiagnosticRoute(session);
          if (next) {
            nav(next, { replace: true });
            return;
          }
        }
        if (analysisId) {
          const access = await getAnalysisAccess(analysisId);
          if (cancelled) return;
          if (access.diagnostic_unlocked && access.diagnostic_session_id) {
            const session = await getDiagnosticSession(access.diagnostic_session_id);
            if (cancelled) return;
            const next = nextDiagnosticRoute(session);
            if (next) {
              nav(next, { replace: true });
              return;
            }
          }
        }
      } catch {
        if (!cancelled) {
          setError('정밀 진단 정보를 불러오지 못했어요. 다시 시도해주세요.');
        }
      } finally {
        if (!cancelled) setResolving(false);
      }
    }
    if (analysisId || existingSession) {
      void resume();
    } else {
      setResolving(false);
    }
    return () => {
      cancelled = true;
    };
  }, [analysisId, existingSession, nav]);

  const labels = (offer?.unresolved_labels || []).filter(Boolean).slice(0, 3);
  const bullets = diagnosticOfferBullets(offer);
  const isStandalone = !analysisId;

  async function start() {
    setBusy(true);
    setError(null);
    try {
      if (existingSession) {
        await mockPaySession(existingSession, productId);
        saveUnlockedSession(existingSession);
        nav(`/diagnostic/${existingSession}/concerns`);
        return;
      }
      const session = await createDiagnosticSession(analysisId);
      const sid = session?.session_id;
      if (!sid) {
        throw new Error('진단 세션을 만들지 못했어요. 잠시 후 다시 시도해주세요.');
      }
      if (analysisId) {
        const iap = await buyProduct({ productId, resourceId: analysisId });
        if (iap.ok) {
          saveUnlockedSession(sid);
          saveSongDetailUnlock(analysisId);
          patchHistory(analysisId, { songDetailUnlocked: true, sessionId: sid });
          nav(`/diagnostic/${sid}/concerns`);
          return;
        }
        if (iap.state === 'CANCELLED') {
          setError(iap.message || '결제가 취소됐어요.');
          setBusy(false);
          return;
        }
        if (import.meta.env.PROD || !(iap.message || '').includes('토스 앱')) {
          setError(iap.message || '결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.');
          setBusy(false);
          return;
        }
      }
      await mockPaySession(sid, productId);
      saveUnlockedSession(sid);
      if (analysisId) {
        saveSongDetailUnlock(analysisId);
        patchHistory(analysisId, {
          songDetailUnlocked: true,
          sessionId: sid,
        });
      }
      nav(`/diagnostic/${sid}/concerns`);
    } catch (e: any) {
      setError(e?.message || '잠금 해제에 실패했어요. 홈으로 이동하지 않고 여기서 다시 시도할 수 있어요.');
      setBusy(false);
    }
  }

  if (resolving || (analysisId && offerLoading)) {
    return (
      <main>
        <Link className="muted" to={analysisId ? `/result/${analysisId}/detail` : '/'}>
          ← 뒤로
        </Link>
        <p className="page-kicker" style={{ marginTop: 16 }}>정밀 검사</p>
        <h1 className="brand" style={{ fontSize: '1.7rem' }}>정밀 발성 진단</h1>
        <p className="muted">정밀 진단 준비 중…</p>
        <div className="skeleton" style={{ height: 18, width: '60%' }} />
        <div className="skeleton" style={{ height: 120 }} />
        {error && <p className="fail">{error}</p>}
      </main>
    );
  }

  const productBullets = isStandalone
    ? [
        '고민 선택 또는 전체 발성 특성 확인',
        '몇 가지 짧은 추가 녹음',
        productId === 'diagnostic_upgrade' ? '업그레이드 요금' : '상세 리포트 포함',
        '한 번 완료한 진단 리포트는 계속 열람 가능',
      ]
    : bullets.length > 0
      ? [
          ...bullets,
          productId === 'diagnostic_upgrade' ? '업그레이드 요금' : '상세 리포트 포함',
        ]
      : offerFailed
        ? [
            '선택한 고민과 현재 분석 결과에 맞춰 필요한 녹음만 진행합니다',
            productId === 'diagnostic_upgrade' ? '업그레이드 요금' : '상세 리포트 포함',
          ]
        : [
            '고민이 있으면 고민 중심, 없으면 전체 발성 특성',
            '몇 가지 짧은 추가 녹음',
            productId === 'diagnostic_upgrade' ? '업그레이드 요금' : '상세 리포트 포함',
          ];

  return (
    <main>
      <Link className="muted" to={analysisId ? `/result/${analysisId}/detail` : '/'}>
        ← 뒤로
      </Link>
      <p className="page-kicker" style={{ marginTop: 16 }}>정밀 검사</p>
      <h1 className="brand" style={{ fontSize: '1.7rem' }}>
        정밀 발성 진단
      </h1>
      <p className="lead">
        {isStandalone
          ? '고민이 있으면 고민 중심으로, 없으면 전체 발성 특성을 짧은 추가 녹음으로 확인해요.'
          : '현재 노래와 짧은 추가 녹음을 함께 분석해 발성 특성을 더 정밀하게 확인해요.'}
      </p>

      {!isStandalone && labels.length > 0 && (
        <div className="offer-summary">
          <p className="offer-summary-title">노래에서 더 확인하면 좋은 항목</p>
          <div className="offer-chips">
            {labels.map((label) => (
              <span key={label} className="offer-chip">{label}</span>
            ))}
          </div>
          <p className="offer-summary-meta">
            몇 가지 짧은 추가 녹음
            {offer?.estimated_duration_text && !String(offer.estimated_duration_text).includes('없음')
              ? ` · ${offer.estimated_duration_text}`
              : ''}
          </p>
        </div>
      )}

      {!isStandalone && (
        <div className="trust-note" style={{ marginBottom: 16 }}>
          <h3>이렇게 진행돼요</h3>
          <p>
            고민 선택(또는 특별한 고민 없음) → 안전 확인 → 짧은 추가 녹음 → 정밀 진단 리포트.
          </p>
        </div>
      )}

      <PremiumProductCard
        badge="가장 정밀한 분석"
        featured
        title="정밀 발성 진단"
        description={
          isStandalone
            ? '표준 추가 녹음으로 발성 특성을 정밀하게 확인합니다.'
            : '선택한 고민과 현재 분석 결과에 맞춰 필요한 녹음만 진행합니다.'
        }
        priceLabel={displayAmount}
        bullets={productBullets}
        ctaLabel={busy ? '준비 중…' : `정밀 진단 시작 · ${displayAmount}`}
        onClick={start}
        busy={busy}
        footer={
          import.meta.env.PROD
            ? undefined
            : '개발 환경 Mock 결제 · 실제 과금이 아닙니다.'
        }
      />

      {error && <p className="fail">{error}</p>}
    </main>
  );
}
