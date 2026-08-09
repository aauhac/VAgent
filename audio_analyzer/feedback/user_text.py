"""
feedback/user_text.py
---------------------
User-facing copy for v2 (no pitch-accuracy / medical language).
"""

AREA_COPY = {
    "stability": {
        "strength_title": "길게 유지한 음이 비교적 안정적이에요",
        "strength_feedback": "같은 음을 유지하는 구간에서 소리가 크게 흔들리지 않았어요.",
        "keep_advice": "작은 볼륨에서도 같은 느낌을 유지해 보세요.",
        "needs_title": "길게 유지한 음의 안정성",
        "what_user_hears": "길게 뻗는 음에서 소리가 조금 흔들리거나 일정하지 않게 들릴 수 있어요.",
        "possible_reason": "호흡 압력이나 힘 조절이 구간마다 달라졌을 가능성이 있어요.",
        "how_to_sing": "큰 소리로 버티기보다, 작은 소리로 목표 음을 먼저 일정하게 유지해 보세요.",
        "practice": "편한 음 하나를 골라도 3초 동안 같은 크기로 유지하는 연습을 해보세요.",
        "check_next": "다음 녹음에서 길게 유지하는 구간의 흔들림이 줄어드는지 확인해 보세요.",
    },
    "projection": {
        "strength_title": "목소리가 비교적 또렷하게 전달돼요",
        "strength_feedback": "소리가 뒤로 묻히지 않고 앞쪽으로 전달되는 편이에요.",
        "keep_advice": "지르지 않고도 말하듯 또렷하게 내는 느낌을 유지해 보세요.",
        "needs_title": "목소리 전달력",
        "what_user_hears": "목소리가 반주나 공간 속에 묻혀 또렷함이 약하게 들릴 수 있어요.",
        "possible_reason": "소리를 부드럽게 내려고 하면서 음의 시작이 흐려졌을 가능성이 있어요.",
        "how_to_sing": "세게 지르기보다, 첫 소리를 말하듯 분명하게 시작해 보세요.",
        "practice": "가사를 말하듯 읽은 뒤, 같은 느낌으로 낮은 볼륨에서 불러 보세요.",
        "check_next": "다음엔 이어폰으로 들으며 목소리가 앞으로 나오는지 확인해 보세요.",
    },
    "resonance": {
        "strength_title": "공명 균형이 무난해요",
        "strength_feedback": "소리가 한쪽에 치우치지 않고 비교적 균형 있게 측정됐어요.",
        "keep_advice": "입을 억지로 크게 열기보다 편한 말소리 위치를 유지해 보세요.",
        "needs_title": "공명 균형",
        "what_user_hears": "소리가 답답하거나, 반대로 가벼워 공허하게 들릴 수 있어요.",
        "possible_reason": "모음 위치나 소리의 무게 조절이 구간에 따라 달라졌을 가능성이 있어요.",
        "how_to_sing": "턱을 많이 내리기보다, 평소 말할 때처럼 앞쪽에서 편하게 내 보세요.",
        "practice": "'네', '니', '냐'로 같은 멜로디를 부르며 소리가 앞으로 나오는지 확인해 보세요.",
        "check_next": "다음 녹음에서 답답함/가벼움이 덜한지 들어 보세요.",
    },
    "dynamic_control": {
        "strength_title": "강약 표현이 자연스러워요",
        "strength_feedback": "소리 크기의 변화가 지나치게 평평하지 않고 표현이 느껴져요.",
        "keep_advice": "중요한 단어만 살짝 더 살리는 느낌을 유지해 보세요.",
        "needs_title": "강약 컨트롤",
        "what_user_hears": "전체적으로 비슷한 크기로 들려 표현이 밋밋하게 느껴질 수 있어요.",
        "possible_reason": "음 높이 유지에 집중하면서 문장별 강조가 줄어들었을 가능성이 있어요.",
        "how_to_sing": "모든 음을 같은 세기로 부르기보다, 중요한 부분만 살짝 더 분명하게 해보세요.",
        "practice": "한 문장을 말하듯 읽고, 강조 단어만 조금 더 크게 불러 보세요.",
        "check_next": "작은 소리와 큰 소리의 대비가 자연스러운지 확인해 보세요.",
    },
}

FORBIDDEN_USER_TERMS = [
    "성대 결절",
    "성대 질환",
    "성대 손상",
    "후두 질환",
    "질병 의심",
    "의학적",
    "음정을 틀렸",
    "음정이 맞지",
    "박자가 안",
    "원곡과",
    "LTAS",
    "SPR",
    "spectral",
    "formant",
    "pYIN",
    "z-score",
]
