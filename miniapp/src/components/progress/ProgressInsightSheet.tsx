import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import type { ProgressCard } from '../../lib/progressPresentation';
import type { GoalProgressPayload } from '../../lib/goalProgress';
import GoalEvidenceDots from './GoalEvidenceDots';

type Props = {
  open: boolean;
  card?: ProgressCard | null;
  goalProgress?: GoalProgressPayload | null;
  mode?: 'card' | 'goal';
  onClose: () => void;
};

/** Lightweight Progress Insight — never primary-links to detail/diagnostic. */
export default function ProgressInsightSheet({
  open,
  card,
  goalProgress,
  mode = 'card',
  onClose,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  if (mode === 'goal' && goalProgress?.goal) {
    return (
      <div className="sheet-root" role="presentation" onClick={onClose}>
        <div
          className="sheet-panel"
          role="dialog"
          aria-modal="true"
          aria-label="목표 변화 상세"
          onClick={(e) => e.stopPropagation()}
          data-testid="goal-progress-sheet"
        >
          <div className="sheet-handle" aria-hidden />
          <p className="page-kicker" style={{ marginTop: 4 }}>
            {goalProgress.goal.display_title || '이번 목표'}
          </p>
          <h2 className="sheet-title">{goalProgress.goal.label}</h2>

          {goalProgress.current_evidence?.evidence ? (
            <div className="sheet-block">
              <p className="sheet-label">이번 녹음</p>
              <p className="sheet-value">{String(goalProgress.current_evidence.evidence)}</p>
            </div>
          ) : null}

          {goalProgress.dots?.length ? (
            <div className="sheet-block">
              <p className="sheet-label">최근 {goalProgress.window?.size || goalProgress.dots.length}회</p>
              <GoalEvidenceDots dots={goalProgress.dots} />
            </div>
          ) : null}

          <div className="sheet-block">
            <p className="sheet-label">목표 방향 결과</p>
            <p className="sheet-value">
              {goalProgress.previous_window
                ? `이전 ${goalProgress.previous_window.size}회 ${goalProgress.previous_window.goal_aligned_count}회 → 최근 ${goalProgress.window?.goal_aligned_count ?? 0}회`
                : `최근 ${goalProgress.window?.size || 5}회 중 ${goalProgress.window?.goal_aligned_count ?? 0}회`}
            </p>
            {goalProgress.window ? (
              <p className="muted" style={{ marginTop: 6, fontSize: '0.82rem' }}>
                비교 가능한 기록 {goalProgress.window.evaluable_count}회
              </p>
            ) : null}
          </div>

          <div className="sheet-block">
            <p className="sheet-label">판단 이유</p>
            <p className="body-text" style={{ margin: 0 }}>
              {goalProgress.summary || '현재 목표와 관련된 결과만 비교했어요.'}
              {' '}
              달성률(%)이 아니라 기록 횟수로 보여드려요.
            </p>
          </div>

          <button type="button" className="btn" style={{ width: '100%', marginTop: 8 }} onClick={onClose}>
            확인
          </button>
          <Link
            className="btn secondary"
            to="/progress"
            style={{ width: '100%', marginTop: 8, display: 'block', textAlign: 'center' }}
            onClick={onClose}
          >
            내 변화 보기
          </Link>
        </div>
      </div>
    );
  }

  if (!card) return null;

  const seq = card.recent_sequence || [];

  return (
    <div className="sheet-root" role="presentation" onClick={onClose}>
      <div
        className="sheet-panel"
        role="dialog"
        aria-modal="true"
        aria-label={`${card.title} 변화 상세`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-handle" aria-hidden />
        <p className="page-kicker" style={{ marginTop: 4 }}>{card.headline}</p>
        <h2 className="sheet-title">{card.title}</h2>

        <div className="sheet-block">
          <p className="sheet-label">이번 녹음</p>
          <p className="sheet-value">{card.current_label}</p>
        </div>

        <div className="sheet-block">
          <p className="sheet-label">최근 기록</p>
          <p className="sheet-value">{card.baseline_modal_label}</p>
        </div>

        {seq.length > 0 ? (
          <div className="sheet-block">
            <p className="sheet-label">최근 {seq.length}회</p>
            <div className="sheet-seq">
              {seq.map((s, i) => (
                <div key={`${s.raw}-${i}`} className="sheet-seq-item">
                  <span className="sheet-seq-raw">{s.raw}</span>
                  <span className="sheet-seq-arrow" aria-hidden>↓</span>
                  <span className="sheet-seq-label">{shortLabel(s)}</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {card.how_much ? (
          <div className="sheet-block">
            <p className="sheet-label">{card.how_much.label}</p>
            <p className="sheet-value">{card.how_much.summary}</p>
          </div>
        ) : null}

        <div className="sheet-block">
          <p className="sheet-label">이번 변화</p>
          <p className="body-text" style={{ margin: 0 }}>
            {card.detail}
            {card.why_improvement ? ` ${card.why_improvement}` : ''}
          </p>
        </div>

        <button type="button" className="btn" style={{ width: '100%', marginTop: 8 }} onClick={onClose}>
          확인
        </button>
      </div>
    </div>
  );
}

function shortLabel(s: { raw: string; label: string }): string {
  if (s.raw === 'CONNECTED') return '안정';
  if (s.raw === 'PARTIAL') return '일부';
  if (s.raw === 'DISRUPTED') return '끊김';
  if (s.raw === 'STABLE') return '안정';
  if (s.raw === 'UNSTABLE') return '흔들';
  return s.label.slice(0, 4);
}
