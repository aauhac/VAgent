# Apps in Toss items that still require a human

None of the following are live-verified in this workspace. Do not mark them PASS until you run them in sandbox / QR.

1. Console: confirm VAgent miniapp `appName` matches WebView.
2. Issue mTLS cert/key. Store **outside** `C:\VocalAgent`. Set `TOSS_MTLS_CERT_PATH` / `TOSS_MTLS_KEY_PATH`.
3. Enable Toss login in console. Prefer `userKey` only; skip name/phone/CI if unused.
4. Register IAP products as CONSUMABLE. Set the three `IAP_*_SKU` env vars to the **console SKU strings**. Use console VAT-inclusive selling price as `displayAmount`.
5. Install sandbox app, developer login, open `intoss://{appName}`.
6. Confirm `getProductItemList()` returns DETAIL + PRECISION with real `displayAmount`.
7. Sandbox purchase DETAIL on a new analysis → grant → Detail unlock after restart. Re-buy on a **second** analysis (consumable).
8. Sandbox purchase PRECISION on that analysis → complete tasks → History card shows `정밀 발성 진단 · 완료 / 보기`.
9. Cancel purchase → `결제가 취소됐어요.` No entitlement.
10. Pending recovery: pay, fail backend grant (stop API or force 500 on `/v1/payments/iap/grant`), relaunch app → `getPendingOrders` → recover → `completeProductGrant` only after grant.
11. Completed/refunded history + server revoke.
12. Upload `.ait` and QR-test in the real Toss app. **No production money charge required for this gate.**

Code-level pending recovery is implemented (`miniapp/src/lib/tossIap.ts` `recoverPendingPurchases`). Live/sandbox still **NOT_RUN**.
