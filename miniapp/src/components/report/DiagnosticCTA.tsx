import { Link } from 'react-router-dom';
import PremiumProductCard from '../ui/PremiumProductCard';
import { concernIntakePath, premiumEntryPath } from '../../lib/diagnosticEntry';
import { diagnosticOfferBullets, type DiagnosticOffer } from '../../lib/diagnosticOffer';

type Props = {
  analysisId?: string;
  priceLabel: string;
  productId: string;
  unlocked?: boolean;
  sessionId?: string | null;
  diagnosticOffer?: DiagnosticOffer | null;
};

export default function DiagnosticCTA({
  analysisId,
  priceLabel,
  productId,
  unlocked,
  sessionId,
  diagnosticOffer,
}: Props) {
  const bullets = diagnosticOfferBullets(diagnosticOffer);
  const displayBullets =
    bullets.length > 0
      ? bullets.filter((b) => !b.includes('추가 녹음 0'))
      : [
          '현재 노래 + 짧은 추가 녹음으로 더 정밀하게',
          '고민이 있으면 고민 중심으로, 없으면 전체 발성 특성으로',
        ];

  if (unlocked && sessionId) {
    return (
      <section className="section" style={{ borderBottom: 0 }}>
        <PremiumProductCard
          badge="이용 가능"
          featured
          title="정밀 발성 진단"
          description="이미 해제한 정밀 진단을 이어서 진행하거나 결과를 볼 수 있어요."
          bullets={displayBullets}
          ctaLabel="정밀 발성 진단 이어가기"
          to={concernIntakePath(sessionId)}
        />
      </section>
    );
  }

  return (
    <section className="section" style={{ borderBottom: 0 }}>
      <h3 className="section-title">한 단계 더 정밀하게</h3>
      <p className="body-text muted" style={{ marginBottom: 14 }}>
        현재 노래와 짧은 추가 녹음을 함께 분석해
        발성 특성을 더 정밀하게 확인해요.
      </p>
      <PremiumProductCard
        badge="가장 정밀한 분석"
        featured
        title="정밀 발성 진단"
        description="고민을 고르거나, 전체 발성 특성을 확인하기 위해 표준 추가 녹음을 진행합니다."
        priceLabel={priceLabel}
        bullets={[
          ...displayBullets.slice(0, 2),
          '선택한 고민과 현재 분석 결과에 맞춰 필요한 녹음만 진행합니다.',
        ]}
        ctaLabel={`정밀 발성 진단 · ${priceLabel}`}
        to={analysisId ? premiumEntryPath(analysisId, productId) : '/premium'}
        footer="상세 리포트는 이 노래만의 분석이에요. 정밀 진단은 추가 녹음이 포함됩니다."
      />
      {analysisId ? (
        <p className="muted" style={{ marginTop: 12, fontSize: '0.82rem' }}>
          <Link to={`/result/${analysisId}`}>무료 결과로 돌아가기</Link>
        </p>
      ) : null}
    </section>
  );
}
