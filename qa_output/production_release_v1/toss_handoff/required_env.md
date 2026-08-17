# Apps in Toss required environment (names only — no values)

These are the variables the current VAgent code reads. Fill them on the host/secret store. Do not put secrets in this repo.

## Login

- `TOSS_LOGIN_ENABLED` — must be `true` when `PAYMENTS_ENABLED=true`
- `TOSS_API_BASE_URL` — allowlisted production default `https://apps-in-toss-api.toss.im`
- `TOSS_IDENTITY_TRUST_MODE` — keep `UNVERIFIED_CLIENT_SUBJECT`. Setting `VERIFIED_TOSS_SUBJECT` does **not** authenticate client headers.

- Frontend sends `authorization_code` + `referrer` (`DEFAULT` | `SANDBOX`) to `POST /v1/auth/toss/login`. Backend exchanges the code and calls login-me. There is no client callback URL in this implementation.
- Disconnect callback URL: `{PUBLIC_BACKEND_BASE_URL}/v1/auth/toss/disconnect`

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

- `PAYMENTS_ENABLED`
- `DATABASE_URL`
- `PUBLIC_BACKEND_BASE_URL` — HTTPS origin of this backend after cloud deploy; composes legal + disconnect URLs
- `CORS_ORIGINS` — production defaults to `https://vocalfb.apps.tossmini.com` and `https://vocalfb.private-apps.tossmini.com`. Must not include localhost or `*`
- `BACKEND_REPLICAS` — must be `1` while artifact mode is `LOCAL_PERSISTENT`
- `RUNTIME_DIR` — persistent volume path
- `ALLOW_MOCK_PREMIUM` — must stay false in production (endpoints 403 anyway)
- `TOSS_DISCONNECT_BASIC_USER` / `TOSS_DISCONNECT_BASIC_PASSWORD` — required when Toss login is enabled in production

Miniapp production build:

- `VITE_API_BASE` — same HTTPS origin as `PUBLIC_BACKEND_BASE_URL` (rebuild after the hostname exists)


## Not used as auth proof

- `X-User-Id`
- `X-VAgent-User-Key`

These remain identifiers only.
