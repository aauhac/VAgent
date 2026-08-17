import { USER_GOAL_OPTIONS } from '../../lib/goalProgress';

type Props = {
  open: boolean;
  onClose: () => void;
  onSelect: (focus: string, label: string, extra?: { target?: string; style_id?: string; kind?: string }) => void;
};

/** Compact goal picker — catalog from coaching focuses, no heavy settings page. */
export default function GoalSelectorSheet({ open, onClose, onSelect }: Props) {
  if (!open) return null;
  return (
    <div className="sheet-root" role="presentation" onClick={onClose}>
      <div
        className="sheet-panel"
        role="dialog"
        aria-modal="true"
        aria-label="목표 선택"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-handle" aria-hidden />
        <h2 className="sheet-title">연습 목표 선택</h2>
        <p className="muted" style={{ marginTop: 0, marginBottom: 14, fontSize: '0.88rem' }}>
          이전 목표는 기록으로 남고, 새 목표부터 다시 변화를 살펴볼게요.
        </p>
        <ul className="goal-option-list">
          {USER_GOAL_OPTIONS.map((opt) => (
            <li key={`${opt.focus}-${opt.style_id || ''}`}>
              <button
                type="button"
                className="goal-option"
                onClick={() => {
                  onSelect(opt.focus, opt.label, {
                    target: opt.target || undefined,
                    style_id: opt.style_id || undefined,
                    kind: opt.kind,
                  });
                  onClose();
                }}
              >
                {opt.label}
              </button>
            </li>
          ))}
        </ul>
        <button type="button" className="btn secondary" style={{ width: '100%', marginTop: 8 }} onClick={onClose}>
          닫기
        </button>
      </div>
    </div>
  );
}
