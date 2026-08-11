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
        // Diagnostic Full/Upgrade also unlocks Song Detail on backend
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
      <h1 className="brand" style={{ fontSize: '1.7rem', marginTop: 16 }}>
        정밀 발성 진단
      </h1>
      <p className="lead">
        아·이 지속음, 사이렌, 강약 변화로 기본 발성 패턴을 표준 과제에서 다시 확인해요.
        한 번 완료한 진단 리포트는 계속 볼 수 있어요.
      </p>
      <div className="card">
        <p className="muted">
          개발 환경 Mock 결제 · {displayAmount}
          {productId === 'diagnostic_upgrade' ? ' (업그레이드)' : ' (상세 리포트 포함)'}
        </p>
        <p className="muted" style={{ fontSize: '0.85rem' }}>
          이 화면은 정밀 진단 전용입니다. 노래 상세 리포트만 보려면 결과 화면의
          「상세 리포트」를 이용하세요.
        </p>
        <button className="btn" disabled={busy} onClick={start} style={{ width: '100%', marginTop: 12 }}>
          {busy ? '준비 중…' : `정밀 진단 시작 · ${displayAmount}`}
        </button>
        {error && <p className="fail">{error}</p>}
      </div>
      <p className="footer-note">음향 기반 발성 분석 서비스</p>
    </main>
  );
}
