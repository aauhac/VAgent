import { useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import type { ProgressCard } from '../../lib/progressPresentation';
import { progressLinkState } from '../../lib/progressNavigation';
import { recentWindowLabel } from '../../lib/userFacingLabels';

type Props = {
  open: boolean;
  card?: ProgressCard | null;
  onClose: () => void;
};

/** Lightweight Progress Insight — change cards only (no goal-management mode). */
export default function ProgressInsightSheet({
  open,
  card,
  onClose,
}: Props) {
  const location = useLocation();
  const progressState = progressLinkState(location.pathname + location.search);
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

  if (!open || !card) return null;

  const seq = card.recent_sequence || [];
  const showSeq = seq.length >= 3;

  return (
    <div className="sheet-root" role="presentation" onClick={onClose}>
      <div
        className="sheet-panel"
        role="dialog"
        aria-modal="true"
        aria-label={`${card.title} 변화 상세`}
        onClick={(e) => e.stopPropagation()}
        data-testid="progress-insight-sheet"
      >
        <div className="sheet-handle" aria-hidden />
        <p className="page-kicker" style={{ marginTop: 4 }}>{card.headline}</p>
        <h2 className="sheet-title">{card.title}</h2>

        <div className="sheet-block">
          <p className="sheet-label">이번 녹음</p>
          <p className="sheet-value">{card.current_label}</p>
        </div>

        <div className="sheet-block">
          <p className="sheet-label">이전 기록</p>
          <p className="sheet-value">{card.baseline_modal_label}</p>
        </div>

        {showSeq ? (
          <div className="sheet-block">
            <p className="sheet-label">{recentWindowLabel(seq.length)}</p>
            <p className="sheet-seq-chips" aria-label={seq.map((s) => s.chip || s.label).join(' · ')}>
              {seq.map((s, i) => (
                <span key={`${s.raw}-${i}`} className="sheet-chip">
                  {s.chip || s.label}
                </span>
              ))}
            </p>
          </div>
        ) : null}

        {card.how_much && seq.length >= 2 ? (
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
        <Link
          className="btn secondary"
          to="/progress"
          state={progressState}
          style={{ width: '100%', marginTop: 8, display: 'block', textAlign: 'center' }}
          onClick={onClose}
        >
          내 변화 보기
        </Link>
      </div>
    </div>
  );
}
