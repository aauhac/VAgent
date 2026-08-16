# Singer Identity Engine — Batch Report

## Overview

- Qualifying audio: 73
- Embedding success: 73
- Failures: 0
- Usable segments (used/total): 478/541
- Encoder: `speechbrain_ecapa_tdnn`
- Model version: `speechbrain-spkrec-ecapa-voxceleb-v1`
- Embedding dim: 192

## Architecture

- Singer Identity = **WHO is singing**
- VAgent Vocal Analyzer = **HOW they are singing**
- Production VAgent integration: **NOT connected**
- Integration gate: **INSUFFICIENT_DATA** (min_speakers, heldout, identification, unknown_rejection)

## Clustering

- Method: agglomerative (cosine distance), no fixed K
- Estimated singer clusters: **25**
- Unresolved: **0**
- Largest cluster: 16
- Smallest cluster: 1
- Mean within-cluster similarity: 0.8225
- Mean nearest between-cluster similarity: 0.6045
- Mean separation: 0.2180

## Known same-singer

- Groups: ['person_controlled_v1']
- Same-singer mean similarity: 0.6435272097587585
- Different reference mean: 0.3744155492458958
- Pair scores: {"54b972ad↔00ae450b": 0.6280401945114136, "54b972ad↔99023e55": 0.7446818351745605, "54b972ad↔10d07cc4": 0.67505943775177, "00ae450b↔99023e55": 0.5738906860351562, "00ae450b↔10d07cc4": 0.6950215101242065, "99023e55↔10d07cc4": 0.5444695949554443}

## Identification

- Status: INSUFFICIENT_SPEAKER_LABELS
- Top-1: None
- Top-3: None

## Verification

- Status: OK
- EER: 0.06944444444444445
- ROC-AUC: 0.9106481481481481
- Same mean: 0.6435272097587585
- Diff mean: 0.346707477419275

## Unknown rejection

- Status: INSUFFICIENT_DATA
- {"status": "INSUFFICIENT_DATA"}

## Fine-tuning

- Ran: NO
- Reason: baseline Stage-0 only; labels insufficient for safe fine-tune / or deferred

## Privacy

- Named enrollment requires `consented_enrollment=true`
- Raw embeddings not exposed on public GET singer endpoints
