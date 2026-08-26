/**
 * The purchase lock must never strand.
 *
 * Backing out of the Toss payment sheet does not always produce an SDK callback. The
 * promise then never settled, the module-level `buying` flag stayed true, and every later
 * purchase was refused with the generic "결제를 시작하지 못했어요" — which is exactly what
 * the device showed on a second attempt.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const ensureTossLogin = vi.fn();
const createIapIntent = vi.fn();
const grantIapOrder = vi.fn();
const createOneTimePurchaseOrder = vi.fn();
const completeProductGrant = vi.fn(async () => true);
const cleanup = vi.fn();
const getPendingOrders = vi.fn();
const recoverIapOrder = vi.fn();

vi.mock('./mediaPlayback', () => ({ pauseAllMediaPlayback: vi.fn() }));
vi.mock('./tossAuth', () => ({
  ensureTossLogin: (...a: unknown[]) => ensureTossLogin(...a),
  tossLoginUserMessage: () => '로그인을 완료하지 못했어요.',
  getVagentSessionToken: () => 'token',
}));
vi.mock('../api/client', () => ({
  createIapIntent: (...a: unknown[]) => createIapIntent(...a),
  grantIapOrder: (...a: unknown[]) => grantIapOrder(...a),
  recoverIapOrder: (...a: unknown[]) => recoverIapOrder(...a),
}));
vi.mock('@apps-in-toss/web-framework', () => ({
  IAP: {
    createOneTimePurchaseOrder: (...a: unknown[]) => createOneTimePurchaseOrder(...a),
    completeProductGrant: (...a: unknown[]) => completeProductGrant(...a),
    getPendingOrders: (...a: unknown[]) => getPendingOrders(...a),
  },
}));

import { buyProduct } from './tossIap';

const INPUT = { productId: 'song_detail', resourceId: 'b'.repeat(32) };

/** Long enough to clear the return-reconcile grace inside buyProduct. */
const RECONCILE_WAIT = 1500;
const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

function setVisibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true });
  document.dispatchEvent(new Event('visibilitychange'));
}

/** Simulate leaving for the payment sheet and coming back without any SDK callback. */
function leaveAndReturn() {
  setVisibility('hidden');
  setVisibility('visible');
}

beforeEach(() => {
  vi.clearAllMocks();
  setVisibility('visible');
  ensureTossLogin.mockResolvedValue({ ok: true, stage: 'LOGIN_SUCCESS' });
  createIapIntent.mockResolvedValue({ intent_id: 'intent-1', sku: 'sku.song.detail' });
  createOneTimePurchaseOrder.mockReturnValue(cleanup);
  getPendingOrders.mockResolvedValue({ orders: [] });
  recoverIapOrder.mockResolvedValue({ granted: false });
});

describe('buyProduct lock lifecycle', () => {
  it('ends the attempt without claiming a cancel when no callback arrives', async () => {
    // Unresolved, not cancelled — the SDK never said the user cancelled.
    const first = buyProduct(INPUT);
    await vi.waitFor(() => expect(createOneTimePurchaseOrder).toHaveBeenCalled());
    leaveAndReturn();

    const result = await first;
    expect(result.state).toBe('PENDING_RECOVERY');
    expect(cleanup).toHaveBeenCalled();
  });

  it('allows a second purchase immediately after backing out', async () => {
    const first = buyProduct(INPUT);
    await vi.waitFor(() => expect(createOneTimePurchaseOrder).toHaveBeenCalledTimes(1));
    leaveAndReturn();
    await first;

    const second = buyProduct(INPUT);
    await vi.waitFor(() => expect(createOneTimePurchaseOrder).toHaveBeenCalledTimes(2));
    leaveAndReturn();
    const result = await second;

    // The generic refusal is what a stranded lock produced. A real flow was started.
    expect(result.message).not.toBe('결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.');
  });

  it('does not abandon an attempt while a grant is in flight', async () => {
    let release: (v: unknown) => void = () => {};
    grantIapOrder.mockImplementation(
      () => new Promise((resolve) => { release = resolve; }),
    );
    createOneTimePurchaseOrder.mockImplementation((params: any) => {
      void params.options.processProductGrant({ orderId: 'order-1' });
      return cleanup;
    });

    const pending = buyProduct(INPUT);
    await vi.waitFor(() => expect(grantIapOrder).toHaveBeenCalled());
    // Returning to the app mid-grant must not cancel a purchase the server is completing.
    leaveAndReturn();
    release({ granted: true });

    const result = await pending;
    expect(result.ok).toBe(true);
    expect(result.state).toBe('GRANTED');
  });

  it('does NOT cancel a purchase whose grant arrives after the app is visible again', async () => {
    // The SDK contract has no visibility signal at all (v2.10.8 type defs: 0 mentions of
    // visibilitychange/pagehide). Returning to the app is not a payment result, and
    // cleanup() unsubscribes — so cancelling on visible can drop a real grant.
    let sdkParams: any = null;
    createOneTimePurchaseOrder.mockImplementation((params: any) => {
      sdkParams = params;
      return cleanup;
    });
    grantIapOrder.mockResolvedValue({ granted: true });

    const pending = buyProduct(INPUT);
    await vi.waitFor(() => expect(sdkParams).not.toBeNull());

    // User pays in the sheet and comes back BEFORE the SDK delivers the grant.
    leaveAndReturn();
    await Promise.resolve();
    void sdkParams.options.processProductGrant({ orderId: 'order-late' });

    const result = await pending;
    expect(result.state).toBe('GRANTED');
    expect(result.ok).toBe(true);
  });

  it('releases the lock when login throws', async () => {
    ensureTossLogin.mockRejectedValueOnce(new Error('network'));
    const first = await buyProduct(INPUT);
    expect(first.ok).toBe(false);

    ensureTossLogin.mockResolvedValue({ ok: true, stage: 'LOGIN_SUCCESS' });
    const second = buyProduct(INPUT);
    await vi.waitFor(() => expect(createOneTimePurchaseOrder).toHaveBeenCalled());
    leaveAndReturn();
    await second;
  });

  it('releases the lock when the SDK reports a cancel', async () => {
    createOneTimePurchaseOrder.mockImplementation((params: any) => {
      params.onError(new Error('USER_CANCEL'));
      return cleanup;
    });
    const first = await buyProduct(INPUT);
    expect(first.state).toBe('CANCELLED');

    const second = await buyProduct(INPUT);
    expect(second.state).toBe('CANCELLED'); // reached the SDK again, not the lock
    expect(createOneTimePurchaseOrder).toHaveBeenCalledTimes(2);
  });

  it('recovers a real order found only after returning to the app', async () => {
    // Empty at pre-purchase time; the order only shows up once the user has paid.
    getPendingOrders
      .mockResolvedValueOnce({ orders: [] })
      .mockResolvedValue({ orders: [{ orderId: 'order-pending', sku: 'sku.song.detail' }] });
    recoverIapOrder.mockResolvedValue({
      granted: true,
      resource_id: INPUT.resourceId,
      product_id: INPUT.productId,
    });

    const pending = buyProduct(INPUT);
    await vi.waitFor(() => expect(createOneTimePurchaseOrder).toHaveBeenCalled());
    leaveAndReturn();

    const result = await pending;
    expect(recoverIapOrder).toHaveBeenCalled();
    expect(result.state).toBe('GRANTED');
    // Recovery has no processProductGrant callback, so it completes the grant itself.
    expect(completeProductGrant).toHaveBeenCalled();
  });

  it('reports pending rather than cancelled when an order exists but is unresolved', async () => {
    getPendingOrders
      .mockResolvedValueOnce({ orders: [] })
      .mockResolvedValue({ orders: [{ orderId: 'order-x', sku: 'sku.song.detail' }] });
    recoverIapOrder.mockResolvedValue({ granted: false });

    const pending = buyProduct(INPUT);
    await vi.waitFor(() => expect(createOneTimePurchaseOrder).toHaveBeenCalled());
    leaveAndReturn();

    const result = await pending;
    expect(result.state).toBe('PENDING_RECOVERY');
  });

  it('surfaces an intent failure without stranding the attempt', async () => {
    createIapIntent.mockRejectedValueOnce(Object.assign(new Error('nope'), { code: 'RESOURCE_NOT_FOUND' }));
    const first = await buyProduct(INPUT);
    expect(first.ok).toBe(false);

    createIapIntent.mockResolvedValue({ intent_id: 'intent-2', sku: 'sku.song.detail' });
    const second = buyProduct(INPUT);
    await vi.waitFor(() => expect(createOneTimePurchaseOrder).toHaveBeenCalled());
    leaveAndReturn();
    await second;
  });

  it('reports pending recovery when the backend grant call fails', async () => {
    grantIapOrder.mockRejectedValue(new Error('backend down'));
    createOneTimePurchaseOrder.mockImplementation((params: any) => {
      void params.options.processProductGrant({ orderId: 'order-1' });
      return cleanup;
    });
    const result = await buyProduct(INPUT);
    expect(result.state).toBe('PENDING_RECOVERY');
  });

  it('calls cleanup exactly once per attempt', async () => {
    createOneTimePurchaseOrder.mockImplementation((params: any) => {
      params.onEvent({ type: 'success' });
      params.onError(new Error('USER_CANCEL'));
      return cleanup;
    });
    await buyProduct(INPUT);
    expect(cleanup).toHaveBeenCalledTimes(1);
  });

  it('ignores a late callback from an attempt that already finished', async () => {
    const captured: any[] = [];
    createOneTimePurchaseOrder.mockImplementation((params: any) => {
      captured.push(params);
      return cleanup;
    });

    const first = buyProduct(INPUT);
    await vi.waitFor(() => expect(captured).toHaveLength(1));
    leaveAndReturn();
    expect((await first).state).toBe('PENDING_RECOVERY');

    grantIapOrder.mockResolvedValue({ granted: true });
    const second = buyProduct(INPUT);
    await vi.waitFor(() => expect(captured).toHaveLength(2));

    // The abandoned first attempt fires late. It must not settle the second one.
    void captured[0].options.processProductGrant({ orderId: 'stale-order' });
    await vi.waitFor(() => expect(grantIapOrder).toHaveBeenCalled());

    void captured[1].options.processProductGrant({ orderId: 'order-2' });
    const result = await second;
    expect(result.state).toBe('GRANTED');
  });

  // --- cancellation authority ------------------------------------------------------
  // getPendingOrders is documented as "결제는 됐지만 지급이 완료되지 않은 주문". An empty
  // list is NOT documented to mean the user cancelled, and on older Toss apps the call
  // returns undefined entirely. So "no pending order" must never be read as a cancel.

  it('A. an empty pending list followed by a real grant must not be a cancel', async () => {
    let sdkParams: any = null;
    createOneTimePurchaseOrder.mockImplementation((params: any) => {
      sdkParams = params;
      return cleanup;
    });
    getPendingOrders.mockResolvedValue({ orders: [] });
    grantIapOrder.mockResolvedValue({ granted: true });

    const pending = buyProduct(INPUT);
    await vi.waitFor(() => expect(sdkParams).not.toBeNull());
    leaveAndReturn();
    await delay(RECONCILE_WAIT);

    // The SDK delivers the grant only after we already looked at pending orders.
    void sdkParams.options.processProductGrant({ orderId: 'order-late' });
    const result = await pending;
    expect(result.state).not.toBe('CANCELLED');
  });

  it('B. an empty pending list that fills in later must not be a cancel', async () => {
    getPendingOrders
      .mockResolvedValueOnce({ orders: [] })
      .mockResolvedValue({ orders: [{ orderId: 'order-slow', sku: 'sku.song.detail' }] });

    const pending = buyProduct(INPUT);
    await vi.waitFor(() => expect(createOneTimePurchaseOrder).toHaveBeenCalled());
    leaveAndReturn();

    const result = await pending;
    expect(result.state).not.toBe('CANCELLED');
  });

  it('B2. an undefined pending list (older Toss app) must not be a cancel', async () => {
    getPendingOrders.mockResolvedValue(undefined);

    const pending = buyProduct(INPUT);
    await vi.waitFor(() => expect(createOneTimePurchaseOrder).toHaveBeenCalled());
    leaveAndReturn();

    const result = await pending;
    expect(result.state).not.toBe('CANCELLED');
  });

  it('C. only the documented USER_CANCELED error is an authoritative cancel', async () => {
    createOneTimePurchaseOrder.mockImplementation((params: any) => {
      params.onError({ code: 'USER_CANCELED' });
      return cleanup;
    });
    const result = await buyProduct(INPUT);
    expect(result.state).toBe('CANCELLED');

    // And it releases immediately, so the user can retry at once.
    const second = await buyProduct(INPUT);
    expect(second.state).toBe('CANCELLED');
    expect(createOneTimePurchaseOrder).toHaveBeenCalledTimes(2);
  });

  it('grants a carried-over payment instead of charging again', async () => {
    // An earlier attempt ended unresolved after a real payment. Retrying must settle that
    // order, not open a second purchase sheet.
    getPendingOrders.mockResolvedValue({ orders: [{ orderId: 'order-carried', sku: 'sku.song.detail' }] });
    recoverIapOrder.mockResolvedValue({
      granted: true,
      resource_id: INPUT.resourceId,
      product_id: INPUT.productId,
    });

    const result = await buyProduct(INPUT);
    expect(result.state).toBe('GRANTED');
    expect(createOneTimePurchaseOrder).not.toHaveBeenCalled();
    expect(completeProductGrant).toHaveBeenCalled();
  });

  it('still opens a purchase when the carried-over order is for another product', async () => {
    getPendingOrders.mockResolvedValue({ orders: [{ orderId: 'other', sku: 'sku.diagnostic' }] });

    const pending = buyProduct(INPUT);
    await vi.waitFor(() => expect(createOneTimePurchaseOrder).toHaveBeenCalled());
    leaveAndReturn();
    await pending;
    expect(recoverIapOrder).not.toHaveBeenCalledWith(
      expect.objectContaining({ order_id: 'other' }),
    );
  });

  // --- cross-resource recovery -------------------------------------------------------
  // song_detail is per-analysis but every analysis shares one Toss SKU, so a recovered
  // order may belong to a DIFFERENT analysis than the one being bought right now.

  it('does not report GRANTED for B when the recovered order belonged to A', async () => {
    getPendingOrders.mockResolvedValue({ orders: [{ orderId: 'order-A', sku: 'sku.song.detail' }] });
    // The server correctly recovers analysis A — but the user is buying B.
    recoverIapOrder.mockResolvedValue({
      granted: true,
      resource_id: 'a'.repeat(32),
      product_id: 'song_detail',
    });
    // B's own purchase still has to run; end it deterministically.
    createOneTimePurchaseOrder.mockImplementation((params: any) => {
      params.onError({ code: 'USER_CANCELED' });
      return cleanup;
    });

    const result = await buyProduct({ productId: 'song_detail', resourceId: 'b'.repeat(32) });
    expect(result.state).not.toBe('GRANTED');
    expect(result.ok).toBe(false);
    // A was settled correctly — that is not this purchase.
    expect(recoverIapOrder).toHaveBeenCalled();
  });

  it('rejects a recovery for a different product on the same analysis', async () => {
    getPendingOrders.mockResolvedValue({ orders: [{ orderId: 'order-D', sku: 'sku.song.detail' }] });
    recoverIapOrder.mockResolvedValue({
      granted: true,
      resource_id: INPUT.resourceId,
      product_id: 'diagnostic_full',
    });
    createOneTimePurchaseOrder.mockImplementation((params: any) => {
      params.onError({ code: 'USER_CANCELED' });
      return cleanup;
    });

    const result = await buyProduct(INPUT);
    expect(result.state).not.toBe('GRANTED');
  });

  it('still reports GRANTED when the recovered order is for the analysis being bought', async () => {
    getPendingOrders.mockResolvedValue({ orders: [{ orderId: 'order-B', sku: 'sku.song.detail' }] });
    recoverIapOrder.mockResolvedValue({
      granted: true,
      resource_id: INPUT.resourceId,
      product_id: INPUT.productId,
    });

    const result = await buyProduct(INPUT);
    expect(result.state).toBe('GRANTED');
  });

  it('does not accept a cross-resource recovery on the return path either', async () => {
    getPendingOrders
      .mockResolvedValueOnce({ orders: [] })
      .mockResolvedValue({ orders: [{ orderId: 'order-A', sku: 'sku.song.detail' }] });
    recoverIapOrder.mockResolvedValue({
      granted: true,
      resource_id: 'a'.repeat(32),
      product_id: 'song_detail',
    });

    const pending = buyProduct({ productId: 'song_detail', resourceId: 'b'.repeat(32) });
    await vi.waitFor(() => expect(createOneTimePurchaseOrder).toHaveBeenCalled());
    leaveAndReturn();

    const result = await pending;
    expect(result.state).not.toBe('GRANTED');
  });

  it('binds by intent id on the return path, and not on the stale pre-purchase path', async () => {
    getPendingOrders
      .mockResolvedValueOnce({ orders: [{ orderId: 'order-stale', sku: 'sku.song.detail' }] })
      .mockResolvedValue({ orders: [{ orderId: 'order-B', sku: 'sku.song.detail' }] });
    // The stale order does not grant this analysis, so the purchase proceeds.
    recoverIapOrder
      .mockResolvedValueOnce({ granted: true, resource_id: 'a'.repeat(32) })
      .mockResolvedValue({ granted: true, resource_id: INPUT.resourceId, product_id: INPUT.productId });

    const pending = buyProduct(INPUT);
    await vi.waitFor(() => expect(createOneTimePurchaseOrder).toHaveBeenCalled());
    leaveAndReturn();
    await pending;

    const [preCall, returnCall] = recoverIapOrder.mock.calls.map((c: any[]) => c[0]);
    // Unknown owner: claiming the current intent here would be the mis-binding itself.
    expect(preCall.intent_id).toBeUndefined();
    // This attempt's own order: bind it exactly.
    expect(returnCall).toMatchObject({ order_id: 'order-B', intent_id: 'intent-1' });
  });

  it('keeps completeProductGrant out of the initial purchase callback', async () => {
    grantIapOrder.mockResolvedValue({ granted: true });
    createOneTimePurchaseOrder.mockImplementation((params: any) => {
      void params.options.processProductGrant({ orderId: 'order-1' });
      return cleanup;
    });

    const result = await buyProduct(INPUT);
    expect(result.ok).toBe(true);
    // Returning true IS the completion signal; calling it here would duplicate it.
    expect(completeProductGrant).not.toHaveBeenCalled();
  });
});
