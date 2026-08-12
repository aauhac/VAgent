import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  getServerHistory,
  loadUnlockedSessions,
  removeHistory,
} from '../api/client';

type Row = {
  id: string;
  overall?: number | null;
  label?: string;
  at: string;
  sessionId?: string;
  songDetailUnlocked?: boolean;
  vocalType?: string;
  filename?: string;
  missing?: boolean;
  interrupted?: boolean;
  status?: string;
};

function formatDate(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${mm}.${dd}`;
}

export default function History() {
  const [items, setItems] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const sessions = loadUnlockedSessions();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const server = await getServerHistory(50);
        if (cancelled) return;
        const rows: Row[] = (server.items || []).map((it) => ({
          id: it.analysis_id,
          at: it.created_at || '',
          filename: it.filename || undefined,
          vocalType: it.vocal_type || undefined,
          songDetailUnlocked: !!it.song_detail_unlocked,
          sessionId: it.diagnostic_session_id || undefined,
          status: it.status,
          missing: it.status === 'missing' || !!it.artifact_missing,
          interrupted: it.error_code === 'INTERRUPTED_RESTART' || it.status === 'failed' && it.error_code === 'INTERRUPTED_RESTART',
        }));
        setItems(rows);
      } catch {
        // Server history is SoT — do not pollute with localStorage on failure in production builds.
        // Dev-only: show empty rather than merging legacy local history into server view.
        if (cancelled) return;
        setItems([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main>
      <Link className="muted" to="/">‹ 홈</Link>
      <h1 className="brand" style={{ fontSize: '1.5rem', marginTop: 16 }}>이전 결과</h1>

      <section className="section">
        <h3 className="section-title" style={{ fontSize: '1.1rem' }}>노래 분석</h3>
        {loading && <p className="muted">불러오는 중…</p>}
        {!loading && items.length === 0 && <p className="muted">아직 기록이 없어요.</p>}
        {items.map((h) => {
          const title = h.vocalType || h.label || '발성 분석';
          if (h.interrupted) {
            return (
              <div key={h.id} style={{ marginBottom: 18 }}>
                <p className="muted" style={{ margin: '0 0 4px', fontSize: '0.85rem' }}>
                  {h.at ? formatDate(h.at) : ''}
                </p>
                <p style={{ margin: '0 0 4px', fontWeight: 700 }}>분석이 중단됐어요</p>
                <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
                  서버 재시작으로 분석이 끝까지 가지 못했어요. 다시 녹음·업로드해 주세요.
                </p>
              </div>
            );
          }
          if (h.missing) {
            return (
              <div key={h.id} style={{ marginBottom: 18 }}>
                <p className="muted" style={{ margin: '0 0 4px', fontSize: '0.85rem' }}>
                  {h.at ? formatDate(h.at) : ''}
                </p>
                <p style={{ margin: '0 0 4px', fontWeight: 700 }}>결과를 찾을 수 없음</p>
                <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
                  서버에 없는 기록이에요. 로컬 목록에서 정리할 수 있어요.
                </p>
                <button
                  type="button"
                  className="btn ghost"
                  style={{ marginTop: 8 }}
                  onClick={() => {
                    removeHistory(h.id);
                    setItems((prev) => prev.filter((x) => x.id !== h.id));
                  }}
                >
                  목록에서 제거
                </button>
              </div>
            );
          }
          return (
            <div key={h.id} style={{ marginBottom: 18 }}>
              <Link
                to={h.songDetailUnlocked ? `/result/${h.id}/detail` : `/result/${h.id}`}
                style={{ color: 'inherit', textDecoration: 'none', display: 'block' }}
              >
                <p className="muted" style={{ margin: '0 0 4px', fontSize: '0.85rem' }}>
                  {h.at ? formatDate(h.at) : ''}
                </p>
                <p style={{ margin: '0 0 4px', fontWeight: 700, fontSize: '1.05rem', wordBreak: 'keep-all' }}>
                  {title}
                </p>
                {h.filename && (
                  <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>{h.filename}</p>
                )}
              </Link>
              <div className="audio-chip-row" style={{ marginTop: 10 }}>
                <Link className="btn chip secondary" to={`/result/${h.id}`}>무료 결과</Link>
                {h.songDetailUnlocked ? (
                  <Link className="btn chip secondary" to={`/result/${h.id}/detail`}>상세 리포트</Link>
                ) : (
                  <Link className="btn chip secondary" to={`/result/${h.id}`}>상세 리포트</Link>
                )}
                {h.sessionId ? (
                  <Link className="btn chip secondary" to={`/diagnostic/${h.sessionId}/report`}>
                    정밀 진단
                  </Link>
                ) : null}
              </div>
            </div>
          );
        })}
      </section>

      <section className="section" style={{ borderBottom: 0 }}>
        <h3 className="section-title" style={{ fontSize: '1.1rem' }}>연결된 정밀 진단</h3>
        <p className="muted" style={{ marginTop: -4, marginBottom: 8, fontSize: '0.85rem' }}>
          노래 분석과 따로 저장된 세션이 있을 때만 여기에 표시돼요.
        </p>
        {sessions.length === 0 && <p className="muted">연결된 추가 세션이 없어요.</p>}
        {sessions.map((sid) => (
          <Link
            key={sid}
            to={`/diagnostic/${sid}/report`}
            className="detail-row"
            style={{ textDecoration: 'none' }}
          >
            <span style={{ fontWeight: 600 }}>세션 {sid.slice(0, 10)}…</span>
            <span className="meta">보기 ›</span>
          </Link>
        ))}
      </section>
    </main>
  );
}
