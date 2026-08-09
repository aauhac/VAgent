import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { submitSafety } from '../api/client';

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
      await submitSafety(sessionId, payload);
      nav(`/diagnostic/${sessionId}/task/sustain_a`);
    } catch (e: any) {
      setError(e?.message || '제출 실패');
      setBusy(false);
    }
  }

  return (
    <main>
      <h1 className="brand" style={{ fontSize: '1.6rem' }}>안전 확인</h1>
      <p className="lead">
        질환을 진단하는 문진이 아니에요. 훈련을 계속해도 되는지 확인하는 최소한의 점검입니다.
      </p>
      <div className="panel">
        {QUESTIONS.map((q) => (
          <label key={q.id} className="area-row" style={{ cursor: 'pointer' }}>
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
        해당 항목이 있으면 질병명을 추정하지 않고, 연습 참고 수준으로 제한하며
        지속되면 전문가 평가를 고려해 달라는 안내만 드려요.
      </p>
      <button className="btn" disabled={busy} onClick={next}>다음</button>
      {error && <p className="fail">{error}</p>}
    </main>
  );
}
