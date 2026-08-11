import { Link } from 'react-router-dom';
import { loadUnlockedSessions } from '../api/client';

function BrandMark() {
  return (
    <div className="brand-row" aria-label="VAgent">
      <span className="brand-mark" aria-hidden />
      <span className="brand-name">VAgent</span>
    </div>
  );
}

export default function Home() {
  const sessions = loadUnlockedSessions();
  return (
    <main>
      <BrandMark />
      <h1 className="brand" style={{ marginTop: 16 }}>
        내 목소리는
        <br />
        어떻게 쓰고 있을까?
      </h1>
      <p className="lead">
        20~40초 노래하면 발성 타입과 주요 특징을 분석해드려요.
      </p>
      <div className="cta-row">
        <Link className="btn" to="/record">노래 녹음하기</Link>
        <Link className="btn secondary" to="/upload">파일로 분석하기</Link>
        <Link className="btn secondary" to="/history">이전 결과</Link>
      </div>
      {sessions.length > 0 && (
        <section className="section" style={{ marginTop: 8 }}>
          <h3 className="section-title" style={{ fontSize: '1.05rem' }}>정밀 진단 기록</h3>
          {sessions.slice(0, 5).map((sid) => (
            <Link
              key={sid}
              to={`/diagnostic/${sid}/report`}
              className="detail-row"
              style={{ textDecoration: 'none' }}
            >
              <span style={{ fontWeight: 600 }}>세션 {sid.slice(0, 8)}…</span>
              <span className="meta">보기 ›</span>
            </Link>
          ))}
        </section>
      )}
      <p className="footer-note">음향 기반 발성 분석 서비스</p>
    </main>
  );
}
