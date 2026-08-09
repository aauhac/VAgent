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

  return (
    <main>
      <Link className="muted" to={`/result/${id}`}>← 무료 결과</Link>
      <h1 className="brand" style={{ fontSize: '1.6rem', marginTop: 12 }}>
        {summary.title || '이 노래의 상세 분석'}
      </h1>
      <p className="lead">{summary.text}</p>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>4축 상세</h3>
        {(report.areas || []).map((a: any) => (
          <div key={a.area_id} style={{ marginBottom: 18 }}>
            <div className="area-row">
              <span>{a.display_name}</span>
              <strong>
                {a.status === 'unknown' || a.score == null
                  ? '—'
                  : `${Math.round(a.score)}점`}
                <span className="muted" style={{ marginLeft: 8, fontWeight: 500 }}>
                  {a.status_label || (a.status === 'unknown' ? '판단 어려움' : a.status)}
                </span>
              </strong>
            </div>
            <p className="muted" style={{ margin: '4px 0' }}>{a.interpretation}</p>
            {a.practice && <p style={{ margin: '4px 0 8px' }}>{a.practice}</p>}
            {(a.submetrics || []).length > 0 && (
              <div style={{ marginTop: 8, paddingLeft: 4 }}>
                {(a.submetrics || []).map((s: any) => (
                  <div className="area-row" key={s.submetric_id} style={{ fontSize: '0.9rem' }}>
                    <span className="muted">{s.display_name}</span>
                    <span>
                      {s.status === 'unknown' || s.score == null ? '—' : Math.round(s.score)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>잘하고 있는 점</h3>
        {(report.strengths || []).length === 0 && <p className="muted">강조할 강점이 없어요.</p>}
        {(report.strengths || []).map((s: any) => (
          <div key={s.area_id} style={{ marginBottom: 10 }}>
            <strong>{s.display_name}</strong>
            <p className="muted">{s.note}</p>
          </div>
        ))}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>개선 우선순위</h3>
        {(report.priority_issues || []).length === 0 && <p className="muted">우선 개선 항목이 없어요.</p>}
        {(report.priority_issues || []).map((p: any) => (
          <div key={p.area_id} style={{ marginBottom: 10 }}>
            <strong>{p.display_name}</strong>
            <p className="muted">{p.what_user_hears}</p>
            {p.practice && <p>{p.practice}</p>}
          </div>
        ))}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>문제가 나타난 구간</h3>
        <audio ref={audioRef} src={blobUrl || previewUrl} controls style={{ width: '100%' }} />
        {(report.timeline || []).length === 0 && (
          <p className="muted">표시할 구간이 없어요.</p>
        )}
        {(report.timeline || []).map((ev: any, i: number) => (
          <div key={i} className="area-row" style={{ marginTop: 8 }}>
            <span className="muted">
              {ev.start_sec != null ? `${Number(ev.start_sec).toFixed(1)}s` : '—'}
              {' – '}
              {ev.end_sec != null ? `${Number(ev.end_sec).toFixed(1)}s` : '—'}
              {' · '}
              {ev.user_message || '참고 구간'}
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
        ))}
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>비브라토 참고</h3>
        {report.vibrato?.available ? (
          <p className="muted">
            rate {report.vibrato.rate_hz ?? '—'} Hz · extent {report.vibrato.extent_cents ?? '—'} cents
            <br />
            {report.vibrato.note}
          </p>
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
