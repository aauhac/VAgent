# Production config audit

| Item | Status |
|---|---|
| DATABASE_URL in production | required at startup |
| Verified identity for payments | Toss login + session secret required when PAYMENTS_ENABLED |
| mTLS cert/key | required when PAYMENTS_ENABLED |
| Production SKUs | placeholder SKUs fail payments startup |
| ALLOW_MOCK_PREMIUM in prod | ignored; mock endpoints 403 |
| CORS localhost | stripped in production |
| FastAPI docs | disabled in production |
| Artifact mode | LOCAL_PERSISTENT, MULTI_INSTANCE UNSAFE |
| Replicas | BACKEND_REPLICAS must be 1 with local artifacts |
| Runtime volume | required (documented) |
| TOSS_API_BASE_URL allowlist | https://apps-in-toss-api.toss.im only |
| Singer identity | remains OFF |

Example file: `.env.production.example` (no secrets).
