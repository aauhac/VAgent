import { Link } from 'react-router-dom';
import { loadUnlockedSessions } from '../api/client';

export default function Home() {
  const sessions = loadUnlockedSessions();
  return (
    <main>
      <p className="muted" style={{ marginBottom: 8 }}>Physiology-informed Vocal Assessment</p>
      <h1 className="brand">노래 실력<br />진단받기</h1>
      <p className="lead">
        무료로 노래 발성 특성을 빠르게 보고, 상세 리포트와 정밀 발성 진단을
        선택해서 이용할 수 있어요.
      </p>
      <div className="cta-row">
        <Link className="btn" to="/record">노래 녹음하기</Link>
        <Link className="btn secondary" to="/upload">파일 업로드</Link>
        <Link className="btn secondary" to="/history">이전 결과</Link>
      </div>
      {sessions.length > 0 && (
        <div className="panel" style={{ marginTop: 20 }}>
          <h3 style={{ marginTop: 0 }}>영구 해제된 진단</h3>
          {sessions.slice(0, 5).map((sid) => (
            <Link
              key={sid}
              to={`/diagnostic/${sid}/report`}
              className="area-row"
              style={{ color: 'inherit', textDecoration: 'none' }}
            >
              <span>세션 {sid.slice(0, 8)}…</span>
              <strong>리포트</strong>
            </Link>
          ))}
        </div>
      )}
      <p className="muted" style={{ marginTop: 28 }}>
        성대 구조·질환을 진단하는 검사가 아닙니다. 음향 기반 발성 패턴 분석·훈련 참고 서비스입니다.
      </p>
    </main>
  );
}
