/**
 * Apps in Toss rewarded fullscreen ad for SONG_DETAIL unlock.
 *
 * Official APIs (web-framework 2.10.x docs):
 *   loadFullScreenAd / showFullScreenAd
 * Reward only on: userEarnedReward
 * Never reward on: dismissed | clicked | failedToShow | loaded | impression | show
 *
 * Official test adGroupId (non-production only): ait-ad-test-rewarded-id
 * Production: VITE_TOSS_REWARDED_DETAIL_AD_GROUP_ID (never invent IDs)
 */

export type RewardedAdLoadState =
  | 'idle'
  | 'loading'
  | 'ready'
  | 'showing'
  | 'unavailable'
  | 'error';

export type RewardedShowOutcome =
  | { type: 'rewarded'; unitType?: string; unitAmount?: number }
  | { type: 'dismissed_without_reward' }
  | { type: 'failed' }
  | { type: 'unavailable'; message: string };

/** Official Apps in Toss test rewarded ad group ID (docs). */
export const OFFICIAL_TEST_REWARDED_AD_GROUP_ID = 'ait-ad-test-rewarded-id';

const UNAVAILABLE = '지금은 광고 무료 열람을 사용할 수 없어요.';

function adLog(event: string) {
  try {
    console.info(`[REWARDED_AD] ${event}`);
  } catch {
    /* ignore */
  }
}

/**
 * Production uses env only. Dev/non-prod falls back to official test ID when env empty.
 * Never invent production IDs.
 */
export function rewardedDetailAdGroupId(): string {
  const configured = String(import.meta.env.VITE_TOSS_REWARDED_DETAIL_AD_GROUP_ID || '').trim();
  if (configured) return configured;
  if (!import.meta.env.PROD) return OFFICIAL_TEST_REWARDED_AD_GROUP_ID;
  return '';
}

export function rewardedAdFeatureConfigured(): boolean {
  return !!rewardedDetailAdGroupId();
}

async function loadSdk(): Promise<{
  loadFullScreenAd?: any;
  showFullScreenAd?: any;
} | null> {
  try {
    return await import('@apps-in-toss/web-framework');
  } catch {
    return null;
  }
}

/** Last observed SDK capability, for the on-device offer trace. Booleans only. */
export const rewardedSupportProbe: { load?: boolean; show?: boolean } = {};

export async function isRewardedAdSupported(): Promise<boolean> {
  if (!rewardedAdFeatureConfigured()) {
    adLog('availability configured=false');
    return false;
  }
  const mod = await loadSdk();
  const loadOk = typeof mod?.loadFullScreenAd?.isSupported === 'function'
    ? mod.loadFullScreenAd.isSupported() === true
    : false;
  const showOk = typeof mod?.showFullScreenAd?.isSupported === 'function'
    ? mod.showFullScreenAd.isSupported() === true
    : false;
  rewardedSupportProbe.load = loadOk;
  rewardedSupportProbe.show = showOk;
  adLog(`availability configured=true load_supported=${loadOk} show_supported=${showOk}`);
  return loadOk && showOk;
}

export function preloadRewardedDetailAd(): {
  promise: Promise<boolean>;
  cancel: () => void;
} {
  let cancelled = false;
  let cleanup: (() => void) | undefined;
  const promise = (async () => {
    const adGroupId = rewardedDetailAdGroupId();
    if (!adGroupId) {
      adLog('availability configured=false');
      return false;
    }
    const mod = await loadSdk();
    if (cancelled) return false;
    if (!mod?.loadFullScreenAd || typeof mod.loadFullScreenAd.isSupported !== 'function') {
      adLog('load_error reason=sdk_missing');
      return false;
    }
    if (mod.loadFullScreenAd.isSupported() !== true) {
      adLog('load_error reason=unsupported');
      return false;
    }
    adLog('load_start');
    return await new Promise<boolean>((resolve) => {
      try {
        cleanup = mod.loadFullScreenAd({
          options: { adGroupId },
          onEvent: (event: { type?: string }) => {
            if (event?.type === 'loaded') {
              adLog('loaded');
              resolve(true);
            }
          },
          onError: () => {
            adLog('load_error');
            resolve(false);
          },
        });
      } catch {
        adLog('load_error');
        resolve(false);
      }
    });
  })();
  return {
    promise,
    cancel: () => {
      cancelled = true;
      try {
        cleanup?.();
      } catch {
        /* ignore */
      }
    },
  };
}

/**
 * Show a preloaded (or on-demand) rewarded ad.
 * Resolves rewarded ONLY on userEarnedReward.
 */
export function showRewardedDetailAd(): Promise<RewardedShowOutcome> {
  return (async () => {
    const adGroupId = rewardedDetailAdGroupId();
    if (!adGroupId) {
      return { type: 'unavailable', message: UNAVAILABLE };
    }
    const mod = await loadSdk();
    if (!mod?.showFullScreenAd || typeof mod.showFullScreenAd.isSupported !== 'function') {
      return { type: 'unavailable', message: UNAVAILABLE };
    }
    if (mod.showFullScreenAd.isSupported() !== true) {
      return { type: 'unavailable', message: UNAVAILABLE };
    }

    adLog('show_start');
    return await new Promise<RewardedShowOutcome>((resolve) => {
      let settled = false;
      let earned = false;
      let cleanup: (() => void) | undefined;
      const finish = (outcome: RewardedShowOutcome) => {
        if (settled) return;
        settled = true;
        try {
          cleanup?.();
        } catch {
          /* ignore */
        }
        resolve(outcome);
      };
      try {
        cleanup = mod.showFullScreenAd({
          options: { adGroupId },
          onEvent: (event: { type?: string; data?: { unitType?: string; unitAmount?: number } }) => {
            const type = String(event?.type || '');
            if (type === 'userEarnedReward') {
              earned = true;
              adLog('reward_earned');
              finish({
                type: 'rewarded',
                unitType: event?.data?.unitType,
                unitAmount: event?.data?.unitAmount,
              });
              return;
            }
            if (type === 'dismissed') {
              adLog('dismissed');
              if (!earned) finish({ type: 'dismissed_without_reward' });
              return;
            }
            if (type === 'failedToShow') {
              adLog('show_error');
              finish({ type: 'failed' });
              return;
            }
            // clicked / impression / show / requested → never reward
          },
          onError: () => {
            adLog('show_error');
            finish({ type: 'failed' });
          },
        });
      } catch {
        adLog('show_error');
        finish({ type: 'failed' });
      }
    });
  })();
}
