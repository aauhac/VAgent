# Legal pages visual smoke (375×812)

Date: 2026-08-20  
Harness: FastAPI `/legal/*` + miniapp embedded markdown (synced from `docs/legal`)  
Viewport: 375×812 (prior screenshot paths retained; re-capture recommended after copy change)

## Screenshots

| Page | File |
| --- | --- |
| Terms | `browser_smoke/screenshots/legal-terms-375x812.png` |
| Terms (tall) | `browser_smoke/screenshots/legal-terms-fullpage-375.png` |
| Privacy | `browser_smoke/screenshots/legal-privacy-375x812.png` |
| Privacy (table) | `browser_smoke/screenshots/legal-privacy-table-375.png` |
| Consent | `browser_smoke/screenshots/legal-privacy-consent-375x812.png` |

## Checks (code/test evidence 2026-08-20)

| Check | Result |
| --- | --- |
| Public routes `/legal/terms|privacy|privacy-consent` HTTP 200 without auth | PASS (`tests/legal`) |
| text/html + H1 | PASS |
| Release blockers (`[TODO:`, `draft-2`, `*_REQUIRED`) absent from markdown + HTML | PASS |
| Draft “정식 시행이 아님” phrases absent | PASS |
| Secrets / env names | PASS |
| `docs/legal` == `miniapp/src/legal` | PASS |
| Placeholders visible | **FAIL (desired)** — no longer shown |
| Mobile screenshot re-capture after copy change | **NOT_RUN** (REQUIRES_OPERATOR_ACTION) |

## Legal release gate

| Gate | Status |
| --- | --- |
| public routes | PASS |
| no placeholder / draft blockers | PASS |
| no secrets | PASS |
| docs/frontend sync | PASS |
| mobile rendering re-smoke | NOT_RUN |
| Operator business registration fields in repo | PASS — 프랙토컬 / 강민혁 / 453-09-03373 in public legal |
| Seoul Lightsail region + same-host DB/audio/logs | PASS — see `PRODUCTION_REGION_CHECKLIST.md` |
| Toss console raw-IP legal/disconnect registration | REQUIRES_TOSS_CONSOLE_CONFIRMATION |
| mobile rendering re-smoke | NOT_RUN |
| `LEGAL_RELEASE_APPROVED` | **NO** until Toss console confirmation + mobile smoke |

Do not mark `LEGAL_RELEASE_APPROVED=YES` while Toss console registration and mobile smoke remain open.
Backup (Lightsail Automatic snapshots OFF) is a separate ops task, not a legal-copy blocker.
