import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useNavigationType } from 'react-router-dom';
import { getVocalProgressInsight } from '../api/client';
import ProgressInsightSheet from '../components/progress/ProgressInsightSheet';
import SubPageHeader from '../components/ui/SubPageHeader';
import { getLocalActiveGoal } from '../lib/localGoalStore';
import { listLocalVocalSnapshots } from '../lib/localVocalHistory';
import { resolveProgressBackTarget } from '../lib/progressNavigation';
import {
  buildLocalProgressInsight,
  type ProgressCard,
  type ProgressInsightPayload,
} from '../lib/progressPresentation';

/**
 * Personal change page — no goal management UI.
 * Active goal (if any) only influences improved/changed classification internally.
 */
export default function ProgressInsightPage() {
  const nav = useNavigate();
  const location = useLocation();
  const navigationType = useNavigationType();
  const [insight, setInsight] = useState<ProgressInsightPayload | null>(null);
  const [sheetCard, setSheetCard] = useState<ProgressCard | null>(null);
  const localCount = useMemo(() => listLocalVocalSnapshots().length, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const activeFocus = getLocalActiveGoal()?.goal_focus || null;
      let serverInsight: ProgressInsightPayload | null = null;
      try {
        const server = await getVocalProgressInsight({ recent_n: 10 });
        if (cancelled) return;
        if (server?.insight_available) {
          serverInsight = { ...server, source: 'server' };
          setInsight(serverInsight);
        }
      } catch {
        /* local */
      }
      if (cancelled) return;

      if (!serverInsight) {
        const snaps = listLocalVocalSnapshots();
        const current = snaps.length ? snaps[snaps.length - 1].canonical : {};
        const hist = snaps.slice(0, -1).map((s) => ({ canonical: s.canonical }));
        setInsight(
          buildLocalProgressInsight(current, hist, {
            goal: activeFocus,
            recentN: 10,
          }),
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function onBack() {
    const resolved = resolveProgressBackTarget(location.state, {
      navigationType,
    });
    if (resolved.mode === 'path') {
      nav(resolved.path);
      return;
    }
    if (resolved.mode === 'history') {
      nav(-1);
      return;
    }
    nav('/');
  }

  const improved = insight?.improved || [];
  const changed = insight?.changed || [];
  const maintained = insight?.maintained || [];
  const hasGenericHistory = !!(insight?.insight_available && (insight.history_count || 0) > 0);
  const noHistoryAtAll = localCount <= 0 && !hasGenericHistory;

  function renderGroup(title: string, cards: ProgressCard[], className: string) {
    if (!cards.length) return null;
    return (
      <div className="progress-group" style={{ marginTop: 18 }} data-testid={`progress-group-${className}`}>
        <h3 className="section-title">{title}</h3>
        {cards.map((c) => (
          <button
            key={`${c.kind}-${c.axis}`}
            type="button"
            className={
              c.kind === 'IMPROVED'
                ? 'progress-card progress-card--improved'
                : c.kind === 'MAINTAINED'
                  ? 'progress-card progress-card--maintained'
                  : 'progress-card'
            }
            onClick={() => setSheetCard(c)}
          >
            <span className="progress-card-main">
              <span className="progress-card-title">{c.title}</span>
              <span className="progress-card-detail">{c.detail}</span>
            </span>
            <span className="progress-card-chevron" aria-hidden>›</span>
          </button>
        ))}
      </div>
    );
  }

  return (
    <main>
      <SubPageHeader title="내 변화" onBack={onBack} />

      <p className="lead" style={{ marginTop: 16, marginBottom: 8 }}>
        이전보다 뭐가 달라졌을까요
      </p>
      <p className="muted" style={{ marginTop: 0, marginBottom: 16, fontSize: '0.88rem' }}>
        최근 기록에서 나타난 변화를 이전 결과와 비교해 보여드려요.
      </p>

      <section className="section" style={{ borderBottom: 0 }} data-testid="progress-generic-changes">
        {!insight ? (
          <p className="muted">불러오는 중…</p>
        ) : noHistoryAtAll ? (
          <div className="card" data-testid="progress-no-history">
            <p className="body-text" style={{ margin: 0 }}>
              아직 비교할 기록이 없어요. 노래를 몇 번 더 분석하면 이전 기록과 달라진 점을 확인할 수 있어요.
            </p>
            <Link className="btn" style={{ width: '100%', marginTop: 14 }} to="/record">
              노래 분석하기
            </Link>
          </div>
        ) : !insight.insight_available ? (
          <>
            <p className="muted" style={{ fontSize: '0.88rem' }}>
              {insight.note || '기록이 조금 더 쌓이면 변화 흐름을 더 자세히 비교할 수 있어요.'}
            </p>
            <Link className="btn secondary" style={{ width: '100%', marginTop: 12 }} to="/record">
              노래 분석하기
            </Link>
          </>
        ) : (
          <>
            {renderGroup('좋아진 부분', improved, 'improved')}
            {renderGroup('달라진 부분', changed, 'changed')}
            {renderGroup('유지하고 있는 부분', maintained, 'maintained')}
            {improved.length + changed.length + maintained.length === 0 ? (
              <div className="card">
                <p className="body-text" style={{ margin: 0 }}>
                  최근 기록과 비슷한 상태예요.
                </p>
              </div>
            ) : null}
          </>
        )}
      </section>

      <ProgressInsightSheet
        open={!!sheetCard}
        card={sheetCard}
        onClose={() => setSheetCard(null)}
      />
    </main>
  );
}
