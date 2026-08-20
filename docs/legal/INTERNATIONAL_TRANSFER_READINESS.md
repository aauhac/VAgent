# International transfer readiness

version: production-2026-08-20  
updated: 2026-08-20  
source: operator-confirmed Lightsail console + production SSH READ-ONLY audit

## Currently confirmed hosting

| Layer | Status |
| --- | --- |
| Miniapp | Apps in Toss (`vocalfb.apps.tossmini.com`) — Toss hosts the miniapp |
| Backend | **AWS Lightsail** Seoul / `ap-northeast-2` / AZ `ap-northeast-2a` |
| Static IPv4 | `54.116.187.5` |
| Public HTTPS origin | `https://54.116.187.5` |
| PostgreSQL | Same Lightsail host (`vocalfb-postgres-1`, volume `/var/lib/vocalfb/postgres`) — Seoul |
| Audio / runtime | Same Lightsail host (`/var/lib/vocalfb/runtime`) — Seoul |
| Nginx access/error logs | Same host (`/var/log/nginx/*`) — Seoul |
| Application / container logs | Same host (Docker `json-file`) — Seoul |
| Lightsail Automatic snapshots | **OFF** |
| Application / PostgreSQL / audio backup job | **Not configured / not confirmed** |

## Does overseas transfer occur?

**Company-hosted personal data** (userKey rows, audio, analysis, payment rows, confirmed local logs):  
stored in **Republic of Korea — AWS Lightsail Seoul (`ap-northeast-2`)**. No company-operated overseas store confirmed for this path.

**Toss platform traffic (confirmed direction):** login token exchange and IAP order
lookup go to `https://apps-in-toss-api.toss.im` (대한민국 사업 토스). That is
platform processing through the Toss app, not a filled “국외 이전 동의” form with
invented foreign entities.

**Apps in Toss / rewarded-ad platform internals:** country and sub-processor chain
beyond our Lightsail audit are **not** claimed as “never transferred overseas.”

## Backup

- Lightsail Automatic snapshots: **OFF** (AWS console)
- No `pg_dump` / app filesystem / S3 backup cron confirmed on the host
- `dpkg-db-backup.timer` is Ubuntu package-DB only — not VAgent user-data backup

## Remaining operator items (not region unknowns)

- Toss console: raw-IP legal / disconnect URL acceptance (**REQUIRES_TOSS_CONSOLE_CONFIRMATION**)
- Mobile legal smoke
- Monetization launch: `PAYMENTS_ENABLED`, IAP SKUs, rewarded-ad production group ID
