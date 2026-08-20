import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { getAnalysis, saveHistory } from '../api/client';
import {
  ANALYSIS_INTERRUPTED,
  ANALYSIS_PROGRESS_HINT,
  ANALYSIS_PROGRESS_WAIT,
  analysisStageLabel,
  isInterruptedStage,
  visualAnalysisProgress,
} from '../lib/analysisProgress';
import { ANALYSIS_FAILED, RESULT_UNAVAILABLE } from '../lib/userFacingErrors';
import {
  notificationFeatureAvailable,
  requestAnalysisCompleteAgreement,
  type NotificationAgreementState,
} from '../lib/tossNotifications';

export default function Analyzing() {
  const { id } = useParams();
  const nav = useNavigate();
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState('queued');
  const [status, setStatus] = useState('queued');
  const [error, setError] = useState<string | null>(null);
  const [notifyState, setNotifyState] = useState<NotificationAgreementState>('IDLE');
  const [notifyError, setNotifyError] = useState<string | null>(null);
  const notifyOfferVisible = notificationFeatureAvailable();

  useEffect(() => {
    if (!id) return;
    let alive = true;
    const tick = async () => {
      try {
        const job = await getAnalysis(id);
        if (!alive) return;
        setProgress(typeof job.progress === 'number' ? job.progress : 0);
        setStage(job.stage || job.status || 'queued');
        setStatus(job.status || '');
        if (job.status === 'failed' || isInterruptedStage(job.stage, job.error)) {
          setError(
            isInterruptedStage(job.stage, job.error) ? ANALYSIS_INTERRUPTED : ANALYSIS_FAILED,
          );
          return;
        }
        if (job.status === 'completed' && job.result) {
          const q = job.result.quality;
          if (q?.status === 'fail') {
            nav('/quality', { state: { quality: q, analysisId: id }, replace: true });
            return;
          }
          try {
            sessionStorage.setItem('vocalfb_last_analysis_id', id);
          } catch {
            /* ignore */
          }
          saveHistory({
            id,
            overall: job.result.score?.overall,
            label: job.result.score?.label,
            filename: sessionStorage.getItem('vocalfb_last_filename') || undefined,
            at: new Date().toISOString(),
          });
          nav(`/result/${id}`, { replace: true });
          return;
        }
        window.setTimeout(tick, 1200);
      } catch {
        if (alive) setError(RESULT_UNAVAILABLE);
      }
    };
    tick();
    return () => {
      alive = false;
    };
  }, [id, nav]);

  const barWidth = visualAnalysisProgress({ status, stage, progress });

  return (
    <main>
      <h1 className="brand" style={{ fontSize: '1.7rem' }}>분석 중</h1>
      <div className="panel">
        {error ? (
          <>
            <p className="fail">{error}</p>
            <Link className="btn secondary" to="/">홈으로</Link>
          </>
        ) : (
          <>
            <p className="analyzing-stage">{analysisStageLabel(stage)}</p>
            <p className="analyzing-hint">{ANALYSIS_PROGRESS_HINT}</p>
            <div
              className="meter"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={barWidth}
              aria-label={analysisStageLabel(stage)}
            >
              <span className="meter-fill" style={{ width: `${barWidth}%` }} />
            </div>
            <p className="analyzing-wait">{ANALYSIS_PROGRESS_WAIT}</p>
            {notifyOfferVisible ? (
              <div className="analyzing-notify">
                <p className="analyzing-notify-kicker">잠깐 다른 일을 보셔도 돼요.</p>
                {notifyState === 'AGREED' ? (
                  <p className="analyzing-notify-ok">✓ 분석이 끝나면 알려드릴게요.</p>
                ) : (
                  <>
                    <p className="analyzing-notify-ask">분석이 끝나면 알려드릴까요?</p>
                    <button
                      type="button"
                      className="btn secondary"
                      style={{ width: '100%', marginTop: 10 }}
                      disabled={notifyState === 'REQUESTING' || !id}
                      onClick={async () => {
                        if (!id) return;
                        setNotifyError(null);
                        setNotifyState('REQUESTING');
                        const result = await requestAnalysisCompleteAgreement(id);
                        if (result.state === 'REJECTED') {
                          setNotifyState('IDLE');
                          return;
                        }
                        if (result.state === 'AGREED') {
                          setNotifyState('AGREED');
                          return;
                        }
                        setNotifyState(result.state === 'UNAVAILABLE' ? 'UNAVAILABLE' : 'ERROR');
                        setNotifyError(result.message || null);
                      }}
                    >
                      {notifyState === 'REQUESTING' ? '설정 중…' : '완료 알림 받기'}
                    </button>
                    {notifyError ? <p className="fail" style={{ marginTop: 8 }}>{notifyError}</p> : null}
                  </>
                )}
              </div>
            ) : null}
          </>
        )}
      </div>
    </main>
  );
}
