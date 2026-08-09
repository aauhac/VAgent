import { Link } from 'react-router-dom';

export default function Home() {
  return (
    <main>
      <p className="muted" style={{ marginBottom: 8 }}>Vocal Skill Test</p>
      <h1 className="brand">노래 실력<br />진단받기</h1>
      <p className="lead">
        녹음하거나 파일을 올리면 발성 안정성, 전달력, 공명, 강약을 분석해 드려요.
        원곡 음정·박자 채점이 아니라, 목소리 발성 특성을 보는 서비스예요.
      </p>
      <div className="cta-row">
        <Link className="btn" to="/record">노래 녹음하기</Link>
        <Link className="btn secondary" to="/upload">파일 업로드</Link>
        <Link className="btn secondary" to="/history">이전 결과</Link>
      </div>
      <p className="muted" style={{ marginTop: 28 }}>
        의료 진단이 아니며, 점수는 아직 보정 전(uncalibrated) 참고값입니다.
      </p>
    </main>
  );
}
