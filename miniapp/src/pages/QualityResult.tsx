import { Link, useLocation } from 'react-router-dom';

export default function QualityResult() {
  const location = useLocation() as { state?: { quality?: any; analysisId?: string } };
  const quality = location.state?.quality;
  const id = location.state?.analysisId;

  if (!quality) {
    return (
      <main>
        <p className="muted">품질 결과가 없어요.</p>
        <Link className="btn" to="/">홈으로</Link>
      </main>
    );
  }

  const statusClass = quality.status === 'fail' ? 'fail' : quality.status === 'warn' ? 'warn' : 'ok';

  return (
    <main>
      <h1 className="brand" style={{ fontSize: '1.7rem' }}>녹음 품질</h1>
      <p className={statusClass}>{quality.user_message}</p>
      <div className="panel">
        <div className="area-row"><span>상태</span><strong className={statusClass}>{quality.status}</strong></div>
        <div className="area-row"><span>길이</span><span>{quality.metrics?.duration_sec}s</span></div>
        <div className="area-row"><span>유성음 비율</span><span>{quality.metrics?.voiced_ratio}</span></div>
      </div>
      {quality.status === 'fail' ? (
        <Link className="btn" to="/record" style={{ display: 'block', marginTop: 16 }}>다시 녹음</Link>
      ) : (
        id && <Link className="btn" to={`/result/${id}`} style={{ display: 'block', marginTop: 16 }}>결과 보기</Link>
      )}
    </main>
  );
}
