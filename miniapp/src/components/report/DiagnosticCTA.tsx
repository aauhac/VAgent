import { Link } from 'react-router-dom';

type Offer = {
  unresolved_count?: number;
  unresolved_labels?: string[];
  selected_task_count?: number;
  estimated_duration_text?: string;
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
  const lead =
    labels.length > 0
      ? `노래만으로 확인하기 어려운 부분이 있어요. ${labels.slice(0, 2).join('과 ')}은(는) 이번 노래만으로 구분하기 어려웠어요.`
      : '노래에서 본 발성 패턴을 표준 과제에서 더 정밀하게 확인할 수 있어요.';
  const follow =
    typeof nTasks === 'number' && nTasks === 0
      ? '이번 음원에서는 주요 발성 특성이 이미 충분히 확인됐어요.'
      : typeof nTasks === 'number'
        ? `짧은 표준 발성 ${nTasks}가지를 추가하면 이 부분을 더 정밀하게 확인할 수 있어요.`
        : '짧은 표준 발성으로 불확실한 항목만 추가로 확인할 수 있어요.';

  return (
    <section className="section" style={{ borderBottom: 0 }}>
      <h3 className="section-title">정밀 발성 진단</h3>
      <p className="body-text muted">{lead}</p>
      <p className="body-text muted">{follow}</p>
      {diagnosticOffer?.estimated_duration_text && (
        <p className="muted">예상 시간 · {diagnosticOffer.estimated_duration_text}</p>
      )}
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
