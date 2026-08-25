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

let buying = false;

export async function buyProduct(input: BuyProductInput): Promise<BuyProductResult> {
  if (buying) {
    return { ok: false, state: 'FAILED', message: '결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.' };
  }
  buying = true;
  pauseAllMediaPlayback();
  iapLog('login_start');
  const login = await ensureTossLogin();
  if (!login.ok) {
    buying = false;
    iapLog('login_failed', login.stage);
    const message = tossLoginUserMessage(login.stage);
    if (!message) {
      return { ok: false, state: 'CANCELLED' };
    }
    return { ok: false, state: 'FAILED', message };
  }
  iapLog('login_ok');
  const { createIapIntent, grantIapOrder } = await import('../api/client');
  try {
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
    try {
      sessionStorage.setItem(LAST_INTENT_KEY, JSON.stringify({ intent_id: intent.intent_id, sku: intent.sku }));
    } catch {
      /* hint only */
    }

    const granted = await new Promise<BuyProductResult>((resolve) => {
      let settled = false;
      const finish = (result: BuyProductResult) => {
        if (settled) return;
        settled = true;
        try {
          cleanup?.();
        } catch {
          /* ignore */
        }
        resolve(result);
      };
      iapLog('order_start');
      const cleanup = IAP.createOneTimePurchaseOrder({
        options: {
          sku: intent.sku,
          processProductGrant: async ({ orderId }: { orderId: string }) => {
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
            cleanup?.();
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
    });
    return granted;
  } catch (error: any) {
    const code = error?.code || error?.error?.code;
    // Reached when the intent call itself throws — the stage that was silently failing.
    iapLog('intent_failed', errorCode(error));
    return { ok: false, state: 'FAILED', message: userMessage(code) };
  } finally {
    buying = false;
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
