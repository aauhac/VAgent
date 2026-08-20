# Demucs Lightsail Benchmark

Source: `/var/lib/vocalfb/runtime/7c1c8f5c49964a7e966746714b65c02c/upload.m4a`
Audio duration (ffprobe): 210.389333

## Verdict

- verdict: FAIL
- vocals/no_vocals: False/False
- realtime_factor: 0.0

## Cache

- MODEL_CACHE_HIT: False
- SEPARATION_ARTIFACT_CACHE_HIT stage_b_clip: False
- SEPARATION_ARTIFACT_CACHE_HIT stage_c_full: False
- SEPARATION_ARTIFACT_CACHE_HIT stage_d_mixed_pipeline: False
- note: MODEL_CACHE_HIT is TORCH_HOME htdemucs weights, reused by every stage.
- note: coldA ran `--max-stage A` only, so it downloaded htdemucs weights and did not produce separation artifacts.

## Stages (summary)

- A_import_model_load: ok=True wall=23.603s max_rss=0.0MB max_swap_used=0.0MB
- B_15_30s_clip_separation: ok=False wall=0.0s max_rss=0.0MB max_swap_used=0.0MB
  - error: skipped_by_max_stage
- C_full_separation: ok=False wall=0.0s max_rss=0.0MB max_swap_used=0.0MB
  - error: skipped_by_max_stage

## Functional verification (MIXED)
- error: None
