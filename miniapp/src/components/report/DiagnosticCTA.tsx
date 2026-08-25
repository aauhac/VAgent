import { Link } from 'react-router-dom';
import PremiumProductCard from '../ui/PremiumProductCard';
import { concernIntakePath, premiumEntryPath } from '../../lib/diagnosticEntry';
import { diagnosticOfferBullets, type DiagnosticOffer } from '../../lib/diagnosticOffer';
import {
  buildVocalProfileView,
} from '../../lib/reportPresentation';

type Props = {
  analysisId?: string;
  priceLabel: string;
  productId: string;
  unlocked?: boolean;
  sessionId?: string | null;
  diagnosticOffer?: DiagnosticOffer | null;
  dimensions?: any;
  criteriaMatrix?: any[];
  canonicalRegister?: any;
  canonicalAcoustic?: any;
  quality?: any;
  highNoteProfile?: any;
  canPurchase?: boolean;
  priceRetryable?: boolean;
  onRetryPrice?: () => void;
  paymentsEnabled?: boolean;
};

export default function DiagnosticCTA({
  analysisId,
  priceLabel,
  productId,
  unlocked,
  sessionId,
  diagnosticOffer,
  dimensions,
  criteriaMatrix = [],
  canonicalRegister,
  canonicalAcoustic,
  quality,
  highNoteProfile,
  canPurchase = true,
  priceRetryable = false,
  onRetryPrice,
  paymentsEnabled = true,
}: Props) {
  const bullets = diagnosticOfferBullets(diagnosticOffer);
  const missingLabels =
    dimensions
      ? buildVocalProfileView(
          dimensions,
          criteriaMatrix,
          canonicalRegister,
          canonicalAcoustic,
          { quality, highNoteProfile },
        ).missing
          .slice(0, 3)
          .map((m) => m.label)
      : [];

  const displayBullets =
    bullets.length > 0
      ? bullets.filter((b) => !b.includes('추가 녹음 0'))
      : missingLabels.length
        ? [
            `이번 노래에서 확인하기 어려웠던 ${missingLabels.join('·')} 등을 짧은 추가 녹음으로 다시 확인해요.`,
            '표준 과제를 통해 발성 특성을 더 정밀하게 비교해요.',
          ]
        : [
            '현재 노래와 짧은 추가 녹음으로 더 정밀하게 확인해요.',
            '선택한 고민과 현재 분석 결과에 맞춰 필요한 녹음만 진행해요.',
          ];

  const description =
    missingLabels.length > 0
      ? `이번 노래에서 확인하기 어려웠던 ${missingLabels.join('·')} 등을 짧은 추가 녹음으로 다시 확인해요.`
      : '현재 노래와 짧은 추가 녹음을 함께 분석해 발성 특성을 더 정밀하게 확인해요.';

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
        {description}
      </p>
      <PremiumProductCard
        featured
        title="정밀 발성 진단"
        description={description}
        priceLabel={paymentsEnabled ? priceLabel : undefined}
        bullets={displayBullets.slice(0, 3)}
        ctaLabel={
          !paymentsEnabled
            ? undefined
            : canPurchase
              ? `정밀 발성 진단 · ${priceLabel}`
              : '정밀 발성 진단'
        }
        to={
          !paymentsEnabled
            ? undefined
            : canPurchase && analysisId
              ? premiumEntryPath(analysisId, productId)
              : canPurchase
                ? '/premium'
                : undefined
        }
        disabled={!paymentsEnabled || !canPurchase}
        retryable={paymentsEnabled && priceRetryable}
        onRetry={paymentsEnabled ? onRetryPrice : undefined}
        footer={
          productId === 'diagnostic_upgrade'
            ? '상세 리포트를 이용 중이어서 정밀 진단만 추가돼요.'
            : '상세 리포트는 이 노래만의 분석이에요. 정밀 진단은 추가 녹음이 포함됩니다.'
        }
      />
      {analysisId ? (
        <p className="muted" style={{ marginTop: 12, fontSize: '0.82rem' }}>
          <Link to={`/result/${analysisId}`}>무료 결과로 돌아가기</Link>
        </p>
      ) : null}
    </section>
  );
}
