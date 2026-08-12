import SpectrumAxis from './SpectrumAxis';

type Props = {
  profile: any;
};

function statusLabel(axis: any): string {
  const s = String(axis?.status || '').toUpperCase();
  const map: Record<string, string> = {
    PRESERVED: '비교적 안정적',
    DEGRADED: '일부 저하',
    CONTINUOUS: '자연스러운 편',
    DISCONTINUOUS: '연결이 급함',
    INCREASED: '일부 증가',
    DECREASED: '감소',
    STABLE: '대체로 유지',
    PRESENCE_LOSS: '존재감 감소',
    BRIGHTNESS_SHIFT: '밝기 이동',
    EXCESS_BRIGHTENING_CANDIDATE: '밝아지는 경향',
    UNCERTAIN: '판단 보류',
  };
  return map[s] || axis?.summary || '참고';
}

export default function HighNoteFunctionSection({ profile }: Props) {
  if (!profile) return null;
  if (!profile.available) {
    const reason = (profile.limitations || [])[0]
      || '이번 녹음에서는 고음 구간이 충분하지 않아 고음 수행 프로필은 표시하지 않았어요.';
    return (
      <section className="section">
        <h3 className="section-title">고음 수행</h3>
        <p className="body-text muted">{reason}</p>
      </section>
    );
  }

  const ctx = profile.pitch_context || {};
  const axes = profile.axes || {};
  const rows = [
    { key: 'high_note_stability', label: '고음 안정성' },
    { key: 'transition_continuity', label: '성구 연결' },
    { key: 'high_note_effort_cost', label: '고음에서 힘 증가' },
    { key: 'high_note_breathiness_shift', label: '고음 숨 섞임 변화' },
    { key: 'high_note_regularity_cost', label: '고음 규칙성' },
    { key: 'resonance_preservation', label: '고음 음색 유지' },
  ];

  const reliable = ctx.highest_reliable_f0_hz;
  const observed = ctx.highest_observed_f0_hz;

  return (
    <section className="section">
      <h3 className="section-title">고음 수행</h3>
      {reliable != null ? (
        <p className="body-text">
          도달 가능한 고음(신뢰)
          {' '}
          <strong style={{ fontWeight: 600 }}>{Math.round(Number(reliable))} Hz</strong>
          {observed != null && Number(observed) > Number(reliable) * 1.05 ? (
            <span className="muted"> · 순간 최고 {Math.round(Number(observed))} Hz와 구분</span>
          ) : null}
        </p>
      ) : null}
      <div className="card" style={{ display: 'grid', gap: 10 }}>
        {rows.map((r) => {
          const ax = axes[r.key];
          if (!ax) return null;
          return (
            <div key={r.key} className="detail-row" style={{ cursor: 'default' }}>
              <span className="detail-label">{r.label}</span>
              <span className="detail-meta">{statusLabel(ax)}</span>
            </div>
          );
        })}
      </div>
      {(profile.summary || []).slice(0, 2).map((s: string) => (
        <p key={s} className="body-text muted">{s}</p>
      ))}
    </section>
  );
}
