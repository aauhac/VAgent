import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  createDiagnosticSession,
  getAnalysis,
  getAnalysisAccess,
  getDiagnosticSession,
  getProducts,
} from '../api/client';
import PremiumProductCard from '../components/ui/PremiumProductCard';
import { nextDiagnosticRoute } from '../lib/diagnosticEntry';
import {
  diagnosticOfferBullets,
  pickDiagnosticOffer,
  type DiagnosticOffer,
} from '../lib/diagnosticOffer';
import { buyProduct } from '../lib/tossIap';
import { PRICE_LOADING_LABEL, PRICE_UNAVAILABLE_LABEL } from '../lib/iapCatalog';
import { useIapProductPrices } from '../lib/useIapProductPrices';

/**
 * Diagnostic unlock — after mock pay / existing entitlement → ConcernIntake.
 * Precision always continues to concern/general intake; task count is planned after that.
 */
export default function PremiumUnlock() {
  const [params] = useSearchParams();
  const analysisId = params.get('analysis') || undefined;
  const existingSession = params.get('session') || undefined;
  const productHint = params.get('product') || undefined;
  const showDebug = params.get('debug') === '1';
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [productId, setProductId] = useState<string>('diagnostic_full');
  const [offer, setOffer] = useState<DiagnosticOffer | null>(null);
  const [offerLoading, setOfferLoading] = useState(!!analysisId);
  const [resolving, setResolving] = useState(!!analysisId || !!existingSession);
  const [catalog, setCatalog] = useState<any>(null);
  // Which analysis this purchase is for. `/premium?session=…` carries no analysis id, so
  // it is recovered from the session the user is trying to unlock.
  const [sourceAnalysisId, setSourceAnalysisId] = useState<string | undefined>(analysisId);
  const { prices, reload: reloadPrices, paymentsEnabled } = useIapProductPrices(catalog);
  const price = prices[productId];

  useEffect(() => {
    getProducts(analysisId)
      .then((cat) => {
        const next = productHint || cat.offers?.diagnostic || 'diagnostic_full';
        setProductId(next);
        setCatalog(cat);
      })
      .catch(() => undefined);
  }, [analysisId, productHint]);

  useEffect(() => {
    if (!analysisId) {
      setOffer(null);
      setOfferLoading(false);
      return;
    }
    setOfferLoading(true);
    getAnalysis(analysisId)
      .then((job) => {
        setOffer(pickDiagnosticOffer(job.result));
        setOfferLoading(false);
      })
      .catch(() => {
        setOffer(null);
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
          if (session?.source_analysis_id) {
            setSourceAnalysisId(String(session.source_analysis_id));
          }
          if (session?.unlocked === false) {
            // Unpaid session: stay here and offer the real purchase, never a mock unlock.
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

  useEffect(() => {
    if (import.meta.env.PROD) return;
    // eslint-disable-next-line no-console
    console.info('[PremiumUnlock] 개발 환경 Mock 결제 · 실제 과금이 아닙니다.');
  }, []);

  const labels = (offer?.unresolved_labels || []).filter(Boolean).slice(0, 3);
  const bullets = diagnosticOfferBullets(offer);
  const isStandalone = !analysisId;
  const upgradeNote =
    productId === 'diagnostic_upgrade'
      ? '상세 리포트를 이용 중이어서 정밀 진단만 추가돼요.'
      : productId === 'diagnostic_full'
        ? '상세 리포트가 함께 포함돼요.'
        : null;

  const lead =
    isStandalone
      ? '추가 녹음으로 발성 특성을 더 정확히 확인해요.'
      : labels.length
        ? `현재 노래에서 확인하기 어려웠던 ${labels.join('·')} 등을 짧은 표준 녹음으로 다시 확인합니다.`
        : '현재 노래에서 확인하기 어려웠던 발성 특성을 짧은 표준 녹음으로 다시 확인합니다.';

  async function start() {
    setBusy(true);
    setError(null);
    try {
      if (!price?.canPurchase) {
        reloadPrices();
        setError(PRICE_UNAVAILABLE_LABEL);
        setBusy(false);
        return;
      }
      const target = sourceAnalysisId || analysisId;
      if (!target) {
        setError('결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.');
        setBusy(false);
        return;
      }

      // Pay FIRST. Nothing is created before the server verifies the order and grants the
      // entitlement, so a cancelled purchase leaves no session, no history change, and no
      // access change.
      const iap = await buyProduct({ productId, resourceId: target });
      if (iap.state === 'CANCELLED') {
        setBusy(false);
        return;
      }
      if (!iap.ok) {
        // DEV ONLY. The condition is statically false in a production build, so this
        // block — and the devMocks chunk it imports — is dropped from the bundle.
        if (!import.meta.env.PROD && (iap.message || '').includes('토스 앱')) {
          const devSid = existingSession || (await createDiagnosticSession(target))?.session_id;
          if (!devSid) {
            throw new Error('진단 세션을 만들지 못했어요. 잠시 후 다시 시도해주세요.');
          }
          const { mockPaySession } = await import('../api/devMocks');
          await mockPaySession(devSid, productId);
          nav(`/diagnostic/${devSid}/concerns`);
          return;
        }
        setError(iap.message || '결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.');
        setBusy(false);
        return;
      }

      // Purchase verified server-side. The server, not localStorage, decides what is open.
      const access = await getAnalysisAccess(target);
      if (!access?.diagnostic_unlocked) {
        setError('결제 상태를 확인하고 있어요. 다시 앱을 열어도 이어서 확인할 수 있어요.');
        setBusy(false);
        return;
      }
      // Reuse the session the entitlement already points at; only create one if none
      // exists, so a purchase can never produce a duplicate session.
      let sid = access.diagnostic_session_id || existingSession;
      if (!sid) {
        sid = (await createDiagnosticSession(target))?.session_id;
      }
      if (!sid) {
        throw new Error('진단 세션을 만들지 못했어요. 잠시 후 다시 시도해주세요.');
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
        <h1 className="brand page-screen-title">정밀 발성 진단</h1>
        <p className="muted">정밀 진단 준비 중…</p>
        <div className="skeleton" style={{ height: 18, width: '60%' }} />
        <div className="skeleton" style={{ height: 120 }} />
        {error && <p className="fail">{error}</p>}
      </main>
    );
  }

  const productBullets = [
    '고민 선택 → 안전 확인 → 짧은 추가 녹음 → 정밀 진단 결과',
    ...(upgradeNote ? [upgradeNote] : []),
    ...(isStandalone
      ? ['한 번 완료한 진단 리포트는 계속 열람 가능']
      : bullets.filter((b) => !upgradeNote || !b.includes('상세 리포트')).slice(0, 2)),
  ];

  const displayAmount = price?.label || PRICE_LOADING_LABEL;
  const canBuy = paymentsEnabled && !!price?.canPurchase;

  return (
    <main>
      <h1 className="brand page-screen-title">정밀 발성 진단</h1>
      <p className="lead" style={{ marginTop: 4 }}>
        추가 녹음으로 발성 특성을 더 정확히 확인해요.
      </p>
      {!isStandalone ? (
        <p className="body-text muted" style={{ marginTop: 8, lineHeight: 1.5 }}>
          {lead}
        </p>
      ) : (
        <p className="body-text muted" style={{ marginTop: 8, lineHeight: 1.5 }}>
          표준 추가 녹음으로 발성 특성을 정밀하게 확인하고, 고민에 맞춘 발성 피드백을 받아요.
        </p>
      )}

      <div className="trust-note" style={{ margin: '16px 0' }}>
        <h3>진행 과정</h3>
        <p>고민 선택 → 안전 확인 → 짧은 추가 녹음 → 정밀 진단 결과</p>
      </div>

      <PremiumProductCard
        variant="purchase"
        title="정밀 발성 진단"
        description={
          isStandalone
            ? '표준 추가 녹음으로 발성 특성을 정밀하게 확인하고, 고민에 맞춘 발성 피드백을 받아요.'
            : '선택한 고민과 현재 분석 결과에 맞춰 필요한 녹음만 진행합니다.'
        }
        priceLabel={paymentsEnabled ? displayAmount : undefined}
        bullets={productBullets.slice(0, 4)}
        ctaLabel={
          !paymentsEnabled
            ? undefined
            : busy
              ? '준비 중…'
              : canBuy
                ? `${displayAmount}에 정밀 진단 시작하기`
                : displayAmount === PRICE_LOADING_LABEL
                  ? '정밀 진단 시작하기'
                  : PRICE_UNAVAILABLE_LABEL
        }
        onClick={paymentsEnabled ? start : undefined}
        busy={busy}
        disabled={!paymentsEnabled || !canBuy}
        retryable={paymentsEnabled && !!price?.retryable}
        onRetry={paymentsEnabled ? reloadPrices : undefined}
        footer={
          showDebug && !import.meta.env.PROD
            ? '개발 환경 Mock 결제 · 실제 과금이 아닙니다.'
            : (upgradeNote || undefined)
        }
      />

      {error && <p className="fail">{error}</p>}
    </main>
  );
}
