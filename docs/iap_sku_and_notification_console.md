# IAP SKU / 완료 알림 콘솔 설정

코드는 Console SKU와 template code를 임의로 만들지 않는다.
backend `IAP_*_SKU` 와 Apps in Toss `getProductItemList().sku` 가 일치해야 가격이 표시된다.

## IAP catalog

| product_id | expected/configured SKU | Toss catalog match | displayAmount |
|---|---|---|---|
| song_detail | `IAP_SONG_DETAIL_SKU` | runtime `[IAP] sku_match product=song_detail matched=` | IAP `displayAmount` only |
| diagnostic_full | `IAP_DIAGNOSTIC_FULL_SKU` | runtime `[IAP] sku_match product=diagnostic_full matched=` | IAP `displayAmount` only |
| diagnostic_upgrade | `IAP_DIAGNOSTIC_UPGRADE_SKU` | runtime `[IAP] sku_match product=diagnostic_upgrade matched=` | IAP `displayAmount` only |

Production UI는 `display_amount=None` backend catalog를 가격으로 쓰지 않는다.
하드코딩 `₩990` / `₩1,980` / `—` 금지.

### CONSOLE_CONFIGURATION_REQUIRED

- Toss Console IAP 상품 **노출 ON**
- Console SKU = 서버 `IAP_SONG_DETAIL_SKU` / `IAP_DIAGNOSTIC_FULL_SKU` / `IAP_DIAGNOSTIC_UPGRADE_SKU`
- placeholder `vagent.song_detail` 등을 production SKU로 쓰지 말 것
- 실제 Console SKU를 코드에 넣지 않음 (서버 env로만)

## 분석 완료 알림

Frontend: `VITE_TOSS_ANALYSIS_COMPLETE_TEMPLATE_CODE` (동의 UI `templateCode`)
Backend: `TOSS_ANALYSIS_COMPLETE_TEMPLATE_SET_CODE` (send-message `templateSetCode`)

값이 없으면 CTA는 보이되 클릭 시 사용 불가 안내 / send skip. 앱과 분석은 계속 동작.

### CONSOLE_CONFIGURATION_REQUIRED

기능성 캠페인 템플릿 (구매 유도 문구 금지)

- 제목: `분석 완료`
- 본문: `발성 분석 결과가 준비됐어요.`
- 결과 화면 deep link: Toss Console 링크 기능 확인 후 설정. 미확인 schema는 구현하지 않음.

Recipient:

- 무료 분석 익명: `x-anon-key`
- 검증된 Toss Login: `x-user-key`
- 두 헤더 동시 사용 금지
- anonymous hash ≠ Toss Login userKey

## 리워드 광고 → 상세 리포트 (SONG_DETAIL)

Frontend: `VITE_TOSS_REWARDED_DETAIL_AD_GROUP_ID` (콘솔 광고 그룹 ID)
공식 테스트 ID (비프로덕션만): `ait-ad-test-rewarded-id`

- 보상: 현재 analysis 1건의 SONG_DETAIL만
- 하루 최대 3회 (Asia/Seoul, backend enforce)
- SDK: `loadFullScreenAd` / `showFullScreenAd`, 보상은 `userEarnedReward`만
- 광고 그룹 ID 미발급이면 production CTA 숨김, IAP 유지

### CONSOLE_CONFIGURATION_REQUIRED

1. 리워드 광고 그룹 ID 발급 대기 (구글 반영 후)
2. `VITE_TOSS_REWARDED_DETAIL_AD_GROUP_ID=<발급 ID>` 설정 후 `build:toss`
3. QR 실기기에서 끝까지 시청 → 상세 해금 + remaining 확인
