# Browser smoke phase 2

CSS fixtures using production `app.css` + Chrome headless screenshots.

Viewports: 375×812, 390×844, 430×932

Evidence: `qa_output/production_release_v1/browser_smoke/screenshots/`

| Page | 375×812 | Notes |
|---|---|---|
| Home | PASS | No logo/VAgent box, compact compare rows, no trust note, no medical footer |
| Record | PASS | ‹ 뒤로 / 녹음 / 홈 |
| Upload | PASS | ‹ 뒤로 / 파일 업로드 / 홈 |
| History collapsed | PASS | Date groups, filename title, separated actions, linked precision sub-row, collapsed `이전 정밀 진단 7건` |
| History expanded | PASS | Legacy section expands without repeating “이전에 진행한 진단” |

Live React session (Result / Detail / Progress / Precision with real data): **NOT_RUN** (no authenticated miniapp session in this pass).

This does **not** replace Apps in Toss WebView QA.
