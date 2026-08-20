# Production cloud decision (AWS Lightsail)

**Current production backend topology (repo source of truth):** Amazon Web Services
**Lightsail** via `deploy/lightsail/` (Dockerfile, compose, deploy scripts, packaging).

Miniapp hosting and VAgent backend hosting remain different:

| Surface | Who hosts | Custom domain needed now |
| --- | --- | --- |
| Apps in Toss miniapp `vocalfb` | Toss | No |
| VAgent backend API | AWS Lightsail (this repo’s production path) | No, if Lightsail / reverse proxy gives a stable public HTTPS hostname |

**AWS region:** not recorded in this repository. Confirm on the live Lightsail instance
or account console before claiming a specific region (do not guess `ap-northeast-2`).

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

- Public HTTPS in front of the backend (TLS at load balancer / reverse proxy / Lightsail HTTPS).
- The application does not invent or terminate a production certificate by itself.
- Initial replica count: **1** (`BACKEND_REPLICAS=1`)
- Uvicorn workers: **1** (in-memory `JobRunner` is process-local unless queue mode is enabled)
- Stable outbound HTTPS (443) to Apps in Toss APIs
- Ability to present a **client** mTLS certificate+key for outbound Toss calls
- Persistent volume mount at `RUNTIME_DIR`

Outbound Toss mTLS client cert ≠ public HTTPS server cert. Do not mix them.

## Database

- PostgreSQL (compose service on the Lightsail host, or managed equivalent)
- Prefer Korea region when selecting infrastructure; **verify** on the live instance
- Automated backup is an operator responsibility
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

Not required to build or test the Toss-hosted miniapp.
Required only if you want a branded API hostname instead of the Lightsail-provided HTTPS name.
Set `PUBLIC_BACKEND_BASE_URL` / `VITE_API_BASE` only after a real hostname exists.
