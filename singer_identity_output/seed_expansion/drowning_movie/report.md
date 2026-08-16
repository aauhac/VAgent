# Drowning / Movie Singer Expansion

Confirmed same-singer seeds:
- drowning.m4a (`5fdfa9eb73e5`)
- movie.m4a (`6fb8c8208c80`)

Seed pair similarity (audio-level): **0.6488**
Seed segment-level median: **0.5298211574554443**
Known-control same-singer mean (person_controlled_v1): **0.6435**

Current clusters:
- drowning → `speaker_009`
- movie → `speaker_009`
- Same cluster: **YES**

Total searched: **71**
- HIGH: 9
- MEDIUM: 5
- CONFLICT: 1
- LOW: 56
- UNRESOLVED: 0

> HIGH_CANDIDATE is **MODEL_CANDIDATE only** until human confirmation.

## 같은 사람일 가능성이 높은 음원 (HIGH)

| 음원 | Drowning | Movie | Prototype | min_seed | Segment Support | 현재 Cluster | status |
|---|---:|---:|---:|---:|---:|---|---|
| 거의동116.m4a | 0.860 | 0.726 | 0.873 | 0.726 | 0.708 | speaker_009 | HIGH_CANDIDATE |
| 요즘 바쁜가봐.m4a | 0.822 | 0.738 | 0.859 | 0.738 | 0.875 | speaker_009 | HIGH_CANDIDATE |
| 좋은사람.m4a | 0.783 | 0.739 | 0.838 | 0.739 | 0.583 | speaker_009 | HIGH_CANDIDATE |
| 거의동115.m4a | 0.749 | 0.746 | 0.823 | 0.746 | 0.542 | speaker_009 | HIGH_CANDIDATE |
| bluemoon.m4a | 0.693 | 0.688 | 0.761 | 0.688 | 0.708 | speaker_009 | HIGH_CANDIDATE |
| 거의동117.m4a | 0.660 | 0.761 | 0.782 | 0.660 | 1.000 | speaker_009 | HIGH_CANDIDATE |
| I'llneverloveagain.m4a | 0.726 | 0.662 | 0.764 | 0.662 | 0.542 | speaker_009 | HIGH_CANDIDATE |
| love again.m4a | 0.643 | 0.714 | 0.747 | 0.643 | 0.625 | speaker_009 | HIGH_CANDIDATE |
| 옥탑방.m4a | 0.617 | 0.746 | 0.751 | 0.617 | 0.708 | speaker_009 | HIGH_CANDIDATE |

## MEDIUM

| 음원 | Drowning | Movie | Prototype | min_seed | Segment Support | Cluster | status |
|---|---:|---:|---:|---:|---:|---|---|
| upload.webm · e8314e2d | 0.499 | 0.514 | 0.558 | 0.499 | 0.667 | speaker_025 | MEDIUM_CANDIDATE |
| upload.webm · 2c9d61eb | 0.496 | 0.521 | 0.560 | 0.496 | 0.500 | speaker_025 | MEDIUM_CANDIDATE |
| 호흡많고헤드.m4a | 0.571 | 0.478 | 0.578 | 0.478 | 0.125 | speaker_006 | MEDIUM_CANDIDATE |
| upload.webm · ee4a74e0 | 0.542 | 0.481 | 0.563 | 0.481 | 0.333 | speaker_004 | MEDIUM_CANDIDATE |
| upload.webm · 5662e809 | 0.526 | 0.464 | 0.545 | 0.464 | 0.250 | speaker_019 | MEDIUM_CANDIDATE |

## CONFLICT

| 음원 | Drowning | Movie | Prototype | min_seed | Segment Support | Cluster | status |
|---|---:|---:|---:|---:|---:|---|---|
| upload.webm · f17b7f4f | 0.606 | 0.391 | 0.549 | 0.391 | 0.000 | speaker_004 | CONFLICT |

## Top 15 by robust score

1. **거의동116.m4a** · cluster `speaker_009` · drowning=0.860 movie=0.726 proto=0.873 min=0.726 gap=0.134 seg=0.708 · **HIGH_CANDIDATE**
2. **요즘 바쁜가봐.m4a** · cluster `speaker_009` · drowning=0.822 movie=0.738 proto=0.859 min=0.738 gap=0.084 seg=0.875 · **HIGH_CANDIDATE**
3. **좋은사람.m4a** · cluster `speaker_009` · drowning=0.783 movie=0.739 proto=0.838 min=0.739 gap=0.044 seg=0.583 · **HIGH_CANDIDATE**
4. **거의동115.m4a** · cluster `speaker_009` · drowning=0.749 movie=0.746 proto=0.823 min=0.746 gap=0.002 seg=0.542 · **HIGH_CANDIDATE**
5. **bluemoon.m4a** · cluster `speaker_009` · drowning=0.693 movie=0.688 proto=0.761 min=0.688 gap=0.005 seg=0.708 · **HIGH_CANDIDATE**
6. **거의동117.m4a** · cluster `speaker_009` · drowning=0.660 movie=0.761 proto=0.782 min=0.660 gap=0.101 seg=1.000 · **HIGH_CANDIDATE**
7. **I'llneverloveagain.m4a** · cluster `speaker_009` · drowning=0.726 movie=0.662 proto=0.764 min=0.662 gap=0.064 seg=0.542 · **HIGH_CANDIDATE**
8. **love again.m4a** · cluster `speaker_009` · drowning=0.643 movie=0.714 proto=0.747 min=0.643 gap=0.071 seg=0.625 · **HIGH_CANDIDATE**
9. **옥탑방.m4a** · cluster `speaker_009` · drowning=0.617 movie=0.746 proto=0.751 min=0.617 gap=0.129 seg=0.708 · **HIGH_CANDIDATE**
10. **upload.webm · e8314e2d** · cluster `speaker_025` · drowning=0.499 movie=0.514 proto=0.558 min=0.499 gap=0.015 seg=0.667 · **MEDIUM_CANDIDATE**
11. **upload.webm · 2c9d61eb** · cluster `speaker_025` · drowning=0.496 movie=0.521 proto=0.560 min=0.496 gap=0.025 seg=0.500 · **MEDIUM_CANDIDATE**
12. **호흡많고헤드.m4a** · cluster `speaker_006` · drowning=0.571 movie=0.478 proto=0.578 min=0.478 gap=0.093 seg=0.125 · **MEDIUM_CANDIDATE**
13. **upload.webm · ee4a74e0** · cluster `speaker_004` · drowning=0.542 movie=0.481 proto=0.563 min=0.481 gap=0.061 seg=0.333 · **MEDIUM_CANDIDATE**
14. **upload.webm · 983379d1** · cluster `speaker_007` · drowning=0.595 movie=0.450 proto=0.575 min=0.450 gap=0.146 seg=0.125 · **LOW_CANDIDATE**
15. **upload.webm · 5662e809** · cluster `speaker_019` · drowning=0.526 movie=0.464 proto=0.545 min=0.464 gap=0.063 seg=0.250 · **MEDIUM_CANDIDATE**

## Consensus nearest neighbors (NN15 drowning ∩ NN15 movie)

- I'llneverloveagain.m4a
- 거의동117.m4a
- 거의동116.m4a
- bluemoon.m4a
- 요즘 바쁜가봐.m4a
- 호흡많고헤드.m4a
- 좋은사람.m4a
- love again.m4a
- 거의동115.m4a
- 옥탑방.m4a
- upload.webm · ee4a74e0

## One-sided matches

Stronger in drowning NN only:

- 목잡이.m4a
- upload.webm · f17b7f4f
- upload.webm · 983379d1
- 기모그.m4a

Stronger in movie NN only:

- upload.webm · e8314e2d
- upload.webm · 2c9d61eb
- upload.webm · d87efe3c
- Lyrics.mp3

## Tuning / Integration

- ECAPA fine-tuned: **NO**
- Cluster threshold changed: **NO**
- VAgent production connected: **NO**
