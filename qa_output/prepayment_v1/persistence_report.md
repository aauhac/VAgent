# Persistence / Restart

## Method
Recreate AnalysisService + DiagnosticSessionService + reset goal store singleton on the same `RUNTIME_DIR` (simulates backend process restart without Docker).

## Results
| Asset | After restart |
|-------|----------------|
| Analysis job | Available |
| Song detail entitlement | Preserved (entitlements.json) |
| User goal | Preserved (voice_identity/user_vocal_goals.json) |
| Diagnostic session | Resume 200 |
| Diagnostic report | GET 200 |
| Unrelated unpaid analysis | Still 402 |

## Postgres
Not exercised this run (Docker unavailable). Existing `tests/api/test_persistence_e2e_audit.py` covers DB-backed paths when DATABASE_URL is set.
