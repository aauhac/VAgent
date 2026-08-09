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
};

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
      <Link className="muted" to="/">← 홈</Link>
      <h1 className="brand" style={{ fontSize: '1.7rem', marginTop: 16 }}>이전 결과</h1>
      <div className="panel">
        <h3 style={{ marginTop: 0 }}>노래 분석</h3>
        {items.length === 0 && <p className="muted">아직 기록이 없어요.</p>}
        {items.map((h) => (
          <div key={h.id} style={{ marginBottom: 14 }}>
            <Link
              to={`/result/${h.id}`}
              className="area-row"
              style={{ color: 'inherit', textDecoration: 'none' }}
            >
              <span>{new Date(h.at).toLocaleString()}</span>
              <strong>{h.overall ?? '—'} {h.label || ''}</strong>
            </Link>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
              <Link className="btn secondary" style={{ fontSize: '0.8rem' }} to={`/result/${h.id}`}>
                무료 결과
              </Link>
              {h.songDetailUnlocked ? (
                <Link
                  className="btn secondary"
                  style={{ fontSize: '0.8rem' }}
                  to={`/result/${h.id}/detail`}
                >
                  상세 리포트 보기
                </Link>
              ) : (
                <Link className="btn secondary" style={{ fontSize: '0.8rem' }} to={`/result/${h.id}`}>
                  상세 리포트 구매
                </Link>
              )}
              {(h.sessionId || sessions.includes(h.sessionId || '')) && h.sessionId ? (
                <Link
                  className="btn secondary"
                  style={{ fontSize: '0.8rem' }}
                  to={`/diagnostic/${h.sessionId}/report`}
                >
                  정밀 진단 보기
                </Link>
              ) : null}
            </div>
          </div>
        ))}
      </div>
      <div className="panel">
        <h3 style={{ marginTop: 0 }}>정밀 발성 진단</h3>
        {sessions.length === 0 && <p className="muted">해제된 진단이 없어요.</p>}
        {sessions.map((sid) => (
          <Link
            key={sid}
            to={`/diagnostic/${sid}/report`}
            className="area-row"
            style={{ color: 'inherit', textDecoration: 'none' }}
          >
            <span>세션 {sid.slice(0, 10)}…</span>
            <strong>리포트 보기</strong>
          </Link>
        ))}
      </div>
    </main>
  );
}
