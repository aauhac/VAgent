import { Link } from 'react-router-dom';
import { loadHistory } from '../api/client';

export default function History() {
  const items = loadHistory();
  return (
    <main>
      <Link className="muted" to="/">← 홈</Link>
      <h1 className="brand" style={{ fontSize: '1.7rem', marginTop: 16 }}>이전 결과</h1>
      <div className="panel">
        {items.length === 0 && <p className="muted">아직 기록이 없어요.</p>}
        {items.map((h) => (
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
    </main>
  );
}
