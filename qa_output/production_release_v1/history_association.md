# Diagnostic association audit (Phase 2)

## Root cause (code)

History was **not** joining `diagnostic_sessions.source_analysis_id`.

It only attached a session when `analyses.public_summary.diagnostic_session_id` was set. The real FK / session JSON field `source_analysis_id` was ignored.

A second bug: `GET /v1/history` did not use the HTTP request, so a VAgent Bearer session was ignored and listings fell back to client headers (`demo-user` vs Toss `userKey`). Analyses created after login and diagnostics created on another identity then looked unrelated.

A third bug: the History page dumped **all** `localStorage.vocalfb_sessions` IDs that were not in the current page as “정밀 진단 기록”. That is not a server SoT. Combined with a 50-item page cap, linked sessions whose analysis was off-page looked like orphans.

`upsert_session_from_dict` could null the FK when the analysis row was not yet in Postgres, which would create true DB orphans. The explicit id is now kept in `plan_rationale._session_ext.persisted_source_analysis_id` and restored only when that analysis exists and is owned by the same user.

No date/filename matching is used.

## Local runtime scan (this workspace — test/dev artifacts, not production)

total analyses dirs: 830
total diagnostic session.json: 699
**RESTORED LINKED DIAGNOSTICS: 692**
(existing `source_analysis_id` already persisted; History now reads/joins it. No bulk DB UPDATE/backfill of 692 rows.)

true orphan (no source_analysis_id): 7
ambiguous (would require filename/date guess): 0 — refused
cross-user rejected: verified in tests (other user's session never appears)

source_deleted: 0 in this runtime scan
mock/test fixture: most of the 699 rows are demo-user* / e2e-* local test identities
history_join_bug: **primary** reason the UI looked orphaned
client_local_session_dump: **primary** reason the bottom list was huge
identity_history_ignored_bearer: contributed to user split
legacy_before_source_binding: 7 sessions with no source field

## After fix

- Server history joins `source_analysis_id` (and public_summary pointer if same user).
- Unlinked list is server-owned sessions with no recoverable same-user source.
- Frontend no longer dumps localStorage session IDs as orphans.
- Multiple sessions per analysis: latest COMPLETED is primary; extras collapsed as `이전 진단 N건`.
