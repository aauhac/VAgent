import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  getPreviewUrl,
  getProducts,
  getSongDetailedReport,
  patchHistory,
} from '../api/client';

function seekTo(audio: HTMLAudioElement | null, sec?: number | null) {
  if (!audio || sec == null || Number.isNaN(Number(sec))) return;
  audio.currentTime = Math.max(0, Number(sec));
  void audio.play();
}

function ScoreLine({
  score,
  label,
  unknown,
}: {
  score?: number | null;
  label?: string;
  unknown?: boolean;
}) {
  if (unknown || score == null) {
    return (
      <strong>
        — · <span className="muted" style={{ fontWeight: 500 }}>{label || '판단 어려움'}</span>
      </strong>
    );
  }
  return (
    <strong>
      {Math.round(score)}점
      <span className="muted" style={{ marginLeft: 8, fontWeight: 500 }}>
        · {label}
      </span>
    </strong>
  );
}

export default function SongDetailReport() {
  const { id } = useParams();
  const nav = useNavigate();
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [diagPrice, setDiagPrice] = useState('—');
  const [diagProduct, setDiagProduct] = useState('diagnostic_upgrade');
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const blobUrl = useMemo(() => sessionStorage.getItem('vocalfb_last_blob'), []);
  const previewUrl = id ? getPreviewUrl(id) : '';

  useEffect(() => {
    if (!id) return;
    getSongDetailedReport(id)
      .then((r) => {
        if (r.error === 'SONG_DETAIL_LOCKED') {
          setError('SONG_DETAIL_LOCKED');
          return;
        }
        setReport(r);
        patchHistory(id, { songDetailUnlocked: true });
      })
      .catch((e) => setError(e.message));
    getProducts(id).then((cat) => {
      const offer = cat.offers?.diagnostic || 'diagnostic_full';
      setDiagProduct(offer);
      setDiagPrice(cat.products?.[offer]?.display_amount || '—');
    }).catch(() => undefined);
  }, [id]);

  if (error === 'SONG_DETAIL_LOCKED') {
    return (
      <main>
        <h1 className="brand" style={{ fontSize: '1.5rem' }}>상세 리포트 잠금</h1>
        <p className="lead">이 노래의 상세 리포트가 아직 해제되지 않았어요.</p>
        <Link className="btn" to={`/result/${id}`}>결과로 돌아가기</Link>
      </main>
    );
  }
  if (error) return <main><p className="fail">{error}</p></main>;
  if (!report) return <main><p className="muted">상세 리포트 불러오는 중…</p></main>;

  const summary = report.summary || {};
  const overall = report.overall_assessment || {};
  const focus = report.focus_segments || report.timeline || [];
  const partial = summary.overall_display_state === 'PARTIAL'
    || overall.overall_display_state === 'PARTIAL';
  const unavailable = summary.overall_display_state === 'UNAVAILABLE'
    || overall.overall_display_state === 'UNAVAILABLE';

  return (
    <main>
      <Link className="muted" to={`/result/${id}`}>← 무료 결과</Link>
      <h1 className="brand" style={{ fontSize: '1.6rem', marginTop: 12 }}>
        {summary.title || '이 노래의 상세 분석'}
      </h1>
      <p className="lead">{summary.text || overall.text}</p>
      {partial && (
        <p className="muted">
          {overall.total_axis_count || 4}개 영역 중 {overall.reliable_axis_count || summary.reliable_axis_count || 0}개만
          신뢰도 있게 계산된 부분 분석이에요.
        </p>
      )}
      {unavailable && (
        <p className="muted">종합 점수는 이번 녹음에서 확정하지 않았어요.</p>
      )}

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>4축 상세</h3>
        {(report.areas || []).map((a: any) => {
          const unknown = a.status === 'unknown' || a.score == null;
          return (
            <div key={a.area_id} style={{ marginBottom: 20 }}>
              <div className="area-row">
                <span>{a.display_name}</span>
                <ScoreLine
                  score={a.score}
                  label={a.status_label || (unknown ? '판단 어려움' : a.status)}
                  unknown={unknown}
                />
              </div>
              {a.headline && <p style={{ margin: '6px 0 4px' }}>{a.headline}</p>}
              <p className="muted" style={{ margin: '4px 0' }}>{a.interpretation}</p>
              {(a.why_this_score || []).length > 0 && (
                <ul className="muted" style={{ margin: '6px 0', paddingLeft: 18 }}>
                  {(a.why_this_score || []).slice(0, 4).map((w: string, i: number) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
              {(a.submetrics || []).length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <p className="muted" style={{ fontSize: '0.85rem', marginBottom: 4 }}>
                    {unknown ? '참고 가능한 세부 항목' : '세부 항목'}
                  </p>
                  {(a.submetrics || []).map((s: any) => (
                    <div className="area-row" key={s.submetric_id} style={{ fontSize: '0.9rem' }}>
                      <span className="muted">{s.display_name}</span>
                      <span>
                        {s.score == null ? '—' : Math.round(s.score)}
                        {s.display_note ? (
                          <span className="muted"> · {s.display_note}</span>
                        ) : s.confidence_label && s.confidence_label !== '신뢰 높음' ? (
                          <span className="muted"> · {s.confidence_label}</span>
                        ) : null}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {(a.practice?.summary) && (
                <p style={{ marginTop: 8 }}><strong>연습</strong> {a.practice.summary}</p>
              )}
            </div>
          );
        })}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>잘하고 있는 점</h3>
        {(report.strengths || []).length === 0 && <p className="muted">강조할 강점이 없어요.</p>}
        {(report.strengths || []).map((s: any, i: number) => (
          <div key={`${s.submetric_id || s.area_id}-${i}`} style={{ marginBottom: 10 }}>
            <strong>{s.display_name}</strong>
            {s.score != null && <span className="muted"> · {Math.round(s.score)}</span>}
            <p className="muted">{s.note}</p>
          </div>
        ))}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>개선 우선순위</h3>
        {(report.priority_issues || []).length === 0 && <p className="muted">우선 개선 항목이 없어요.</p>}
        {(report.priority_issues || []).map((p: any, i: number) => (
          <div key={`${p.area_id}-${i}`} style={{ marginBottom: 10 }}>
            <strong>{p.display_name}</strong>
            <p className="muted">{p.what_user_hears}</p>
            {p.practice && <p>{p.practice}</p>}
          </div>
        ))}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>다시 들어볼 구간</h3>
        <audio ref={audioRef} src={blobUrl || previewUrl} controls style={{ width: '100%' }} />
        {focus.length === 0 && (
          <p className="muted">표시할 구간이 없어요.</p>
        )}
        {focus.map((ev: any, i: number) => (
          <div key={i} style={{ marginTop: 12 }}>
            <div className="area-row">
              <span>
                {ev.time_label
                  || `${Number(ev.start_sec).toFixed(1)}s – ${Number(ev.end_sec).toFixed(1)}s`}
                {ev.score != null ? ` · ${Math.round(ev.score)}` : ''}
              </span>
              <button
                type="button"
                className="btn secondary"
                style={{ fontSize: '0.8rem', padding: '6px 10px' }}
                onClick={() => seekTo(audioRef.current, ev.start_sec)}
              >
                듣기
              </button>
            </div>
            <p className="muted" style={{ margin: '4px 0' }}>
              {ev.headline || ev.user_message}
            </p>
            {ev.why && ev.why !== ev.user_message && (
              <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>{ev.why}</p>
            )}
          </div>
        ))}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>비브라토 참고</h3>
        {report.vibrato?.available ? (
          <>
            {(report.vibrato.lines || []).map((line: any, i: number) => (
              <p key={i} className="muted" style={{ margin: '4px 0' }}>
                {line.label}: {line.value}
              </p>
            ))}
            <p className="muted">{report.vibrato.note}</p>
          </>
        ) : (
          <p className="muted">{report.vibrato?.note || '참고 분석 없음'}</p>
        )}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>오늘의 연습</h3>
        <ul>
          {(report.training_plan || []).map((x: string, i: number) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>한계</h3>
        <ul className="muted">
          {(report.limitations || []).map((x: string, i: number) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
        <p className="muted">{report.disclaimer}</p>
      </div>

      <div className="panel" style={{ borderColor: 'var(--accent, #2a6)' }}>
        <h3 style={{ marginTop: 0 }}>{report.upgrade?.title || '더 정밀하게 알고 싶나요?'}</h3>
        <p className="muted">{report.upgrade?.body}</p>
        <button
          className="btn"
          type="button"
          onClick={() => nav(`/premium?analysis=${id}&product=${diagProduct}`)}
        >
          {report.upgrade?.cta || '정밀 발성 진단'} · {diagPrice}
        </button>
      </div>
    </main>
  );
}
