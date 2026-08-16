# Confirmed Singer Profile v2

Singer: **person_drowning_movie**

Human-confirmed recordings: **8**

1. drowning.m4a (`5fdfa9eb73e5`) · cluster `speaker_009`
2. movie.m4a (`6fb8c8208c80`) · cluster `speaker_009`
3. 거의동115.m4a (`d5045bc290a1`) · cluster `speaker_009`
4. 거의동116.m4a (`3ced1f723c5e`) · cluster `speaker_009`
5. 거의동117.m4a (`1387ae324719`) · cluster `speaker_009`
6. 좋은사람.m4a (`a7c957603751`) · cluster `speaker_009`
7. 요즘 바쁜가봐.m4a (`8156c1254947`) · cluster `speaker_009`
8. bluemoon.m4a (`5e7819c3abb4`) · cluster `speaker_009`

## Identity profile

- Centroid: L2-normalized mean of 8 cached ECAPA embeddings (dim=192)
- Medoid: **요즘 바쁜가봐.m4a**
- Within-singer mean/median/min/max: 0.7473 / 0.7474 / 0.5876 / 0.8596
- Hardest pair: 거의동117.m4a ↔ bluemoon.m4a (0.5876)

## Leave-One-Song-Out

- MATCH: 8/8 · UNCERTAIN: 0/8 · NON_MATCH: 0/8
- Rank-1 recognition: 4/8
- LOO mean similarity: 0.8446
- LOO min similarity: 0.7785

## 2-seed frozen baseline retrieval (known 6 confirmed)

- Seed pair: 0.6488
- Recall@3: 0.500
- Recall@5: 0.833
- Recall@10: 1.000
- Recall@15: 1.000

## Enrollment-size robustness

- More enrollment improves robustness: **YES**

> Do not claim absolute improvement beyond comparable metrics (LOO / enrollment curve).

## Remaining 65 rediscovery

- CONSISTENT_HIGH: 2
- STYLE_SPECIFIC: 0
- BORDERLINE: 2
- CONFLICT: 1
- LOW: 60

## Safety

- Profile contains only USER_CONFIRMED recordings
- I'llneverloveagain / love again / 옥탑방 remain unconfirmed
- ECAPA fine-tuned: NO · thresholds retuned: NO · VAgent production: NO
