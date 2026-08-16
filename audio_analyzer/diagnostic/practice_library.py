"""Canonical low-risk practice library for Precision Guidance v2.

Practices are selected by primary functional focus — never by concern id alone.
No anatomical / pressure claims.
"""

from __future__ import annotations

from typing import Any, Optional

PRACTICE_LIBRARY: dict[str, dict[str, Any]] = {
    "REGISTER_GLIDE_LIGHT": {
        "practice_id": "REGISTER_GLIDE_LIGHT",
        "title": "작은 강도로 중음→고음 연결하기",
        "goal": "전환 구간에서 끊기지 않는 연결 만들기",
        "instruction": (
            "편안한 중음에서 시작해 립트릴·빨대 발성 또는 가벼운 '우—'로 "
            "천천히 위로 연결하세요. 끊기는 지점에서 더 세게 밀지 말고, "
            "연결이 유지되는 범위까지만 반복한 뒤 조금씩 높여보세요."
        ),
        "success_cues": [
            "음이 올라가도 음량이 갑자기 커지지 않음",
            "전환 지점에서 소리가 갑자기 끊기지 않음",
            "힘이 급격히 늘지 않음",
            "통증/불편 없음",
        ],
        "avoid": [
            "끊기는 음을 세게 밀어서 통과하기",
            "높은 음에 도달하려고 음량부터 키우기",
            "통증 상태에서 반복",
        ],
        "safe_for": ["REGISTER_CONNECTION", "HIGH_NOTE_FLIPS", "HIGH_NOTE_CANNOT_REACH"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "REDUCE_HIGH_NOTE_EFFORT": {
        "practice_id": "REDUCE_HIGH_NOTE_EFFORT",
        "title": "고음에서 힘 증가 줄이기",
        "goal": "높은 음에서 힘 사용이 급격히 커지지 않게 하기",
        "instruction": (
            "현재 편하게 낼 수 있는 음보다 조금 높은 음을 "
            "작은~중간 강도로 짧게 내세요. 음이 올라가도 음량을 더 키우지 않고 "
            "같은 편안함을 유지한 채 한두 음씩 범위를 넓혀보세요."
        ),
        "success_cues": [
            "높은 음에서도 음량을 먼저 키우지 않음",
            "짧은 구간에서 불편감 없이 유지",
            "힘 느낌이 급증하지 않음",
        ],
        "avoid": [
            "높은 음에 도달하기 위해 음량부터 키우기",
            "통증 상태에서 반복",
        ],
        "safe_for": ["EFFORT", "HIGH_NOTE_TOO_EFFORTFUL", "THROAT_EFFORT"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "SOVT_GLIDE": {
        "practice_id": "SOVT_GLIDE",
        "title": "립트릴·빨대로 부드럽게 연결하기",
        "goal": "작은 강도로 음역 이동을 이어가기",
        "instruction": (
            "작은 강도의 립트릴이나 빨대 발성으로 편한 음에서 위로 천천히 glide하세요. "
            "소리가 갑자기 바뀌는 지점이 나오면 그 음을 세게 버티지 말고 "
            "조금 아래에서 다시 시작해 끊기지 않는 범위를 반복하세요."
        ),
        "success_cues": [
            "전환 지점에서 갑작스러운 음질 변화가 줄어듦",
            "음량을 키우지 않아도 연결됨",
            "glide가 한 흐름으로 이어짐",
        ],
        "avoid": ["끊기는 지점을 세게 넘기기", "통증 상태에서의 반복"],
        "safe_for": ["REGISTER_CONNECTION", "EFFORT"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "STABILITY_SHORT_HOLD": {
        "practice_id": "STABILITY_SHORT_HOLD",
        "title": "짧은 안정 구간 유지하기",
        "goal": "흔들림이 적은 짧은 지속 만들기",
        "instruction": (
            "편안한 중음에서 2~3초만 짧게 유지한 뒤 쉬세요. "
            "안정이 유지되면 한 음씩 위로 옮겨 같은 짧은 유지를 반복하세요."
        ),
        "success_cues": [
            "짧은 구간에서 흔들림이 크지 않음",
            "음량을 키우지 않아도 유지됨",
            "불편감 없음",
        ],
        "avoid": ["길게 버텨 흔들림을 키우기", "불안정한 음을 세게 고정하기"],
        "safe_for": ["STABILITY", "HIGH_NOTE_UNSTABLE"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "MAINTAIN_LOW_EFFORT": {
        "practice_id": "MAINTAIN_LOW_EFFORT",
        "title": "편안한 힘 패턴 유지하며 범위 넓히기",
        "goal": "이미 편안한 패턴을 유지한 채 범위만 천천히 확장",
        "instruction": (
            "세게 힘을 빼려 하기보다, 현재 편한 강도를 유지한 채 "
            "한두 음씩 범위를 천천히 넓혀보세요."
        ),
        "success_cues": [
            "음이 올라가도 음량이 갑자기 커지지 않음",
            "불편감 없이 짧은 구간 유지",
        ],
        "avoid": ["힘을 빼는 것에만 집착해 연결을 끊기"],
        "safe_for": ["EFFORT", "MAINTAIN"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "PRESENCE_WITHOUT_PUSHING": {
        "practice_id": "PRESENCE_WITHOUT_PUSHING",
        "title": "음량을 키우지 않고 중음 존재감 유지하기",
        "goal": "음량을 키우지 않으면서 중역 존재감 유지",
        "instruction": (
            "편한 중음에서 짧은 모음을 1~2초 유지하세요. "
            "음량을 키우지 않고 소리가 중간에 흐려지지 않는 강도를 찾은 뒤, "
            "같은 강도로 2~3음 연결하세요."
        ),
        "success_cues": ["중역 존재감이 유지됨", "음량을 과하게 키우지 않음"],
        "avoid": ["얇음을 가리기 위해 과하게 밀기", "존재감을 유지하세요만 말하기"],
        "safe_for": ["PRESENCE", "TIMBRE"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "BREATHINESS_CONTROL": {
        "practice_id": "BREATHINESS_CONTROL",
        "title": "숨이 먼저 새지 않게 짧게 유지하기",
        "goal": "숨 섞임이 과해지지 않는 짧은 지속",
        "instruction": "낮은 강도에서 짧은 지속음을 유지하며 숨이 먼저 새지 않게 하세요.",
        "success_cues": ["숨이 먼저 빠져나가는 느낌이 과하지 않음"],
        "avoid": ["숨만 흘리는 긴 발성"],
        "safe_for": ["BREATHINESS"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "TIMBRE_PRESERVE": {
        "practice_id": "TIMBRE_PRESERVE",
        "title": "현재 음색 특징 유지하기",
        "goal": "관찰된 음색 특징을 무리 없이 유지",
        "instruction": "편안한 강도로 짧은 지속음을 유지하며 소리를 과하게 밀거나 바꾸려 하지 마세요.",
        "success_cues": ["음색이 갑자기 과하게 바뀌지 않음"],
        "avoid": ["음색을 바꾸려고 세게 밀기"],
        "safe_for": ["TIMBRE"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "SAFETY_STOP": {
        "practice_id": "SAFETY_STOP",
        "title": "불편할 때는 강한 고음·큰 소리 피하기",
        "goal": "통증·지속 불편이 있을 때 무리한 연습 중단",
        "instruction": "불편감이 있으면 강한 고음과 큰 소리 반복을 멈추고 짧게 쉬세요.",
        "success_cues": ["불편감이 늘지 않음", "무리한 고음 시도를 하지 않음"],
        "avoid": ["통증 상태에서의 강한 고음 반복"],
        "safe_for": ["SAFETY"],
        "blocked_when": [],
    },
    "STYLE_DENSE_SOLID": {
        "practice_id": "STYLE_DENSE_SOLID",
        "title": "밀도를 밀지 않고 찾아보기",
        "goal": "음량을 키우지 않으면서 소리 중심이 흐려지지 않는 표현 탐색",
        "instruction": (
            "편안한 중음의 짧은 구절에서 음량을 먼저 키우지 않고 "
            "소리 중심이 흐려지지 않는 표현을 찾아보세요."
        ),
        "success_cues": ["음량을 먼저 키우지 않음", "불편감 없음"],
        "avoid": ["밀도를 위해 세게 밀어붙이기"],
        "safe_for": ["STYLE", "TIMBRE"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "STYLE_BRIGHT_CLEAR": {
        "practice_id": "STYLE_BRIGHT_CLEAR",
        "title": "음량 유지하며 더 선명하게 만들기",
        "goal": "음량을 키우지 않고 발음·모음 표현으로 선명함 만들기",
        "instruction": (
            "편한 중음의 짧은 구절에서 음량은 그대로 두고 "
            "자음 시작을 조금 더 분명하게 하세요. "
            "모음을 오래 눌러 끌지 말고 다음 음으로 또렷하게 이어주세요. 2~3회만 반복하세요."
        ),
        "success_cues": ["더 선명하게 느껴짐", "음량·힘 급증 없음"],
        "avoid": ["선명함을 위해 음량부터 키우기", "소리를 앞으로 보내라는 단독 지시만 하기"],
        "safe_for": ["STYLE", "TIMBRE", "BRIGHTNESS"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "STYLE_SOFT_SWEET": {
        "practice_id": "STYLE_SOFT_SWEET",
        "title": "부드럽고 감미로운 표현 탐색하기",
        "goal": "자극 없이 매끄러운 연결 찾기",
        "instruction": (
            "편안한 중음의 짧은 구절을 작은~중간 강도로 매끄럽게 이어보고, "
            "현재보다 편안하고 부드럽게 들리는 표현을 찾아보세요."
        ),
        "success_cues": ["연결이 끊기지 않음", "불편감 없음"],
        "avoid": ["부드럽게 하려고 숨을 과도하게 흘리기"],
        "safe_for": ["STYLE", "TIMBRE"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "STYLE_LIGHT_CLEAR": {
        "practice_id": "STYLE_LIGHT_CLEAR",
        "title": "맑고 가벼운 표현 탐색하기",
        "goal": "무겁게 밀지 않으면서 깨끗한 인상을 짧게 비교",
        "instruction": (
            "작은 강도로 짧은 구절을 부르며 소리가 무거워지지 않게 유지해 보세요. "
            "가벼움을 위해 힘을 완전히 빼 연결을 끊지는 마세요."
        ),
        "success_cues": ["짧은 구간이 한 흐름으로 이어짐", "음량을 키우지 않음"],
        "avoid": ["가볍게 하려고 연결을 끊기"],
        "safe_for": ["STYLE", "TIMBRE"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "STYLE_WARM_FULL": {
        "practice_id": "STYLE_WARM_FULL",
        "title": "따뜻하고 풍성한 표현 탐색하기",
        "goal": "힘을 더하지 않으면서 밀도와 깊이가 느껴지는 표현 찾기",
        "instruction": (
            "편안한 중음에서 짧은 모음을 유지하며 "
            "소리의 중심이 얇아지지 않는 표현을 찾아보세요. 음량부터 키우지 마세요."
        ),
        "success_cues": ["존재감이 갑자기 사라지지 않음", "힘을 급증시키지 않음"],
        "avoid": ["풍성함을 위해 세게 밀기"],
        "safe_for": ["STYLE", "TIMBRE"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "STYLE_AIRY_DELICATE": {
        "practice_id": "STYLE_AIRY_DELICATE",
        "title": "섬세한 공기감 표현 탐색하기",
        "goal": "과도한 숨 흘림 없이 여린 표현 찾기",
        "instruction": (
            "작은 강도에서 섬세하게 표현하되 "
            "숨을 과도하게 흘리거나 불편함이 생기지 않도록 하세요."
        ),
        "success_cues": ["짧은 구간에서 불편 없음", "숨이 먼저 다 빠지지 않음"],
        "avoid": ["공기감을 위해 숨을 과도하게 흘리기"],
        "safe_for": ["STYLE", "TIMBRE"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "STYLE_INTENSE_DISTINCT": {
        "practice_id": "STYLE_INTENSE_DISTINCT",
        "title": "개성 있는 질감을 작게 탐색하기",
        "goal": "강렬함을 음량 증가로 대체하지 않기",
        "instruction": (
            "짧은 구절을 작은~중간 강도로 부르며 "
            "질감이 느껴지는 표현을 찾아보세요. 강렬함을 위해 처음부터 세게 밀지 마세요."
        ),
        "success_cues": ["짧은 구간 유지", "음량을 먼저 키우지 않음"],
        "avoid": ["개성을 위해 세게 밀어붙이기"],
        "safe_for": ["STYLE", "TIMBRE"],
        "blocked_when": ["PAIN_LIMITED"],
    },
}


FOCUS_TO_PRACTICE: dict[str, str] = {
    "REGISTER_CONNECTION": "REGISTER_GLIDE_LIGHT",
    "EFFORT": "REDUCE_HIGH_NOTE_EFFORT",
    "STABILITY": "STABILITY_SHORT_HOLD",
    "PRESENCE": "PRESENCE_WITHOUT_PUSHING",
    "BRIGHTNESS": "STYLE_BRIGHT_CLEAR",
    "BREATHINESS": "BREATHINESS_CONTROL",
    "AIRINESS": "BREATHINESS_CONTROL",
    "CONTACT": "MAINTAIN_LOW_EFFORT",
    "TIMBRE": "TIMBRE_PRESERVE",
    "TEXTURE": "TIMBRE_PRESERVE",
    "DYNAMICS": "MAINTAIN_LOW_EFFORT",
    "HIGH_NOTE": "REGISTER_GLIDE_LIGHT",
    "MAINTAIN": "MAINTAIN_LOW_EFFORT",
    "SAFETY": "SAFETY_STOP",
    "STYLE": "STYLE_SOFT_SWEET",
    "STYLE_DENSE_SOLID": "STYLE_DENSE_SOLID",
    "STYLE_BRIGHT_CLEAR": "STYLE_BRIGHT_CLEAR",
    "STYLE_SOFT_SWEET": "STYLE_SOFT_SWEET",
    "STYLE_LIGHT_CLEAR": "STYLE_LIGHT_CLEAR",
    "STYLE_WARM_FULL": "STYLE_WARM_FULL",
    "STYLE_AIRY_DELICATE": "STYLE_AIRY_DELICATE",
    "STYLE_INTENSE_DISTINCT": "STYLE_INTENSE_DISTINCT",
}

CATEGORY_FALLBACK_PRACTICE: dict[str, str] = {
    "high_note": "REGISTER_GLIDE_LIGHT",
    "effort": "REDUCE_HIGH_NOTE_EFFORT",
    "timbre": "TIMBRE_PRESERVE",
    "control": "STABILITY_SHORT_HOLD",
    "safety": "SAFETY_STOP",
    "other": "MAINTAIN_LOW_EFFORT",
}


def get_practice(practice_id: str) -> Optional[dict[str, Any]]:
    p = PRACTICE_LIBRARY.get(practice_id)
    return dict(p) if p else None


def practice_for_focus(
    primary_focus: str,
    *,
    alternative: bool = False,
    category: str = "",
) -> Optional[dict[str, Any]]:
    """Select practice by primary functional focus.

    Unknown focus does NOT fall back to register glide.
    Missing/unknown with no category → None.
    """
    focus = str(primary_focus or "").upper()
    if not focus or focus in ("UNKNOWN", "UNKNOWN_FOCUS", "NONE"):
        cat = str(category or "").lower()
        if cat:
            pid = CATEGORY_FALLBACK_PRACTICE.get(cat)
            return dict(get_practice(pid) or {}) if pid else None
        return None
    pid = FOCUS_TO_PRACTICE.get(focus)
    if not pid:
        pid = CATEGORY_FALLBACK_PRACTICE.get(str(category or "").lower())
        if not pid:
            return None
    if alternative and pid == "REGISTER_GLIDE_LIGHT":
        pid = "SOVT_GLIDE"
    elif alternative and pid == "REDUCE_HIGH_NOTE_EFFORT":
        pid = "SOVT_GLIDE"
    p = get_practice(pid)
    return dict(p) if p else None
