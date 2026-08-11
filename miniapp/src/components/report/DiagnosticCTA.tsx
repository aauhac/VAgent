import { Link } from 'react-router-dom';

type Props = {
  analysisId?: string;
  priceLabel: string;
  productId: string;
  unlocked?: boolean;
  sessionId?: string | null;
};

export default function DiagnosticCTA({
  analysisId,
  priceLabel,
  productId,
  unlocked,
  sessionId,
}: Props) {
  return (
    <section className="section" style={{ borderBottom: 0 }}>
      <h3 className="section-title">이 발성을 더 정확히 확인할까요?</h3>
      <p className="body-text muted">
        아·이 지속음과 사이렌으로 노래에서 본 발성 패턴을 표준 과제에서 다시 확인할 수 있어요.
      </p>
      <div style={{ marginTop: 16 }}>
        {unlocked && sessionId ? (
          <Link className="btn" to={`/diagnostic/${sessionId}/report`}>
            정밀 발성 진단 보기
          </Link>
        ) : (
          <Link
            className="btn"
            to={`/premium?analysis=${analysisId || ''}&product=${productId}`}
            style={{ width: '100%' }}
          >
            정밀 발성 진단 · {priceLabel}
          </Link>
        )}
      </div>
    </section>
  );
}
