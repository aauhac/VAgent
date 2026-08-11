import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  getAnalysisAccess,
  loadHistory,
  loadUnlockedSessions,
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
};

function formatDate(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${mm}.${dd}`;
}

export default function History() {
  const [items, setItems] = useState<Row[]>(() => loadHistory());
  const sessions = loadUnlockedSessions();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const next: Row[] = [];
      for (const h of loadHistory()) {
        try {
          const access = await getAnalysisAccess(h.id);
          next.push({
            ...h,
            songDetailUnlocked: !!access.song_detail_unlocked,
            sessionId: access.diagnostic_session_id || h.sessionId,
          });
        } catch {
          next.push(h);
        }
      }
      if (!cancelled) setItems(next);
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
        {items.length === 0 && <p className="muted">아직 기록이 없어요.</p>}
        {items.map((h) => {
          const title = h.vocalType || h.label || '발성 분석';
          return (
            <div key={h.id} style={{ marginBottom: 18 }}>
              <Link
                to={h.songDetailUnlocked ? `/result/${h.id}/detail` : `/result/${h.id}`}
                style={{ color: 'inherit', textDecoration: 'none', display: 'block' }}
              >
                <p className="muted" style={{ margin: '0 0 4px', fontSize: '0.85rem' }}>
                  {formatDate(h.at)}
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
        <h3 className="section-title" style={{ fontSize: '1.1rem' }}>정밀 발성 진단</h3>
        {sessions.length === 0 && <p className="muted">해제된 진단이 없어요.</p>}
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
