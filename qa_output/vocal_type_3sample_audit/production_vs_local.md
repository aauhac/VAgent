# Production vs Local Runtime Comparison

Generated: 2026-08-18T07:11:08.350172+00:00

## Local fingerprint

- git HEAD: `cecbb894a05babe02d62332b1afd9ca93cf0b66f`
- packaged release HEAD: `﻿40407e77467298523bf9ce1e8d5832825df2d1dc`
- deploy lag vs local HEAD: `True`
- coach profile: `vocal-type-v1.4`

### AIT (local latest build)

- path: `C:\VocalAgent\miniapp\vocalfb.ait`
- size: 3885902
- last_write: 2026-08-18T06:23:20.634435+00:00
- sha256: `ed4355fdcf22a354d77aaa3efcb9c7318039827df463c13e4d1868c9de5efb96`

**MANUAL_CONFIRMATION_REQUIRED: LATEST_AIT_REGISTERED**

Apps in Toss Console 테스트 버전에 위 .ait가 등록됐는지 사람이 확인해야 합니다.

## Root cause hypotheses

Fill after production analysis_ids are provided.

| hypothesis | status |
|---|---|
| PRODUCTION_DEPLOY_LAG | PENDING — compare git HEAD vs packaged HEAD |
| STALE_AIT_BUNDLE | PENDING — MANUAL_CONFIRMATION_REQUIRED |
| FRONTEND_CONFIG_MISMATCH | check input_mode / separation_used |
| UPLOAD_CONTENT_MISMATCH | check content_sha256 |
| female calibration | REJECTED — not in scope |
| evidence threshold change | REJECTED — audit only |

