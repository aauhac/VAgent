import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { createDiagnosticSession, mockPaySession, saveUnlockedSession } from '../api/client';

export default function PremiumUnlock() {
  const [params] = useSearchParams();
  const analysisId = params.get('analysis') || undefined;
  const existingSession = params.get('session') || undefined;
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      if (existingSession) {
        await mockPaySession(existingSession);
        saveUnlockedSession(existingSession);
        nav(`/diagnostic/${existingSession}/safety`);
        return;
      }
      const session = await createDiagnosticSession(analysisId);
      await mockPaySession(session.session_id);
      saveUnlockedSession(session.session_id);
      nav(`/diagnostic/${session.session_id}/safety`);
    } catch (e: any) {
      setError(e?.message || '잠금 해제 실패');
      setBusy(false);
    }
  }

  return (
    <main>
      <Link className="muted" to={analysisId ? `/result/${analysisId}` : '/'}>← 뒤로</Link>
      <h1 className="brand" style={{ fontSize: '1.7rem', marginTop: 16 }}>상세 발성 진단<br />영구 해제</h1>
      <p className="lead">
        표준화된 짧은 Diagnostic Task로 발성 메커니즘 경향을 추정하고,
        실제 몸 사용 코칭을 제공해요. 한 번 완료한 상세 리포트는 계속 확인할 수 있어요.
      </p>
      <div className="panel">
        <p className="muted">개발 환경에서는 Mock Premium으로 바로 진행합니다. (Production에서는 Toss IAP)</p>
        <button className="btn" disabled={busy} onClick={start}>
          {busy ? '준비 중…' : '진단 시작 (Mock 결제)'}
        </button>
        {error && <p className="fail">{error}</p>}
      </div>
      <p className="muted" style={{ marginTop: 16 }}>
        성대 구조나 질환을 진단하는 검사가 아닙니다. 훈련 참고용 표준화 발성 평가입니다.
      </p>
    </main>
  );
}
