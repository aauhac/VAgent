import { Link } from 'react-router-dom';
import type { GoalProgressPayload } from '../../lib/goalProgress';
import { goalCountLabel } from '../../lib/goalProgress';
import GoalEvidenceDots from './GoalEvidenceDots';

type Props = {
  progress: GoalProgressPayload;
  onOpenInsight?: () => void;
  onChangeGoal?: () => void;
  compact?: boolean;
};

/**
 * Compact goal progress card — evidence counts / dots only.
 * Opens Progress Insight sheet; never navigates to diagnostic as primary action.
 */
export default function GoalProgressCard({ progress, onOpenInsight, onChangeGoal, compact }: Props) {
  if (!progress || progress.status === 'NO_GOAL' || !progress.goal) {
    return null;
  }

  const title = progress.goal.display_title || '이번 목표';
  const w = progress.window;
  const countText = goalCountLabel(progress);
  const hideHeavy =
    progress.status === 'INSUFFICIENT_HISTORY'
    || progress.status === 'INSUFFICIENT_EVIDENCE'
    || progress.status === 'STARTING';

  return (
    <div className={`goal-card${compact ? ' goal-card--compact' : ''}`} data-testid="goal-progress-card">
      <p className="page-kicker" style={{ marginTop: 0 }}>{title}</p>
      <p className="goal-card-label">{progress.goal.label}</p>

      {w && !hideHeavy ? (
        <>
          <p className="goal-card-meta">최근 {w.size}회</p>
          {progress.dots?.length ? (
            <GoalEvidenceDots
              dots={progress.dots}
              label={`최근 ${w.size}회 중 목표 방향 ${w.goal_aligned_count}회`}
            />
          ) : null}
          <p className="goal-card-count">{countText}</p>
        </>
      ) : null}

      {progress.summary ? (
        <p className="goal-card-summary">{progress.summary}</p>
      ) : null}

      {progress.previous_window && progress.comparison_available ? (
        <p className="muted goal-card-prev">
          이전 {progress.previous_window.size}회 · 목표 방향 {progress.previous_window.goal_aligned_count}회
        </p>
      ) : null}

      <div className="goal-card-actions">
        {onOpenInsight ? (
          <button type="button" className="btn secondary" onClick={onOpenInsight}>
            변화 보기
          </button>
        ) : (
          <Link className="btn secondary" to="/progress">변화 보기</Link>
        )}
        {onChangeGoal ? (
          <button type="button" className="btn ghost" onClick={onChangeGoal}>
            목표 바꾸기
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function GoalEmptyCta({ onSetGoal }: { onSetGoal: () => void }) {
  return (
    <div className="goal-empty" data-testid="goal-empty-cta">
      <p className="muted" style={{ margin: '0 0 10px', fontSize: '0.88rem' }}>
        목표를 정하면 변화 과정을 더 쉽게 볼 수 있어요
      </p>
      <button type="button" className="btn ghost" style={{ width: '100%' }} onClick={onSetGoal}>
        목표 정하기
      </button>
    </div>
  );
}
