import RatioSpectrum from './RatioSpectrum';

type Props = {
  profile: any;
  styleProfile?: any;
  compact?: boolean;
};

export default function VocalTypeHero({ profile, styleProfile, compact }: Props) {
  const style = styleProfile || profile?.vocal_style_profile || null;

  if ((!profile || profile.available === false) && (!style || style.available === false)) {
    return (
      <section className="section">
        <p className="eyebrow">내 발성 스타일</p>
        <h2 className="type-title">
          이번 녹음에서는 발성 스타일을 안정적으로 구분하기 어려웠어요.
        </h2>
      </section>
    );
  }

  const sbPres = style?.source_balance_presentation || {};
  const hc = profile?.head_chest || {};
  const sb = profile?.source_balance || sbPres || {};
  const canonical =
    style?.canonical_register
    || style?.register_strategy_public
    || profile?.canonical_register
    || profile?.register_strategy
    || {};

  const chest = sbPres.chest_percent ?? sb.chest_percent ?? hc.chest_ratio;
  const head = sbPres.head_percent ?? sb.head_percent ?? hc.head_ratio;
  const showRatio = Boolean(
    (sbPres.show_ratio ?? sb.show_ratio ?? hc.show_ratio ?? true)
    && hc.available !== false
    && sb.balance_class !== 'CONFLICTED'
    && sbPres.conflicted !== true
    && chest != null
    && head != null,
  );

  const title =
    style?.display_name
    || profile?.display_name
    || profile?.headline
    || '발성 스타일';
  const description =
    style?.description
    || profile?.description
    || '';

  const traits: Array<{ label: string; value: string }> =
    (style?.primary_traits || []).slice(0, 3).map((t: any) => ({
      label: t.label || t.key,
      value: t.value,
    }));

  const showRegister = !compact && (canonical.title || canonical.status || canonical.profile_label);
  const registerTitle = canonical.title || canonical.profile_label || '추가 확인 필요';
  const registerBody =
    canonical.description
    || '이번 녹음만으로 성구 연결 방식을 충분히 확인하기 어려웠어요.';

  const balanceClass = (sbPres.balance_class || sb.balance_class || '').toUpperCase();
  const balanceLabel =
    sbPres.label
    || sb.label
    || (balanceClass === 'CONFLICTED'
      ? '여러 음향 특징이 서로 다른 방향으로 나타났어요.'
      : null);

  return (
    <section className="section">
      <div className={compact ? undefined : 'card'}>
        <p className="eyebrow">내 발성 스타일</p>
        <h2 className="type-title">{title}</h2>
        {description ? (
          <p className="body-text" style={{ marginTop: 14 }}>
            {description}
          </p>
        ) : null}

        {traits.length > 0 ? (
          <div style={{ marginTop: 16 }}>
            <p className="eyebrow">주요 특징</p>
            <ul className="body-text" style={{ paddingLeft: 18, margin: '8px 0 0' }}>
              {traits.map((t) => (
                <li key={`${t.label}-${t.value}`} style={{ marginBottom: 4 }}>
                  {t.label} · {t.value}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      {!compact ? (
        <div style={{ marginTop: 18 }}>
          <p className="eyebrow">흉성·두성 관련 음향 성향</p>
          {showRatio ? (
            <>
              <RatioSpectrum chest={Number(chest)} head={Number(head)} />
              <p className="body-text muted" style={{ marginTop: 8 }}>
                음향 성향 참고값이며, 실제 성구 사용 시간 비율이 아니에요.
              </p>
            </>
          ) : (
            <p className="body-text" style={{ marginTop: 6 }}>
              {balanceLabel
                || '이번 녹음에서는 흉성·두성 관련 음향 성향을 안정적으로 나누기 어려웠어요.'}
            </p>
          )}
        </div>
      ) : null}

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
