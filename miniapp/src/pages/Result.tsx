import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getAnalysis } from '../api/client';

export default function Result() {
  const { id } = useParams();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [showTech, setShowTech] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const blobUrl = useMemo(() => sessionStorage.getItem('vocalfb_last_blob'), []);

  useEffect(() => {
    if (!id) return;
    getAnalysis(id)
      .then((job) => setData(job.result))
      .catch((e) => setError(e.message));
  }, [id]);

  if (error) return <main><p className="fail">{error}</p><Link to="/">홈</Link></main>;
  if (!data) return <main><p className="muted">불러오는 중…</p></main>;

  const score = data.score || {};
  const feedback = data.feedback || {};
  const timeline = data.timeline || [];
  const duration = data.audio?.duration_sec || 1;

  function seekTo(sec: number) {
    const el = audioRef.current;
    if (!el) return;
    el.currentTime = sec;
    void el.play();
  }

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
            <p className="muted" style={{ fontSize: '0.8rem' }}>
              {score.version} · {score.calibration_status}
            </p>
          </div>

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

      {blobUrl && (
        <audio ref={audioRef} src={blobUrl} controls style={{ width: '100%', marginTop: 16 }} />
      )}

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>문제가 나타난 구간</h3>
        <div className="timeline">
          {timeline.map((ev: any, i: number) => {
            const left = `${(ev.start_sec / duration) * 100}%`;
            return (
              <button
                key={i}
                className="mark"
                style={{ left }}
                title={ev.user_message}
                onClick={() => seekTo(ev.start_sec)}
              />
            );
          })}
        </div>
        <div className="muted" style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>0:00</span>
          <span>{formatSec(duration)}</span>
        </div>
        {timeline.length === 0 && <p className="muted">표시할 구간이 없어요.</p>}
        {timeline.map((ev: any, i: number) => (
          <button
            key={`t-${i}`}
            className="btn secondary"
            style={{ display: 'block', width: '100%', marginTop: 8 }}
            onClick={() => seekTo(ev.start_sec)}
          >
            {formatSec(ev.start_sec)}–{formatSec(ev.end_sec)} · {ev.user_message}
          </button>
        ))}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>잘하고 있는 점</h3>
        {(feedback.well_done || data.strengths || []).length === 0 && (
          <p className="muted">이번엔 강조할 강점이 없어요.</p>
        )}
        {(feedback.well_done || []).map((w: any, i: number) => (
          <div key={i} style={{ marginBottom: 12 }}>
            <strong>{w.title}</strong>
            <p className="muted">{w.feedback}</p>
          </div>
        ))}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>개선하면 좋은 점</h3>
        {(feedback.needs_work || []).length === 0 && <p className="muted">우선 개선 항목이 없어요.</p>}
        {(feedback.needs_work || []).map((n: any, i: number) => (
          <div key={i} style={{ marginBottom: 14 }}>
            <strong>{n.title}</strong>
            <p className="muted">{n.what_user_hears}</p>
            <p>{n.practice}</p>
          </div>
        ))}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>오늘의 연습</h3>
        <ul>
          {(feedback.practice_plan || ['편한 음 유지 연습']).map((p: string, i: number) => (
            <li key={i}>{p}</li>
          ))}
        </ul>
        {feedback.weekly_goal && <p className="muted">주간 목표: {feedback.weekly_goal}</p>}
      </div>

      <button className="btn secondary" style={{ width: '100%' }} onClick={() => setShowTech((v) => !v)}>
        {showTech ? '분석 상세 닫기' : '분석 상세'}
      </button>
      {showTech && (
        <pre className="panel" style={{ overflow: 'auto', fontSize: 11 }}>
          {JSON.stringify(
            {
              quality: data.quality,
              optional_analysis: data.optional_analysis,
              analysis_notes: data.analysis_notes,
              feedback_status: data.feedback_status,
            },
            null,
            2,
          )}
        </pre>
      )}
    </main>
  );
}

function formatSec(sec: number) {
  const s = Math.max(0, Math.floor(sec || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
