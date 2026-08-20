# Production region checklist

Provider packaging path: **AWS Lightsail** (`deploy/lightsail/`).  
Evidence: operator console + production SSH READ-ONLY audit (2026-08-20).

| Asset | Question | Status |
| --- | --- | --- |
| Compute | Lightsail instance country/region | **PASS** — Seoul / `ap-northeast-2` / AZ `ap-northeast-2a` |
| PostgreSQL | Primary region | **PASS** — same Lightsail host (`/var/lib/vocalfb/postgres`) |
| PostgreSQL replicas / PITR | Replica and backup region | **NONE CONFIRMED** — no replica/PITR configured |
| Audio / runtime artifacts | Region of the persistent volume | **PASS** — same Lightsail host (`/var/lib/vocalfb/runtime`) |
| Backup | Snapshot / backup region and retention location | **OFF / NONE CONFIRMED** — Lightsail Automatic snapshots **OFF**; no app/pg_dump/S3 backup job |
| Logs | Log sink region | **PASS** — nginx + Docker json-file on same Seoul host |
| Monitoring | Metrics / traces region | unused if unset |
| External processor | Apps in Toss / Toss servers (login, IAP, callbacks) | Toss infrastructure — separate processor |
| LLM / OpenAI-compatible | Only if `OPENAI_API_KEY` / `BASE_URL` is enabled | unused on live HTTP analysis path |
| CDN / miniapp static | Toss-hosted `*.apps.tossmini.com` | Toss-hosted; not our origin |
| Public backend HTTPS | Live origin | **PASS** — `https://54.116.187.5` |
| TLS | Certbot short-lived IP SAN + auto renew | **PASS** — `snap.certbot.renew.timer`; deploy hook reloads nginx |

Rules:

- Company-hosted stores above are Korea (Seoul). Do not claim “no overseas transfer ever” for Toss/platform internals.
- Privacy policy §6 reflects company-hosted Seoul storage without inventing AWS legal-entity names.
- Backup improvement (snapshots / `pg_dump`) is a separate ops task — do not invent backup claims while OFF.
