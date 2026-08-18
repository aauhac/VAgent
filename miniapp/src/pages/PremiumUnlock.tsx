import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
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
  const showDebug = params.get('debug') === '1';
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [displayAmount, setDisplayAmount] = useState<string>('—');
  const [productId, setProductId] = useState<string>('diagnostic_full');
  const [offer, setOffer] = useState<DiagnosticOffer | null>(null);
  const [offerLoading, setOfferLoading] = useState(!!analysisId);
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
          if (iap.message) setError(iap.message);
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
        featured
        title="짧은 추가 녹음으로 확인"
        description={
          isStandalone
            ? '표준 추가 녹음으로 발성 특성을 정밀하게 확인하고, 고민에 맞춘 발성 피드백을 받아요.'
            : '선택한 고민과 현재 분석 결과에 맞춰 필요한 녹음만 진행합니다.'
        }
        priceLabel={displayAmount}
        bullets={productBullets.slice(0, 4)}
        ctaLabel={busy ? '준비 중…' : `정밀 진단 시작 · ${displayAmount}`}
        onClick={start}
        busy={busy}
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
