import { useCallback, useEffect, useRef, useState } from 'react';
import {
  claimRewardedSongDetail,
  createRewardedAdSession,
  getRewardedAdStatus,
  type RewardedAdStatus,
} from '../api/client';
import {
  isRewardedAdSupported,
  preloadRewardedDetailAd,
  rewardedAdFeatureConfigured,
  showRewardedDetailAd,
  type RewardedAdLoadState,
} from './tossRewardedAd';

const MSG_UNAVAILABLE = '지금은 광고 무료 열람을 사용할 수 없어요.';
const MSG_LOAD_FAIL = '광고를 불러오지 못했어요.';
const MSG_CLAIM_FAIL = '무료 열람을 완료하지 못했어요. 다시 시도해 주세요.';
const MSG_LIMIT = '오늘 무료 열람 기회를 모두 사용했어요. 내일 다시 이용할 수 있어요.';

export function useRewardedDetailUnlock(analysisId: string | undefined, alreadyUnlocked: boolean) {
  const [status, setStatus] = useState<RewardedAdStatus | null>(null);
  const [loadState, setLoadState] = useState<RewardedAdLoadState>('idle');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const preloadRef = useRef<ReturnType<typeof preloadRewardedDetailAd> | null>(null);

  const refreshStatus = useCallback(async () => {
    if (!analysisId || alreadyUnlocked) {
      setStatus(null);
      return;
    }
    try {
      const next = await getRewardedAdStatus(analysisId);
      setStatus(next);
    } catch {
      setStatus(null);
    }
  }, [analysisId, alreadyUnlocked]);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  useEffect(() => {
    if (!analysisId || alreadyUnlocked) return;
    if (!rewardedAdFeatureConfigured()) {
      setLoadState('unavailable');
      return;
    }
    let alive = true;
    (async () => {
      const supported = await isRewardedAdSupported();
      if (!alive) return;
      if (!supported) {
        setLoadState('unavailable');
        return;
      }
      setLoadState('loading');
      const job = preloadRewardedDetailAd();
      preloadRef.current = job;
      const ok = await job.promise;
      if (!alive) return;
      setLoadState(ok ? 'ready' : 'error');
    })();
    return () => {
      alive = false;
      preloadRef.current?.cancel();
      preloadRef.current = null;
    };
  }, [analysisId, alreadyUnlocked]);

  const retryLoad = useCallback(async () => {
    setError(null);
    if (!rewardedAdFeatureConfigured()) {
      setLoadState('unavailable');
      return;
    }
    setLoadState('loading');
    preloadRef.current?.cancel();
    const job = preloadRewardedDetailAd();
    preloadRef.current = job;
    const ok = await job.promise;
    setLoadState(ok ? 'ready' : 'error');
  }, []);

  const watchAndUnlock = useCallback(async (): Promise<'unlocked' | 'cancelled' | 'failed'> => {
    if (!analysisId || alreadyUnlocked || busy) return 'failed';
    setBusy(true);
    setError(null);
    try {
      if (!rewardedAdFeatureConfigured()) {
        setError(MSG_UNAVAILABLE);
        setLoadState('unavailable');
        return 'failed';
      }
      const server = await createRewardedAdSession(analysisId);
      setStatus({
        daily_limit: server.daily_limit,
        used_today: server.used_today,
        remaining_today: server.remaining_today,
        already_unlocked: server.already_unlocked,
        can_use_rewarded_ad: server.can_use_rewarded_ad,
        reward_type: server.reward_type,
      });
      if (!server.can_use_rewarded_ad || server.remaining_today <= 0) {
        setError(MSG_LIMIT);
        return 'failed';
      }
      const sessionToken = server.session_token;
      if (!sessionToken) {
        setError(MSG_UNAVAILABLE);
        return 'failed';
      }

      if (loadState !== 'ready') {
        setLoadState('loading');
        const job = preloadRewardedDetailAd();
        preloadRef.current = job;
        const ok = await job.promise;
        setLoadState(ok ? 'ready' : 'error');
        if (!ok) {
          setError(MSG_LOAD_FAIL);
          return 'failed';
        }
      }

      setLoadState('showing');
      const outcome = await showRewardedDetailAd();
      if (outcome.type !== 'rewarded') {
        setLoadState('idle');
        // Preload next ad after dismiss/fail
        void retryLoad();
        if (outcome.type === 'unavailable') {
          setError(outcome.message || MSG_UNAVAILABLE);
          return 'failed';
        }
        if (outcome.type === 'failed') {
          setError(MSG_LOAD_FAIL);
          return 'failed';
        }
        return 'cancelled';
      }

      const claimed = await claimRewardedSongDetail(analysisId, sessionToken);
      setStatus({
        daily_limit: claimed.daily_limit,
        used_today: claimed.used_today,
        remaining_today: claimed.remaining_today,
        already_unlocked: true,
        can_use_rewarded_ad: false,
        reward_type: claimed.reward_type || 'SONG_DETAIL',
      });
      try {
        console.info('[REWARDED_AD] claim_success');
      } catch {
        /* ignore */
      }
      return 'unlocked';
    } catch (err: any) {
      const detail = String(err?.message || '');
      if (detail.includes('DAILY_LIMIT_REACHED')) {
        setError(MSG_LIMIT);
        await refreshStatus();
      } else if (detail.includes('ALREADY_UNLOCKED')) {
        return 'unlocked';
      } else {
        setError(MSG_CLAIM_FAIL);
      }
      setLoadState('error');
      void retryLoad();
      return 'failed';
    } finally {
      setBusy(false);
    }
  }, [analysisId, alreadyUnlocked, busy, loadState, refreshStatus, retryLoad]);

  const configured = rewardedAdFeatureConfigured();
  const remaining = status?.remaining_today;
  const canOffer =
    !alreadyUnlocked &&
    configured &&
    loadState !== 'unavailable' &&
    (status == null || status.can_use_rewarded_ad);

  return {
    status,
    loadState,
    busy,
    error,
    configured,
    canOffer,
    remainingToday: typeof remaining === 'number' ? remaining : null,
    dailyLimit: status?.daily_limit ?? 3,
    refreshStatus,
    retryLoad,
    watchAndUnlock,
  };
}
