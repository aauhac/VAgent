# Demucs Lightsail Benchmark

Source: `/var/lib/vocalfb/runtime/7c1c8f5c49964a7e966746714b65c02c/upload.m4a`
Audio duration (ffprobe): 210.389333

## Verdict

- verdict: PASS
- vocals/no_vocals: True/True
- realtime_factor: 7.889463673521889

## Cache

- MODEL_CACHE_HIT: True
- SEPARATION_ARTIFACT_CACHE_HIT stage_b_clip: False
- SEPARATION_ARTIFACT_CACHE_HIT stage_c_full: False
- SEPARATION_ARTIFACT_CACHE_HIT stage_d_mixed_pipeline: True
- note: MODEL_CACHE_HIT is TORCH_HOME htdemucs weights, reused by every stage.
- note: Stage B clip SHA != Stage C full SHA, so Stage C always recomputes full source.
- note: Stage D reuses Stage C full vocals/no_vocals only after source SHA sidecar verification.
- note: This Cache section was added after the warm1 run. Stage D hit is inferred from FUNCTIONAL+MIXED `skip_if_exists` on `recording_id=stage_c_full` after Stage C wrote vocals/no_vocals; Stage B (284.8s) and Stage C (1659.9s) wall times show those stages did not reuse each other's artifacts.

## Stages (summary)

- A_import_model_load: ok=True wall=21.005s max_rss=0.0MB max_swap_used=0.0MB
- B_15_30s_clip_separation: ok=True wall=284.796s max_rss=0.0MB max_swap_used=0.0MB
- C_full_separation: ok=True wall=1659.859s max_rss=0.0MB max_swap_used=0.0MB

## Functional verification (MIXED)
- analysis_quality_status: pass
- analysis_quality_codes: []
- separation_used: True
- separation_status: success
- source_mode: separated
- functional_quality: FULL_MIXED
- vocal_type_resolution_state: RESOLVED
