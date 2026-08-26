/**
 * Apps in Toss one-time IAP.
 * processProductGrant returns true only after VAgent backend VERIFIED grant.
 */

import { pauseAllMediaPlayback } from './mediaPlayback';
import { ensureTossLogin, tossLoginUserMessage } from './tossAuth';

export { getIapProductMap, loadIapCatalog } from './iapCatalog';

export type PurchaseState =
  | 'IDLE'
  | 'PREPARING'
  | 'PURCHASING'
  | 'VERIFYING'
  | 'GRANTED'
  | 'CANCELLED'
  | 'FAILED'
  | 'PENDING_RECOVERY';

export type BuyProductInput = {
  productId: string;
  resourceId: string;
};

export type BuyProductResult = {
  ok: boolean;
  state: PurchaseState;
  message?: string;
};

const LAST_INTENT_KEY = 'vagent_last_payment_intent_v1';

/**
 * Stage-only purchase trace. The user-facing copy stays one generic message, but the
 * dev console shows which step actually failed.
 * Never pass tokens, authorization codes, userKeys, anonymous hashes, or order payloads
 * — `stage` and a short error code are the entire allowed vocabulary.
 */
function iapLog(stage: string, code?: string) {
  try {
    const safeCode = code ? String(code).replace(/[^A-Za-z0-9_.:-]/g, '').slice(0, 48) : '';
    console.warn(`[IAP] ${stage}${safeCode ? ` code=${safeCode}` : ''}`);
  } catch {
    /* ignore */
  }
}

function errorCode(error: unknown): string {
  const raw = (error as any)?.code || (error as any)?.error?.code;
  if (raw) return String(raw);
  const status = Number((error as any)?.status);
  return Number.isFinite(status) ? `HTTP_${status}` : 'UNKNOWN';
}

function userMessage(code?: string, fallback?: string): string {
  switch (code) {
    case 'PAYMENT_CANCELLED':
    case 'USER_CANCEL':
      return '결제가 취소됐어요.';
    case 'ALREADY_PURCHASED':
      return '이미 이용할 수 있는 리포트예요.';
    case 'PAYMENT_REFUNDED':
      return '환불된 구매라 현재 이용할 수 없어요.';
    case 'PAYMENT_PENDING':
    case 'NEEDS_MANUAL_RESTORE':
      return '결제 상태를 확인하고 있어요. 다시 앱을 열어도 이어서 확인할 수 있어요.';
    case 'IAP_UNAVAILABLE':
      return '토스 앱에서 결제를 진행할 수 있어요.';
    default:
      return fallback || '결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.';
  }
}

function isCancelError(error: unknown): boolean {
  const text = String((error as any)?.message || (error as any)?.code || error || '').toLowerCase();
  return text.includes('cancel') || text.includes('취소') || text.includes('user_cancel');
}

async function loadIap(): Promise<any | null> {
  try {
    const mod = await import('@apps-in-toss/web-framework');
    return (mod as any).IAP || null;
  } catch {
    return null;
  }
}

/**
 * One purchase attempt at a time, tracked as an object rather than a bare boolean so a
 * late callback from a finished attempt can never disturb the next one.
 */
type PurchaseAttempt = {
  token: number;
  settled: boolean;
  grantStarted: boolean;
  returnedFromPaymentUi: boolean;
  cleanedUp: boolean;
  sku?: string;
};

let activeAttempt: PurchaseAttempt | null = null;
let attemptCounter = 0;

/**
 * Grace before treating "back in the app, still no callback" as worth reconciling.
 *
 * This never decides the outcome by itself — afterwards we ask getPendingOrders(), which
 * is authoritative. Returning to the app is NOT a payment result: the installed SDK
 * (@apps-in-toss/web-framework 2.10.8) declares no visibility or pagehide contract at all,
 * and cleanup() unsubscribes, so finishing on `visible` can drop a real grant.
 */
const RETURN_RECONCILE_GRACE_MS = 1200;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * A recovered order only counts as THIS purchase when the server says it granted the very
 * resource being bought. song_detail is per-analysis on one shared SKU, so a stranded
 * order may legitimately belong to a different analysis — settling that is good, but it is
 * not the purchase the user just made.
 */
function recoveredMatches(recovered: any, input: BuyProductInput): boolean {
  if (!recovered?.granted) return false;
  if (String(recovered.resource_id || '') !== input.resourceId) return false;
  // Same analysis can hold song_detail and diagnostic; a recovered upgrade is not the
  // detail purchase the user just made.
  return String(recovered.product_id || '') === input.productId;
}

export async function buyProduct(input: BuyProductInput): Promise<BuyProductResult> {
  if (activeAttempt && !activeAttempt.settled) {
    return { ok: false, state: 'FAILED', message: '결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.' };
  }
  attemptCounter += 1;
  const attempt: PurchaseAttempt = {
    token: attemptCounter,
    settled: false,
    grantStarted: false,
    returnedFromPaymentUi: false,
    cleanedUp: false,
  };
  activeAttempt = attempt;
  // Everything below is inside the finally that releases the attempt — including login,
  // which used to sit outside it and could strand the lock on a throw.
  try {
    pauseAllMediaPlayback();
    iapLog('login_start');
    const login = await ensureTossLogin();
    if (!login.ok) {
      iapLog('login_failed', login.stage);
      const message = tossLoginUserMessage(login.stage);
      if (!message) {
        return { ok: false, state: 'CANCELLED' };
      }
      return { ok: false, state: 'FAILED', message };
    }
    iapLog('login_ok');
    const { createIapIntent, grantIapOrder, recoverIapOrder } = await import('../api/client');
    const IAP = await loadIap();
    if (!IAP?.createOneTimePurchaseOrder) {
      iapLog('sdk_unavailable', 'IAP_UNAVAILABLE');
      return { ok: false, state: 'FAILED', message: userMessage('IAP_UNAVAILABLE') };
    }
    iapLog('intent_start');
    const intent = await createIapIntent({
      product_id: input.productId,
      analysis_id: input.resourceId,
    });
    iapLog('intent_ok');
    attempt.sku = intent.sku;

    // A previous attempt may have ended unresolved after a payment that was never
    // granted. Settle that first so the user is not charged a second time for it.
    try {
      const carried = await IAP.getPendingOrders?.();
      const stale = (carried?.orders || []).find(
        (o: { sku?: string }) => o?.sku === intent.sku,
      );
      if (stale?.orderId) {
        iapLog('pre_purchase_recover');
        const recovered = await recoverIapOrder({
          order_id: String(stale.orderId),
          sku: stale.sku,
        });
        if (recovered?.granted) {
          try {
            if (IAP.completeProductGrant) {
              await IAP.completeProductGrant({ params: { orderId: stale.orderId } });
            }
          } catch {
            /* recoverPendingPurchases retries on next entry */
          }
          if (recoveredMatches(recovered, input)) {
            iapLog('pre_purchase_recovered');
            return { ok: true, state: 'GRANTED' };
          }
          // Someone else's analysis was settled. Good, but this purchase still has to run.
          iapLog('pre_purchase_recovered_other_resource');
        }
      }
    } catch (error: unknown) {
      iapLog('pre_purchase_recover_failed', errorCode(error));
    }

    try {
      sessionStorage.setItem(LAST_INTENT_KEY, JSON.stringify({ intent_id: intent.intent_id, sku: intent.sku }));
    } catch {
      /* hint only */
    }

    const granted = await new Promise<BuyProductResult>((resolve) => {
      // The SDK may invoke onEvent/onError synchronously, before createOneTimePurchaseOrder
      // has even returned its cleanup function. Declared with `let` up here so a same-tick
      // callback reads `undefined` instead of hitting a const's temporal dead zone, and the
      // request is replayed the moment the function exists.
      let cleanup: (() => void) | undefined;
      let cleanupRequested = false;
      const cleanupOnce = () => {
        if (attempt.cleanedUp) return;
        if (!cleanup) {
          cleanupRequested = true;
          return;
        }
        attempt.cleanedUp = true;
        try {
          cleanup();
        } catch {
          /* ignore */
        }
      };
      const finish = (result: BuyProductResult) => {
        if (attempt.settled) return;
        attempt.settled = true;
        document.removeEventListener('visibilitychange', onVisibility);
        cleanupOnce();
        resolve(result);
      };

      /**
       * Coming back from the payment sheet is a hint, never a verdict.
       *
       * Authoritative order, highest first: processProductGrant → onError → onEvent →
       * pending-order reconciliation. The attempt is abandoned only when none of those
       * produced anything — otherwise a payment completed just as the user returned would
       * be reported as cancelled while the money was taken.
       */
      async function onVisibility() {
        if (document.visibilityState === 'hidden') {
          attempt.returnedFromPaymentUi = true;
          return;
        }
        if (!attempt.returnedFromPaymentUi || attempt.settled || attempt.grantStarted) return;
        // Give the SDK its turn to deliver a queued callback before concluding anything.
        await delay(RETURN_RECONCILE_GRACE_MS);
        if (attempt.settled || attempt.grantStarted) return;

        iapLog('return_reconcile_start');
        try {
          const pending = await IAP.getPendingOrders?.();
          const order = (pending?.orders || []).find(
            (o: { sku?: string }) => !attempt.sku || o?.sku === attempt.sku,
          );
          if (order?.orderId) {
            if (attempt.settled || attempt.grantStarted) return;
            iapLog('return_reconcile_pending');
            const recovered = await recoverIapOrder({
              order_id: String(order.orderId),
              sku: order.sku,
              intent_id: intent.intent_id,
            });
            if (recoveredMatches(recovered, input)) {
              try {
                if (IAP.completeProductGrant) {
                  await IAP.completeProductGrant({ params: { orderId: order.orderId } });
                }
              } catch {
                /* recoverPendingPurchases retries on next entry */
              }
              iapLog('return_reconcile_granted');
              finish({ ok: true, state: 'GRANTED' });
              return;
            }
            iapLog('return_reconcile_unresolved');
            finish({
              ok: false,
              state: 'PENDING_RECOVERY',
              message: userMessage('PAYMENT_PENDING'),
            });
            return;
          }
        } catch (error: unknown) {
          iapLog('return_reconcile_failed', errorCode(error));
        }
        if (attempt.settled || attempt.grantStarted) return;
        /**
         * Returned with no callback and nothing pending. This is NOT a cancel.
         *
         * getPendingOrders is documented as "결제는 됐지만 지급이 완료되지 않은 주문" and says
         * nothing about cancellation; it also returns undefined on older Toss apps
         * (Android < 5.234.0, iOS < 5.231.0). An empty list therefore cannot distinguish
         * "user backed out" from "payment not reflected yet". The only authoritative
         * cancel is onError USER_CANCELED. So the attempt ends unresolved: the lock is
         * released so the user can act, and the next purchase reconciles before charging.
         */
        iapLog('return_unresolved');
        finish({
          ok: false,
          state: 'PENDING_RECOVERY',
          message: userMessage('PAYMENT_PENDING'),
        });
      }
      document.addEventListener('visibilitychange', onVisibility);

      iapLog('order_start');
      cleanup = IAP.createOneTimePurchaseOrder({
        options: {
          sku: intent.sku,
          processProductGrant: async ({ orderId }: { orderId: string }) => {
            attempt.grantStarted = true;
            iapLog('grant_start');
            try {
              const grant = await grantIapOrder({ intent_id: intent.intent_id, order_id: orderId });
              if (!grant?.granted) {
                iapLog('grant_denied');
                return false;
              }
              // Returning true IS the completion signal for this callback — the SDK
              // finishes the grant itself. Calling IAP.completeProductGrant here would
              // duplicate it. That call belongs only to recoverPendingPurchases(),
              // where no processProductGrant callback exists.
              iapLog('grant_ok');
              finish({ ok: true, state: 'GRANTED' });
              return true;
            } catch (error: unknown) {
              iapLog('grant_failed', errorCode(error));
              finish({
                ok: false,
                state: 'PENDING_RECOVERY',
                message: userMessage('PAYMENT_PENDING'),
              });
              return false;
            }
          },
        },
        onEvent: (event: { type?: string }) => {
          if (event?.type === 'success') {
            iapLog('order_ok');
            cleanupOnce();
          }
        },
        onError: (error: unknown) => {
          if (isCancelError(error)) {
            iapLog('order_cancelled');
            finish({ ok: false, state: 'CANCELLED', message: userMessage('PAYMENT_CANCELLED') });
            return;
          }
          iapLog('order_failed', errorCode(error));
          finish({
            ok: false,
            state: 'FAILED',
            message: userMessage(),
          });
        },
      });
      if (cleanupRequested) cleanupOnce();
    });
    return granted;
  } catch (error: any) {
    const code = error?.code || error?.error?.code;
    // Reached when the intent call itself throws — the stage that was silently failing.
    iapLog('intent_failed', errorCode(error));
    return { ok: false, state: 'FAILED', message: userMessage(code) };
  } finally {
    attempt.settled = true;
    if (activeAttempt?.token === attempt.token) {
      activeAttempt = null;
    }
  }
}

export async function recoverPendingPurchases(): Promise<void> {
  const { getVagentSessionToken } = await import('./tossAuth');
  if (!getVagentSessionToken()) return;
  const IAP = await loadIap();
  if (!IAP?.getPendingOrders) return;
  let pending: { orders?: Array<{ orderId?: string; sku?: string }> } | undefined;
  try {
    pending = await IAP.getPendingOrders();
  } catch {
    return;
  }
  if (pending == null) return;
  const orders = pending.orders || [];
  const { recoverIapOrder } = await import('../api/client');
  for (const order of orders) {
    const orderId = order?.orderId;
    if (!orderId) continue;
    try {
      const result = await recoverIapOrder({ order_id: String(orderId), sku: order.sku });
      if (result?.granted && IAP.completeProductGrant) {
        try {
          await IAP.completeProductGrant({ params: { orderId } });
        } catch {
          /* retry later */
        }
      }
    } catch {
      /* ignore-safe / ambiguous */
    }
  }
}
