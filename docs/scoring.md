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
- low_noise / rumble (recording quality)
- global pitch_stability_cents
- reference melody / rhythm accuracy

## Calibration

```
SCORE_VERSION = "vocal-score-v2.0"
CALIBRATION_STATUS = "uncalibrated"
```

Thresholds are provisional heuristics pending a reference dataset.
