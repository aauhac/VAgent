type DotKind = 'ALIGNED' | 'NOT_ALIGNED' | 'NEUTRAL' | 'INSUFFICIENT' | string;

type Props = {
  dots: DotKind[];
  label?: string;
};

/** Evidence dots — count-based, never a percentage bar. */
export default function GoalEvidenceDots({ dots, label }: Props) {
  if (!dots?.length) return null;
  return (
    <div className="goal-dots" role="img" aria-label={label || evidenceAria(dots)}>
      {dots.map((d, i) => (
        <span
          key={`${d}-${i}`}
          className={`goal-dot goal-dot--${dotClass(d)}`}
          title={dotTitle(d)}
        >
          {dotChar(d)}
        </span>
      ))}
    </div>
  );
}

function dotClass(d: string): string {
  if (d === 'ALIGNED' || d === 'GOAL_ALIGNED') return 'on';
  if (d === 'INSUFFICIENT') return 'gap';
  return 'off';
}

function dotChar(d: string): string {
  if (d === 'ALIGNED' || d === 'GOAL_ALIGNED') return '●';
  if (d === 'INSUFFICIENT') return '–';
  return '○';
}

function dotTitle(d: string): string {
  if (d === 'ALIGNED' || d === 'GOAL_ALIGNED') return '목표 방향';
  if (d === 'INSUFFICIENT') return '비교 근거 부족';
  return '목표와 다름';
}

function evidenceAria(dots: DotKind[]): string {
  const n = dots.filter((d) => d === 'ALIGNED' || d === 'GOAL_ALIGNED').length;
  return `최근 ${dots.length}회 중 목표 방향 ${n}회`;
}
