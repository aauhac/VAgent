type Props = {
  checked: boolean;
  onChange: (next: boolean) => void;
  /** "녹음" | "파일" */
  noun?: string;
  disabled?: boolean;
};

/**
 * Default unchecked = pure vocal (VOCAL_ONLY).
 * Checked = accompaniment present (MIXED + separation).
 */
export default function AccompanimentToggle({
  checked,
  onChange,
  noun = '녹음',
  disabled,
}: Props) {
  return (
    <label className={`accomp-toggle${checked ? ' is-on' : ''}`}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="accomp-toggle-body">
        <span className="accomp-toggle-title">이 {noun}에는 반주가 있어요</span>
        <span className="accomp-toggle-help">
          {checked
            ? '반주가 섞인 노래로 처리해 보컬을 분리해 분석해요.'
            : '체크하지 않으면 순수 보컬 기준으로 분석해요.'}
        </span>
      </span>
    </label>
  );
}

export function analysisOptsFromAccompaniment(hasAccompaniment: boolean) {
  if (hasAccompaniment) {
    return {
      analysis_mode: 'FUNCTIONAL' as const,
      input_mode: 'MIXED' as const,
      separate: true,
    };
  }
  return {
    analysis_mode: 'FUNCTIONAL' as const,
    input_mode: 'VOCAL_ONLY' as const,
    separate: false,
  };
}
