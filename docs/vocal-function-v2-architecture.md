# Vocal Function Engine v2 — Architecture

Five layers (never mixed):

1. DIRECT ACOUSTIC OBSERVATIONS  
2. GLOTTAL-SOURCE / VOCAL-TRACT PROXIES  
3. FUNCTIONAL_STATE_ESTIMATE (not ANATOMY_ESTIMATE)  
4. TECHNIQUE / CONTROL CHARACTERIZATION  
5. COACHING DECISION  

Packages:

- `audio_analyzer/vocal_function/` — fusion, report, evidence graph  
- `audio_analyzer/glottal_source/` — IAIF proxy + estimated_naq / estimated_oq_proxy / …  
- `audio_analyzer/vocal_tract/` — formants + descriptive timbre  
- `audio_analyzer/coaching/` — exercise registry + pre/post response  

Versions:

- FUNCTION_ENGINE_VERSION = `vocal-function-v2.0`  
- REPORT_VERSION = `vocal-coach-report-v2.0`  

Measurement mode: `AUDIO_ONLY` (future: `AUDIO_PLUS_EGG`).

Performance v3 and Vocal Quality v1 remain available as supplements / prior layer.
