# Toss SKU mapping (code vs console)

Internal product ids are owned by VAgent. Toss SKU strings come from env. Match the console SKU to the env value — do not invent new names in code during console setup.

| Internal product_id | Entitlement | Resource | Env var | Current code default (PLACEHOLDER) |
|---|---|---|---|---|
| `song_detail` | SONG_DETAIL | ANALYSIS (analysis_id) | `IAP_SONG_DETAIL_SKU` | `vagent.song_detail` |
| `diagnostic_full` | DIAGNOSTIC (+ bundled SONG_DETAIL) | ANALYSIS (analysis_id) | `IAP_DIAGNOSTIC_FULL_SKU` | `vagent.diagnostic_full` |
| `diagnostic_upgrade` | DIAGNOSTIC | ANALYSIS (analysis_id) | `IAP_DIAGNOSTIC_UPGRADE_SKU` | `vagent.diagnostic_upgrade` |

DETAIL = `song_detail`  
PRECISION full = `diagnostic_full` (when the analysis does not already own Detail)  
PRECISION upgrade = `diagnostic_upgrade` (when Detail is already owned)

Production: if any env SKU is empty or still a placeholder, payments startup **FAIL**.

Recommended console product type for per-recording unlocks: **CONSUMABLE**.

Frontend production prices come from `IAP.getProductItemList()` `displayAmount`, not from these defaults.
