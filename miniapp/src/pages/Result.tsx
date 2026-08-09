import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getAnalysis, getPreviewUrl, removeHistory } from '../api/client';

const AREA_COPY: Record<string, { good: string; need: string; practice: string }> = {
  stability: {
    good: '길게 유지한 음이 비교적 안정적이에요.',
    need: '길게 뻗는 음에서 소리가 조금 흔들릴 수 있어요.',
    practice: '편한 음 하나를 골라 3초 동안 같은 크기로 유지해 보세요.',
  },
  projection: {
    good: '목소리가 비교적 또렷하게 전달돼요.',
    need: '목소리가 공간에 묻혀 또렷함이 약하게 들릴 수 있어요.',
    practice: '첫 소리를 말하듯 분명하게 시작해 보세요.',
  },
  resonance: {
    good: '공명 균형이 무난해요.',
    need: '소리가 답답하거나 가볍게 들릴 수 있어요.',
    practice: "'네', '니', '냐'로 같은 멜로디를 편하게 불러 보세요.",
  },
  dynamic_control: {
    good: '강약 표현이 자연스러워요.',
    need: '전체적으로 비슷한 크기로 들려 표현이 밋밋할 수 있어요.',
    practice: '중요한 부분만 살짝 더 분명하게 불러 보세요.',
  },
};

export default function Result() {
  const { id } = useParams();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const [showTech, setShowTech] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const blobUrl = useMemo(() => sessionStorage.getItem('vocalfb_last_blob'), []);
  const previewUrl = id ? getPreviewUrl(id) : '';

  useEffect(() => {
    if (!id) return;
    getAnalysis(id)
      .then((job) => {
        if (!job.result) {
          setExpired(true);
          return;
        }
        setData(job.result);
      })
      .catch(() => {
        setExpired(true);
        setError('분석 기록이 만료됐어요.');
      });
  }, [id]);

  if (expired) {
    return (
      <main>
        <h1 className="brand" style={{ fontSize: '1.6rem' }}>분석 기록이 만료됐어요</h1>
        <p className="lead">서버에서 결과를 찾을 수 없어요. 다시 녹음해 주세요.</p>
        {id && (
          <button
            className="btn secondary"
            style={{ marginBottom: 12 }}
            onClick={() => {
              removeHistory(id);
              window.location.href = '/history';
            }}
          >
            기록에서 삭제
          </button>
        )}
        <Link className="btn" to="/record">다시 녹음</Link>
      </main>
    );
  }

  if (error && !data) return <main><p className="fail">{error}</p><Link to="/">홈</Link></main>;
  if (!data) return <main><p className="muted">불러오는 중…</p></main>;

  const score = data.score || {};
  const best = score.best_area;
  const focus = score.focus_area;
  const cta = data.premium_cta || {};

  return (
    <main>
      <Link className="muted" to="/">← 홈</Link>

      {!score.available ? (
        <div className="panel" style={{ marginTop: 16 }}>
          <h1 className="brand" style={{ fontSize: '1.6rem' }}>정확한 분석이 어려운 녹음</h1>
          <p className="lead">{data.quality?.user_message}</p>
          <Link className="btn" to="/record">다시 녹음하기</Link>
        </div>
      ) : (
        <>
          <div className="score-hero">
            <div className="num">{Math.round(score.overall)}</div>
            <div className="label">{score.label || '좋은 편이에요'}</div>
            {score.calibration_status === 'uncalibrated' && (
              <p className="muted" style={{ fontSize: '0.85rem', marginTop: 6 }}>베타 분석 점수</p>
            )}
          </div>

          <p className="lead">{data.short_summary}</p>

          <div className="panel">
            {(score.areas || []).map((a: any) => (
              <div className="area-row" key={a.area_id}>
                <span>{a.display_name}</span>
                <strong>
                  {a.status === 'unknown' ? '—' : Math.round(a.score)}
                  <span className="muted" style={{ marginLeft: 8, fontWeight: 500 }}>{a.status}</span>
                </strong>
              </div>
            ))}
          </div>
        </>
      )}

      <audio
        ref={audioRef}
        src={blobUrl || previewUrl}
        controls
        style={{ width: '100%', marginTop: 16 }}
      />

      {score.available && (
        <>
          <div className="panel">
            <h3 style={{ marginTop: 0 }}>가장 잘한 영역</h3>
            {best ? (
              <>
                <strong>{best.display_name}</strong>
                <p className="muted">{AREA_COPY[best.area_id]?.good || '좋은 편으로 측정됐어요.'}</p>
              </>
            ) : (
              <p className="muted">이번엔 강조할 강점이 없어요.</p>
            )}
          </div>

          <div className="panel">
            <h3 style={{ marginTop: 0 }}>먼저 개선할 영역</h3>
            {focus ? (
              <>
                <strong>{focus.display_name}</strong>
                <p className="muted">{AREA_COPY[focus.area_id]?.need}</p>
                <p>{AREA_COPY[focus.area_id]?.practice}</p>
              </>
            ) : (
              <p className="muted">우선 개선 항목이 없어요.</p>
            )}
          </div>

          <div className="panel" style={{ borderColor: 'var(--accent, #2a6)' }}>
            <h3 style={{ marginTop: 0 }}>{cta.title || '상세 발성 진단 영구 해제'}</h3>
            <p className="muted">{cta.body}</p>
            <p className="muted" style={{ fontSize: '0.85rem' }}>
              노래 점수와 별도로, 표준 Diagnostic Task로 발성 메커니즘 경향을 추정해요.
            </p>
            <Link className="btn" to={`/premium?analysis=${id}`}>
              정밀 발성 진단 시작
            </Link>
          </div>
        </>
      )}

      <p className="muted" style={{ marginTop: 16 }}>{data.disclaimer}</p>

      <button className="btn secondary" style={{ width: '100%' }} onClick={() => setShowTech((v) => !v)}>
        {showTech ? '분석 상세 닫기' : '녹음 품질'}
      </button>
      {showTech && (
        <pre className="panel" style={{ overflow: 'auto', fontSize: 11 }}>
          {JSON.stringify(
            {
              tier: data.tier,
              analysis_mode: data.analysis_mode,
              score_version: score.version,
              calibration_status: score.calibration_status,
              quality: data.quality,
            },
            null,
            2,
          )}
        </pre>
      )}
    </main>
  );
}
