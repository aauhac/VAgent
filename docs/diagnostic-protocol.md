# Diagnostic Protocol (`diagnostic-protocol-v1.1`)

Adaptive Precision Diagnostic selects **only the standardized tasks needed** to resolve
song-level dimension uncertainty. It is not a fixed 4-task battery.

Planner: `adaptive-dx-planner-v1.1`  
Report: `diagnostic-report-v1.1`

## Product definition

Song Analysis answers: *how do I phonate in this song?*  
Precision Diagnostic answers: *for dimensions the song leaves uncertain, what appears under controlled tasks?*

- Uncertainty ≠ abnormality
- Required tasks may be **zero** when song evidence is already sufficient
- One task may cover multiple unresolved dimensions (set-cover)

## Supported tasks

| task_id | Covers (primary) |
|--|--|
| `sustain_a` | contact, breathiness, stability |
| `sustain_i` | contact, breathiness, resonance |
| `siren` | register |
| `dynamic_swell` | effort, dynamic response |

Each task: **2 attempts**; Quality FAIL retries **that task only**.

## Safety Check (pre-tasks)

Minimal training safety screen (not disease intake). Positive flags → softer coaching, **no** disease inference, **no** physiology score penalty.

## Session fields (additive)

```
source_analysis_id
unresolved_dimensions
selected_tasks
current_task_index
task_results
final_diagnostic_profile
planner_version
protocol_version
```

## Song + task fusion

Song and task results are **both retained**. Conflicts become contextual differences — no blind averaging. Invalid task recordings do not raise confidence.

## Status machine

`CREATED` → `PAID` → `SAFETY_CHECK` / `TASKS_IN_PROGRESS` → `READY_FOR_ANALYSIS` → `ANALYZING` → `COMPLETED` | `FAILED`
