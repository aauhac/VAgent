# Apps in Toss console — legal / login config

Do not store secrets here.

Production legal HTML is served by the VAgent backend:

`{PUBLIC_BACKEND_BASE_URL}/legal/terms`  
`{PUBLIC_BACKEND_BASE_URL}/legal/privacy`  
`{PUBLIC_BACKEND_BASE_URL}/legal/privacy-consent`  
`{PUBLIC_BACKEND_BASE_URL}/v1/auth/toss/disconnect`

`PUBLIC_BACKEND_BASE_URL` is the live Lightsail (or reverse-proxy) HTTPS origin.
Fill the real hostname in the **Toss console** after it exists. Do not commit secrets.
Until the hostname is set in console, leave console URL fields empty rather than inventing one.

**REQUIRES_TOSS_CONSOLE_ACTION:** paste the three legal URLs + disconnect URL once hostname exists.  
**REQUIRES_OPERATOR_ACTION:** confirm business registration / DPO contact in Apps in Toss partner profile.

Official sources:

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

조건: `필수 동의` — 음성·식별값 처리가 서비스 핵심입니다.

마케팅 정보 수신 동의: **등록하지 않음** (기능 없음)

국외 이전 동의: Lightsail **region 확인 전**에는 등록하지 않음.
Region이 국외로 확인되면 **REQUIRES_TOSS_CONSOLE_ACTION**으로 동의문을 추가한다.
확인되지 않은 국가·법인을 콘솔에 넣지 않는다.

## Privacy Policy

URL: `{PUBLIC_BACKEND_BASE_URL}/legal/privacy`

「개인정보 보호법」 제30조에 따라 미니앱 `/legal/privacy` 및 백엔드 HTML에 게시합니다.
콘솔 약관 목록에 별도 항목으로 넣을지는 운영자가 콘솔 UI를 확인한 뒤 결정합니다
(**REQUIRES_OPERATOR_ACTION**).

## Disconnect callback

구현: `POST` 및 `GET` `/v1/auth/toss/disconnect`

URL: `{PUBLIC_BACKEND_BASE_URL}/v1/auth/toss/disconnect`

Basic Auth: `TOSS_DISCONNECT_BASIC_USER` / `TOSS_DISCONNECT_BASIC_PASSWORD` (host secrets only).
