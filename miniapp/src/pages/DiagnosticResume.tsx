import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getDiagnosticSession } from '../api/client';
import { resolveDiagnosticRoute } from '../lib/diagnosticEntry';

/**
 * Catch-all for /diagnostic/:sessionId and unknown subpaths.
 * Never dumps the user on Home while a session id exists.
 */
export default function DiagnosticResume() {
  const { sessionId } = useParams();
  const nav = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setError('진단 세션 정보가 없어요.');
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const session = await getDiagnosticSession(sessionId);
        if (cancelled) return;
        const route = resolveDiagnosticRoute({ ...session, session_id: sessionId });
        if (route) {
          nav(route, { replace: true });
          return;
        }
        setError('진단 진행 상태를 확인하고 있어요. 잠시 후 다시 시도해 주세요.');
      } catch (e: any) {
        if (!cancelled) {
          setError(e?.message || '진단 세션을 불러오지 못했어요. 홈으로 이동하지 않고 여기서 다시 시도할 수 있어요.');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, nav]);

  return (
    <main>
      <p className="page-kicker">정밀 발성 진단</p>
      <p className="muted">{error || '진단 진행 상태를 확인하고 있어요…'}</p>
      {error && sessionId ? (
        <button
          className="btn"
          type="button"
          style={{ marginTop: 12 }}
          onClick={() => nav(`/diagnostic/${sessionId}/concerns`, { replace: true })}
        >
          이어서 진행
        </button>
      ) : null}
    </main>
  );
}
