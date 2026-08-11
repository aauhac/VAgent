# Vocal Function Engine v2.6 — Architecture

Layers + Coach Profile:

1. OBSERVATIONS → 2. SOURCE PROXIES → 3. FUNCTIONAL STATE → 4. EPISODES → 5. COACHING → 6. VOCAL TYPE v1.2

## v1.2 highlights

- Signed family votes (−1 chest … +1 head)
- Absolute vs relative baselines (no self-normalize when variance=0)
- CONTACT supporting-only
- Breathiness/roughness reliability gates (no auto-head)
- `global_ratio_directionality` vs `segment_directionality_*`
- Global type vs `local_register_events` (CHEST_PULL never renames global type)
- `REGISTER_SPLIT_GLOBAL` requires transition-opportunity prevalence

Versions: `vocal-function-v2.6` / `vocal-coach-report-v2.6` / `vocal-type-v1.2`
