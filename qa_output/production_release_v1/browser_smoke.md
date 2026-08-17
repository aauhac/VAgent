# Browser smoke

Visual device pass (375×812 / 390×844) was **not** executed in this run (no Playwright config / no interactive Apps in Toss WebView).

Source-contract tests (`tests/product/test_home_history_ux.py`) PASS:

- Home logo removed
- New product copy
- Compact compare rows
- Trust note removed
- Home medical footer removed
- Record/Upload/History SubPageHeader
- History raw session IDs gone

Pages covered by implementation: Home, Record, Upload, History, Result (header). Detail / Progress / Precision were not visually re-shot.

Status: SOURCE_PASS / VISUAL_NOT_RUN
