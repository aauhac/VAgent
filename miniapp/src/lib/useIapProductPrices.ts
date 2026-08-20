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

export function useIapProductPrices(backendCatalog: any | null | undefined) {
  const [snapshot, setSnapshot] = useState<IapCatalogSnapshot>(LOADING);
  const [generation, setGeneration] = useState(0);

  const reload = useCallback(() => {
    setSnapshot(LOADING);
    setGeneration((n) => n + 1);
  }, []);

  useEffect(() => {
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
  }, [generation]);

  useEffect(() => {
    if (backendCatalog && snapshot.state !== 'LOADING') {
      logSkuMatches(backendCatalog, snapshot);
    }
  }, [backendCatalog, snapshot]);

  const prices = useMemo(() => {
    const map: Record<string, ResolvedProductPrice> = {};
    const products = backendCatalog?.products || {};
    for (const productId of Object.keys(products)) {
      map[productId] = resolveProductPrice(productId, backendCatalog, snapshot);
    }
    if (backendCatalog && snapshot.state !== 'LOADING') {
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
  }, [backendCatalog, snapshot]);

  const audit = useMemo(() => skuAuditRows(backendCatalog, snapshot), [backendCatalog, snapshot]);

  return {
    catalogState: snapshot.state,
    prices,
    reload,
    audit,
    snapshot,
  };
}
