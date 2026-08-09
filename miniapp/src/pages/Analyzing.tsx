import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { getAnalysis, saveHistory } from '../api/client';

export default function Analyzing() {
  const { id } = useParams();
  const nav = useNavigate();
  const [progress, setProgress] = useState(5);
  const [stage, setStage] = useState('queued');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let alive = true;
    const tick = async () => {
      try {
        const job = await getAnalysis(id);
        if (!alive) return;
        setProgress(job.progress ?? 10);
        setStage(job.stage || job.status);
        if (job.status === 'failed') {
          setError(job.error || '분석 실패');
          return;
        }
        if (job.status === 'completed' && job.result) {
          const q = job.result.quality;
          if (q?.status === 'fail') {
            nav('/quality', { state: { quality: q, analysisId: id }, replace: true });
            return;
          }
          saveHistory({
            id,
            overall: job.result.score?.overall,
            label: job.result.score?.label,
            at: new Date().toISOString(),
          });
          nav(`/result/${id}`, { replace: true });
          return;
        }
        window.setTimeout(tick, 1200);
      } catch (e: any) {
        if (alive) setError(e?.message || '상태 조회 실패');
      }
    };
    tick();
    return () => {
      alive = false;
    };
  }, [id, nav]);

  return (
    <main>
      <h1 className="brand" style={{ fontSize: '1.7rem' }}>분석 중</h1>
      <p className="lead">목소리를 듣고 발성 특성을 계산하고 있어요.</p>
      <div className="panel">
        <div className="muted">단계: {stage}</div>
        <div className="meter"><span style={{ width: `${progress}%` }} /></div>
        <div>{progress}%</div>
        {error && (
          <>
            <p className="fail">{error}</p>
            <Link className="btn secondary" to="/">홈으로</Link>
          </>
        )}
      </div>
    </main>
  );
}
