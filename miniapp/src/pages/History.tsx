import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { deleteAnalysis, getServerHistory, removeHistory } from '../api/client';
import { ensureTossLogin, tossLoginUserMessage } from '../lib/tossAuth';
import { SESSION_CLEARED_EVENT } from '../lib/clientSession';
import { vocalTypeUnresolvedCopy } from '../lib/reportPresentation';

type DiagnosticBrief = {
  session_id: string;
  status?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
};

type Row = {
  id: string;
  at: string;
  filename?: string;
  vocalType?: string;
  songDetailUnlocked?: boolean;
  diagnosticUnlocked?: boolean;
  sessions: DiagnosticBrief[];
  missing?: boolean;
  interrupted?: boolean;
  status?: string;
};

const PAGE_SIZE = 20;

function formatDate(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${mm}.${dd}`;
}

function isCompleted(session: DiagnosticBrief) {
  return String(session.status || '').toUpperCase() === 'COMPLETED';
}

function pickPrimary(sessions: DiagnosticBrief[]) {
  const completed = sessions.filter(isCompleted);
  const pool = (completed.length ? completed : sessions).slice();
  pool.sort((a, b) =>
    String(b.completed_at || b.created_at || '').localeCompare(String(a.completed_at || a.created_at || '')),
  );
  return pool[0];
}

/** Defensive UI boundary — never show internal unresolved engine label. */
function presentHistoryVocalType(raw?: string | null): string | undefined {
  const name = String(raw || '').trim();
  if (!name) return undefined;
  if (name.includes('판단 보류')) {
    return vocalTypeUnresolvedCopy('INSUFFICIENT_EVIDENCE').title;
  }
  return name;
}

function mapItems(serverItems: Array<Record<string, unknown>>): Row[] {
  return (serverItems || []).map((it) => ({
    id: String(it.analysis_id || ''),
    at: String(it.created_at || ''),
    filename: (it.filename as string) || undefined,
    vocalType: presentHistoryVocalType((it.vocal_type as string) || undefined),
    songDetailUnlocked: !!it.song_detail_unlocked,
    diagnosticUnlocked: !!it.diagnostic_unlocked,
    sessions: Array.isArray(it.diagnostic_sessions)
      ? (it.diagnostic_sessions as DiagnosticBrief[])
      : it.diagnostic_session_id
        ? [{ session_id: String(it.diagnostic_session_id), status: 'COMPLETED' }]
        : [],
    status: it.status as string | undefined,
    missing: it.status === 'missing' || !!it.artifact_missing,
    interrupted:
      it.error_code === 'INTERRUPTED_RESTART' ||
      (it.status === 'failed' && it.error_code === 'INTERRUPTED_RESTART'),
  }));
}

export default function History() {
  const [items, setItems] = useState<Row[]>([]);
  const [unlinked, setUnlinked] = useState<DiagnosticBrief[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [legacyOpen, setLegacyOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Row | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  async function loadPage(nextOffset: number, append: boolean) {
    const server = await getServerHistory(PAGE_SIZE, nextOffset);
    const rows = mapItems(server.items || []);
    setItems((prev) => (append ? [...prev, ...rows] : rows));
    setUnlinked(server.unlinked_diagnostics || []);
    setHasMore(!!server.has_more);
    setOffset(nextOffset + rows.length);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const server = await getServerHistory(PAGE_SIZE, 0);
        if (cancelled) return;
        setItems(mapItems(server.items || []));
        setUnlinked(server.unlinked_diagnostics || []);
        setHasMore(!!server.has_more);
        setOffset((server.items || []).length);
      } catch {
        if (cancelled) return;
        setItems([]);
        setUnlinked([]);
        setHasMore(false);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onCleared = () => {
      setItems([]);
      setUnlinked([]);
      setHasMore(false);
      setPendingDelete(null);
    };
    window.addEventListener(SESSION_CLEARED_EVENT, onCleared);
    return () => window.removeEventListener(SESSION_CLEARED_EVENT, onCleared);
  }, []);

  const groups = useMemo(() => {
    const out: Array<{ date: string; rows: Row[] }> = [];
    for (const row of items) {
      const date = row.at ? formatDate(row.at) : '이전';
      const last = out[out.length - 1];
      if (last && last.date === date) {
        last.rows.push(row);
      } else {
        out.push({ date, rows: [row] });
      }
    }
    return out;
  }, [items]);

  async function confirmDelete() {
    if (!pendingDelete || deleting) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await deleteAnalysis(pendingDelete.id);
      removeHistory(pendingDelete.id);
      setItems((prev) => prev.filter((row) => row.id !== pendingDelete.id));
      setPendingDelete(null);
    } catch (e: any) {
      if (e?.name === 'LOGIN_REQUIRED') {
        const login = await ensureTossLogin();
        if (login.ok) {
          setDeleteError('로그인 후 다시 삭제를 눌러주세요.');
        } else {
          setDeleteError(tossLoginUserMessage(login.stage) || '');
        }
      } else {
        setDeleteError('삭제하지 못했어요. 잠시 후 다시 시도해주세요.');
      }
    } finally {
      setDeleting(false);
    }
  }

  return (
    <main>
      <h1 className="brand page-screen-title">분석 기록</h1>

      <section className="section history-feed" style={{ borderBottom: 0, marginTop: 8 }}>
        {loading && <p className="muted">불러오는 중…</p>}
        {!loading && items.length === 0 && (
          <div className="history-empty" data-testid="history-empty">
            <p className="history-empty-title">아직 분석 기록이 없어요</p>
            <p className="muted">
              노래를 분석하면
              <br />
              결과를 여기에서 다시 볼 수 있어요.
            </p>
            <Link className="btn" to="/record" style={{ width: '100%', marginTop: 8 }}>
              노래 분석하기
            </Link>
          </div>
        )}
        {groups.map((group) => (
          <div key={group.date} className="history-day" data-testid="history-day-group">
            <p className="history-day-label">{group.date}</p>
            {group.rows.map((h) => {
              if (h.interrupted) {
                return (
                  <article key={h.id} className="history-card" data-testid="history-analysis-card">
                    <p className="history-title">분석이 중단됐어요</p>
                    <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
                      다시 분석해주세요.
                    </p>
                    <div className="history-actions">
                      <Link className="btn chip secondary" to="/record">다시 분석하기</Link>
                      <button
                        type="button"
                        className="history-delete"
                        data-testid="history-delete"
                        onClick={() => { setPendingDelete(h); setDeleteError(''); }}
                      >
                        삭제
                      </button>
                    </div>
                  </article>
                );
              }
              if (h.missing) {
                return (
                  <article key={h.id} className="history-card" data-testid="history-analysis-card">
                    <p className="history-title">결과를 찾을 수 없어요</p>
                    <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
                      다시 분석해주세요.
                    </p>
                    <div className="history-actions">
                      <Link className="btn chip secondary" to="/record">다시 분석하기</Link>
                      <button
                        type="button"
                        className="history-delete"
                        data-testid="history-delete"
                        onClick={() => { setPendingDelete(h); setDeleteError(''); }}
                      >
                        삭제
                      </button>
                    </div>
                  </article>
                );
              }
              const title = h.filename || '이전 분석';
              const primary = pickPrimary(h.sessions);
              const previous = h.sessions.filter((s) => s.session_id !== primary?.session_id);
              return (
                <article key={h.id} className="history-card" data-testid="history-analysis-card">
                  <p className="history-title">{title}</p>
                  {h.vocalType ? (
                    <p className="history-subtitle">{h.vocalType}</p>
                  ) : null}
                  <p className="history-status">
                    {h.songDetailUnlocked ? '상세 리포트 이용 가능' : '무료 분석 완료'}
                  </p>
                  <div className="history-actions">
                    {h.songDetailUnlocked ? (
                      <>
                        <Link className="btn chip" to={`/result/${h.id}/detail`}>상세 리포트</Link>
                        <Link className="btn chip secondary" to={`/result/${h.id}`}>무료 결과</Link>
                      </>
                    ) : (
                      <Link className="btn chip" to={`/result/${h.id}`}>무료 결과</Link>
                    )}
                    <button
                      type="button"
                      className="history-delete"
                      data-testid="history-delete"
                      onClick={() => { setPendingDelete(h); setDeleteError(''); }}
                    >
                      삭제
                    </button>
                  </div>
                  {primary ? (
                    <div className="history-precision" data-testid="history-linked-precision">
                      <span>
                        정밀 발성 진단 · {isCompleted(primary) ? '완료' : '진행 중'}
                      </span>
                      <Link to={`/diagnostic/${primary.session_id}/report`}>보기</Link>
                    </div>
                  ) : null}
                  {previous.length > 0 ? (
                    <details className="history-prev-diag">
                      <summary>이전 진단 {previous.length}건</summary>
                      {previous.map((s) => (
                        <div key={s.session_id} className="history-precision">
                          <span>정밀 발성 진단 · {isCompleted(s) ? '완료' : '진행 중'}</span>
                          <Link to={`/diagnostic/${s.session_id}/report`}>보기</Link>
                        </div>
                      ))}
                    </details>
                  ) : null}
                </article>
              );
            })}
          </div>
        ))}
        {hasMore && (
          <button
            type="button"
            className="btn secondary history-more"
            disabled={loadingMore}
            onClick={async () => {
              setLoadingMore(true);
              try {
                await loadPage(offset, true);
              } finally {
                setLoadingMore(false);
              }
            }}
          >
            이전 기록 더 보기
          </button>
        )}
      </section>

      {unlinked.length > 0 && (
        <section className="section history-legacy" style={{ borderBottom: 0 }} data-testid="history-orphan-precision">
          <button
            type="button"
            className="history-legacy-toggle"
            data-testid="history-legacy-toggle"
            onClick={() => setLegacyOpen((open) => !open)}
          >
            이전 정밀 진단 {unlinked.length}건
            <span aria-hidden="true">{legacyOpen ? ' ˄' : ' ›'}</span>
          </button>
          {legacyOpen &&
            unlinked.map((session) => (
              <article key={session.session_id} className="history-card history-legacy-card">
                <p className="history-date">{session.created_at ? formatDate(session.created_at) : ''}</p>
                <p className="history-title">정밀 진단 {isCompleted(session) ? '완료' : '기록'}</p>
                <div className="history-actions">
                  <Link className="btn chip" to={`/diagnostic/${session.session_id}/report`}>
                    보기
                  </Link>
                </div>
              </article>
            ))}
        </section>
      )}
      {pendingDelete ? (
        <div className="confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="history-delete-title" data-testid="history-delete-confirm">
          <div className="confirm-sheet">
            <p id="history-delete-title" className="confirm-title">이 분석을 삭제할까요?</p>
            <p className="confirm-body">
              녹음 파일과 분석 결과, 이 분석에 이어진 정밀 발성 진단이 함께 삭제됩니다.
            </p>
            {pendingDelete.songDetailUnlocked || pendingDelete.diagnosticUnlocked ? (
              <p className="confirm-body">거래 확인에 필요한 결제 기록은 별도로 보관될 수 있습니다.</p>
            ) : null}
            {deleteError ? <p className="fail" style={{ margin: '0 0 12px' }}>{deleteError}</p> : null}
            <div className="confirm-actions">
              <button
                type="button"
                className="btn secondary"
                disabled={deleting}
                onClick={() => { if (!deleting) setPendingDelete(null); }}
              >
                취소
              </button>
              <button
                type="button"
                className="btn ghost"
                data-testid="history-delete-confirm-btn"
                disabled={deleting}
                onClick={() => { void confirmDelete(); }}
              >
                {deleting ? '삭제 중…' : '삭제'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
