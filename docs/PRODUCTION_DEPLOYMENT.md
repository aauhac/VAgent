# Production deployment

Initial launch topology for VAgent. Local workspace is the implementation source of truth.

**Production backend packaging path:** AWS Lightsail (`deploy/lightsail/`).  
See `docs/PRODUCTION_CLOUD_DECISION.md`. Confirm the live Lightsail **region** on the
instance/account console before documenting it (do not guess).

## Miniapp vs backend

- Miniapp `appName=vocalfb` is hosted by Apps in Toss.
  Live origin: `https://vocalfb.apps.tossmini.com`
  QR origin: `https://vocalfb.private-apps.tossmini.com`
- VAgent backend is a separate public HTTPS service on Lightsail (compose + Dockerfile).
  Set `PUBLIC_BACKEND_BASE_URL` after that hostname exists.
- Frontend origin and API origin are **not** the same. Production miniapp builds
  must set `VITE_API_BASE` to `PUBLIC_BACKEND_BASE_URL`, then `npm run build:toss`.

## Environment

- `VAGENT_ENV=production`
- See `.env.production.example` for the full key list (no secrets).
- `ALLOW_MOCK_PREMIUM` must stay false. Production ignores the flag and returns 403 on mock unlock/pay/regenerate.
- `SINGER_IDENTITY_ENABLED=false` until that gate is separately unblocked.
- `PHYSIOLOGY_DEBUG=false`

## TLS

- Assume the backend sits behind platform HTTPS / load balancer / reverse proxy.
- Do not generate a production certificate in the app.
- Toss **outbound mTLS** client cert/key (`TOSS_MTLS_CERT_PATH` / `TOSS_MTLS_KEY_PATH`)
  is only for backend → Apps in Toss APIs. It is not the public HTTPS certificate.

## PostgreSQL

- Required. Startup fails closed without `DATABASE_URL` and a reachable database.
- SSL: put the vendor's requirement in `DATABASE_URL` (the engine does not invent `sslmode`).
- Pool: SQLAlchemy default QueuePool, `pool_pre_ping=True`, Postgres `connect_timeout=5`.
- `/health` does not probe the database. `/ready` does.

### Migration policy

Do **not** auto-run destructive migrations on application start. Current startup
only checks connectivity.

Recommended deploy flow:

1. Confirm `DATABASE_URL` connectivity
2. Run migrations separately from the repo root:

```
alembic upgrade head
```

3. Confirm migration PASS
4. Start the app

`alembic.ini` `sqlalchemy.url` is a dummy; `backend/alembic/env.py` uses `DATABASE_URL`.

## Runtime volume — LOCAL_PERSISTENT / MULTI_INSTANCE_UNSAFE

- Artifact mode is `LOCAL_PERSISTENT` under `RUNTIME_DIR`.
- This store is **MULTI_INSTANCE_UNSAFE**.
- Initial deploy: **backend replicas = 1** (`BACKEND_REPLICAS=1`).
- Uvicorn **workers = 1** (in-memory `JobRunner`).
- Mount a persistent volume at `RUNTIME_DIR`. Restart the process, keep the volume.
- Do not keep analysis audio on an ephemeral container filesystem.

Filesystem coupling (live path; object-storage migration boundary):

| Location | What |
| --- | --- |
| `backend/app/services/analysis_service.py` | `RUNTIME_DIR/{id}/upload*` |
| `backend/app/jobs/runner.py` | analysis artifacts + in-memory job map |
| `backend/app/diagnostic/service.py` | `RUNTIME_DIR/diagnostic_sessions` |
| `backend/app/services/history_service.py` | per-analysis meta files |
| `backend/app/services/deletion.py` | deletes analysis dirs |
| `backend/app/services/voice_profile_store.py` | `RUNTIME_DIR/voice_identity` |
| `backend/app/services/goal_store.py` | same tree |
| `backend/app/storage/artifacts.py` | `LocalArtifactStore`; `ObjectStorageArtifactStore` raises `NotImplementedError` and is unused |

No storage migration in this phase.

## Process

Preferred path: package with `scripts/package_lightsail_release.py`, transfer the
archive to the Lightsail host, then run `deploy/lightsail/deploy.sh`
(Postgres → `alembic upgrade head` → backend).

Compose assets:

- `deploy/lightsail/Dockerfile.backend`
- `deploy/lightsail/docker-compose.production.yml`
- optional worker: `Dockerfile.worker` + compose profile `queue-worker`

Direct uvicorn (dev / emergency) from repo root after migrations:

```
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Restart policy: restart the single process on failure; do not scale replicas while
`LOCAL_PERSISTENT` is in use.

## Frontend

- Apps in Toss miniapp: `npm run build:toss` from `miniapp/`.
- Production prices come from `IAP.getProductItemList().displayAmount`. Backend catalog amounts are not authoritative in production.
- Production API base is `VITE_API_BASE`. Empty is allowed for an unconfigured CI bundle (runtime fail-closed: `API_BASE_NOT_CONFIGURED`). It must not be localhost.
- After the cloud hostname exists, rebuild with `VITE_API_BASE=$PUBLIC_BACKEND_BASE_URL`.
- Scan: `python scripts/check_production_bundle.py`

## Toss console

- Register real SKUs. Do not ship placeholder `vagent.song_detail` / `vagent.diagnostic_full` / `vagent.diagnostic_upgrade` when payments are enabled.
- Set `IAP_SONG_DETAIL_SKU`, `IAP_DIAGNOSTIC_FULL_SKU`, `IAP_DIAGNOSTIC_UPGRADE_SKU`.
- Legal / disconnect URLs: `{PUBLIC_BACKEND_BASE_URL}/legal/...` and `{PUBLIC_BACKEND_BASE_URL}/v1/auth/toss/disconnect`. Keep console placeholders until the hostname exists. Do not invent one.

## Toss login (required for payments)

Official flow: miniapp `appLogin()` → backend exchanges `authorizationCode` → `login-me` `userKey` → VAgent session.

- Token exchange and user lookup are server-side only (`/v1/auth/toss/login`).
- Toss AccessToken / RefreshToken are never returned to the client.
- `TOSS_IDENTITY_TRUST_MODE=VERIFIED_TOSS_SUBJECT` does **not** make `X-User-Id` / `X-VAgent-User-Key` verified auth.
- Disconnect callback: public HTTPS, Basic Auth, session revoke only. No analysis/payment delete.

## mTLS

- Apps in Toss order status and login APIs use mTLS.
- Mount cert/key outside the repo: `TOSS_MTLS_CERT_PATH`, `TOSS_MTLS_KEY_PATH`.
- `TOSS_API_BASE_URL` must be `https://apps-in-toss-api.toss.im`.
- Production + `PAYMENTS_ENABLED=true` fails startup if cert/key/SKUs/login/session secret/disconnect Basic Auth are missing.
- Production + `TOSS_LOGIN_ENABLED=true` (even without payments) fails startup if session secret, mTLS, allowlisted API base, or disconnect Basic Auth are missing.

## Payments

- Flag: `PAYMENTS_ENABLED`.
- Turning the flag off does not delete entitlements. Free analysis keeps working.
- Grant path: intent → Toss order → server order status → user/sku/resource bind → DB grant → frontend `completeProductGrant`.
- Paid access is fail-closed when the payment DB path is down. `/ready` stays up for analysis if runtime+DB are healthy; payments report `degraded`.

## Health

- `GET /health` — liveness only (process up). No secret fields. No DB probe.
- `GET /ready` — runtime writable + PostgreSQL reachable. Payment/login misconfig is `degraded` and does not 503. `multi_instance_safe` is always false on this path.

## CORS / docs

- Production CORS defaults to the two verified vocalfb Toss origins. Localhost is not allowed. `*` is forbidden. `allow_credentials=False`.
- FastAPI `/docs`, `/redoc`, `/openapi.json` are disabled in production.

## Rollback

- Set `PAYMENTS_ENABLED=false`.
- Code rollback must keep `purchase_orders` / `entitlements` / `payment_intents` readable.
- Do not delete granted rows.

## Logs

- Structured payment logs: request_id, masked user, product, masked order, status, intent.
- Never log AccessToken, RefreshToken, mTLS private keys, authorization codes, full session tokens, or disconnect Basic Auth passwords.

## Region

- Prefer a Korea region for API, database, audio, backup, and logs on Lightsail.
- Confirm the actual region on the live instance before filling
  `docs/PRODUCTION_REGION_CHECKLIST.md`. Do not invent a region string in docs or legal.
