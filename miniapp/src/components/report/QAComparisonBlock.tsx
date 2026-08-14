type Comparison = {
  baseline_label?: string;
  baseline_instruction?: string;
  variant_label?: string;
  variant_instruction?: string;
  success_condition?: string;
  if_better?: string;
  if_not_better?: string;
  A?: string;
  B?: string;
  success?: string;
};

export default function QAComparisonBlock({
  comparison,
  testIdPrefix,
}: {
  comparison?: Comparison | null;
  testIdPrefix?: string;
}) {
  if (!comparison) return null;
  const a = comparison.baseline_instruction || comparison.A;
  const b = comparison.variant_instruction || comparison.B;
  if (!a || !b) return null;
  const success = comparison.success_condition || comparison.success;
  const ifBetter = comparison.if_better;
  const prefix = testIdPrefix || 'qa-compare';

  return (
    <div data-testid={prefix} style={{ marginTop: 10 }}>
      <p className="body-text" style={{ fontWeight: 600, margin: 0 }}>
        비교해보기
      </p>
      <p className="body-text" style={{ marginTop: 6, lineHeight: 1.5 }} data-testid={`${prefix}-a`}>
        ① {a}
      </p>
      <p className="body-text" style={{ marginTop: 4, lineHeight: 1.5 }} data-testid={`${prefix}-b`}>
        ② {b}
      </p>
      {success ? (
        <div style={{ marginTop: 10 }} data-testid={`${prefix}-success`}>
          <p className="body-text" style={{ fontWeight: 600, margin: 0 }}>
            잘 맞는 방향
          </p>
          <p className="body-text muted" style={{ marginTop: 4, lineHeight: 1.5 }}>
            두 번째에서 {success}
            {ifBetter && !success.includes(ifBetter) ? ` — ${ifBetter}` : ''}
          </p>
        </div>
      ) : null}
    </div>
  );
}
