# Apps in Toss console — legal / login config

Do not store secrets here.

Production URLs are composed from `PUBLIC_BACKEND_BASE_URL` after the backend
HTTPS hostname exists (cloud-provided hostname is allowed). Until then, leave
console fields as placeholders. Do not invent a hostname.

`{PUBLIC_BACKEND_BASE_URL}/legal/terms`  
`{PUBLIC_BACKEND_BASE_URL}/legal/privacy`  
`{PUBLIC_BACKEND_BASE_URL}/legal/privacy-consent`

Official sources (2026-08-18):

- [토스 로그인 소개](https://developers-apps-in-toss.toss.im/guide/authentication/intro.md)
- [토스 로그인 API](https://developers-apps-in-toss.toss.im/documentation/common/authentication/toss-login.md)
- [서비스 오픈 정책](https://developers-apps-in-toss.toss.im/intro/guide.md)
- [인앱 결제](https://developers-apps-in-toss.toss.im/guide/monetization/in-app-payment.md)
- [서버 API / CORS](https://developers-apps-in-toss.toss.im/documentation/integration/server-api.md)

## Technical

appName: `vocalfb`

Do not rename `appName`. Deep links and sandbox identifiers stay `vocalfb`.

Live miniapp origin: `https://vocalfb.apps.tossmini.com`  
QR / private test origin: `https://vocalfb.private-apps.tossmini.com`

## User-facing service name

`노래 실력 진단받기`

Matches granite `displayName`.

## User information

name: `필수 동의`

email: `사용 안함`

gender: `사용 안함`

birthday: `사용 안함`

nationality: `사용 안함`

phone: `사용 안함`

CI: `사용 안함`

서버는 login-me에서 **`userKey`만** 사용합니다. 이름은 저장하지 않습니다.

공식 문서상 이름·이메일·성별 **이외** 항목을 켜면 연결 끊기 콜백이 필수입니다. 현재는 이름만 필수입니다. 프로덕션 라이프사이클을 위해 콜백은 구현되어 있습니다.

Apps in Toss 사용자정보 SDK (`getConsentedUserData` / `termsUrl` HTTPS 회사 도메인) 는 **현재 코드에서 호출하지 않음 (`NOT_USED`)**. 나중에 쓰면 `CUSTOM_DOMAIN_REQUIRED_BY_TOSS`.

## Terms

토스가 자동으로 넣는 항목(파트너가 임의 삭제 불가):

- 토스 로그인 **서비스 약관**
- **개인정보 제3자 제공 동의** (토스 → 파트너)

파트너가 직접 등록:

### Service Terms

제목: `노래 실력 진단받기 서비스 이용약관`

URL: `{PUBLIC_BACKEND_BASE_URL}/legal/terms`

권장 약관 유형: 콘솔 예시 **서비스 이용약관**

조건: `필수 동의`

### Personal Information Collection/Use Consent

제목: `개인정보 수집·이용 동의`

URL: `{PUBLIC_BACKEND_BASE_URL}/legal/privacy-consent`

약관 유형: 콘솔 예시 **개인정보 수집·이용 동의**

조건: `필수 동의` — 음성·식별값 처리가 서비스 핵심입니다. 민감정보·14세 여부는 `LEGAL_REVIEW_REQUIRED`.

마케팅 정보 수신 동의: **등록하지 않음** (기능 없음)

국외 이전 동의: 서버 국가 확정 전에는 **등록하지 않음**. `PRODUCTION_HOSTING_DECISION_REQUIRED`.

## Privacy Policy

URL: `{PUBLIC_BACKEND_BASE_URL}/legal/privacy`

앱인토스 로그인 약관 유형 목록에 개인정보처리방침이 별도 항목으로 명시되어 있지 않습니다. 「개인정보 보호법」 제30조에 따라 미니앱 `/legal/privacy`에 게시합니다. 콘솔 약관 목록에 넣을지는 **LEGAL_REVIEW_REQUIRED**.

## Disconnect callback

구현: `POST` 및 `GET` `/v1/auth/toss/disconnect`

콘솔 URL: `{PUBLIC_BACKEND_BASE_URL}/v1/auth/toss/disconnect`

권장 메서드: **POST** (공식 문서의 JSON body: `userKey`, `referrer`)

Basic Auth: 콘솔에 입력. 값은 서버 환경변수 `TOSS_DISCONNECT_BASIC_USER` / `TOSS_DISCONNECT_BASIC_PASSWORD`와 맞출 것. **저장소에 비밀번호를 두지 말 것.**

콜백 동작: 해당 `userKey`의 로그인 세션 폐기. 분석 음성·결제 기록은 삭제하지 않음.

`referrer`: `UNLINK` | `WITHDRAWAL_TERMS` | `WITHDRAWAL_TOSS` (공식 문서)

## Display names

- 사용자-facing: **노래 실력 진단받기**
- `appName`: `vocalfb`
- granite `displayName`: **노래 실력 진단받기**
