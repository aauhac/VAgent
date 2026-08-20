/**
 * Toss IAP catalog to backend product price resolution.
 * Production never hardcodes mock amounts and never displays a dash as the price.
 * Catalog lookup does not require Toss Login.
 */

export type IapCatalogState =
  | 'LOADING'
  | 'READY'
  | 'SDK_UNAVAILABLE'
  | 'UNSUPPORTED_APP'
  | 'EMPTY'
  | 'SKU_NOT_FOUND'
  | 'ERROR';

export type IapCatalogItem = {
  sku: string;
  displayAmount: string;
  displayName: string;
};

export type IapCatalogSnapshot = {
  state: Exclude<IapCatalogState, 'SKU_NOT_FOUND' | 'LOADING'> | 'LOADING';
  itemsBySku: Record<string, IapCatalogItem>;
  count: number;
  tossAppVersion: string | null;
  errorCode?: string;
};

export type ResolvedProductPrice = {
  productId: string;
  configuredSku: string | null;
  state: IapCatalogState;
  displayAmount: string | null;
  label: string;
  canPurchase: boolean;
  retryable: boolean;
  matched: boolean;
  hasDisplayAmount: boolean;
};

export const PRICE_LOADING_LABEL = '가격 확인 중…';
export const PRICE_UNAVAILABLE_LABEL = '가격 정보를 불러오지 못했어요.';
export const PRICE_RETRY_LABEL = '가격 다시 확인하기';

const PRODUCT_IDS = ['song_detail', 'diagnostic_full', 'diagnostic_upgrade'] as const;

export type SkuMismatchReason =
  | 'missing_configured_sku'
  | 'sku_not_in_toss_list'
  | 'missing_display_amount';

function iapLog(event: string) {
  try {
    console.info(`[IAP] ${event}`);
  } catch {
    /* ignore */
  }
}

function safeCode(error: unknown): string {
  const rec = error as { code?: unknown; name?: unknown; message?: unknown };
  const raw = String(rec?.code || rec?.name || 'ERROR');
  if (/eyJ|bearer|token|userKey|authorization|orderId/i.test(raw)) return 'REDACTED';
  const cleaned = raw.replace(/[^A-Za-z0-9._-]/g, '').slice(0, 40);
  return cleaned || 'ERROR';
}

function safeTossAppVersion(): string | null {
  try {
    const version = (globalThis as { __VAGENT_TOSS_APP_VERSION__?: string }).__VAGENT_TOSS_APP_VERSION__;
    if (typeof version === 'string' && /^[\d.]+$/.test(version)) return version;
  } catch {
    /* ignore */
  }
  return null;
}

async function readTossAppVersion(): Promise<string | null> {
  try {
    const mod = await import('@apps-in-toss/web-framework');
    const fn = (mod as { getTossAppVersion?: () => string }).getTossAppVersion;
    if (typeof fn !== 'function') return null;
    const raw = String(fn() || '');
    const version = raw.replace(/[^0-9.]/g, '').slice(0, 24);
    return version || null;
  } catch {
    return null;
  }
}

async function loadIapSdk(): Promise<any | null> {
  try {
    const mod = await import('@apps-in-toss/web-framework');
    return (mod as { IAP?: unknown }).IAP || null;
  } catch {
    return null;
  }
}

function extractProducts(response: unknown): { kind: 'undefined' | 'list'; products: any[] } {
  if (response == null) return { kind: 'undefined', products: [] };
  const rec = response as Record<string, unknown>;
  if (Array.isArray(response)) return { kind: 'list', products: response };
  const nested =
    rec.products ||
    (rec.success && typeof rec.success === 'object'
      ? (rec.success as { products?: unknown }).products
      : null) ||
    (rec.result && typeof rec.result === 'object'
      ? (rec.result as { products?: unknown }).products
      : null);
  if (Array.isArray(nested)) return { kind: 'list', products: nested };
  return { kind: 'list', products: [] };
}

function itemSku(product: any): string {
  return String(product?.sku || product?.productId || '').trim();
}

function itemAmount(product: any): string {
  const raw = product?.displayAmount;
  return typeof raw === 'string' ? raw.trim() : raw != null ? String(raw).trim() : '';
}

function backendProducts(catalog: any | null | undefined): Array<{
  product_id: string;
  sku?: string;
  display_amount?: string | null;
}> {
  const map = catalog?.products || {};
  return Object.values(map) as Array<{
    product_id: string;
    sku?: string;
    display_amount?: string | null;
  }>;
}

/** Backend catalog SKUs the app expects — compare with Toss Console 노출 ON SKUs. */
export function expectedBackendSkus(backendCatalog: any | null | undefined): Record<string, string | null> {
  const out: Record<string, string | null> = {};
  for (const productId of PRODUCT_IDS) {
    const row = backendProducts(backendCatalog).find((p) => p.product_id === productId);
    out[productId] = row?.sku ? String(row.sku).trim() : null;
  }
  return out;
}

export async function loadIapCatalog(): Promise<IapCatalogSnapshot> {
  const tossAppVersion = (await readTossAppVersion()) || safeTossAppVersion();
  iapLog(`catalog_start${tossAppVersion ? ` toss_app_version=${tossAppVersion}` : ''}`);
  const IAP = await loadIapSdk();
  if (!IAP?.getProductItemList) {
    iapLog('catalog_state=SDK_UNAVAILABLE reason=getProductItemList_missing');
    return {
      state: 'SDK_UNAVAILABLE',
      itemsBySku: {},
      count: 0,
      tossAppVersion,
      errorCode: 'SDK_UNAVAILABLE',
    };
  }
  try {
    const response = await IAP.getProductItemList();
    const extracted = extractProducts(response);
    if (response == null || extracted.kind === 'undefined') {
      iapLog('catalog_state=SDK_UNAVAILABLE reason=getProductItemList_returned_undefined');
      return {
        state: 'SDK_UNAVAILABLE',
        itemsBySku: {},
        count: 0,
        tossAppVersion,
        errorCode: 'SDK_UNAVAILABLE',
      };
    }
    const itemsBySku: Record<string, IapCatalogItem> = {};
    for (const product of extracted.products) {
      const sku = itemSku(product);
      if (!sku) continue;
      const displayAmount = itemAmount(product);
      itemsBySku[sku] = {
        sku,
        displayAmount,
        displayName: String(product?.displayName || ''),
      };
      iapLog(`catalog_item sku=${sku} has_display_amount=${displayAmount ? 'true' : 'false'}`);
    }
    const count = Object.keys(itemsBySku).length;
    const skuList = Object.keys(itemsBySku).join(',') || '-';
    iapLog(`catalog_loaded state=${count === 0 ? 'EMPTY' : 'READY'} count=${count} skus=${skuList}`);
    if (count === 0) {
      iapLog('catalog_state=EMPTY reason=products_array_empty');
      return { state: 'EMPTY', itemsBySku, count, tossAppVersion, errorCode: 'EMPTY' };
    }
    return { state: 'READY', itemsBySku, count, tossAppVersion };
  } catch (error) {
    const code = safeCode(error);
    iapLog(`catalog_state=ERROR code=${code}`);
    return {
      state: 'ERROR',
      itemsBySku: {},
      count: 0,
      tossAppVersion,
      errorCode: code,
    };
  }
}

function skuMismatchReason(
  configuredSku: string | null,
  snapshot: IapCatalogSnapshot,
  item: IapCatalogItem | undefined,
): SkuMismatchReason | null {
  if (!configuredSku) return 'missing_configured_sku';
  if (!item) return 'sku_not_in_toss_list';
  if (!(item.displayAmount || '').trim()) return 'missing_display_amount';
  return null;
}

export function resolveProductPrice(
  productId: string,
  backendCatalog: any | null | undefined,
  snapshot: IapCatalogSnapshot,
): ResolvedProductPrice {
  const row = backendProducts(backendCatalog).find((p) => p.product_id === productId);
  const configuredSku = row?.sku ? String(row.sku).trim() : null;
  const mockAmount =
    !import.meta.env.PROD && row?.display_amount ? String(row.display_amount).trim() : '';

  const unavailable = (state: IapCatalogState, retryable: boolean): ResolvedProductPrice => ({
    productId,
    configuredSku,
    state,
    displayAmount: null,
    label: snapshot.state === 'LOADING' ? PRICE_LOADING_LABEL : PRICE_UNAVAILABLE_LABEL,
    canPurchase: false,
    retryable,
    matched: false,
    hasDisplayAmount: false,
  });

  if (snapshot.state === 'LOADING') {
    return unavailable('LOADING', false);
  }
  if (snapshot.state === 'SDK_UNAVAILABLE') {
    if (mockAmount) {
      return {
        productId,
        configuredSku,
        state: 'READY',
        displayAmount: mockAmount,
        label: mockAmount,
        canPurchase: true,
        retryable: false,
        matched: false,
        hasDisplayAmount: true,
      };
    }
    return unavailable('SDK_UNAVAILABLE', true);
  }
  if (snapshot.state === 'UNSUPPORTED_APP') return unavailable('UNSUPPORTED_APP', true);
  if (snapshot.state === 'ERROR') {
    if (mockAmount) {
      return {
        productId,
        configuredSku,
        state: 'READY',
        displayAmount: mockAmount,
        label: mockAmount,
        canPurchase: true,
        retryable: false,
        matched: false,
        hasDisplayAmount: true,
      };
    }
    return unavailable('ERROR', true);
  }
  if (snapshot.state === 'EMPTY') {
    if (mockAmount) {
      return {
        productId,
        configuredSku,
        state: 'READY',
        displayAmount: mockAmount,
        label: mockAmount,
        canPurchase: true,
        retryable: false,
        matched: false,
        hasDisplayAmount: true,
      };
    }
    return unavailable('EMPTY', true);
  }

  const item = configuredSku ? snapshot.itemsBySku[configuredSku] : undefined;
  const matched = !!item;
  const amount = item?.displayAmount?.trim() || '';
  if (matched && amount) {
    return {
      productId,
      configuredSku,
      state: 'READY',
      displayAmount: amount,
      label: amount,
      canPurchase: true,
      retryable: false,
      matched: true,
      hasDisplayAmount: true,
    };
  }
  if (mockAmount) {
    return {
      productId,
      configuredSku,
      state: 'READY',
      displayAmount: mockAmount,
      label: mockAmount,
      canPurchase: true,
      retryable: false,
      matched,
      hasDisplayAmount: true,
    };
  }
  const mismatch = skuMismatchReason(configuredSku, snapshot, item);
  if (mismatch) {
    iapLog(
      `price_unavailable product=${productId} configured_sku=${configuredSku || '-'} `
        + `catalog_state=${snapshot.state} reason=${mismatch}`,
    );
  }
  return {
    productId,
    configuredSku,
    state: 'SKU_NOT_FOUND',
    displayAmount: null,
    label: PRICE_UNAVAILABLE_LABEL,
    canPurchase: false,
    retryable: true,
    matched,
    hasDisplayAmount: false,
  };
}

export function logSkuMatches(backendCatalog: any | null | undefined, snapshot: IapCatalogSnapshot) {
  const expected = expectedBackendSkus(backendCatalog);
  iapLog(`catalog_state=${snapshot.state} toss_product_count=${snapshot.count}`);
  for (const productId of PRODUCT_IDS) {
    const configuredSku = expected[productId];
    const item = configuredSku ? snapshot.itemsBySku[configuredSku] : undefined;
    const matched = !!item;
    const hasDisplayAmount = !!(item?.displayAmount || '').trim();
    const reason = matched
      ? hasDisplayAmount
        ? 'ready'
        : 'missing_display_amount'
      : configuredSku
        ? snapshot.state === 'EMPTY'
          ? 'toss_products_empty'
          : snapshot.state === 'SDK_UNAVAILABLE'
            ? 'sdk_unavailable'
            : 'sku_not_in_toss_list'
        : 'missing_configured_sku';
    iapLog(
      `sku_audit product=${productId} configured_sku=${configuredSku || '-'} `
        + `matched=${matched ? 'true' : 'false'} has_display_amount=${hasDisplayAmount ? 'true' : 'false'} `
        + `reason=${reason}`,
    );
  }
  if (snapshot.state === 'READY' && snapshot.count > 0) {
    const tossSkus = Object.keys(snapshot.itemsBySku).join(',');
    iapLog(`toss_skus=${tossSkus}`);
  }
}

export function skuAuditRows(
  backendCatalog: any | null | undefined,
  snapshot: IapCatalogSnapshot,
): Array<{
  product_id: string;
  configuredSku: string | null;
  matched: boolean;
  hasDisplayAmount: boolean;
}> {
  return backendProducts(backendCatalog).map((p) => {
    const sku = p.sku ? String(p.sku) : null;
    const item = sku ? snapshot.itemsBySku[sku] : undefined;
    return {
      product_id: p.product_id,
      configuredSku: sku,
      matched: !!item,
      hasDisplayAmount: !!(item?.displayAmount || '').trim(),
    };
  });
}

/** Back-compat: sku → item map when catalog is READY. Empty on any failure. */
export async function getIapProductMap(): Promise<Record<string, IapCatalogItem>> {
  const snapshot = await loadIapCatalog();
  if (snapshot.state !== 'READY') return {};
  return snapshot.itemsBySku;
}
