# Legal claim audit

version: draft-2  
generated: 2026-08-18

Status: SUPPORTED_BY_CODE | SUPPORTED_BY_POLICY | LEGAL_REQUIREMENT | TODO

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
| Privacy policy public notice | LEGAL_REQUIREMENT | 개인정보 보호법 §30; 2026 작성지침 |
| Analysis is not medical diagnosis | SUPPORTED_BY_POLICY | product copy |
| Retention 1/3/5 years | TODO | not in code; not invented |
| Hosting country / processors | TODO | PRODUCTION_HOSTING_DECISION_REQUIRED |
| International transfer | TODO | not verified; Korea region preferred, not confirmed |
| DPO / business registration | TODO | not in repo |
| Electronic commerce 청약철회 vs IAP | LEGAL_REVIEW_REQUIRED | do not invent 7-day or no-refund blanket |
| Safety answers as sensitive health data | LEGAL_REVIEW_REQUIRED | boolean discomfort fields stored |
| Under-14 users | LEGAL_REVIEW_REQUIRED | not implemented |
| No analytics SDK | SUPPORTED_BY_CODE | miniapp/src, backend |
| External font CDN | SUPPORTED_BY_CODE | removed; system fonts |
| Generative AI labeling (Toss §5) | SUPPORTED_BY_POLICY | live path is local acoustic analysis |
