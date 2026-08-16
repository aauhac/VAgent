import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { getVocalGoalProgress, getVocalProgressInsight } from '../api/client';
import GoalEvidenceDots from '../components/progress/GoalEvidenceDots';
import GoalProgressCard from '../components/progress/GoalProgressCard';
import ProgressInsightSheet from '../components/progress/ProgressInsightSheet';
import { buildLocalGoalProgress, type GoalProgressPayload } from '../lib/goalProgress';
import { getLocalActiveGoal, listLocalGoalHistory } from '../lib/localGoalStore';
import { listLocalVocalSnapshots } from '../lib/localVocalHistory';
import {
  buildLocalProgressInsight,
  type ProgressCard,
  type ProgressInsightPayload,
} from '../lib/progressPresentation';

/**
 * Full-period progress — current goal evidence vs previous goals (never mixed).
 */
export default function ProgressInsightPage() {
  const [insight, setInsight] = useState<ProgressInsightPayload | null>(null);
  const [goalProgress, setGoalProgress] = useState<GoalProgressPayload | null>(null);
  const [sheetCard, setSheetCard] = useState<ProgressCard | null>(null);
  const [goalSheetOpen, setGoalSheetOpen] = useState(false);
  const historyGoals = useMemo(() => listLocalGoalHistory(), []);
  const localCount = useMemo(() => listLocalVocalSnapshots().length, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const server = await getVocalProgressInsight({ recent_n: 10 });
        if (cancelled) return;
        if (server?.insight_available) {
          setInsight({ ...server, source: 'server' });
          if (server.goal_progress) setGoalProgress(server.goal_progress);
        }
      } catch {
        /* local */
      }
      if (cancelled) return;

      const snaps = listLocalVocalSnapshots();
      const current = snaps.length ? snaps[snaps.length - 1].canonical : {};
      const hist = snaps.slice(0, -1).map((s) => ({
        canonical: s.canonical,
        created_at: s.created_at,
        goal_id: s.goal_id || undefined,
      }));
      if (!insight) {
        setInsight(
          buildLocalProgressInsight(current, hist.map((h) => ({ canonical: h.canonical })), {
            goal: getLocalActiveGoal()?.goal_focus || null,
            recentN: 10,
          }),
        );
      }

      const gpServer = await getVocalGoalProgress({ recent_n: 5 });
      if (cancelled) return;
      if (gpServer && gpServer.status !== 'NO_GOAL') {
        setGoalProgress(gpServer);
      } else {
        const active = getLocalActiveGoal();
        setGoalProgress(
          active
            ? buildLocalGoalProgress(active, hist, { recentN: 5, current })
            : { status: 'NO_GOAL', uses_fake_percent: false },
        );
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const allCards = useMemo(() => {
    if (!insight) return [] as ProgressCard[];
    return [...insight.improved, ...insight.changed, ...insight.maintained];
  }, [insight]);

  return (
    <main>
      <Link className="muted" to="/">‹ 홈</Link>
      <p className="page-kicker" style={{ marginTop: 14 }}>내 변화</p>
      <h1 className="brand" style={{ fontSize: '1.4rem', marginBottom: 4 }}>
        이전보다 뭐가 달라졌을까요
      </h1>
      <p className="lead" style={{ marginBottom: 16 }}>
        가짜 점수(%)가 아니라, 실제로 나타난 기록 변화로 보여드려요.
      </p>

      <section className="section">
        <h3 className="section-title">현재 목표</h3>
        {goalProgress && goalProgress.status !== 'NO_GOAL' && goalProgress.goal ? (
          <GoalProgressCard
            progress={goalProgress}
            onOpenInsight={() => setGoalSheetOpen(true)}
          />
        ) : (
          <div className="card">
            <p className="body-text" style={{ margin: 0 }}>
              아직 목표가 없어요. 결과 화면에서 목표를 정하면 여기에 변화가 쌓여요.
            </p>
          </div>
        )}
      </section>

      {goalProgress?.dots?.length ? (
        <section className="section">
          <h3 className="section-title">최근 goal evidence</h3>
          <GoalEvidenceDots dots={goalProgress.dots} />
          <p className="muted" style={{ marginTop: 10, fontSize: '0.88rem' }}>
            최근 {goalProgress.window?.size}회 중 목표 방향 {goalProgress.window?.goal_aligned_count}회
            {goalProgress.previous_window
              ? ` · 이전 ${goalProgress.previous_window.goal_aligned_count}회`
              : ''}
          </p>
          {goalProgress.summary ? (
            <p className="body-text">{goalProgress.summary}</p>
          ) : null}
        </section>
      ) : null}

      {historyGoals.length > 0 ? (
        <section className="section">
          <h3 className="section-title">이전 목표</h3>
          <ul className="goal-history-list">
            {historyGoals
              .slice()
              .reverse()
              .map((g) => (
                <li key={g.id} className="goal-history-item">
                  <p className="goal-history-label">{g.goal_label}</p>
                  <p className="muted" style={{ margin: 0, fontSize: '0.8rem' }}>
                    {g.started_at?.slice(0, 10) || ''}
                    {(g as any).ended_at ? ` ~ ${String((g as any).ended_at).slice(0, 10)}` : ''}
                    {' · '}
                    {g.status}
                  </p>
                </li>
              ))}
          </ul>
          <p className="muted" style={{ fontSize: '0.82rem' }}>
            이전 목표와 현재 목표의 진행은 섞지 않아요.
          </p>
        </section>
      ) : null}

      {!insight ? (
        <p className="muted">불러오는 중…</p>
      ) : (
        <section className="section" style={{ borderBottom: 0 }}>
          <h3 className="section-title">기타 변화</h3>
          <p className="muted" style={{ fontSize: '0.85rem' }}>
            기록 {insight.history_count ?? localCount}회
            {insight.source === 'local' ? ' · 이 기기' : ''}
          </p>

          {!insight.insight_available ? (
            <>
              <div className="card">
                <p className="body-text" style={{ margin: 0 }}>
                  {insight.note || '녹음이 조금 더 쌓이면 변화를 보여드릴 수 있어요.'}
                </p>
              </div>
              <Link className="btn" style={{ marginTop: 16, width: '100%' }} to="/record">
                녹음하러 가기
              </Link>
            </>
          ) : (
            <>
              {insight.improved.map((c) => (
                <button
                  key={c.axis}
                  type="button"
                  className="progress-card progress-card--improved"
                  onClick={() => setSheetCard(c)}
                >
                  <span className="progress-card-main">
                    <span className="progress-card-title">{c.title}</span>
                    <span className="progress-card-detail">{c.detail}</span>
                  </span>
                  <span className="progress-card-chevron" aria-hidden>›</span>
                </button>
              ))}
              {insight.changed.map((c) => (
                <button
                  key={c.axis}
                  type="button"
                  className="progress-card"
                  onClick={() => setSheetCard(c)}
                >
                  <span className="progress-card-main">
                    <span className="progress-card-title">{c.title}</span>
                    <span className="progress-card-detail">{c.detail}</span>
                  </span>
                  <span className="progress-card-chevron" aria-hidden>›</span>
                </button>
              ))}
              {insight.maintained.map((c) => (
                <button
                  key={c.axis}
                  type="button"
                  className="progress-card progress-card--maintained"
                  onClick={() => setSheetCard(c)}
                >
                  <span className="progress-card-main">
                    <span className="progress-card-title">{c.title}</span>
                    <span className="progress-card-detail">{c.detail}</span>
                  </span>
                  <span className="progress-card-chevron" aria-hidden>›</span>
                </button>
              ))}
              {allCards.length === 0 ? (
                <div className="card">
                  <p className="body-text" style={{ margin: 0 }}>
                    최근 기록과 비슷한 상태예요.
                  </p>
                </div>
              ) : null}
            </>
          )}
        </section>
      )}

      <ProgressInsightSheet
        open={!!sheetCard}
        card={sheetCard}
        mode="card"
        onClose={() => setSheetCard(null)}
      />
      <ProgressInsightSheet
        open={goalSheetOpen}
        goalProgress={goalProgress}
        mode="goal"
        onClose={() => setGoalSheetOpen(false)}
      />
    </main>
  );
}
