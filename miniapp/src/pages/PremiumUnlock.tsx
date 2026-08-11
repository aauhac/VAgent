import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  createDiagnosticSession,
  getProducts,
  mockPaySession,
  patchHistory,
  saveSongDetailUnlock,
  saveUnlockedSession,
} from '../api/client';
import PremiumProductCard from '../components/ui/PremiumProductCard';

/**
 * Diagnostic unlock only — never used for Song Detail purchase.
 * After mock pay → Safety → Diagnostic Tasks.
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

  useEffect(() => {
    getProducts(analysisId)
      .then((cat) => {
        const offer = productHint || cat.offers?.diagnostic || 'diagnostic_full';
        setProductId(offer);
        setDisplayAmount(cat.products?.[offer]?.display_amount || '—');
      })
      .catch(() => undefined);
  }, [analysisId, productHint]);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      if (existingSession) {
        await mockPaySession(existingSession, productId);
        saveUnlockedSession(existingSession);
        nav(`/diagnostic/${existingSession}/safety`);
        return;
      }
      const session = await createDiagnosticSession(analysisId);
      await mockPaySession(session.session_id, productId);
      saveUnlockedSession(session.session_id);
      if (analysisId) {
        saveSongDetailUnlock(analysisId);
        patchHistory(analysisId, {
          songDetailUnlocked: true,
          sessionId: session.session_id,
        });
      }
      nav(`/diagnostic/${session.session_id}/safety`);
    } catch (e: any) {
      setError(e?.message || '잠금 해제 실패');
      setBusy(false);
    }
  }

  return (
    <main>
      <Link className="muted" to={analysisId ? `/result/${analysisId}` : '/'}>← 뒤로</Link>
      <p className="page-kicker" style={{ marginTop: 16 }}>정밀 검사</p>
      <h1 className="brand" style={{ fontSize: '1.7rem' }}>
        정밀 발성 진단
      </h1>
      <p className="lead">
        노래 한 곡만으로 알기 어려운 부분을, 짧은 표준 과제로 다시 확인해요.
        과제 수는 최소화하고 필요한 항목만 진행합니다.
      </p>

      <PremiumProductCard
        badge="가장 정확한 분석"
        featured
        title="정밀 발성 진단"
        description="추가 녹음으로 불확실한 항목을 더 정확하게 확인합니다."
        priceLabel={displayAmount}
        bullets={[
          '아·이 지속음, 사이렌, 강약 변화 등 짧은 과제',
          productId === 'diagnostic_upgrade' ? '업그레이드 요금' : '상세 리포트 포함',
          '한 번 완료한 진단 리포트는 계속 열람 가능',
        ]}
        ctaLabel={busy ? '준비 중…' : `진단 시작 · ${displayAmount}`}
        onClick={start}
        busy={busy}
        footer="개발 환경 Mock 결제 · 실제 과금이 아닙니다."
      />

      <div className="trust-note" style={{ marginTop: 16 }}>
        <h3>이렇게 진행돼요</h3>
        <p>
          안전 확인 → 필요한 짧은 과제 녹음 → 정밀 리포트.
          중간에 녹음을 다시 할 수 있어요.
        </p>
      </div>

      {error && <p className="fail">{error}</p>}
    </main>
  );
}
