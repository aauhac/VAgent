# Vocal Physiology Engine

VAgent Premium uses a **Physiology-informed Vocal Assessment** pipeline
(`physiology-inference-v1.1`).

It does **not** diagnose disease, image the larynx, or estimate intrinsic
laryngeal muscle activity (TA/CT/LCA/IA/PCA).

See also: `docs/physiology-evidence-audit.md`, `docs/medical-boundary.md`.

## Pipeline

```
Audio
 → Acoustic Observation (honest proxy metric ids)
 → Metric Validity Gate
 → Evidence Fusion by independent families
 → Rule-registry Physiology Inference
 → Motor Coaching
 → Premium Report (+ scientific_debug)
```

## Metric naming honesty (v1.1)

| metric_id | Status |
|-----------|--------|
| `cepstral_prominence_proxy_db` | Hillenbrand-inspired; **not** Praat CPPS |
| `hnr_ac_proxy_db` | AC HNR idea; **not** Praat-identical |
| `raw_h1_h2_proxy_db` | Uncorrected; **not** H1*-H2* |
| `f0_frame_period_perturbation_proxy_percent` | **not** clinical jitter |
| `amplitude_window_shimmer_proxy_percent` | **not** clinical shimmer |

## Evidence families

`periodicity` (cepstral **and** HNR count as **one** family),
`spectral_source`, `temporal_stability`, `onset`, `release`,
`intensity_coordination`, `register_continuity`.

## Confidence

Internal numeric confidence is an **engineering** value with audio-only caps.
Users see 낮음 / 중간 / 높음 — never “clinical probability”.

## Mechanism audit snapshot (v1.2 product UX)

**Primary cards:** phonation_stability, register_transition_coordination,
intensity_phonation_coordination, phonation_contact_pattern

**Auxiliary:** onset_coordination

**Needs more (not primary):** phonatory_efficiency, release_coordination,
vocal_tract_resonance_balance

Contact pattern requires ≥2 evidence families **and** cross-vowel replication;
confidence label never reaches 높음.
