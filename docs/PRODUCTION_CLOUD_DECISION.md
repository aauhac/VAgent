# Production cloud decision (AWS Lightsail)

**Current production backend topology (repo source of truth):** Amazon Web Services
**Lightsail** via `deploy/lightsail/` (Dockerfile, compose, deploy scripts, packaging).

Miniapp hosting and VAgent backend hosting remain different:

| Surface | Who hosts | Custom domain needed now |
| --- | --- | --- |
| Apps in Toss miniapp `vocalfb` | Toss | No |
| VAgent backend API | AWS Lightsail (this repo’s production path) | No, if Lightsail / reverse proxy gives a stable public HTTPS hostname |

**AWS region (confirmed):** Seoul / `ap-northeast-2` / AZ `ap-northeast-2a`  
**Static IPv4:** `54.116.187.5`  
**Public HTTPS origin:** `https://54.116.187.5` (`PUBLIC_BACKEND_BASE_URL`)  
**Miniapp API bake:** `VITE_API_BASE=https://54.116.187.5`

## Miniapp origins (verified)

SDK: granite / `@apps-in-toss/web-framework` 2.x → CORS rules for **SDK 1.x–2.x**.

Official source: [서버 API 이용하기](https://developers-apps-in-toss.toss.im/documentation/integration/server-api.md)

For `appName=vocalfb`:

- Live: `https://vocalfb.apps.tossmini.com`
- QR / private test: `https://vocalfb.private-apps.tossmini.com`

SDK 3.x `*.web.tossmini.com` origins do **not** apply unless this app migrates.

## Compute (Lightsail)

Packaging and deploy assets:

- `deploy/lightsail/Dockerfile.backend`
- `deploy/lightsail/Dockerfile.worker` (optional queue worker profile)
- `deploy/lightsail/docker-compose.production.yml`
- `deploy/lightsail/deploy.sh`
- `scripts/package_lightsail_release.py`

Topology:

- Public HTTPS: host Nginx terminates TLS on `443` → `127.0.0.1:8000` (FastAPI).
- Certificate: Let's Encrypt **IP SAN** for `54.116.187.5` (short-lived profile).
- TLS auto renewal: **confirmed** (`snap.certbot.renew.timer`); nginx reload after renew: **confirmed** (deploy hook).
- Initial replica count: **1** (`BACKEND_REPLICAS=1`)
- Uvicorn workers: **1** (in-memory `JobRunner` is process-local unless queue mode is enabled)
- Stable outbound HTTPS (443) to Apps in Toss APIs
- Ability to present a **client** mTLS certificate+key for outbound Toss calls
- Persistent volume mount at `RUNTIME_DIR=/var/lib/vocalfb/runtime` on the same Seoul host
- PostgreSQL on the same host (`/var/lib/vocalfb/postgres`); no public DB port

Outbound Toss mTLS client cert ≠ public HTTPS server cert. Do not mix them.

## Database

- PostgreSQL compose service on the **same Seoul Lightsail host** (`vocalfb-postgres-1`)
- Data volume: `/var/lib/vocalfb/postgres`
- Lightsail Automatic snapshots: **OFF**; dedicated `pg_dump`/app backup: **not configured**
- Encrypted connection — pass provider SSL through `DATABASE_URL` (do not invent `sslmode` in app code)
- App uses SQLAlchemy `pool_pre_ping=True` and Postgres `connect_timeout=5`

## Storage

Current: `ARTIFACT_STORAGE_MODE=LOCAL_PERSISTENT` under `RUNTIME_DIR` on the Lightsail host volume.

Status: **MULTI_INSTANCE_UNSAFE**

Initial production path:

Internet / Toss → HTTPS → **one** backend instance → mounted runtime volume → PostgreSQL

Optional queue path (S3 + SQS + worker) may be enabled via env; see compose profiles and
`VAGENT_ANALYSIS_EXECUTION_MODE`. Do not claim multi-instance safety while local artifact
storage and a single-process job runner remain the default.

## Secrets

Secret manager or host env files (e.g. `/etc/vocalfb/…`). Names only — never commit values:

- `DATABASE_URL`
- `PAYMENTS_ENABLED`
- `TOSS_LOGIN_ENABLED`
- `TOSS_MTLS_CERT_PATH`
- `TOSS_MTLS_KEY_PATH`
- `TOSS_API_BASE_URL`
- `IAP_SONG_DETAIL_SKU`
- `IAP_DIAGNOSTIC_FULL_SKU`
- `IAP_DIAGNOSTIC_UPGRADE_SKU`
- `VAGENT_SESSION_SECRET`
- `CORS_ORIGINS`
- `TOSS_DISCONNECT_BASIC_USER`
- `TOSS_DISCONNECT_BASIC_PASSWORD`
- `PUBLIC_BACKEND_BASE_URL`
- Miniapp production build: `VITE_API_BASE` (same origin as `PUBLIC_BACKEND_BASE_URL`)

## Network

Inbound (browser / Toss miniapp → backend):

- CORS allowlist: live + QR origins above
- Public disconnect callback: `{PUBLIC_BACKEND_BASE_URL}/v1/auth/toss/disconnect`
- Public legal HTML: `/legal/terms`, `/legal/privacy`, `/legal/privacy-consent`
- Toss inbound callback IPs (official): see server-api inbound table, port 443

Outbound (backend → Apps in Toss):

- `https://apps-in-toss-api.toss.im` with mTLS client cert
- Official outbound IPs/port in the same server-api document

## Custom domain

Not required for the current live origin `https://54.116.187.5` (Let's Encrypt IP certificate).
A branded hostname is optional later; if added, rebuild miniapp with matching `VITE_API_BASE`
and update Toss console URLs. **REQUIRES_TOSS_CONSOLE_CONFIRMATION** whether raw-IP URLs
are accepted for legal/disconnect registration.

## Live monetization flags (server audit)

- `TOSS_LOGIN_ENABLED=true`
- `PAYMENTS_ENABLED=false` (IAP backend currently disabled — do not document as live IAP)
- Miniapp rewarded-ad production group ID: empty (CTA hidden)

