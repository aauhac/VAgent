import SpectrumAxis from './SpectrumAxis';
import { helpTextForAxis } from '../../lib/axisHelpText';

type Props = {
  profile: any;
  /** When true, omit presence axis (already shown in VocalProfile). */
  omitPresence?: boolean;
};

const REASON_COPY: Record<string, string> = {
  INSUFFICIENT_VOCAL_SEGMENTS: '음색을 비교할 수 있는 보컬 구간이 충분하지 않았어요.',
  MIXED_CONTAMINATION: '반주 영향이 큰 구간이 많아 음색 특성을 안정적으로 분리하지 못했어요.',
};

export default function TimbreProfileSection({ profile, omitPresence = false }: Props) {
  if (!profile) return null;

  const availability = String(profile.availability || (profile.available ? 'FULL' : 'UNAVAILABLE')).toUpperCase();
  const reasonUser =
    profile.reason_user
    || REASON_COPY[String(profile.reason || '')]
    || null;
  const disclaimer = '음색은 좋고 나쁨이 아니라 관찰된 특징으로 설명합니다.';

  if (!profile.available && availability === 'UNAVAILABLE') {
    return (
      <section className="section">
        <h3 className="section-title">음색 프로필</h3>
        <p className="body-text muted">
          {reasonUser || '이번 녹음에서는 음색 프로필을 안정적으로 구성하지 못했어요.'}
        </p>
        <p className="body-text muted" style={{ marginTop: 8, fontSize: '0.9rem' }}>
          {disclaimer}
        </p>
      </section>
    );
  }

  const axes = profile.axes || {};
  const order = [
    'brightness',
    ...(omitPresence ? [] : ['presence']),
    'airiness',
    'texture',
    'harmonic_concentration',
    'timbre_consistency',
  ];
  const labels: Record<string, string> = {
    brightness: '밝기',
    presence: '중역 존재감',
    airiness: '음색의 공기감',
    texture: '질감',
    harmonic_concentration: '배음 집중',
    timbre_consistency: '음색 일관성',
  };

  return (
    <section className="section">
      <h3 className="section-title">음색 프로필</h3>
      {availability === 'PARTIAL' && reasonUser ? (
        <p className="body-text muted" style={{ marginTop: 0 }}>{reasonUser}</p>
      ) : null}
      <p className="body-text muted" style={{ marginTop: availability === 'PARTIAL' ? 8 : 0 }}>
        {disclaimer}
      </p>
      {order.map((id) => {
        const ax = axes[id];
        if (!ax || ax.continuum == null) return null;
        if (ax.available === false) return null;
        return (
          <SpectrumAxis
            key={id}
            label={labels[id] || id}
            leftLabel={ax.left_label || ''}
            rightLabel={ax.right_label || ''}
            value={Number(ax.continuum)}
            stateLabel={ax.status || ''}
            helpText={helpTextForAxis(id)}
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
