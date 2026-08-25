import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  loadIapCatalog,
  logSkuMatches,
  resolveProductPrice,
  skuAuditRows,
  type IapCatalogSnapshot,
  type ResolvedProductPrice,
} from './iapCatalog';

const LOADING: IapCatalogSnapshot = {
  state: 'LOADING',
  itemsBySku: {},
  count: 0,
  tossAppVersion: null,
};

const DISABLED: IapCatalogSnapshot = {
  state: 'DISABLED',
  itemsBySku: {},
  count: 0,
  tossAppVersion: null,
};

export type UseIapProductPricesOptions = {
  /** When false, never call Toss IAP SDK. Backend PAYMENTS_ENABLED is source of truth. */
  enabled?: boolean;
};

export function useIapProductPrices(
  backendCatalog: any | null | undefined,
  options?: UseIapProductPricesOptions,
) {
  const paymentsEnabled = options?.enabled ?? backendCatalog?.payments_enabled === true;
  const [snapshot, setSnapshot] = useState<IapCatalogSnapshot>(
    paymentsEnabled ? LOADING : DISABLED,
  );
  const [generation, setGeneration] = useState(0);

  const reload = useCallback(() => {
    if (!paymentsEnabled) {
      setSnapshot(DISABLED);
      return;
    }
    setSnapshot(LOADING);
    setGeneration((n) => n + 1);
  }, [paymentsEnabled]);

  useEffect(() => {
    if (!paymentsEnabled) {
      setSnapshot(DISABLED);
      return;
    }
    let cancelled = false;
    loadIapCatalog()
      .then((next) => {
        if (!cancelled) setSnapshot(next);
      })
      .catch(() => {
        if (cancelled) return;
        setSnapshot({
          state: 'ERROR',
          itemsBySku: {},
          count: 0,
          tossAppVersion: null,
          errorCode: 'ERROR',
        });
      });
    return () => {
      cancelled = true;
    };
  }, [generation, paymentsEnabled]);

  useEffect(() => {
    if (paymentsEnabled && backendCatalog && snapshot.state !== 'LOADING') {
      logSkuMatches(backendCatalog, snapshot);
    }
  }, [backendCatalog, snapshot, paymentsEnabled]);

  const prices = useMemo(() => {
    const map: Record<string, ResolvedProductPrice> = {};
    const products = backendCatalog?.products || {};
    for (const productId of Object.keys(products)) {
      map[productId] = resolveProductPrice(productId, backendCatalog, snapshot);
    }
    if (paymentsEnabled && backendCatalog && snapshot.state !== 'LOADING') {
      for (const [productId, price] of Object.entries(map)) {
        try {
          console.info(
            `[IAP] price_state product=${productId} state=${price.state} `
              + `can_purchase=${price.canPurchase ? 'true' : 'false'} `
              + `retryable=${price.retryable ? 'true' : 'false'}`,
          );
        } catch {
          /* ignore */
        }
      }
    }
    return map;
  }, [backendCatalog, snapshot, paymentsEnabled]);

  const audit = useMemo(
    () => (paymentsEnabled ? skuAuditRows(backendCatalog, snapshot) : []),
    [backendCatalog, snapshot, paymentsEnabled],
  );

  return {
    catalogState: snapshot.state,
    paymentsEnabled,
    prices,
    reload,
    audit,
    snapshot,
  };
}
