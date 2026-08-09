# Diagnostic Protocol (`vocal-dx-v1.0`)

Premium Diagnostic Session runs standardized tasks (≈1–2 minutes total).
Each task: **2 attempts**; Quality FAIL retries **that task only**.

## Safety Check (pre-tasks)

Minimal training safety screen (not disease intake). Positive flags → softer coaching, **no** disease inference, **no** physiology score penalty.

## Tasks

### 1. `sustain_a` — Sustained /a/

| | |
|--|--|
| Purpose | Reduce melody influence; observe stable phonation |
| Method | Comfortable pitch, “아—” 4–5s |
| min_sec | 3.0 |
| attempts | 2 |
| Metrics | CPP, HNR, H1−H2 proxy, tilt, residual F0, RMS stability, onset/release, jitter/shimmer if valid |
| Limitation | Not tongue/larynx position imaging |

### 2. `sustain_i` — Vowel contrast /i/

| | |
|--|--|
| Purpose | Phonation/resonance consistency across vowel change |
| Method | Same comfortable pitch, “이—” 4–5s |
| min_sec | 3.0 |
| attempts | 2 |
| Metrics | Same family as sustain_a |
| Limitation | Do not claim tongue/pharynx shape from audio alone |

### 3. `siren`

| | |
|--|--|
| Purpose | Register/F0 continuity, dropout, transition coordination |
| Method | Easy low → comfortable high → down; **no** “sing higher” pressure |
| min_sec | 4.0 |
| attempts | 2 |
| Metrics | F0 continuity, energy continuity, dropout candidates |
| Limitation | Pitch accuracy and max pitch are **not** skill scores |

### 4. `dynamic_swell`

| | |
|--|--|
| Purpose | Breath–phonation–intensity coordination |
| Method | Soft → a bit louder → soft on one comfortable pitch (~5s) |
| min_sec | 3.5 |
| attempts | 2 |
| Metrics | Envelope smoothness, RMS percentiles, F0 displacement during intensity |
| Limitation | Louder ≠ better |

## Optional future: SOVT response

Architecture supports baseline → SOVT → retest acoustic deltas.
Must **not** be described as treatment / disease improvement — only acoustic response to an exercise.

## Session status machine

`CREATED` → `PAID` → `SAFETY_CHECK` / `TASKS_IN_PROGRESS` → `READY_FOR_ANALYSIS` → `ANALYZING` → `COMPLETED` | `FAILED`

Always store `protocol_version = vocal-dx-v1.0`.
