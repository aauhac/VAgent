# 노래 실력 진단받기 data processing inventory

version: draft-2  
generated: 2026-08-18  
source: local workspace code (`backend/`, `miniapp/src/`)  
not a user-facing document

Provenance: SUPPORTED_BY_CODE unless marked otherwise.

| Data | Source | Purpose | Storage | Retention | Deletion | User-facing disclosure |
| ---- | ------ | ------- | ------- | --------- | -------- | ---------------------- |
| Toss `userKey` | Toss login-me (mTLS) after `authorizationCode` exchange | Account identity; History; payment/entitlement owner | Postgres `users.external_subject`, `auth_sessions.toss_user_key`; HMAC session payload | Session HMAC 12h; DB user row: no TTL | Toss disconnect callback revokes sessions (`auth_revoked_at`); does not delete analyses | Privacy / consent |
| Toss `name` (`user_name` scope) | May be present on login-me if console requests USER_NAME | Not used as identity | Not persisted. Code reads only `userKey` | Transient request memory only | Discarded after login handler | Privacy / consent |
| `authorizationCode` | Miniapp `appLogin()` | One-time token exchange | Not stored | Toss: 10 minutes (official) | Not persisted | Terms (login) |
| Toss access/refresh token | Token exchange response | login-me only | In-process memory; nulled in `finally`; never returned to client | Request lifetime | Dropped after login | Privacy (not stored) |
| Session token | HMAC-SHA256 (`v1.{payload}.{mac}`) | Verified auth for payments, owner checks, analysis delete | Client `sessionStorage` `vagent_session_token_v1`; DB `auth_sessions` (jti, exp, revoked_at) | 12 hours (`SESSION_TTL_SECONDS`) | Expiry; disconnect sets `revoked_at` / `users.auth_revoked_at` | Privacy |
| Toss anonymous key | Apps in Toss `getAnonymousKey` (non-login) | Header identifier only, not payment proof | `sessionStorage` `vagent_user_identity_v1`; sent as `X-VAgent-User-Key` | Tab session | Tab close | Privacy (technical) |
| Client identity headers | Miniapp | Identifier fallback | Not a store | Request | n/a | Not used as payment identity |
| Uploaded/recorded audio | User Record/Upload | Analysis | `RUNTIME_DIR/<analysis_id>/upload.*`, `analysis.wav`, `preview.wav` | No TTL in code | Owner-verified `DELETE /v1/analyses/{id}` removes job dir | Terms / privacy / consent |
| Diagnostic task audio | User diagnostic recordings | Precision diagnosis | `runtime/diagnostic_sessions/<sid>/tasks/...` | No TTL | Deleted when **explicitly linked** source analysis is deleted | Terms / privacy |
| Original filename | Client multipart | Display on History | `analyses.original_filename`; local cache | No TTL | With analysis delete | Privacy |
| Analysis id, status, timestamps | Server | Job tracking | Postgres `analyses`; filesystem JSON | No TTL | Soft-delete `deleted_at` + files | Privacy |
| Public summary / vocal type teaser | Analyzer | Free result | `analyses.public_summary`; `public_result.json` | No TTL | Cleared/removed with analysis delete | Privacy |
| Full analysis JSON | Local analyzer | Detail report | `runtime/<id>/analysis.json` | No TTL | With analysis delete | Privacy |
| Diagnostic session, `source_analysis_id`, report | Server | Precision flow + History link | Postgres `diagnostic_sessions`; `session.json` | No TTL | Cascade when source analysis deleted (explicit relation only). Orphans kept | Privacy |
| User concerns / safety yes-no answers | User forms | Plan diagnostic tasks; safety gating | Session JSON; deleted with diagnostic session | No TTL | With linked diagnostic delete | Privacy. LEGAL_REVIEW_REQUIRED: 민감정보 해당 여부 |
| Payment intent | Miniapp after login | Bind SKU to analysis before IAP | `payment_intents` | Intent expires 20 minutes | Row remains after analysis delete | Privacy |
| Purchase order | After Toss order verify | Accounting / grant | `purchase_orders` (order id, sku, product, resource, status, refunded_at). **No card/PAN.** | No TTL | **Not** deleted on analysis delete | Privacy / terms |
| Entitlement | After verified grant | Unlock Detail/Precision for that analysis | `entitlements` | Until refund revoke | Refund → REVOKED. Analysis delete does not erase purchase rows | Terms / privacy |
| IP address | TCP peer | Login/payment in-memory rate limit bucket | Not persisted by app | In-memory window | Process restart | Privacy: not stored. Reverse proxy access logs: TODO_BEFORE_PRODUCTION |
| User-Agent | Not read by app middleware | — | Not stored | — | — | Not disclosed as collected |
| Request id / error logs | Middleware | Debug unhandled exceptions | Process logs: request_id, method, path, exception type | Deploy/log policy: POLICY_DECISION_REQUIRED | POLICY_DECISION_REQUIRED | Privacy (operational logs) |
| localStorage history/goals/snapshots | Miniapp | UX cache | Device only | Caps (history 20, etc.) | User can clear site data; History delete also drops local cache after server success | Privacy (device storage) |
| Analytics SDK | — | — | None in miniapp/src or backend | — | — | Do not claim analytics |
| External font CDN | Previously jsDelivr Pretendard | — | Removed; system fonts only | — | — | Privacy §10 |
| AI training corpus | — | — | No live-app path | — | — | Explicitly **not** used for training |

## Absences (do not invent)

- Toss 계정 회원탈퇴를 이 앱이 수행하는 API
- 원클릭 전체 이용정보 일괄 삭제 UI
- Audio TTL/cron for undeleted analyses
- Card number, payment method PAN
- Business entity, hosting country, DPO contact in repo
- Marketing push/email/SMS
- Google Analytics / Sentry / PostHog / pixels
