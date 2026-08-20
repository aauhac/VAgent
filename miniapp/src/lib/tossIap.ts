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
  const login = await ensureTossLogin();
  if (!login.ok) {
    buying = false;
    const message = tossLoginUserMessage(login.stage);
    if (!message) {
      return { ok: false, state: 'CANCELLED' };
    }
    return { ok: false, state: 'FAILED', message };
  }
  const { createIapIntent, grantIapOrder } = await import('../api/client');
  try {
    const IAP = await loadIap();
    if (!IAP?.createOneTimePurchaseOrder) {
      return { ok: false, state: 'FAILED', message: userMessage('IAP_UNAVAILABLE') };
    }
    const intent = await createIapIntent({
      product_id: input.productId,
      analysis_id: input.resourceId,
    });
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
      const cleanup = IAP.createOneTimePurchaseOrder({
        options: {
          sku: intent.sku,
          processProductGrant: async ({ orderId }: { orderId: string }) => {
            try {
              const grant = await grantIapOrder({ intent_id: intent.intent_id, order_id: orderId });
              if (!grant?.granted) return false;
              try {
                if (IAP.completeProductGrant) {
                  await IAP.completeProductGrant({ params: { orderId } });
                }
              } catch {
                /* retry on next entry */
              }
              finish({ ok: true, state: 'GRANTED' });
              return true;
            } catch {
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
            cleanup?.();
          }
        },
        onError: (error: unknown) => {
          if (isCancelError(error)) {
            finish({ ok: false, state: 'CANCELLED', message: userMessage('PAYMENT_CANCELLED') });
            return;
          }
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
