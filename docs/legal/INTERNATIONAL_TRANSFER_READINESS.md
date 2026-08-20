# International transfer readiness

version: production-2026-08-20  
updated: 2026-08-20

## Currently confirmed hosting

| Layer | Status |
| --- | --- |
| Miniapp | Apps in Toss (`vocalfb.apps.tossmini.com`) — Toss hosts the miniapp |
| Backend packaging | **AWS Lightsail** (`deploy/lightsail/` in this repo) |
| PostgreSQL | Compose/host DB on the Lightsail deployment path |
| Audio / runtime volume | Local persistent volume on the Lightsail host (`RUNTIME_DIR`) |
| AWS region | **Not recorded in repo** — confirm on live instance/account |

Do not invent `ap-northeast-2` or any other region string.

## Does overseas transfer occur?

**Toss platform traffic (confirmed direction):** login token exchange and IAP order
lookup go to `https://apps-in-toss-api.toss.im` (대한민국 사업 토스). That is
platform processing through the Toss app, not a filled “국외 이전 동의” form with
invented foreign entities.

**Company-hosted personal data (userKey rows, audio, analysis, payment rows):**
storage country = Lightsail **instance region**. Until the operator confirms that
region is in Korea (or elsewhere), do not publish a user-facing claim of
「국외 이전 없음」 or fill overseas-transfer consent fields with guessed countries.

## Unconfirmed (OPERATOR_INPUT_REQUIRED)

- Lightsail instance region
- PostgreSQL region (if not co-located)
- Backup region / snapshot location
- Reverse-proxy access-log retention location

## Operator checklist

1. Confirm Lightsail region in the AWS console.
2. If all personal-data stores are Korea-only, document that fact with the region
   evidence and keep privacy policy §6 aligned.
3. If any store is outside Korea, register **개인정보 국외 이전 동의** in Apps in Toss
   login terms and publish: 이전받는 자, 국가, 연락처, 항목, 시점·방법, 목적, 보유기간.
4. Never leave unfinished overseas-transfer placeholders in public legal pages.

Do not invent AWS/Google/Cloudflare legal entity names or countries.
