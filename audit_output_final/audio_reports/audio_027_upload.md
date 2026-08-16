# Audio 027 — upload.wav

**Audit status:** `REVIEW`  
**Audio id:** `7b8c45cdd16b`

## 기본 정보

- 파일: `C:\VocalAgent\runtime\0cc29f91aee74ab29f02519e3b381df5\upload.wav`
- SHA: `7b8c45cdd16b1f9e08bbf2d6391f364f9bdd303ac58a1f78baa457df76d4f322`
- 길이: None
- Sample Rate: None
- Analysis status: OK
- Source: fresh
- Analysis version: —

## 이 음원에서 분석된 발성 특징

| 축 | 상태 | 신뢰도 | 설명 |
|---|---|---|---|
| 힘 사용 | UNKNOWN | low | 이번 녹음에서 단정하기 어려움 |
| 접촉감 | UNKNOWN | — | 이번 녹음에서 단정하기 어려움 |
| 숨 섞임 | UNKNOWN | — | 이번 녹음에서 단정하기 어려움 |
| 성구 연결 | PARTIAL | — | 성구 연결이 부분적으로만 이어짐 |
| 흉성/두성 음향 성향 | UNKNOWN | — | 이번 녹음에서 단정하기 어려움 |
| 안정성 | STABLE | — | 안정성이 유지되는 편 |
| 중역 존재감 | LOW | — | 중역 존재감이 낮은 편 |
| 밝기 | LOW | — | 밝기가 어두운 편 |
| 음색의 공기감 | UNAVAILABLE | — | 이번 녹음에서 단정하기 어려움 |
| 질감 | UNKNOWN | — | 이번 녹음에서 단정하기 어려움 |
| 배음 집중 | UNKNOWN | — | 이번 녹음에서 단정하기 어려움 |
| 음색 일관성 | UNKNOWN | — | — |
| 고음 분석 | UNAVAILABLE | — | 고음 직접 분석 지표가 제한적 |

## 한 줄 평가

성구 연결이 일부 구간에서만 안정적으로 이어지는이지만, 발성 안정성이 유지되는 편인, 중역 존재감이 낮은 편인, 밝기가 어두운 편인 발성으로 분석됐어요.

> 이 요약은 concern/target과 무관한 canonical song evidence만 사용합니다.

## 가장 중요한 특징

1. **register_connection** — 성구 연결이 부분적으로만 이어짐
2. **presence** — 중역 존재감이 낮은 편
3. **brightness** — 밝기가 어두운 편

## 유지하면 좋은 특징

- 발성 안정성이 유지되는 편

## 우선 확인할 부분

### 성구 연결

성구 연결이 일부 구간에서만 안정적으로 이어져요. 전환 구간을 짧게 반복해보는 쪽이 도움이 될 수 있어요.

## 분석이 충분하지 않은 항목

- `effort`
- `contact`
- `breathiness`
- `source_balance`
- `airiness`
- `texture`
- `harmonic_concentration`
- `timbre_consistency`

## 고민 체크리스트 결과

### 고음

| 고민 | Focus | 첫 처방 | Protocol | Status |
|---|---|---|---|---|
| 고음이 잘 안 올라가요 | REGISTER_CONNECTION | 고음 접근이 편한 쪽으로, 편안한 중음에서 시작해 립트릴 또는 빨대 발성으로 위쪽 음역… | REGISTER_CONNECTION | PASS |
| 고음은 나오는데 너무 힘들어요 | REGISTER_CONNECTION | 고음에서 힘을 덜 쓰는 쪽으로, 편안한 중음에서 시작해 립트릴 또는 빨대 발성으로 위쪽… | REGISTER_CONNECTION | PASS |
| 고음에서 소리가 갑자기 뒤집혀요 | REGISTER_CONNECTION | 뒤집힘이 덜한 쪽으로, 편안한 중음에서 시작해 립트릴 또는 빨대 발성으로 위쪽 음역까지… | REGISTER_CONNECTION | PASS |
| 고음에서 소리가 너무 얇아져요 | PRESENCE | 고음에서 얇아지지 않는 쪽으로, 립트릴로 편안한 중음에서 위쪽 음역까지 작은 강도로 천… | PRESENCE | PASS |
| 고음에서 음정이나 소리가 흔들려요 | REGISTER_CONNECTION | 고음 흔들림이 덜한 쪽으로, 편안한 중음에서 시작해 립트릴 또는 빨대 발성으로 위쪽 음… | REGISTER_CONNECTION | PASS |

### 힘·피로

| 고민 | Focus | 첫 처방 | Protocol | Status |
|---|---|---|---|---|
| 목에 힘이 자꾸 들어가요 | REGISTER_CONNECTION | 목으로 밀지 않는 쪽으로, 편안한 중음에서 시작해 립트릴 또는 빨대 발성으로 위쪽 음역… | REGISTER_CONNECTION | PASS |
| 큰 소리를 내면 힘들어요 | REGISTER_CONNECTION | 큰 소리에서도 편한 쪽으로, 편안한 중음에서 시작해 립트릴 또는 빨대 발성으로 위쪽 음… | REGISTER_CONNECTION | PASS |
| 조금만 불러도 금방 지쳐요 | REGISTER_CONNECTION | 피로가 덜 쌓이는 쪽으로, 편안한 중음에서 시작해 립트릴 또는 빨대 발성으로 위쪽 음역… | REGISTER_CONNECTION | PASS |
| 노래 후 목소리가 쉽게 지쳐요 | REGISTER_CONNECTION | 부른 뒤 피로가 덜한 쪽으로, 편안한 중음에서 시작해 립트릴 또는 빨대 발성으로 위쪽 … | REGISTER_CONNECTION | PASS |

### 음색

| 고민 | Focus | 첫 처방 | Protocol | Status |
|---|---|---|---|---|
| 내 음색이 마음에 들지 않아요 | TIMBRE | 같은 음량에서 자음 시작을 조금 더 분명하게 하고 모음을 오래 눌러 붙이지 않은 채 짧… | TIMBRE_STYLE | PASS |
| 소리가 얇고 모기소리처럼 느껴져요 | PRESENCE | 얇게 느껴지지 않는 쪽으로, 편한 중음에서 짧은 모음을 1~2초 유지하세요. 음량을 키… | PRESENCE | PASS |
| 소리가 답답하게 들려요 | BRIGHTNESS | 답답·어두운 인상이 덜한 쪽으로, 편한 중음의 짧은 구절에서 음량은 그대로 두고 자음 … | TIMBRE_STYLE | PASS |
| 콧소리처럼 들려요 | PRESENCE | 콧소리처럼 들리지 않는 쪽으로, 콧소리처럼 느껴지는 모음·음절 하나만 골라, 같은 음높… | PRESENCE | PASS |
| 숨이 많이 섞여요 | TIMBRE | 숨 섞임이 과해지지 않는 쪽으로, 짧은 한 음 유지에서 숨이 먼저 과하게 새지 않는 쪽… | TIMBRE_STYLE | PASS |
| 소리가 너무 날카롭게 들려요 | MAINTAIN | 날카로움이 덜한 쪽으로, 작은~중간 강도에서 짧은 구절을 2~3회 부르세요. 음절 사이… | MAINTAIN | PASS |
| 거칠게 들려요 | STABILITY | 거친 인상이 덜한 쪽으로, 흔들리는 음을 길게 버티지 마세요. 먼저 편한 음높이에서 1… | STABILITY | PASS |
| 고음에서 음색이 갑자기 달라져요 | REGISTER_CONNECTION | 고음 음색이 급격히 바뀌지 않는 쪽으로, 립트릴로 편안한 중음에서 위쪽 음역까지 작은 … | REGISTER_CONNECTION | PASS |

### 컨트롤

| 고민 | Focus | 첫 처방 | Protocol | Status |
|---|---|---|---|---|
| 음정이 흔들려요 | REGISTER_CONNECTION | 음정이 덜 흔들리는 쪽으로, 편안한 중음에서 시작해 립트릴 또는 빨대 발성으로 위쪽 음… | REGISTER_CONNECTION | PASS |
| 낮은 음과 높은 음이 자연스럽게 연결되지 않아요 | REGISTER_CONNECTION | 중·고음 연결이 끊기지 않는 쪽으로, 편안한 중음에서 시작해 립트릴 또는 빨대 발성으로… | REGISTER_CONNECTION | PASS |
| 비브라토가 불안정해요 | STABILITY | 자연스러운 흔들림이 유지되는 쪽으로, 억지로 크게 만들지 말고, 짧은 지속음에서 자연스… | VIBRATO_CONTROL | PASS |
| 강약 조절이 어려워요 | DYNAMICS | 편한 강도로 짧은 구절을 유지하세요. 처음부터 큰 소리로 연습하지 마세요. (3회) | DYNAMICS | PASS |
| 긴 구절을 끝까지 유지하기 어려워요 | DYNAMICS | 조금 짧은 프레이즈부터 끝까지 같은 편안함을 유지하세요. (3회) | PHRASE_ENDURANCE | PASS |

### 안전

| 고민 | Focus | 첫 처방 | Protocol | Status |
|---|---|---|---|---|
| 노래할 때 목이 아파요 | SAFETY | — | SAFETY | PASS |
| 노래 후에도 통증이 남아요 | SAFETY | — | SAFETY | PASS |
| 말할 때도 불편해요 | SAFETY | — | SAFETY | PASS |
| 노래 후 쉰 느낌이 오래 지속돼요 | SAFETY | — | SAFETY | PASS |

### 기타

| 고민 | Focus | 첫 처방 | Protocol | Status |
|---|---|---|---|---|
| 직접 입력 | MAINTAIN | 지금 궁금한 표현을 기준으로, 답답하게 느껴지는 한 구절을 편한 음량으로 2~3번 부르… | MAINTAIN | PASS |

<details><summary>원본 singleton JSONL</summary>

`../concern_singletons.jsonl`

</details>

## 이 음원에서 고민에 따라 달라진 코칭

- Focus 종류: BRIGHTNESS, DYNAMICS, MAINTAIN, PRESENCE, REGISTER_CONNECTION, SAFETY, STABILITY, TIMBRE
- Protocol 종류: DYNAMICS, MAINTAIN, PHRASE_ENDURANCE, PRESENCE, REGISTER_CONNECTION, SAFETY, STABILITY, TIMBRE_STYLE, VIBRATO_CONTROL
- Expected shared: 45
- Over-shared: 0
- Wrong collapse: 0

## 목표 음색별 반응

| 목표 음색 | Primary | Secondary cue | Protocol |
|---|---|---|---|
| DENSE_SOLID | STYLE | — | TIMBRE_STYLE |
| BRIGHT_CLEAR | BRIGHTNESS | — | TIMBRE_STYLE |
| SOFT_SWEET | STYLE | — | TIMBRE_STYLE |
| LIGHT_CLEAR | BRIGHTNESS | — | TIMBRE_STYLE |
| WARM_FULL | STYLE | — | TIMBRE_STYLE |
| AIRY_DELICATE | STYLE | — | TIMBRE_STYLE |
| INTENSE_DISTINCT | STYLE | — | TIMBRE_STYLE |
| RECOMMEND_FOR_ME | STYLE | — | TIMBRE_STYLE |

목표 음색 변경에 따른 canonical acoustic mutation: **없음**

## Review flags

- `REGISTER_LIMITATION_PRESENT`
- `UNKNOWN_HEAVY`
