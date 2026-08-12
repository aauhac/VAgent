import RatioSpectrum from './RatioSpectrum';

type Props = {
  profile: any;
  compact?: boolean;
};

export default function VocalTypeHero({ profile, compact }: Props) {
  if (!profile || profile.available === false) {
    return (
      <section className="section">
        <p className="eyebrow">내 발성 성향</p>
        <h2 className="type-title">
          이번 녹음에서는 발성 성향을 안정적으로 구분하기 어려웠어요.
        </h2>
      </section>
    );
  }

  const hc = profile.head_chest || {};
  const sb = profile.source_balance || {};
  const rs = profile.register_strategy || {};
  const chest = sb.chest_percent ?? hc.chest_ratio;
  const head = sb.head_percent ?? hc.head_ratio;
  const showRatio = hc.available !== false && chest != null && head != null;
  const title =
    sb.label
    || profile.display_name
    || profile.headline
    || '발성 성향';
  const description =
    profile.description
    || (showRatio
      ? '흉성과 두성 쪽 발성 특성이 관찰됐어요.'
      : '');

  const showRegister = !compact && (rs.title || rs.status);
  const registerTitle = rs.title || '추가 확인 필요';
  const registerBody =
    rs.description
    || '이번 녹음만으로 성구 연결 방식을 충분히 확인하기 어려웠어요.';

  return (
    <section className="section">
      <div className={compact ? undefined : 'card'}>
        <p className="eyebrow">내 발성 성향</p>
        <h2 className="type-title">{title}</h2>
        {showRatio ? <RatioSpectrum chest={Number(chest)} head={Number(head)} /> : null}
        {description ? (
          <p className="body-text" style={{ marginTop: 14 }}>
            {description}
          </p>
        ) : null}
      </div>

      {showRegister ? (
        <div style={{ marginTop: compact ? 12 : 18 }}>
          <p className="eyebrow">성구 연결</p>
          <h3 className="finding-title" style={{ marginTop: 4 }}>{registerTitle}</h3>
          <p className="body-text muted" style={{ marginTop: 8 }}>
            {registerBody}
          </p>
        </div>
      ) : null}
    </section>
  );
}
