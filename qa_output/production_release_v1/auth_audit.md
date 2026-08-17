# Auth audit

## Old trust boundary

`X-User-Id` / `X-VAgent-User-Key` are client-asserted identifiers. Code previously could label `TOSS_ANONYMOUS` when `TOSS_IDENTITY_TRUST_MODE=VERIFIED_TOSS_SUBJECT` without proof.

## New boundary

- Header path: always `authenticated=false`, `trust_mode=UNVERIFIED_CLIENT_SUBJECT`.
- Verified path: `Authorization: Bearer <vagent_session>` issued after server token exchange + login-me `userKey`.
- Env flag alone cannot mark identity verified (tested).

## Payment/account ownership

Payment intents/grants use provider=`TOSS` + userKey. Analysis create with a verified session stores the same provider. Cross-user resource probe on `/v1/products?analysis_id=` now 404s if not owner.

## Remaining

Free analysis in development still accepts client headers (needed for local/dev). Production payments are blocked without a verified session.
