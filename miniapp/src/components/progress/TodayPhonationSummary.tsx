import { Link, useLocation } from 'react-router-dom';
import type { ProgressCard, ProgressInsightPayload } from '../../lib/progressPresentation';
import { progressLinkState } from '../../lib/progressNavigation';

type Props = {
  insight: ProgressInsightPayload;
  onOpenCard: (card: ProgressCard) => void;
};

/**
 * Free Result: recent change only — no goal card / goal CTAs.
 * Goal context may already shape insight.improved vs changed upstream.
 */
export default function TodayPhonationSummary({
  insight,
  onOpenCard,
}: Props) {
  const location = useLocation();
  const progressState = progressLinkState(location.pathname + location.search);
  const cards = [
    ...insight.improved.slice(0, 1),
    ...insight.changed.slice(0, 1),
    ...insight.maintained.slice(0, 1),
  ].slice(0, 3);

  const hasHistory = !!insight.insight_available && insight.history_count && insight.history_count > 0;

  if (!hasHistory && !cards.length) {
    return (
      <section className="section progress-summary" data-testid="recent-progress-summary">
        <p className="muted" style={{ margin: 0, fontSize: '0.88rem' }}>
          몇 번 더 부르면 이전 기록과 비교해드릴게요.
        </p>
        <div style={{ marginTop: 16 }}>
          <Link
            className="btn secondary"
            style={{ width: '100%' }}
            to="/progress"
            state={progressState}
          >
            내 변화 보기
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section className="section progress-summary" data-testid="recent-progress-summary">
      {hasHistory && cards.length > 0 ? (
        <div className="progress-group" style={{ marginTop: 0 }}>
          <h3 className="section-title">최근 변화</h3>
          {cards.map((card) => (
            <button
              key={`${card.kind}-${card.axis}`}
              type="button"
              className={
                card.kind === 'IMPROVED'
                  ? 'progress-card progress-card--improved'
                  : card.kind === 'MAINTAINED'
                    ? 'progress-card progress-card--maintained'
                    : 'progress-card'
              }
              onClick={() => onOpenCard(card)}
            >
              <span className="progress-card-main">
                <span className="progress-card-title">{card.title}</span>
                <span className="progress-card-detail">{card.detail}</span>
              </span>
              <span className="progress-card-chevron" aria-hidden>›</span>
            </button>
          ))}
        </div>
      ) : hasHistory ? (
        <p className="muted" style={{ marginTop: 0, fontSize: '0.88rem' }}>
          최근 기록과 비슷한 상태예요.
        </p>
      ) : (
        <p className="muted" style={{ margin: 0, fontSize: '0.88rem' }}>
          몇 번 더 부르면 이전 기록과 비교해드릴게요.
        </p>
      )}

      <div style={{ marginTop: 20 }}>
        <Link
          className="btn secondary"
          style={{ width: '100%' }}
          to="/progress"
          state={progressState}
        >
          내 변화 보기
        </Link>
      </div>
    </section>
  );
}
