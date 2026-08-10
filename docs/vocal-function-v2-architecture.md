# Vocal Function Engine v2.1 — Architecture

Five layers (never mixed):

1. DIRECT ACOUSTIC OBSERVATIONS  
2. GLOTTAL-SOURCE / VOCAL-TRACT PROXIES  
3. FUNCTIONAL_STATE_ESTIMATE (not ANATOMY_ESTIMATE)  
4. TECHNIQUE / CONTROL CHARACTERIZATION  
5. COACHING DECISION  

## Separation policy (product)

| Path | Mode | Separation |
|------|------|------------|
| FREE Quick Analysis | `QUICK` | raw allowed |
| Song Detail / Functional Vocal Coach | `FUNCTIONAL` | **required** (backend forces `separate=True`) |
| Diagnostic | `DIAGNOSTIC` | caller / existing policy |

Functional Coach quality levels:

- **FULL** — separated + `no_vocals` contrast available  
- **LIMITED** — separation partial / no-vocals missing / QUICK raw  
- **UNAVAILABLE** — FUNCTIONAL requested but separation failed (do not trust raw mix for coaching)

Long-song clips apply the **same** original-time window to vocals and no_vocals (`slice_aligned_stems`).  
Events expose `local_*` (analysis clip) and `original_*` (file / preview seek).

Packages:

- `audio_analyzer/vocal_function/` — fusion, report, evidence graph, alignment  
- `audio_analyzer/glottal_source/` — IAIF proxy + estimated_naq / estimated_oq_proxy / estimated_mfdr_norm_proxy  
- `audio_analyzer/vocal_tract/` — formants + descriptive timbre  
- `audio_analyzer/coaching/` — bottleneck + exercise registry  

Versions:

- FUNCTION_ENGINE_VERSION = `vocal-function-v2.1`  
- REPORT_VERSION = `vocal-coach-report-v2.1`  

Measurement mode: `AUDIO_ONLY` (future: `AUDIO_PLUS_EGG`).

Performance v3 and Vocal Quality v1 remain available as supplements / prior layer.
