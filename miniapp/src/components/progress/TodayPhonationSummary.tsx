import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { ProgressCard, ProgressInsightPayload } from '../../lib/progressPresentation';
import type { GoalProgressPayload } from '../../lib/goalProgress';
import GoalProgressCard, { GoalEmptyCta } from './GoalProgressCard';

type Props = {
  insight: ProgressInsightPayload;
  onOpenCard: (card: ProgressCard) => void;
  practiceSlot?: ReactNode;
  goalProgress?: GoalProgressPayload | null;
  onOpenGoalInsight?: () => void;
  onSetGoal?: () => void;
  onChangeGoal?: () => void;
};

/**
 * Result-loop surface: today → goal → improved → changed/maintained → practice → full progress.
 */
export default function TodayPhonationSummary({
  insight,
  onOpenCard,
  practiceSlot,
  goalProgress,
  onOpenGoalInsight,
  onSetGoal,
  onChangeGoal,
}: Props) {
  const hasProgress =
    insight.insight_available
    && (insight.improved.length > 0 || insight.changed.length > 0 || insight.maintained.length > 0);
  const showGoal = goalProgress && goalProgress.status !== 'NO_GOAL' && goalProgress.goal;
  const showGoalCta = !showGoal && onSetGoal;

  return (
    <section className="section progress-summary" data-testid="today-phonation-summary">
      <h3 className="section-title">오늘의 발성</h3>

      {insight.today.length > 0 ? (
        <div className="progress-today">
          <p className="progress-subhead">가장 중요한 현재 상태</p>
          <ul className="progress-today-list">
            {insight.today.map((row) => (
              <li key={row.axis} className="progress-today-row">
                <span className="progress-today-axis">{row.title}</span>
                <span className="progress-today-label">{row.label}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {showGoal ? (
        <div className="progress-group">
          <GoalProgressCard
            progress={goalProgress!}
            onOpenInsight={onOpenGoalInsight}
            onChangeGoal={onChangeGoal}
          />
        </div>
      ) : null}

      {showGoalCta ? (
        <div className="progress-group">
          <GoalEmptyCta onSetGoal={onSetGoal!} />
        </div>
      ) : null}

      {!insight.insight_available ? (
        <div className="progress-empty card" style={{ marginTop: 16 }}>
          <p className="body-text" style={{ margin: 0 }}>
            {insight.note || '몇 번 더 부르면, 이전보다 달라진 점을 보여드려요.'}
          </p>
        </div>
      ) : null}

      {insight.improved.length > 0 ? (
        <div className="progress-group">
          <p className="progress-group-title">
            <span aria-hidden>✨ </span>
            이전보다 좋아진 부분 {insight.improved.length}
          </p>
          {insight.improved.map((card) => (
            <button
              key={card.axis}
              type="button"
              className="progress-card progress-card--improved"
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
      ) : null}

      {insight.changed.length > 0 ? (
        <div className="progress-group">
          <p className="progress-group-title">
            <span aria-hidden>↔ </span>
            달라진 부분
          </p>
          {insight.changed.map((card) => (
            <button
              key={card.axis}
              type="button"
              className="progress-card"
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
      ) : null}

      {insight.maintained.length > 0 ? (
        <div className="progress-group">
          <p className="progress-group-title">
            <span aria-hidden>✓ </span>
            잘 유지한 부분
          </p>
          {insight.maintained.map((card) => (
            <button
              key={card.axis}
              type="button"
              className="progress-card progress-card--maintained"
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
      ) : null}

      {practiceSlot ? (
        <div className="progress-group">
          <p className="progress-group-title">오늘 이렇게 연습해보세요</p>
          {practiceSlot}
        </div>
      ) : null}

      <div style={{ marginTop: 20 }}>
        <Link className="btn secondary" style={{ width: '100%' }} to="/progress">
          내 변화 보기
        </Link>
        {hasProgress ? (
          <p className="muted" style={{ marginTop: 8, fontSize: '0.82rem', textAlign: 'center' }}>
            좋아진 부분을 누르면 짧은 근거만 보여드려요. 상세 리포트로 이동하지 않아요.
          </p>
        ) : null}
      </div>
    </section>
  );
}
