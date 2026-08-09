import { Link } from 'react-router-dom';
import { loadHistory, loadUnlockedSessions } from '../api/client';

export default function History() {
  const items = loadHistory();
  const sessions = loadUnlockedSessions();
  return (
    <main>
      <Link className="muted" to="/">← 홈</Link>
      <h1 className="brand" style={{ fontSize: '1.7rem', marginTop: 16 }}>이전 결과</h1>
      <div className="panel">
        <h3 style={{ marginTop: 0 }}>노래 분석 (무료)</h3>
        {items.length === 0 && <p className="muted">아직 기록이 없어요.</p>}
        {items.map((h: any) => (
          <Link
            key={h.id}
            to={`/result/${h.id}`}
            className="area-row"
            style={{ color: 'inherit', textDecoration: 'none' }}
          >
            <span>{new Date(h.at).toLocaleString()}</span>
            <strong>{h.overall ?? '—'} {h.label || ''}</strong>
          </Link>
        ))}
      </div>
      <div className="panel">
        <h3 style={{ marginTop: 0 }}>상세 발성 진단 (영구 해제)</h3>
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
