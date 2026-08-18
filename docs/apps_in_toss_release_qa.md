# Apps in Toss 비게임 출시 QA

수동 `.ait` QR 검증용 체크리스트. 코드만으로 PASS 처리하지 말 것.

결제는 `PAYMENTS_ENABLED=false` 유지. IAP Sandbox는 Toss Login PASS 이후 별도 단계.

## Navigation smoke

- [ ] Home → Record → Toss 뒤로가기 → Home
- [ ] Home → Upload → Toss 뒤로가기 → Home
- [ ] Home → 분석 기록 → 상세 결과 → Toss 뒤로가기
- [ ] Home → 내 변화 보기 → Toss 뒤로가기
- [ ] 앱 최초 화면에서 Toss 뒤로가기 → 미니앱 종료
- [ ] deep-link / app scheme 진입 → Toss 뒤로가기 → 예상 화면 또는 종료
- [ ] 자체 `SubPageHeader` / `뒤로 | 화면명 | 홈` 이 Toss 바와 동시에 보이는 화면 0개
- [ ] modal close, wizard 이전, 녹음 취소, 결제 취소 버튼은 유지

## Home / Login

- [ ] 진입 직후 자동 bottom sheet/modal 없음
- [ ] Home 서비스 설명이 로그인 없이 보임
- [ ] 녹음하기 / 파일 업로드 / 무료 분석은 Toss Login을 강제하지 않음
- [ ] 자체 로그인 UI 없음 (Toss `appLogin`만, 유료·계정 기능 진입 시)
- [ ] 콘솔에 등록한 약관 URL이 로그인/약관 화면에서 열림
- [ ] 유료 진입 중 로그인/약관 닫기 → 이전 화면 유지, 오류 토스트 없음
- [ ] 연결 해제 후 무료 분석은 가능, 유료/계정 기능은 다시 로그인

## Disconnect cleanup (client)

연결 해제 후 아래가 화면에 남지 않아야 함. 서버 음성/분석/결제 원본 삭제는 이 체크가 아님.

- [ ] VAgent session token 없음
- [ ] History / entitlement / 분석 결과 client cache 없음
- [ ] 이전 사용자 기록이 렌더링되지 않음
- [ ] 해제된 session으로 API 호출 시 401 후 로그인 필요 화면으로 이동

## Recording / Upload / Permission

- [ ] 녹음 시작 전 `노래를 분석하려면 마이크 사용 권한이 필요해요.` 안내
- [ ] 권한 거부 시 crash 없음, 무한 permission loop 없음, 파일 업로드 가능
- [ ] 실제 재생되면 `이 브라우저에서는 미리듣기를 지원하지 않아요` 가 뜨지 않음
- [ ] Upload file picker 동작, 지원 포맷만, 30MB 초과 시 이유 표시

## Light mode / viewport

- [ ] 기기 dark mode여도 light UI 유지
- [ ] pinch zoom이 켜지지 않음 (지도가 아닌 서비스)

## Interaction

- [ ] 분석하기 / 파일 업로드 / Toss Login / 상세 리포트 / 정밀 진단 / IAP 시작 시 즉시 loading
- [ ] 중복 클릭으로 분석·결제가 여러 번 생성되지 않음

## IAP (코드 준비, 이번 빌드에서 활성화하지 않음)

- [ ] 결제창 직전 재생 중 오디오 pause, 완료/취소 후 자동 재생 없음
- [ ] UI 가격은 catalog/IAP displayAmount
- [ ] 취소 시 구매 화면 복귀, 실패 시 실패 표시

## Bundle / console

새 `.ait` 는 콘솔 테스트 버전을 자동 갱신하지 않음. 빌드 후 콘솔에 다시 등록해야 함.
