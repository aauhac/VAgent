import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getLatestNotificationResult } from '../api/client';
import { getUserIdentity } from '../lib/userIdentity';

/**
 * Landing for `intoss://vocalfb/notification-result`.
 *
 * The Smart Message campaign has one fixed 이동 URL, so the click cannot carry an analysis
 * id. This page restores the device identity, asks the server which delivered alert it
 * most recently has, and forwards to that result.
 *
 * Limitation: tapping a very old notification after newer ones were sent opens the newest
 * usable analysis. Tapping a freshly received alert — the normal case — is always exact.
 * No per-send URL parameter is invented for this; no official contract for one is known.
 *
 * Never falls back to Home: an unresolved alert lands on /history, where the user can pick
 * the analysis themselves.
 */
export const NOTIFICATION_RESULT_PATH = '/notification-result';

const FALLBACK = '/history';

export default function NotificationResultRedirect() {
  const nav = useNavigate();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let target = FALLBACK;
      try {
        await getUserIdentity();
        const latest = await getLatestNotificationResult();
        if (latest.found && latest.analysis_id) {
          target = `/result/${latest.analysis_id}`;
        }
      } catch {
        /* identity or network unavailable — /history, never Home */
      }
      if (!cancelled) nav(target, { replace: true });
    })();
    return () => {
      cancelled = true;
    };
  }, [nav]);

  return (
    <main>
      <p className="muted">분석 결과를 불러오고 있어요.</p>
    </main>
  );
}
