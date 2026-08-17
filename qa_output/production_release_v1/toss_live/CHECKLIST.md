# Apps in Toss live/sandbox evidence (human)

Do **not** store access tokens, refresh tokens, authorization codes, private keys, session secrets, or client secrets here.

Fill each folder with screenshots/logs after the human sandbox run. Keep filenames descriptive, no secrets.

Gate values: `PASS` / `FAIL` / `NOT_RUN` only after real Apps in Toss evidence exists.

| # | Folder | Check | DB/entitlement also required | Status |
|---|---|---|---|---|
| 01 | `01_login/` | sandbox `appLogin` → backend code exchange → login-me `userKey` → VAgent session. Tokens not in frontend. | Auth session row optional; user `provider=TOSS` | NOT_RUN |
| 02 | `02_product_catalog/` | `getProductItemList` returns three SKUs; UI `displayAmount` matches console VAT-inclusive price | Backend SKU env matches console | NOT_RUN |
| 03 | `03_detail_purchase/` | DETAIL purchase → server order verify → user/SKU/resource match → purchase COMPLETED → entitlement ACTIVE → 상세 리포트 접근 | YES | NOT_RUN |
| 04 | `04_diagnostic_full/` | PRECISION full on analysis **without** Detail → DIAGNOSTIC (+ bundled Detail) ACTIVE → session `source_analysis_id` set | YES | NOT_RUN |
| 05 | `05_diagnostic_upgrade/` | Same user, Detail already owned → `diagnostic_upgrade` SKU, not full | YES | NOT_RUN |
| 06 | `06_cancel/` | User cancel → `결제가 취소됐어요.` No entitlement. Retry works | entitlement still locked | NOT_RUN |
| 07 | `07_pending_recovery/` | Pay OK, grant fails → relaunch `getPendingOrders` → recover → grant → then `completeProductGrant` | entitlement after recover | NOT_RUN |
| 08 | `08_refund/` | Server-verified REFUNDED → purchase REFUNDED → entitlement REVOKED → Detail/Precision locked | YES | NOT_RUN |
| 09 | `09_history_binding/` | After precision complete, History **source analysis card** shows `정밀 발성 진단 · 완료 / 보기`. Not only the legacy section | `source_analysis_id` join | NOT_RUN |
| 10 | `10_ait_qr/` | `.ait` uploaded, QR in real Toss app. No production money charge required | same grant path | NOT_RUN |

Console must register **three** IAP products, mapped to:

- `IAP_SONG_DETAIL_SKU` ← `song_detail`
- `IAP_DIAGNOSTIC_FULL_SKU` ← `diagnostic_full`
- `IAP_DIAGNOSTIC_UPGRADE_SKU` ← `diagnostic_upgrade`

Placeholder `vagent.song_detail` / `vagent.diagnostic_full` / `vagent.diagnostic_upgrade` must be absent from production env.
