# Legal pages visual smoke (375×812)

Date: 2026-08-17  
Harness: `miniapp` QA Vite `http://127.0.0.1:5177/qa-visual.html#/legal/...`  
Viewport: 375×812 (plus tall captures for tables)

## Screenshots

| Page | File |
| --- | --- |
| Terms | `browser_smoke/screenshots/legal-terms-375x812.png` |
| Terms (tall) | `browser_smoke/screenshots/legal-terms-fullpage-375.png` |
| Privacy | `browser_smoke/screenshots/legal-privacy-375x812.png` |
| Privacy (table) | `browser_smoke/screenshots/legal-privacy-table-375.png` |
| Consent | `browser_smoke/screenshots/legal-privacy-consent-375x812.png` |

## Checks

| Check | Result |
| --- | --- |
| Title / 조항 번호 / spacing | PASS |
| Semantic headings (h1 document, h2 articles) | PASS |
| Light/minimal UI (not dark-only) | PASS |
| Tables: horizontal scroll wrapper, no page-break overflow | PASS |
| Long Toss URL wrap (`overflow-wrap: anywhere`) | PASS (terms 환불 조항) |
| Footer / Home legal links | PASS (이용약관, 개인정보처리방침). Home does not restore medical disclaimer |
| `[TODO: 사업자명]` not rendered as a hyperlink | PASS (space before 이하; renderer https-only) |
| Placeholders visible | PASS — expected until business facts filled |
| Secrets / env names | PASS — none in DOM |
| Login/payment API calls on open | PASS — static markdown |
| Safe-area padding | PASS — `env(safe-area-inset-*)` on legal page / backend HTML |

## Notes

- These captures do **not** overwrite prior `home-*` / `react-detail-*` screenshots.
- `LEGAL_RELEASE_APPROVED` remains NO because `[TODO: …]` placeholders are user-visible by design.
