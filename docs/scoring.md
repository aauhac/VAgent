# Scoring v2

## Why global pitch variance was removed

Songs naturally change notes:

`C4 → E4 → G4 → C5`

Even a perfectly stable singer will show **large global F0 variance**.

Therefore:

> **melody variation ≠ vocal instability**

The legacy metric `pitch_stability_cents` (std of cents vs whole-song mean F0) is kept only as **legacy/debug** and is **never** used for:

- user score
- issue detection
- strength generation
- timeline events

## Local sustained-note stability

`features/phonation.py` detects sustained regions (≥ ~0.5s) with small frame-to-frame jumps, removes **local** trend inside each region, then measures residual fluctuation in cents.

Only residual instability inside sustained notes can create `phonation_instability` timeline events.

## Four user axes

| area_id | display | primary metrics |
|---------|---------|-----------------|
| stability | 발성 안정성 | median residual std cents from sustained regions |
| projection | 목소리 전달력 | SPR, singer-formant prominence (not ASR lyrics) |
| resonance | 공명 균형 | weight_gap, mouth_gap, spectral slope |
| dynamic_control | 강약 컨트롤 | dynamic_range_db as **target range** (not higher-is-better) |

## Explicitly excluded from skill score

- vibrato (optional analysis only)
- low_noise / rumble (recording quality; `RUMBLE` code does not lower skill confidence)
- global pitch_stability_cents
- reference melody / rhythm accuracy

## Metric completeness → confidence

Projection expects 2 metrics (SPR, singer-formant prominence).  
Resonance expects 3 metrics (weight_gap, mouth_gap, spectral slope).

Missing metrics reduce confidence via `PROJECTION_COMPLETENESS_CONF` /
`RESONANCE_COMPLETENESS_CONF` rather than quietly pretending full reliability.

## RMS variation (robust)

Within each sustained region, level variation uses **90th / 20th percentile RMS**
(not max/min). A single near-silent edge frame must not inflate `rms_variation_db`.

## Demucs artifact flags

`demucs_high_band_loss_likely` is evaluated **only** when `source_mode == "separated"`.
A naturally dark RAW recording is not treated as a Demucs artifact.

## Calibration

```
SCORE_VERSION = "vocal-score-v2.0"
CALIBRATION_STATUS = "uncalibrated"
```

Thresholds are provisional heuristics pending a reference dataset.
Do not retune from a handful of anecdotal samples.
