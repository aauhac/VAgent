import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  getDiagnosticProtocol,
  getDiagnosticSession,
  submitConcerns,
} from '../api/client';
import { nextDiagnosticRoute } from '../lib/diagnosticEntry';

type ConcernItem = { id: string; label: string };
type ConcernGroup = { category_id: string; category_label: string; concerns: ConcernItem[] };
type TimbreOption = {
  id: string;
  label: string;
  description: string;
  genre_display?: string;
};

const FOLLOW_UP_IDS = new Set(['HIGH_NOTE_CANNOT_REACH', 'TIMBRE_DISSATISFIED']);

export default function ConcernIntake() {
  const { sessionId } = useParams();
  const nav = useNavigate();
  const [groups, setGroups] = useState<ConcernGroup[]>([]);
  const [maxConcerns, setMaxConcerns] = useState(3);
  const [followUpOptions, setFollowUpOptions] = useState<Record<string, { id: string; label: string }[]>>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [followUps, setFollowUps] = useState<Record<string, string>>({});
  const [generalMode, setGeneralMode] = useState(false);
  const [openCategory, setOpenCategory] = useState<string | null>('high_note');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sourceAnalysisId, setSourceAnalysisId] = useState<string | null>(null);
  const [plannedHint, setPlannedHint] = useState<string | null>(null);
  const [step, setStep] = useState<'concerns' | 'timbre'>('concerns');
  const [timbreOptions, setTimbreOptions] = useState<TimbreOption[]>([]);
  const [timbreConcernIds, setTimbreConcernIds] = useState<string[]>([]);
  const [timbrePrompt, setTimbrePrompt] = useState('어떤 음색으로 노래하고 싶나요?');
  const [timbreHelper, setTimbreHelper] = useState('가장 원하는 느낌 하나를 골라주세요.');
  const [timbreGoalId, setTimbreGoalId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      if (!sessionId) {
        setLoadError('진단 세션 정보가 없어요. 상세 리포트에서 다시 시작해 주세요.');
        setLoading(false);
        return;
      }
      try {
        const [session, protocol] = await Promise.all([
          getDiagnosticSession(sessionId),
          getDiagnosticProtocol(),
        ]);
        if (cancelled) return;
        if (!session) {
          setLoadError('정밀 진단 세션을 불러오지 못했어요. 잠시 후 다시 시도해주세요.');
          setLoading(false);
          return;
        }
        setSourceAnalysisId(session.source_analysis_id || null);

        if (session.diagnostic_mode) {
          const next = nextDiagnosticRoute(session);
          if (next && !next.endsWith('/concerns')) {
            nav(next, { replace: true });
            return;
          }
        }
        if ((session.status || '').toUpperCase() === 'COMPLETED') {
          nav(`/diagnostic/${sessionId}/report`, { replace: true });
          return;
        }

        const cat = protocol.concern_catalog || {};
        setGroups(cat.groups || []);
        setMaxConcerns(cat.max_concerns || 3);
        setFollowUpOptions(cat.follow_up_options || {});
        const tt = cat.target_timbre || {};
        setTimbreOptions(tt.options || []);
        setTimbreConcernIds(tt.concern_ids || []);
        if (tt.prompt) setTimbrePrompt(tt.prompt);
        if (tt.helper) setTimbreHelper(tt.helper);
        const existing = (session.user_concerns || [])
          .map((c: any) => c?.id)
          .filter(Boolean);
        if (existing.length) {
          setSelected(existing.slice(0, cat.max_concerns || 3));
          setGeneralMode(false);
        } else if (session.diagnostic_mode === 'GENERAL_DISCOVERY') {
          setGeneralMode(true);
        }
        const existingGoal = session.timbre_goal?.id;
        if (existingGoal) setTimbreGoalId(existingGoal);
        setLoading(false);
      } catch {
        if (!cancelled) {
          setLoadError('정밀 진단 정보를 불러오지 못했어요. 잠시 후 다시 시도해주세요.');
          setLoading(false);
        }
      }
    }
    void boot();
    return () => {
      cancelled = true;
    };
  }, [sessionId, nav]);

  function needsTimbreGoal(ids: string[]) {
    const listed = new Set(timbreConcernIds);
    if (ids.some((id) => listed.has(id))) return true;
    return groups.some(
      (g) => g.category_id === 'timbre' && ids.some((id) => g.concerns.some((c) => c.id === id)),
    );
  }

  function toggle(id: string) {
    setGeneralMode(false);
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= maxConcerns) return prev;
      return [...prev, id];
    });
  }

  function chooseGeneral() {
    setGeneralMode(true);
    setSelected([]);
    setFollowUps({});
    setTimbreGoalId(null);
    setStep('concerns');
  }

  async function submit(timbreGoal?: { id: string } | null) {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      const mode = generalMode ? 'GENERAL_DISCOVERY' : 'CONCERN_FOCUSED';
      const payload = generalMode
        ? []
        : selected.map((id, i) => ({
            id,
            source: 'USER_REPORTED',
            priority: i + 1,
            ...(followUps[id] ? { follow_up: followUps[id] } : {}),
          }));
      const session = await submitConcerns(sessionId, payload, mode, timbreGoal || null);
      const n = session?.planned_task_count ?? (session?.selected_tasks || []).length;
      if (typeof n === 'number' && n > 0) {
        setPlannedHint(
          generalMode
            ? `전체 발성 특성을 확인하기 위해 짧은 추가 녹음 ${n}개를 진행해요.`
            : `선택한 고민을 확인하기 위해 짧은 추가 녹음 ${n}개를 진행해요.`,
        );
      }
      nav(`/diagnostic/${sessionId}/safety`);
    } catch (e: any) {
      setError(e?.message || '저장에 실패했어요. 여기서 다시 시도할 수 있어요.');
      setBusy(false);
    }
  }

  async function next() {
    if (!sessionId) return;
    if (!generalMode && selected.length === 0) {
      setError('고민을 선택하거나, 「특별한 고민은 없어요」를 골라 주세요.');
      return;
    }
    if (generalMode) {
      await submit(null);
      return;
    }
    if (needsTimbreGoal(selected)) {
      setError(null);
      setStep('timbre');
      return;
    }
    await submit(null);
  }

  async function submitTimbre() {
    if (!timbreGoalId) {
      setError('가장 원하는 느낌을 하나 골라 주세요.');
      return;
    }
    await submit({ id: timbreGoalId });
  }

  if (loading) {
    return (
      <main>
        <p className="page-kicker">정밀 발성 진단</p>
        <p className="muted">고민 체크리스트 준비 중…</p>
        <div className="skeleton" style={{ height: 28, width: '55%' }} />
        <div className="skeleton" style={{ height: 120 }} />
      </main>
    );
  }

  if (loadError) {
    return (
      <main>
        <p className="page-kicker">정밀 발성 진단</p>
        <p className="fail">{loadError}</p>
        {sourceAnalysisId ? (
          <Link className="btn" to={`/result/${sourceAnalysisId}/detail`}>상세 리포트로 돌아가기</Link>
        ) : null}
      </main>
    );
  }

  if (step === 'timbre') {
    return (
      <main data-testid="timbre-goal-step">
        <p className="page-kicker">정밀 발성 진단</p>
        <h1 className="brand" style={{ fontSize: '1.6rem' }}>{timbrePrompt}</h1>
        <p className="lead">{timbreHelper}</p>
        {timbreOptions.map((opt) => {
          const selectedOpt = timbreGoalId === opt.id;
          return (
            <button
              key={opt.id}
              type="button"
              data-testid={`timbre-option-${opt.id}`}
              className="card"
              onClick={() => setTimbreGoalId(opt.id)}
              style={{
                width: '100%',
                textAlign: 'left',
                marginBottom: 10,
                cursor: 'pointer',
                border: selectedOpt ? '2px solid var(--accent, #3182F6)' : undefined,
                background: 'inherit',
                color: 'inherit',
              }}
            >
              <strong style={{ display: 'block', fontSize: '1.05rem' }}>{opt.label}</strong>
              <span className="body-text" style={{ display: 'block', marginTop: 6, lineHeight: 1.45 }}>
                {opt.description}
              </span>
              {opt.genre_display ? (
                <span
                  className="muted"
                  style={{ display: 'block', marginTop: 8, fontSize: '0.82rem', fontStyle: 'italic' }}
                >
                  {opt.genre_display}
                </span>
              ) : null}
            </button>
          );
        })}
        <button
          className="btn"
          disabled={busy || !timbreGoalId}
          onClick={() => void submitTimbre()}
          data-testid="timbre-goal-submit"
        >
          {busy ? '저장 중…' : '계속'}
        </button>
        <button
          type="button"
          className="btn secondary"
          style={{ marginTop: 10 }}
          disabled={busy}
          onClick={() => {
            setStep('concerns');
            setError(null);
          }}
        >
          고민 선택으로 돌아가기
        </button>
        {error && <p className="fail">{error}</p>}
      </main>
    );
  }

  return (
    <main>
      <p className="page-kicker">정밀 발성 진단</p>
      <p className="lead">
        현재 특별히 고민되는 부분이 있나요?
        <br />
        고민이 있으면 {maxConcerns}개까지 선택하고, 없으면 전체 발성 특성을 확인할 수 있어요.
      </p>

      <div
        className="card"
        style={{
          marginBottom: 12,
          border: generalMode ? '2px solid var(--accent, #3182F6)' : undefined,
        }}
      >
        <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer' }}>
          <input type="radio" checked={generalMode} onChange={chooseGeneral} />
          <span>
            <strong>특별히 고민되는 부분은 없어요.</strong>
            <br />
            <span className="muted" style={{ fontSize: '0.9rem' }}>
              제 발성을 더 자세히 알고 싶어요. (전체 발성 특성 정밀 진단)
            </span>
          </span>
        </label>
      </div>

      {groups.map((g) => (
        <div key={g.category_id} className="card" style={{ marginBottom: 10, opacity: generalMode ? 0.55 : 1 }}>
          <button
            type="button"
            className="detail-row"
            style={{ width: '100%', border: 'none', background: 'transparent', padding: 0 }}
            onClick={() => setOpenCategory((c) => (c === g.category_id ? null : g.category_id))}
          >
            <span className="detail-label">{g.category_label}</span>
            <span className="chevron">{openCategory === g.category_id ? '▴' : '›'}</span>
          </button>
          {openCategory === g.category_id && (
            <div style={{ marginTop: 8 }}>
              {g.concerns.map((c) => (
                <label
                  key={c.id}
                  data-testid={`concern-${c.id}`}
                  style={{ display: 'flex', gap: 10, padding: '8px 0', cursor: 'pointer' }}
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(c.id)}
                    disabled={generalMode || (!selected.includes(c.id) && selected.length >= maxConcerns)}
                    onChange={() => toggle(c.id)}
                  />
                  <span>{c.label}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      ))}

      {!generalMode &&
        selected.filter((id) => FOLLOW_UP_IDS.has(id)).map((id) => (
          <div key={id} className="card" style={{ marginTop: 10 }}>
            <p className="offer-summary-title">추가 질문 (선택)</p>
            <p className="muted" style={{ fontSize: '0.9rem' }}>
              {id === 'HIGH_NOTE_CANNOT_REACH'
                ? '고음에서 어떤 느낌이 가장 가까운가요?'
                : '어떤 느낌이 가장 가까운가요?'}
            </p>
            {(followUpOptions[id] || []).map((opt) => (
              <label key={opt.id} style={{ display: 'flex', gap: 10, padding: '6px 0' }}>
                <input
                  type="radio"
                  name={`fu-${id}`}
                  checked={followUps[id] === opt.id}
                  onChange={() => setFollowUps((f) => ({ ...f, [id]: opt.id }))}
                />
                <span>{opt.label}</span>
              </label>
            ))}
          </div>
        ))}

      <details className="profile-missing" style={{ margin: '12px 0' }}>
        <summary className="profile-missing__toggle" style={{ listStyle: 'none' }}>
          고민 선택이 분석에 어떻게 쓰이나요?
        </summary>
        <p className="muted" style={{ fontSize: '0.85rem', margin: '8px 0 0' }}>
          고민은 확인할 방향을 정하는 신호예요. 음향 분석 결과를 바꾸지는 않아요.
        </p>
      </details>
      {plannedHint ? <p className="body-text">{plannedHint}</p> : null}

      <button
        className="btn"
        disabled={busy || (!generalMode && selected.length === 0)}
        onClick={() => void next()}
        data-testid="concern-continue"
      >
        {busy ? '저장 중…' : '계속'}
      </button>
      {error && <p className="fail">{error}</p>}
    </main>
  );
}
