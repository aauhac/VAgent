# International transfer readiness

version: draft-2  
generated: 2026-08-18

## Currently confirmed hosting location

**Not confirmed.** `PRODUCTION_HOSTING_DECISION_REQUIRED`.

Production **may** use a cloud backend (Toss miniapp → HTTPS → FastAPI → PostgreSQL → persistent/object storage). Cloud itself is not a blocker.

Initial production **should prefer a Korea region** for backend, PostgreSQL, audio storage, backup, and logs. That preference is not a confirmed vendor/region.

`docs/PRODUCTION_DEPLOYMENT.md` requires PostgreSQL and a local persistent volume for audio (`LOCAL_PERSISTENT`, single replica) but does not name a cloud provider, region, or legal entity.

## Does overseas transfer occur today?

**Unknown for production.** Do not write 「국외 이전 없음」 until vendor + region are verified.

- Toss login and IAP order lookup go to Toss (대한민국 사업) infrastructure. That is platform processing through the Toss app.
- Browser no longer loads Pretendard from `cdn.jsdelivr.net`. Miniapp uses device system fonts.
- Storage country of `userKey`, audio, analysis, and payment rows is unknown until hosting is chosen.

## Unconfirmed

- Hosting provider / legal entity
- Server country / region
- PostgreSQL region
- Audio storage region
- Backup region
- Logging region

## Before production

1. Choose cloud vendor and Korea (or other) region for every store of personal data.
2. Audit that personal data is not written to a non-Korea region unless an overseas-transfer notice is added.
3. If personal data is stored or processed outside Korea, register **개인정보 국외 이전 동의** in Apps in Toss login terms per [토스 로그인 소개](https://developers-apps-in-toss.toss.im/guide/authentication/intro.md).
4. Fill: 이전받는 자, 국가, 연락처, 항목, 시점·방법, 목적, 보유기간.

Apps in Toss console overseas-transfer placeholders:

- 국가: `[TODO: 이전 국가]`
- 법인명: `[TODO: 이전받는 자]`
- 연락처: `[TODO: 이전받는 자 연락처]`

Do not invent AWS/Google/Cloudflare facts.
