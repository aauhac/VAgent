"""
docs/scoring-v3.md
------------------
Song Performance Scoring v3 — hierarchical precision scoring.
"""

# Vocal Score v3.0

**Version:** `vocal-score-v3.0`  
**Calibration:** `uncalibrated` (engineering scale, not clinical)

## Why v3 (score saturation)

v2 mapped single metrics with 2-point helpers:

- `score_lower_is_better`: value ≤ good → **100**
- `score_target_range`: value inside good band → **100**

So “괜찮음” and “매우 뛰어남” collapsed to the same ceiling.  
v3 removes whole-band saturation. High scores require multiple independent submetrics, temporal consistency, acceptable worst segment, coverage, and confidence.

## Hierarchy

```
Raw Metrics
  → Submetrics (piecewise multi-anchor curves)
  → Temporal distribution (median / p25 / p75 / p90 / worst / bad_ratio)
  → Worst-segment + bad-ratio penalties
  → Coverage & confidence ceilings
  → 100-point eligibility gate
  → Axis score
  → Overall (arith + geometric blend + weakest-axis guard)
```

## Axes & submetrics

| Axis | Submetrics |
|------|------------|
| stability | sustain_pitch_stability, sustain_level_stability, region_consistency, unstable_region_ratio, stability_worst_region |
| projection | spectral_projection, presence_prominence, projection_consistency, weak_projection_segment_ratio, projection_worst_segment |
| resonance | weight_balance, mid_resonance_balance, spectral_slope_balance, resonance_consistency, extreme_resonance_ratio, resonance_worst_segment |
| dynamic_control | global_dynamic_range, local_dynamic_variation, smoothness, phrase_consistency, abrupt_change_ratio, dynamic_worst_segment |

Resonance / projection remain **acoustic spectral balance / presence** — not vocal-tract anatomy.

## Score curves

`score_piecewise()` / `score_abs_deviation()` use multi-anchor maps (poor → normal → good → excellent → elite).  
Target-range-flat-100 is **forbidden** in v3.

## Temporal consistency & segments

- Stability: sustained regions  
- Projection / resonance: ~3s spectral windows (when audio available)  
- Dynamic: per-second / window RMS dynamics  

Each axis stores `temporal` stats and optional `segment_scores`.

## Worst segment & bad ratio

`apply_worst_segment_penalty` + `apply_bad_ratio_penalty` (config tables).  
High average cannot keep 100 if a severe weak region exists; isolated vs widespread bad segments are distinguished.

## Coverage & confidence ceilings

Engineering ceilings (not calibration claims):

- coverage &lt; 0.4 → max ~70 (or unknown if confidence fails)
- 0.4–0.6 → max 80  
- 0.6–0.8 → max 90  
- ≥0.8 → up to 100 *if* elite eligibility passes  

Confidence bands similarly cap 75 / 85 / 95 / 100.

Missing submetrics are **not** zero-filled; they reduce coverage/confidence/ceiling.

## 100-point eligibility

All of:

- required submetrics valid and ≥ elite threshold  
- coverage ≥ 0.90  
- confidence ≥ 0.85  
- worst segment ≥ 90  
- bad_segment_ratio ≤ 0.05  
- no severe contradiction  

Otherwise ceiling ≤ 99.

## Overall formula

```
arith = confidence×coverage weighted mean of reliable axes
geo   = weighted geometric mean of reliable axis scores
blend = 0.7*arith + 0.3*geo
overall = (1-0.25)*blend + 0.25*weakest_reliable
```

Then overall coverage/confidence ceilings apply.  
Weakest reliable axis prevents one low axis from being hidden.

## Unknown / partial display

Axis `unknown` does not imply all submetrics unknown.  
Song Detail can show partial submetric rows with `—` where invalid.

## Out of scope

Physiology engine, diagnostic inference, entitlements, ProductCatalog — untouched.
