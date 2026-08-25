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

## 분석 완료 알림 (Smart Message)

세 값을 혼동하지 않는다.

| 역할 | env / source | Toss API field |
|---|---|---|
| 프론트 동의 UI | `VITE_TOSS_ANALYSIS_COMPLETE_TEMPLATE_CODE` (miniapp build-time) | `requestNotificationAgreement` → `templateCode` |
| 백엔드 발송 템플릿 | `TOSS_ANALYSIS_COMPLETE_TEMPLATE_SET_CODE` (server runtime) | send-message body → `templateSetCode` |

운영 발송에 필요한 서버 설정은 `TOSS_ANALYSIS_COMPLETE_TEMPLATE_SET_CODE` **하나**다.

`deploymentId`는 Apps in Toss Console > **앱 출시**에서 업로드한 bundle(AIT) 식별값으로,
`POST /api-partner/v1/apps-in-toss/messenger/send-test-message`에서 대상 번들을 지정할 때만 쓴다.
운영 `POST /api-partner/v1/apps-in-toss/messenger/send-message`는 `deploymentId`를 받지 않으며,
현재 VAgent live 발송 경로의 필수 설정이 **아니다**. (server-side test-message 기능은 구현하지 않음)

Recipient header (send-message):

- 무료 분석 익명: `x-anon-key`
- 검증된 Toss Login: `x-toss-user-key` (not `x-user-key`)
- 두 recipient header **동시 사용 금지**
- anonymous hash ≠ Toss Login userKey

Send body:

```json
{
  "templateSetCode": "<configured>",
  "context": {}
}
```

`templateSetCode`가 없으면 Toss API를 호출하지 않는다.
REQUESTED record는 유지 가능하나 SENT로 표시하면 안 된다.

Production miniapp build: `VITE_TOSS_ANALYSIS_COMPLETE_TEMPLATE_CODE`가 없으면 `build:web` / `build:toss` FAIL.

### Release sequence (notification + AIT)

1. Console 기능성 캠페인 **templateCode** → `miniapp/.env.production.local` (gitignored)
2. `npm --prefix miniapp run build:web` → `npm --prefix miniapp run build:toss`
3. 새 `vocalfb.ait`를 Apps in Toss Console에 업로드
4. Lightsail server env에 `TOSS_ANALYSIS_COMPLETE_TEMPLATE_SET_CODE=<templateSetCode>` 설정/확인
5. backend recreate/restart
6. Console 완료 알림 **이동 URL**을 `intoss://vocalfb/notification-result`로 설정
7. 실기기: 알림 동의 → 분석 완료 → Toss 알림 수신 → 알림 탭 → 결과 화면 진입 확인

AIT 업로드/`deploymentId` 확인은 live 알림 발송의 선행 조건이 아니다.

### CONSOLE_CONFIGURATION_REQUIRED

기능성 캠페인 템플릿 (구매 유도 문구 금지)

- 제목: `분석 완료`
- 본문: `발성 분석 결과가 준비됐어요.`
- 이동 URL: `intoss://vocalfb/notification-result`

#### 완료 알림 이동 URL

```
intoss://vocalfb/notification-result
```

Apps in Toss는 `intoss://<appName>/<path>` 형태의 내부 deep link를 지원한다.
이 URL에 `deploymentId`를 넣지 않는다. 출시 전 QR/deployment 테스트 scheme과
production `intoss` scheme을 혼동하지 않는다.

동작:

```
완료 알림 클릭
  → miniapp /notification-result
  → 현재 request가 제시한 identity(verified Toss session / anonymous 헤더)로 scope 제한
  → GET /v1/notifications/latest-result
  → 가장 최근 "열 수 있는" SENT completion notification resolve
  → /result/<analysisId>
  → 없으면 /history   (Home으로 보내지 않는다)
```

resolve 조건: `status == SENT` AND `sent_at IS NOT NULL`, `sent_at DESC`.
`REQUESTED` / `FAILED`는 제외한다. 최신 건이 삭제된 분석이면 다음 후보를 검사한다.
recipient 일치만으로 반환하지 않고 기존 `can_access_analysis` 게이트를 그대로 통과해야 한다.

**한계 (의도된 것):** Smart Message 캠페인 이동 URL은 **고정**이라 클릭마다
`analysis_id`를 URL에 동적으로 넣는 계약이 공식 확인되지 않았다. 따라서 resolver는
"가장 최근에 열 수 있는 SENT 알림"을 연다. 방금 받은 알림을 누르는 일반적인 경우는
정확히 해당 분석으로 이동하지만, 아주 오래된 알림을 나중에 누르면 그 사이 발송된
더 최신 분석으로 갈 수 있다. 공식 dynamic click parameter가 확인되기 전까지
임의 query interpolation은 구현하지 않는다.

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
