# Vocal Function Engine v2.2 — Architecture

Five layers (never mixed):

1. DIRECT ACOUSTIC OBSERVATIONS  
2. GLOTTAL-SOURCE / VOCAL-TRACT PROXIES  
3. FUNCTIONAL_STATE_ESTIMATE (not ANATOMY_ESTIMATE)  
4. TECHNIQUE / CONTROL CHARACTERIZATION  
5. COACHING DECISION  

## analysis_mode vs input_mode (independent)

| analysis_mode | meaning |
|---------------|---------|
| QUICK | free lightweight analysis |
| FUNCTIONAL | Song Detail / Functional Vocal Coach |
| DIAGNOSTIC | diagnostic protocol path |

| input_mode | meaning |
|------------|---------|
| AUTO / MIXED | try Demucs; vocals + no_vocals contrast |
| VOCAL_ONLY | skip Demucs; raw treated as vocal (still FUNCTIONAL) |

Functional quality:

- **FULL_MIXED** — separated + no_vocals  
- **FULL_VOCAL_ONLY** — VOCAL_ONLY with usable vocal evidence (missing no_vocals is OK)  
- **LIMITED** / **UNAVAILABLE** — restricted coaching  

Episode contexts use **true PRE / DURING / POST** segments outside the episode span.  
Primary bottlenecks require medium+ confidence, supporting_episode_ids, and a playable target.

Versions: `vocal-function-v2.2` / `vocal-coach-report-v2.2`  

This is engineering validity / localization — **not** human-coach validated accuracy.
