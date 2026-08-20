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
| Operator business registration fields in repo | OPERATOR_INPUT_REQUIRED |
| `LEGAL_RELEASE_APPROVED` | **NO** until operator business/DPO registration details are confirmed and mobile smoke re-run |

Do not mark `LEGAL_RELEASE_APPROVED=YES` while operator legal-entity fields remain outside the repo and mobile smoke is not re-run.
