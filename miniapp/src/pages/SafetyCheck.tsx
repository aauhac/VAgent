import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { analyzeDiagnosticSession, submitSafety } from '../api/client';

const QUESTIONS = [
  { id: 'pain_on_phonation', label: '발성 시 통증' },
  { id: 'sudden_voice_change', label: '갑자기 생긴 뚜렷한 음성 변화' },
  { id: 'persistent_severe_hoarseness', label: '오랫동안 지속되는 심한 쉰 목소리' },
  { id: 'severe_discomfort_after', label: '발성 후 심한 불편감' },
  { id: 'breathing_difficulty', label: '호흡이 어려운 증상' },
];

export default function SafetyCheck() {
  const { sessionId } = useParams();
  const nav = useNavigate();
  const [answers, setAnswers] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function next() {
    if (!sessionId) return;
    setBusy(true);
    try {
      const payload: Record<string, boolean> = {};
      QUESTIONS.forEach((q) => {
        payload[q.id] = !!answers[q.id];
      });
      const session = await submitSafety(sessionId, payload);
      const selected: string[] = session?.selected_tasks || [];
      const first = session?.next_task_id || selected[0];
      if (first) {
        nav(`/diagnostic/${sessionId}/task/${first}`);
        return;
      }
      // Zero required tasks — analyze song-only precision diagnostic
      if (session?.status === 'READY_FOR_ANALYSIS') {
        await analyzeDiagnosticSession(sessionId);
        nav(`/diagnostic/${sessionId}/report`);
        return;
      }
      nav(`/diagnostic/${sessionId}/report`);
    } catch (e: any) {
      setError(e?.message || '제출 실패');
      setBusy(false);
    }
  }

  return (
    <main>
      <h1 className="brand" style={{ fontSize: '1.6rem' }}>안전 확인</h1>
      <p className="lead">
        질환을 진단하는 문진이 아니에요. 정밀 진단을 진행하기 전 안전 관련 증상을 확인합니다.
      </p>
      <div className="card">
        {QUESTIONS.map((q) => (
          <label key={q.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '10px 0', cursor: 'pointer' }}>
            <span>{q.label}</span>
            <input
              type="checkbox"
              checked={!!answers[q.id]}
              onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.checked }))}
            />
          </label>
        ))}
      </div>
      <p className="muted">
        해당 항목이 있으면 질병명을 추정하지 않고, 분석을 제한하며
        지속되면 전문가 평가를 고려해 달라는 안내만 드려요.
      </p>
      <button className="btn" disabled={busy} onClick={next}>다음</button>
      {error && <p className="fail">{error}</p>}
    </main>
  );
}
