import SpectrumAxis from './SpectrumAxis';

type Props = {
  profile: any;
};

export default function TimbreProfileSection({ profile }: Props) {
  if (!profile) return null;
  if (!profile.available) {
    const reason = (profile.limitations || [])[0]
      || '이번 녹음에서는 음색 프로필을 안정적으로 구성하지 못했어요.';
    return (
      <section className="section">
        <h3 className="section-title">음색 프로필</h3>
        <p className="body-text muted">{reason}</p>
      </section>
    );
  }

  const axes = profile.axes || {};
  const order = [
    'brightness',
    'presence',
    'airiness',
    'texture',
    'harmonic_concentration',
    'timbre_consistency',
  ];
  const labels: Record<string, string> = {
    brightness: '밝기',
    presence: '존재감',
    airiness: '숨 섞임',
    texture: '질감',
    harmonic_concentration: '배음 집중',
    timbre_consistency: '음색 일관성',
  };

  return (
    <section className="section">
      <h3 className="section-title">음색 프로필</h3>
      <p className="body-text muted" style={{ marginTop: 0 }}>
        좋고 나쁨이 아니라, 이번 녹음에서 관찰된 음색 특성이에요.
      </p>
      {order.map((id) => {
        const ax = axes[id];
        if (!ax || ax.continuum == null) return null;
        return (
          <SpectrumAxis
            key={id}
            label={labels[id] || id}
            leftLabel={ax.left_label || ''}
            rightLabel={ax.right_label || ''}
            value={Number(ax.continuum)}
            stateLabel={ax.status || ''}
            confidenceLabel={ax.confidence_label}
            showConfidence={false}
          />
        );
      })}
      {(profile.summary || []).slice(0, 2).map((s: string) => (
        <p key={s} className="body-text muted">{s}</p>
      ))}
    </section>
  );
}
