# Legal claim audit

version: production-2026-08-20  
updated: 2026-08-20

Status: SUPPORTED_BY_CODE | SUPPORTED_BY_POLICY | LEGAL_REQUIREMENT | OPERATOR_INPUT_REQUIRED

| Claim | Status | Evidence |
| --- | --- | --- |
| User-facing service name is 노래 실력 진단받기 | SUPPORTED_BY_CODE | Home kicker, legal H1, granite `displayName`, `index.html` title |
| Technical appName remains `vocalfb` | SUPPORTED_BY_CODE | `granite.config.ts`, `package.json` |
| Auth/payment identity is verified Toss `userKey` | SUPPORTED_BY_CODE | `auth_routes.py` stores `me["userKey"]`; payments require verified session |
| Headers are not payment identity | SUPPORTED_BY_CODE | `identity.py` |
| `user_name` not persisted | SUPPORTED_BY_CODE | login-me only reads `userKey`; no name column on `users` |
| Same display name cannot share entitlements | SUPPORTED_BY_CODE | identity is userKey; names ignored |
| Toss access/refresh tokens not returned to client | SUPPORTED_BY_CODE | login response fields |
| Session TTL 12 hours | SUPPORTED_BY_CODE | `SESSION_TTL_SECONDS` |
| Analysis delete is server-side | SUPPORTED_BY_CODE | `DELETE /v1/analyses/{id}` + History confirmation |
| Delete requires verified session + owner | SUPPORTED_BY_CODE | `routes.py` delete_analysis |
| Delete removes audio artifacts | SUPPORTED_BY_CODE | `deletion.py` rmtree analysis dir |
| Delete removes explicitly linked diagnostics | SUPPORTED_BY_CODE | `source_analysis_id` / persisted explicit id |
| Orphan diagnostics are not cascade-deleted | SUPPORTED_BY_CODE | no source id → skip |
| Payment records survive analysis delete | SUPPORTED_BY_CODE | `purchase_orders` not touched |
| Path traversal cannot delete outside runtime | SUPPORTED_BY_CODE | `validate_analysis_id` + `relative_to` |
| Toss disconnect callback revokes sessions | SUPPORTED_BY_CODE | `POST/GET /v1/auth/toss/disconnect` |
| Disconnect does not delete analyses | SUPPORTED_BY_CODE | callback only `revoke_sessions_for_user_key` |
| Toss account withdrawal is not our feature | SUPPORTED_BY_POLICY | Terms §21; callback referrer `WITHDRAWAL_TOSS` only revokes sessions |
| Audio not sent to external LLM on HTTP upload path | SUPPORTED_BY_CODE | `include_feedback` false |
| No user-audio training pipeline in live app | SUPPORTED_BY_CODE | inventory search |
| Products bound to analysis resource | SUPPORTED_BY_CODE | `payment_intents.resource_id`, entitlements |
| Three products: 상세 / 정밀 / 업그레이드 | SUPPORTED_BY_CODE | `catalog.py` display_name |
| No PAN stored | SUPPORTED_BY_CODE | purchase models |
| Refund revoke after server REFUNDED | SUPPORTED_BY_CODE | payment refund route |
| IAP refund follows Apple/Google + Apps in Toss console | LEGAL_REQUIREMENT | [인앱 결제](https://developers-apps-in-toss.toss.im/guide/monetization/in-app-payment.md) |
| Digital goods must use IAP not Toss Pay | LEGAL_REQUIREMENT | [서비스 오픈 정책](https://developers-apps-in-toss.toss.im/intro/guide.md) §6 |
| Partner must register 서비스 이용약관 + 수집·이용 동의 | LEGAL_REQUIREMENT | [토스 로그인 소개](https://developers-apps-in-toss.toss.im/guide/authentication/intro.md) |
| Privacy policy public notice | LEGAL_REQUIREMENT | 개인정보 보호법 §30 |
| Analysis is not medical diagnosis | SUPPORTED_BY_POLICY | product copy |
| Audio auto-TTL (e.g. 1 year) | OPERATOR_INPUT_REQUIRED | not in code; docs state delete-on-request only |
| Lightsail as production packaging | SUPPORTED_BY_CODE | `deploy/lightsail/*` |
| Lightsail / DB region string | OPERATOR_INPUT_REQUIRED | not in repo |
| International transfer notice filled | OPERATOR_INPUT_REQUIRED | wait for confirmed region |
| DPO name / business registration in repo | OPERATOR_INPUT_REQUIRED | public docs point to Apps in Toss partner registration |
| Electronic commerce 청약철회 vs IAP | SUPPORTED_BY_POLICY | Terms §14: no blanket “환불 불가”; follow law + platform |
| Safety answers as sensitive health data | OPERATOR_INPUT_REQUIRED | boolean discomfort fields stored; not labeled medical |
| Under-14 dedicated flow | SUPPORTED_BY_POLICY | Privacy: no under-14 signup flow |
| No separate analytics/error-tracking SDK (GA/Sentry/PostHog) | SUPPORTED_BY_CODE | miniapp/src, backend |
| Apps in Toss rewarded ads used for SONG_DETAIL unlock | SUPPORTED_BY_CODE | `tossRewardedAd.ts`, `rewarded_detail.py` |
| Rewarded ad only unlocks SONG_DETAIL (not diagnostic) | SUPPORTED_BY_CODE | `REWARD_TYPE_SONG_DETAIL` / entitlement grant |
| Reward only after `userEarnedReward` + valid server session | SUPPORTED_BY_CODE | claim requires session token; client watched-alone insufficient |
| Daily limit 3 Asia/Seoul enforced server-side | SUPPORTED_BY_CODE | `RewardedAdDailySlot` unique slots |
| Production ad group ID from env only | SUPPORTED_BY_CODE | `VITE_TOSS_REWARDED_DETAIL_AD_GROUP_ID`; empty → hide CTA |
| No invented production ad group ID | SUPPORTED_BY_CODE | non-prod may use official test id only |
| Login not required solely to watch rewarded ad | SUPPORTED_BY_CODE | routes use `_ident` / headers; anonymous principal_key |
| Privacy distinguishes rewarded ads vs analytics SDKs | SUPPORTED_BY_POLICY | `PRIVACY_POLICY.ko.md` §2 / §10 |
| Public privacy discloses reward records in user-friendly language | SUPPORTED_BY_POLICY | §2 E; no `principal_key` / table names |
| External font CDN | SUPPORTED_BY_CODE | removed; system fonts |
| Generative AI labeling (Toss §5) | SUPPORTED_BY_POLICY | live path is local acoustic analysis |
| Public legal pages free of draft/TODO blockers | SUPPORTED_BY_CODE | `tests/legal/test_legal_pages.py`, package/bundle scanners |
