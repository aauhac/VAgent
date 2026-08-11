import { Link } from 'react-router-dom';
import PremiumProductCard from '../ui/PremiumProductCard';

type Offer = {
  unresolved_count?: number;
  unresolved_labels?: string[];
  selected_task_count?: number;
  estimated_duration_text?: string;
  required?: boolean;
  required_tasks?: boolean;
};

type Props = {
  analysisId?: string;
  priceLabel: string;
  productId: string;
  unlocked?: boolean;
  sessionId?: string | null;
  diagnosticOffer?: Offer | null;
};

export default function DiagnosticCTA({
  analysisId,
  priceLabel,
  productId,
  unlocked,
  sessionId,
  diagnosticOffer,
}: Props) {
  const labels = diagnosticOffer?.unresolved_labels || [];
  const nTasks = diagnosticOffer?.selected_task_count;
  const required = diagnosticOffer?.required !== false && (nTasks == null || nTasks > 0);

  if (!required && typeof nTasks === 'number' && nTasks === 0) {
    return (
      <section className="section" style={{ borderBottom: 0 }}>
        <PremiumProductCard
          badge="완료 가능"
          title="정밀 발성 진단"
          description="이번 음원에서는 주요 발성 특성이 이미 충분히 확인됐어요. 추가 측정이 필요한 항목은 없어요."
          bullets={['추가 과제 없음']}
          ctaLabel={unlocked && sessionId ? '정밀 발성 진단 보기' : '홈으로'}
          to={unlocked && sessionId ? `/diagnostic/${sessionId}/report` : '/'}
        />
      </section>
    );
  }

  const bullets = [
    labels.length > 0
      ? `확인 항목 · ${labels.slice(0, 2).join(' · ')}`
      : '노래만으로 구분하기 어려운 항목을 추가 확인',
    typeof nTasks === 'number'
      ? `짧은 과제 ${nTasks}개`
      : '필요한 짧은 과제만 진행',
    diagnosticOffer?.estimated_duration_text
      ? `예상 시간 · ${diagnosticOffer.estimated_duration_text}`
      : '대략 1분 내외',
  ];

  return (
    <section className="section" style={{ borderBottom: 0 }}>
      <h3 className="section-title">한 단계 더 정확하게</h3>
      <p className="body-text muted" style={{ marginBottom: 14 }}>
        노래 한 곡만으로는 모든 발성 특성을 확정할 수 없어요.
        필요한 항목만 짧게 추가 녹음해 더 정확하게 확인해요.
      </p>
      {unlocked && sessionId ? (
        <PremiumProductCard
          badge="UNLOCKED"
          featured
          title="정밀 발성 진단"
          description="이미 해제한 정밀 진단 결과를 볼 수 있어요."
          bullets={bullets}
          ctaLabel="정밀 발성 진단 보기"
          to={`/diagnostic/${sessionId}/report`}
        />
      ) : (
        <PremiumProductCard
          badge="가장 정확한 분석"
          featured
          title="정밀 발성 진단"
          description="추가 녹음으로 불확실한 항목을 더 정확하게 확인합니다."
          priceLabel={priceLabel}
          bullets={bullets}
          ctaLabel={`정밀 발성 진단 · ${priceLabel}`}
          to={`/premium?analysis=${analysisId || ''}&product=${productId}`}
          footer="상세 리포트만으로도 충분할 수 있어요. 확신이 필요할 때 이어가세요."
        />
      )}
      {!unlocked && (
        <p className="muted" style={{ marginTop: 12, fontSize: '0.82rem' }}>
          <Link to={`/result/${analysisId}`}>무료 결과로 돌아가기</Link>
        </p>
      )}
    </section>
  );
}
