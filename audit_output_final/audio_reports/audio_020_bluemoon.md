# Audio 020 — bluemoon.m4a

**Audit status:** `REVIEW`  
**Audio id:** `5e7819c3abb4`

## 기본 정보

- 파일: `C:\VocalAgent\bluemoon.m4a`
- SHA: `5e7819c3abb42ae14873c91ee99825d29ceaf6da01bc898aa396259cbc99c253`
- 길이: None
- Sample Rate: None
- Analysis status: OK
- Source: fresh
- Analysis version: —

## 이 음원에서 분석된 발성 특징

| 축 | 상태 | 신뢰도 | 설명 |
|---|---|---|---|
| 힘 사용 | MODERATE | medium | 힘 사용이 중간 이상인 편 |
| 접촉감 | FIRM | — | 접촉감이 단단한 편 |
| 숨 섞임 | LOW | — | 숨 섞임이 적은 편 |
| 성구 연결 | DISRUPTED | — | 성구 연결 변화가 급격한 구간 있음 |
| 흉성/두성 음향 성향 | BALANCED_ACOUSTIC | — | 음향적으로 균형에 가까운 편 |
| 안정성 | STABLE | — | 안정성이 유지되는 편 |
| 중역 존재감 | UNAVAILABLE | — | 이번 녹음에서 단정하기 어려움 |
| 밝기 | UNAVAILABLE | — | 이번 녹음에서 단정하기 어려움 |
| 음색의 공기감 | LOW | — | LOW |
| 질감 | UNKNOWN | — | 이번 녹음에서 단정하기 어려움 |
| 배음 집중 | UNKNOWN | — | 이번 녹음에서 단정하기 어려움 |
| 음색 일관성 | UNKNOWN | — | — |
| 고음 분석 | UNAVAILABLE | — | 고음 직접 분석 지표가 제한적 |

## 한 줄 평가

접촉감은 단단한 편이지만, 음역이 올라가는 과정에서 성구 연결 변화가 큰, 발성 안정성이 유지되는 편인, 숨 섞임이 적은 편인 발성으로 분석됐어요.

> 이 요약은 concern/target과 무관한 canonical song evidence만 사용합니다.

## 가장 중요한 특징

1. **register_connection** — 성구 연결 변화가 급격한 구간 있음
2. **contact** — 접촉감이 단단한 편
3. **breathiness** — 숨 섞임이 적은 편

## 유지하면 좋은 특징

- 발성 안정성이 유지되는 편
- 숨 섞임이 적은 편

## 우선 확인할 부분

### 성구 연결

음역이 올라가는 과정에서 연결 변화가 급격한 구간이 보여요. 중음에서 위쪽으로 작은 강도로 이어 올리는 쪽을 우선 확인해보세요.

## 분석이 충분하지 않은 항목

- `presence`
- `brightness`
- `texture`
- `harmonic_concentration`
- `timbre_consistency`

## 고민 체크리스트 결과

### 고음

| 고민 | Focus | 첫 처방 | Protocol | Status |
|---|---|---|---|---|
| 고음이 잘 안 올라가요 | REGISTER_CONNECTION | 고음 접근이 편한 쪽으로, 편안한 중음에서 시작해 립트릴 또는 빨대 발성으로 위쪽 음역… | REGISTER_CONNECTION | PASS |
| 고음은 나오는데 너무 힘들어요 | EFFORT | 고음에서 힘을 덜 쓰는 쪽으로, 현재 문제 음보다 조금 쉬운 음역에서 작은~중간 강도로… | EFFORT | PASS |
| 고음에서 소리가 갑자기 뒤집혀요 | REGISTER_CONNECTION | 뒤집힘이 덜한 쪽으로, 편안한 중음에서 시작해 립트릴 또는 빨대 발성으로 위쪽 음역까지… | REGISTER_CONNECTION | PASS |
| 고음에서 소리가 너무 얇아져요 | REGISTER_CONNECTION | 고음에서 얇아지지 않는 쪽으로, 립트릴로 편안한 중음에서 위쪽 음역까지 작은 강도로 천… | REGISTER_CONNECTION | PASS |
| 고음에서 음정이나 소리가 흔들려요 | EFFORT | 고음 흔들림이 덜한 쪽으로, 현재 문제 음보다 조금 쉬운 음역에서 작은~중간 강도로 짧… | EFFORT | PASS |

### 힘·피로

| 고민 | Focus | 첫 처방 | Protocol | Status |
|---|---|---|---|---|
| 목에 힘이 자꾸 들어가요 | EFFORT | 목으로 밀지 않는 쪽으로, 현재 문제 음보다 조금 쉬운 음역에서 작은~중간 강도로 짧게… | EFFORT | PASS |
| 큰 소리를 내면 힘들어요 | EFFORT | 큰 소리에서도 편한 쪽으로, 현재 문제 음보다 조금 쉬운 음역에서 작은~중간 강도로 짧… | EFFORT | PASS |
| 조금만 불러도 금방 지쳐요 | EFFORT | 피로가 덜 쌓이는 쪽으로, 현재 문제 음보다 조금 쉬운 음역에서 작은~중간 강도로 짧게… | EFFORT | PASS |
| 노래 후 목소리가 쉽게 지쳐요 | EFFORT | 부른 뒤 피로가 덜한 쪽으로, 현재 문제 음보다 조금 쉬운 음역에서 작은~중간 강도로 … | EFFORT | PASS |

### 음색

| 고민 | Focus | 첫 처방 | Protocol | Status |
|---|---|---|---|---|
| 내 음색이 마음에 들지 않아요 | REGISTER_CONNECTION | 같은 음량에서 자음 시작을 조금 더 분명하게 하고 모음을 오래 눌러 붙이지 않은 채 짧… | REGISTER_CONNECTION | PASS |
| 소리가 얇고 모기소리처럼 느껴져요 | REGISTER_CONNECTION | 얇게 느껴지지 않는 쪽으로, 립트릴로 편안한 중음에서 위쪽 음역까지 작은 강도로 천천히… | REGISTER_CONNECTION | PASS |
| 소리가 답답하게 들려요 | REGISTER_CONNECTION | 답답·어두운 인상이 덜한 쪽으로, 답답하게 느껴지는 한 구절을 편한 음량으로 2~3번 … | REGISTER_CONNECTION | PASS |
| 콧소리처럼 들려요 | REGISTER_CONNECTION | 콧소리처럼 들리지 않는 쪽으로, 콧소리처럼 느껴지는 모음·음절 하나만 골라, 같은 음높… | REGISTER_CONNECTION | PASS |
| 숨이 많이 섞여요 | REGISTER_CONNECTION | 숨 섞임이 과해지지 않는 쪽으로, 짧은 한 음 유지에서 숨이 먼저 과하게 새지 않는 쪽… | REGISTER_CONNECTION | PASS |
| 소리가 너무 날카롭게 들려요 | REGISTER_CONNECTION | 날카로움이 덜한 쪽으로, 작은~중간 강도에서 짧은 구절을 2~3회 부르세요. 음절 사이… | REGISTER_CONNECTION | PASS |
| 거칠게 들려요 | REGISTER_CONNECTION | 거친 인상이 덜한 쪽으로, 작은~중간 강도에서 짧은 구절을 2~3회 부르세요. 음절 사… | REGISTER_CONNECTION | PASS |
| 고음에서 음색이 갑자기 달라져요 | REGISTER_CONNECTION | 고음 음색이 급격히 바뀌지 않는 쪽으로, 립트릴로 편안한 중음에서 위쪽 음역까지 작은 … | REGISTER_CONNECTION | PASS |

### 컨트롤

| 고민 | Focus | 첫 처방 | Protocol | Status |
|---|---|---|---|---|
| 음정이 흔들려요 | EFFORT | 음정이 덜 흔들리는 쪽으로, 현재 문제 음보다 조금 쉬운 음역에서 작은~중간 강도로 짧… | EFFORT | PASS |
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
| 직접 입력 | REGISTER_CONNECTION | 지금 궁금한 표현을 기준으로, 답답하게 느껴지는 한 구절을 편한 음량으로 2~3번 부르… | REGISTER_CONNECTION | PASS |

<details><summary>원본 singleton JSONL</summary>

`../concern_singletons.jsonl`

</details>

## 이 음원에서 고민에 따라 달라진 코칭

- Focus 종류: DYNAMICS, EFFORT, REGISTER_CONNECTION, SAFETY, STABILITY
- Protocol 종류: DYNAMICS, EFFORT, PHRASE_ENDURANCE, REGISTER_CONNECTION, SAFETY, VIBRATO_CONTROL
- Expected shared: 29
- Over-shared: 0
- Wrong collapse: 0

## 목표 음색별 반응

| 목표 음색 | Primary | Secondary cue | Protocol |
|---|---|---|---|
| DENSE_SOLID | REGISTER_CONNECTION | — | REGISTER_CONNECTION |
| BRIGHT_CLEAR | REGISTER_CONNECTION | — | REGISTER_CONNECTION |
| SOFT_SWEET | REGISTER_CONNECTION | — | REGISTER_CONNECTION |
| LIGHT_CLEAR | REGISTER_CONNECTION | — | REGISTER_CONNECTION |
| WARM_FULL | REGISTER_CONNECTION | — | REGISTER_CONNECTION |
| AIRY_DELICATE | REGISTER_CONNECTION | — | REGISTER_CONNECTION |
| INTENSE_DISTINCT | REGISTER_CONNECTION | — | REGISTER_CONNECTION |
| RECOMMEND_FOR_ME | REGISTER_CONNECTION | — | REGISTER_CONNECTION |

목표 음색 변경에 따른 canonical acoustic mutation: **없음**

## Review flags

- `REGISTER_LIMITATION_PRESENT`
- `UNKNOWN_HEAVY`
