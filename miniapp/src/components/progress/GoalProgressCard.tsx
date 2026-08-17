import { Link } from 'react-router-dom';
import type { GoalProgressPayload } from '../../lib/goalProgress';
import { goalCountLabel } from '../../lib/goalProgress';
import { recentWindowLabel } from '../../lib/userFacingLabels';
import GoalEvidenceDots from './GoalEvidenceDots';

type Props = {
  progress: GoalProgressPayload;
  onOpenInsight?: () => void;
  onChangeGoal?: () => void;
  compact?: boolean;
  /** Free Result / Progress: no change CTA */
  readOnly?: boolean;
  /** When linking to /progress (no onOpenInsight), pass return context */
  progressReturnTo?: string;
};

/**
 * Compact goal progress card — evidence counts / dots only.
 */
export default function GoalProgressCard({
  progress,
  onOpenInsight,
  onChangeGoal,
  compact,
  readOnly,
  progressReturnTo = '/',
}: Props) {
  if (!progress || progress.status === 'NO_GOAL' || !progress.goal) {
    return null;
  }

  const title = progress.goal.is_recommended ? '추천 목표' : (progress.goal.display_title || '이번 목표');
  const w = progress.window;
  const actual = w?.recording_count ?? w?.evaluable_count ?? progress.dots?.length ?? 0;
  const requested = w?.size ?? 5;
  const windowText = recentWindowLabel(actual, requested);
  const countText = goalCountLabel(progress);
  const hideHeavy =
    progress.status === 'INSUFFICIENT_HISTORY'
    || progress.status === 'INSUFFICIENT_EVIDENCE'
    || progress.status === 'STARTING'
    || actual < 2;

  return (
    <div className={`goal-card${compact ? ' goal-card--compact' : ''}`} data-testid="goal-progress-card">
      <p className="page-kicker" style={{ marginTop: 0 }}>{title}</p>
      <p className="goal-card-label">{progress.goal.label}</p>

      {w && !hideHeavy ? (
        <>
          <p className="goal-card-meta">{windowText}</p>
          {progress.dots?.length && actual >= 3 ? (
            <GoalEvidenceDots
              dots={progress.dots}
              label={`${windowText} 중 목표 방향 ${w.goal_aligned_count}회`}
            />
          ) : null}
          <p className="goal-card-count">{countText}</p>
        </>
      ) : progress.summary ? null : (
        <p className="goal-card-summary">기록이 조금 더 쌓이면 목표 방향 변화를 보여드릴게요.</p>
      )}

      {progress.summary ? (
        <p className="goal-card-summary">{progress.summary}</p>
      ) : null}

      {progress.previous_window && progress.comparison_available && actual >= 3 ? (
        <p className="muted goal-card-prev">
          이전 기록 · 목표 방향 {progress.previous_window.goal_aligned_count}회
        </p>
      ) : null}

      <div className={`goal-card-actions${readOnly || !onChangeGoal ? ' goal-card-actions--single' : ''}`}>
        {onOpenInsight ? (
          <button type="button" className="btn secondary" onClick={onOpenInsight}>
            변화 보기
          </button>
        ) : (
          <Link
            className="btn secondary"
            to="/progress"
            state={{ returnTo: progressReturnTo }}
          >
            변화 보기
          </Link>
        )}
        {!readOnly && onChangeGoal ? (
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
        이 노래의 분석 결과를 바탕으로 앞으로 집중할 목표를 정해보세요.
      </p>
      <button type="button" className="btn" style={{ width: '100%' }} onClick={onSetGoal}>
        목표 정하기
      </button>
    </div>
  );
}
