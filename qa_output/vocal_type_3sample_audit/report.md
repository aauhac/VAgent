# Vocal Type 3-Sample Audit

Generated: 2026-08-18T07:05:15.237330+00:00

## PRODUCTION_ANALYSIS_CONFIG

| key | value |
|---|---|
| analysis_mode | FUNCTIONAL |
| input_mode | VOCAL_ONLY |
| separate | False |
| include_feedback | False |
| sample_rate | 44100 |

Default miniapp upload (no accompaniment): FUNCTIONAL + VOCAL_ONLY + separate=false.

## Comparison

| Metric | 강1(남) | 강2(남) | 박1(여) |
|---|---|---|---|
| Source RMS | -10.81 | -14.24 | -11.17 |
| Analysis RMS | -10.9 | -14.24 | -11.26 |
| Quality | warn | warn | warn |
| Silent ratio | 0.0289 | 0.0106 | 0.004 |
| Voiced ratio | 0.7939 | 0.6507 | 0.6476 |
| F0 mean | 98.09 | 320.96 | 84.0 |
| F0 min/max | 70.1/663.07 | 70.1/911.03 | 70.1/282.03 |
| Usable segments |  |  |  |
| Evidence mass |  |  |  |
| Source families |  |  |  |
| Family agreement |  |  |  |
| Ratio eligible | False | False | False |
| Vocal type | 흉성 쪽 음향 성향이 다소 강한 편 | 흉성 쪽 음향 성향이 더 강한 편 | 흉성 쪽 음향 성향이 더 강한 편 |
| Confidence | medium | medium | medium |
| Root cause | SEGMENT_EXTRACTION_INSUFFICIENT | SEGMENT_EXTRACTION_INSUFFICIENT | SEGMENT_EXTRACTION_INSUFFICIENT |

## 강1 (kang1)

**ROOT CAUSE:** SEGMENT_EXTRACTION_INSUFFICIENT  
**Tags:** EVIDENCE_MASS_INSUFFICIENT, SEGMENT_EXTRACTION_INSUFFICIENT, SOURCE_FAMILY_INSUFFICIENT
- quality: warn
- silent_ratio=0.0 voiced_ratio=0.7939 voiced_duration_sec=35.726
- usable_segments=None evidence_mass=None mean_source_families=None family_agreement=None ratio_eligible=False

## 강2 (kang2)

**ROOT CAUSE:** SEGMENT_EXTRACTION_INSUFFICIENT  
**Tags:** EVIDENCE_MASS_INSUFFICIENT, SEGMENT_EXTRACTION_INSUFFICIENT, SOURCE_FAMILY_INSUFFICIENT
- quality: warn
- silent_ratio=0.0106 voiced_ratio=0.6507 voiced_duration_sec=29.281
- usable_segments=None evidence_mass=None mean_source_families=None family_agreement=None ratio_eligible=False

## 박1 (park1)

**ROOT CAUSE:** SEGMENT_EXTRACTION_INSUFFICIENT  
**Tags:** EVIDENCE_MASS_INSUFFICIENT, SEGMENT_EXTRACTION_INSUFFICIENT, SOURCE_FAMILY_INSUFFICIENT
- quality: warn
- silent_ratio=0.0 voiced_ratio=0.6476 voiced_duration_sec=29.142
- usable_segments=None evidence_mass=None mean_source_families=None family_agreement=None ratio_eligible=False

## COMMON FAILURE POINT

SEGMENT_EXTRACTION_INSUFFICIENT

## SAFE TO FIX NOW

NEED MORE EVIDENCE — audit only, no production code changes applied.
