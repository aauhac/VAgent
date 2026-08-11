import RatioSpectrum from './RatioSpectrum';

type Props = {
  profile: any;
  compact?: boolean;
};

export default function VocalTypeHero({ profile, compact }: Props) {
  if (!profile || profile.available === false) {
    return (
      <section className="section">
        <p className="eyebrow">내 발성 타입</p>
        <h2 className="type-title">
          이번 녹음에서는 발성 타입을 안정적으로 구분하기 어려웠어요.
        </h2>
      </section>
    );
  }

  const hc = profile.head_chest || {};
  const chest = hc.chest_ratio;
  const head = hc.head_ratio;
  const showRatio = hc.available !== false && chest != null && head != null;

  return (
    <section className="section">
      <div className={compact ? undefined : 'card'}>
        <p className="eyebrow">내 발성 타입</p>
        <h2 className="type-title">{profile.display_name || profile.headline}</h2>
        {showRatio ? <RatioSpectrum chest={Number(chest)} head={Number(head)} /> : null}
        {profile.description && (
          <p className="body-text" style={{ marginTop: 14 }}>
            {profile.description}
          </p>
        )}
      </div>
    </section>
  );
}
