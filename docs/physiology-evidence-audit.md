# Physiology Evidence Audit (hostile)

**Registry version:** `physiology-evidence-2026-08`  
**Inference version:** `physiology-inference-v1.1`  
**Date:** 2026-08

This audit asks whether each inference is scientifically defensible — not whether it sounds professional. Unsupported claims were weakened or removed in code.

## Source count

Approximately **14 primary / methodological sources** were used for rule decisions (Hillenbrand 1994/1996; Heman-Ackah 2002; Boersma 1993; Hanson 1997; Iseli & Alwan 2004; Kreiman et al. 2008; Holmberg et al. 1995; Titze 2006; Butte et al. singing perturbation; Brockmann-Bauser 2021; Saldías CPPS singing 2022; Saldías perturbation in silico 2024; Kuang/JASA H1–H2 2022). Reviews used only for landscape.

Machine-readable: `audio_analyzer/physiology/literature_registry.py`.

---

## Metric matrix

| Metric (new id) | Direct measurement | Supported correlates | Major confounds | Valid task | Strength | Production use |
|---|---|---|---|---|---|---|
| `cepstral_prominence_proxy_db` | Simplified cepstral peak vs trend | Breathiness / harmonic organization (group) | SPL, F0, vowel, mic | sustained | CONDITIONAL | Family: periodicity; not closure geometry |
| `hnr_ac_proxy_db` | Simplified AC harmonicity | Periodicity / noise | Same as above; **not independent of cepstral** | sustained | CONDITIONAL | Same periodicity family |
| `raw_h1_h2_proxy_db` | Raw H1−H2 | OQ / phonation type **only after correction** | Vowel/F1, sex, register, SPL | sustained | WEAK | Spectral family only; never alone |
| `spectral_tilt_db_per_oct` | Broadband slope | Weak phonation-type | Tract, singer’s formant, mic | sustained | WEAK | Restricted |
| `f0_frame_period_perturbation_proxy_percent` | Frame-F0 period diffs | Local irregularity | Vibrato, F0, tracker | sustain only | WEAK | Renamed; strict validity |
| `amplitude_window_shimmer_proxy_percent` | Fixed-window peaks | Amplitude irregularity | Vibrato, intensity | sustain only | WEAK | Renamed; strict validity |
| `sustained_residual_f0_cents` | Local trend residual | Micro-instability | Tracker noise, soft phonation | sustained | CONDITIONAL | Keep |
| `onset_slope_db_per_sec` | RMS rise | Soft/hard attack (weak) | Level, clipping | sustained | CONDITIONAL | Needs 2nd family |
| `release_drop_db` | Tail energy drop | Offset abruptness (weak) | Task ending style | sustained | WEAK | No directional user claim |
| `envelope_smoothness_index` | Custom log-RMS smoothness | Intensity coordination | Absolute SPL, mic distance | swell | CONDITIONAL | Coordination only — **not abdominal pressure** |
| `f0_continuity_ratio` | Voiced F0 continuity | Transition dropout | Tracker errors, narrow range | siren | CONDITIONAL | No TA/CT claim |

### Implementation honesty

| Old name | Audit | New name / action |
|---|---|---|
| `cpp_db` | Not CPPS/Praat-identical | **RENAME** → `cepstral_prominence_proxy_db` |
| `hnr_ac_db` | Missing Boersma window-AC norm | **RENAME** → `hnr_ac_proxy_db` |
| `h1_h2_db` | Uncorrected; ≠ H1*-H2* | **RENAME** → `raw_h1_h2_proxy_db` |
| `local_jitter_percent` | Not cycle jitter | **RENAME** → `f0_frame_period_perturbation_proxy_percent` |
| `local_shimmer_percent` | Not cycle shimmer | **RENAME** → `amplitude_window_shimmer_proxy_percent` |

---

## Mechanism matrix

| Mechanism | Evidence families | Support | Cap | Allowed claim | Forbidden |
|---|---|---|---|---|---|
| glottal_closure_tendency | periodicity + spectral (+ onset) | CONDITIONAL | 0.72 | breathier / lighter-contact **tendency** | 성대가 벌어짐, LCA 약함 |
| phonatory_efficiency | periodicity only | **WEAK** | 0.40 | none (always unknown) | glottal efficiency fact |
| breath_phonation_coordination | intensity + release/stability | CONDITIONAL | 0.62 | intensity–phonation coordination | 복압 부족 |
| onset_coordination | onset + periodicity | CONDITIONAL | 0.55 | onset energy pattern | glottal attack 확정 |
| release_coordination | release | **WEAK** | 0.48 | observation only | abduction muscle |
| register_transition_coordination | register_continuity | CONDITIONAL | 0.65 | F0 continuity / dropout | TA/CT |
| vocal_tract_resonance_balance | spectral | **WEAK** | 0.50 | none (unknown) | 혀/턱 긴장 확정 |
| phonation_stability | temporal_stability | CONDITIONAL | 0.68 | local residual F0 | pathology |

---

## Evidence families

`periodicity` = cepstral **or** HNR proxy (count once)  
`spectral_source` = raw H1−H2 / tilt  
`temporal_stability` = residual F0 / RMS / perturbation proxies  
`onset` / `release` / `intensity_coordination` / `register_continuity`

---

## Not identifiable from audio

See `NOT_IDENTIFIABLE_FROM_AUDIO` in `knowledge.py` (lesions, gap geometry, mucosal wave, intrinsic muscle %, true Psub, lung volume, abdominal/diaphragm activation, exact tongue-root/jaw tension, etc.).

---

## Most dangerous prior claims (pre-audit)

1. **CPP low + HNR low → light glottal contact / efficiency** while treating CPP and HNR as two independent sensors.  
2. **Raw H1−H2 as if H1*-H2* / open quotient.**  
3. **Dynamic swell / release → respiratory support / 복압.**  

These are now family-capped, renamed, or suppressed.

---

## Remaining scientific uncertainty

- No calibrated singer norms; absolute bands remain engineering proxies.  
- No formant correction / inverse filtering / EGG.  
- Singing-domain CPPS still fo/SPL confounded (Saldías 2022).  
- Onset/release acoustic→coordination mapping remains thin.
