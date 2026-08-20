# Apps in Toss required environment (names only — no values)

These are the variables the current VAgent code reads. Fill them on the host/secret store. Do not put secrets in this repo.

## Login

- `TOSS_LOGIN_ENABLED` — must be `true` when `PAYMENTS_ENABLED=true`
- `TOSS_API_BASE_URL` — allowlisted production default `https://apps-in-toss-api.toss.im`
- `TOSS_IDENTITY_TRUST_MODE` — keep `UNVERIFIED_CLIENT_SUBJECT`. Setting `VERIFIED_TOSS_SUBJECT` does **not** authenticate client headers.

- Frontend sends `authorization_code` + `referrer` (`DEFAULT` | `SANDBOX`) to `POST /v1/auth/toss/login`. Backend exchanges the code and calls login-me. There is no client callback URL in this implementation.
- Disconnect callback URL: `https://54.116.187.5/v1/auth/toss/disconnect` (**REQUIRES_TOSS_CONSOLE_CONFIRMATION**)

## Session / HMAC

- `VAGENT_SESSION_SECRET` — required when payments are enabled; used to sign the VAgent bearer session. Not a Toss token.

## mTLS (server-to-server)

- `TOSS_MTLS_CERT_PATH` — path to the server certificate file (not in git)
- `TOSS_MTLS_KEY_PATH` — path to the private key file (not in git)

Used for:

- `POST /api-partner/v1/apps-in-toss/user/oauth2/generate-token`
- `GET /api-partner/v1/apps-in-toss/user/oauth2/login-me`
- `POST /api-partner/v1/apps-in-toss/order/get-order-status`

## Production SKU mappings

- `IAP_SONG_DETAIL_SKU`
- `IAP_DIAGNOSTIC_FULL_SKU`
- `IAP_DIAGNOSTIC_UPGRADE_SKU`

Placeholder defaults (`vagent.song_detail`, `vagent.diagnostic_full`, `vagent.diagnostic_upgrade`) fail production payments startup.

## Payments flag / CORS / DB / public URL

- `PAYMENTS_ENABLED` — live server currently `false` (IAP backend disabled until launch decision)
- `DATABASE_URL`
- `PUBLIC_BACKEND_BASE_URL` — live: `https://54.116.187.5`
- `CORS_ORIGINS` — production default / example:
  `https://vocalfb.apps.tossmini.com,https://vocalfb.private-apps.tossmini.com,https://apps-in-toss.toss.im`
  (miniapp live + QR + Toss Console callback-test origin). Must not include localhost or `*`
- `BACKEND_REPLICAS` — must be `1` while artifact mode is `LOCAL_PERSISTENT`
- `RUNTIME_DIR` — live: `/var/lib/vocalfb/runtime`
- `VAGENT_ANALYSIS_EXECUTION_MODE` — launch host must stay `local` (compose pins backend to local;
  do not let `aws-queue-staging.env` flip the API to `queue` without S3/SQS)
- `ALLOW_MOCK_PREMIUM` — must stay false in production (endpoints 403 anyway)
- `TOSS_DISCONNECT_BASIC_USER` / `TOSS_DISCONNECT_BASIC_PASSWORD` — required when Toss login is enabled in production

Miniapp production build:

- `VITE_API_BASE` — live bake: `https://54.116.187.5` (must match `PUBLIC_BACKEND_BASE_URL`)
- `VITE_TOSS_REWARDED_DETAIL_AD_GROUP_ID` — currently empty in production artifact (CTA hidden)


## Not used as auth proof

- `X-User-Id`
- `X-VAgent-User-Key`

These remain identifiers only.
