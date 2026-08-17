# Production cloud decision (vendor not chosen)

No cloud vendor, region, or custom domain has been selected. This file is the
requirement list for when a vendor is chosen. It is not a deployment.

Miniapp hosting and VAgent backend hosting are different:

| Surface | Who hosts | Custom domain needed now |
| --- | --- | --- |
| Apps in Toss miniapp `vocalfb` | Toss | No |
| VAgent backend API | Our cloud (not chosen) | No, if the platform gives a stable public HTTPS hostname |

## Miniapp origins (verified)

SDK: granite / `@apps-in-toss/web-framework` 2.x → CORS rules for **SDK 1.x–2.x**.

Official source: [서버 API 이용하기](https://developers-apps-in-toss.toss.im/documentation/integration/server-api.md)

GitBook currently renders the appName wildcard as a missing label
(`https://.apps.tossmini.com`). The established pattern is
`https://{appName}.apps.tossmini.com`. For `appName=vocalfb`:

- Live: `https://vocalfb.apps.tossmini.com`
- QR / private test: `https://vocalfb.private-apps.tossmini.com`

SDK 3.x `*.web.tossmini.com` origins do **not** apply unless this app migrates.

## Compute

- Public HTTPS in front of one backend process (TLS at load balancer / platform / reverse proxy).
- The application does not invent or terminate a production certificate.
- Initial replica count: **1**
- Uvicorn workers: **1** (in-memory `JobRunner` is process-local)
- Stable outbound HTTPS (443) to Apps in Toss APIs
- Ability to present a **client** mTLS certificate+key for outbound Toss calls
- Persistent volume mount at `RUNTIME_DIR`

Outbound Toss mTLS client cert ≠ public HTTPS server cert. Do not mix them.

## Database

- PostgreSQL
- Korea region preferred (not verified until a vendor is chosen)
- Automated backup
- Encrypted connection — pass provider SSL through `DATABASE_URL` (do not invent `sslmode` in app code)
- App uses SQLAlchemy `pool_pre_ping=True` and Postgres `connect_timeout=5`

## Storage

Current: `ARTIFACT_STORAGE_MODE=LOCAL_PERSISTENT` under `RUNTIME_DIR`.

Status: **MULTI_INSTANCE_UNSAFE**

Initial production path:

Internet / Toss → HTTPS → **one** backend instance → mounted runtime volume → PostgreSQL

Do not claim multi-instance safety while local artifact storage and the in-memory job registry remain.

Future: object storage behind `ArtifactStore`. `ObjectStorageArtifactStore` is an unimplemented stub. Live analysis/diagnostic paths still write the filesystem directly (see coupling list in `docs/PRODUCTION_DEPLOYMENT.md`). This work does not migrate storage.

Do not hardcode AWS EBS / GCP Persistent Disk / NCP Block Storage product names in app config.

## Secrets

Secret manager or equivalent. Names only — never commit values:

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

Backend may use the cloud-provided HTTPS hostname for first technical validation.

`CUSTOM_DOMAIN_REQUIRED_BY_TOSS` applies if we later call the Apps in Toss
사용자정보 SDK (`getConsentedUserData`) whose `termsUrl` must be an HTTPS
company-owned domain. **Current VAgent code does not call that API: `NOT_USED`.**

## Not chosen

- Cloud vendor: **NO**
- Production region: **NO**
- International transfer verification: **NO**
