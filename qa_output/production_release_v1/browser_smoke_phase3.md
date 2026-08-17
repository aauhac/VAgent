# Browser smoke phase 3 — live React Detail / Progress / Precision

QA-only harness: `miniapp/qa-visual.html` + `miniapp/vite.qa-visual.config.ts` (port 5177).  
Not used by `build:web` / `build:toss`. Fixture GET mocks only; no mock-unlock of paid APIs.

Viewports: **375×812** (required), 390×844, 430×932 (additional).  
New screenshots only (phase 2 Home/Record/Upload/History CSS fixtures were not overwritten).

Evidence: `qa_output/production_release_v1/browser_smoke/screenshots/`

| Page | 375×812 | Extra | Notes |
|---|---|---|---|
| Detail (`SongDetailReport`) | PASS `react-detail-375x812.png` | 390/430 + `react-detail-fullpage-375.png` + `react-detail-cta-375.png` | `‹ 무료 결과` (not SubPageHeader). Profile bars, 흉성 58%, sticky audio, accordion “더 자세히”, CTA `정밀 발성 진단 · ₩2,200` (upgrade because Detail already owned). |
| Diagnostic Progress (`DiagnosticTask`) | PASS `react-diag-task-375x812.png` | 390/430 | `정밀 진단 · 1 / 2`, long Korean instruction, `녹음 시작` unclipped. No SubPageHeader (pre-existing inner-page header). |
| Progress Insight (`/progress`) | PASS `react-progress-375x812.png` | 390/430 | SubPageHeader `‹ 뒤로` / 내 변화 / `홈`. Cards wrap. |
| Precision report (`PremiumReport`) | PASS `react-precision-375x812.png` | 390/430 + `react-precision-fullpage-375.png` | `‹ 홈` + 상세 리포트로 돌아가기. Profile bars, accordion rows, disclaimer, bottom CTAs unclipped. |
| History linked diagnostic | PASS `react-history-linked-375x812.png` | 390/430 | Filename wraps; `정밀 발성 진단 · 완료` / `보기` on the source analysis card; `‹ 뒤로` / `홈`. |

DOM dumps (no secrets): `detail_dom.html`, `history_dom.html`, `progress_dom.html`, `precision_dom.html`.

## Checklist (375×812, actual React)

| Item | Result |
|---|---|
| header | PASS (Detail/Precision custom links; Progress/History SubPageHeader) |
| back/home navigation | PASS on Progress/History (`‹ 뒤로` + `홈`). Detail: `‹ 무료 결과`. Precision: `‹ 홈`. Diagnostic task: progress kicker only (existing P3). |
| CTA clipping | PASS (`녹음 시작`, `목표 정하기`, precision purchase CTA, precision bottom buttons) |
| long Korean text wrapping | PASS (filename wrap on History; instruction blocks) |
| product price | PASS `₩2,200` on Detail DiagnosticCTA (`diagnostic_upgrade`) |
| profile bars | PASS |
| accordion | PASS (“더 자세히” / precision “더 살펴보기” rows present) |
| audio controls | PASS (sticky player on Detail) |
| bottom spacing / safe-area | PASS |
| purchase status message | N/A on these fixtures (already-unlocked Detail; no live IAP) |
| diagnostic progress | PASS `1 / 2` |
| History return + linked diagnostic | PASS `정밀 발성 진단 · 완료` + `보기` |

## DID FULL 375×812 PRODUCT VISUAL SMOKE PASS?

**YES**

This does **not** replace Apps in Toss WebView QA. Toss live/sandbox remains NOT_RUN.
