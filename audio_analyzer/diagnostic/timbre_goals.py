"""Perceptual target-timbre catalog (display + planner labels).

Genre strings are UI examples only — never used as acoustic reasoning input.
Target timbre is a perceptual goal, not an acoustic diagnosis.
"""

from __future__ import annotations

from typing import Any, Optional

TIMBRE_RELATED_CONCERN_IDS = frozenset(
    {
        "TIMBRE_DISSATISFIED",
        "VOICE_TOO_THIN",
        "VOICE_TOO_DARK_MUFFLED",
        "VOICE_TOO_NASAL_PERCEPT",
        "VOICE_TOO_BREATHY",
        "VOICE_TOO_SHARP",
        "VOICE_ROUGH",
        "TIMBRE_CHANGES_HIGH",
        "HIGH_NOTE_THINS",
    }
)

TARGET_TIMBRE_OPTIONS: list[dict[str, Any]] = [
    {
        "id": "DENSE_SOLID",
        "label": "단단하고 밀도 있게",
        "description": "밀도 있고 중심이 분명하게 들리는 음색",
        "genre_display": "록 · 뮤지컬 · 파워 발라드",
    },
    {
        "id": "BRIGHT_CLEAR",
        "label": "밝고 선명하게",
        "description": "또렷하고 시원하게 앞으로 들리는 음색",
        "genre_display": "K-POP · 팝 · 댄스",
    },
    {
        "id": "SOFT_SWEET",
        "label": "부드럽고 감미롭게",
        "description": "자극적이지 않고 매끄럽고 편안하게 들리는 음색",
        "genre_display": "발라드 · R&B · 어쿠스틱",
    },
    {
        "id": "LIGHT_CLEAR",
        "label": "맑고 가볍게",
        "description": "무겁지 않고 깨끗하고 청량하게 들리는 음색",
        "genre_display": "인디팝 · 시티팝 · 포크",
    },
    {
        "id": "WARM_FULL",
        "label": "따뜻하고 풍성하게",
        "description": "포근하면서 소리의 밀도와 깊이가 느껴지는 음색",
        "genre_display": "소울 · 재즈 · 발라드",
    },
    {
        "id": "AIRY_DELICATE",
        "label": "공기감 있고 여리게",
        "description": "숨결이 살짝 느껴지며 섬세하게 들리는 음색",
        "genre_display": "인디 · 드림팝 · 어쿠스틱",
    },
    {
        "id": "INTENSE_DISTINCT",
        "label": "강렬하고 개성 있게",
        "description": "질감과 존재감이 뚜렷해 인상이 강하게 남는 음색",
        "genre_display": "록 · 얼터너티브 · R&B",
    },
    {
        "id": "RECOMMEND_FOR_ME",
        "label": "잘 모르겠어요",
        "description": "현재 목소리 특징을 바탕으로 무리 없이 시도할 수 있는 방향을 추천받을게요.",
        "genre_display": "",
    },
]

_BY_ID = {o["id"]: o for o in TARGET_TIMBRE_OPTIONS}

HIGH_NOTE_DESIRED_OUTCOMES: dict[str, dict[str, str]] = {
    "HIGH_NOTE_CANNOT_REACH": {
        "id": "CONNECT_HIGH_COMFORTABLY",
        "label": "편안하게 높은 음까지 연결",
    },
    "HIGH_NOTE_TOO_EFFORTFUL": {
        "id": "HIGH_NOTE_LESS_EFFORT",
        "label": "같은 높은 음을 더 편안한 힘으로 유지",
    },
    "HIGH_NOTE_FLIPS": {
        "id": "CONNECT_WITHOUT_FLIP",
        "label": "중음→고음 전환을 급격한 뒤집힘 없이 연결",
    },
    "HIGH_NOTE_UNSTABLE": {
        "id": "STABLE_HIGH",
        "label": "높은 음에서도 안정성 유지",
    },
    "HIGH_NOTE_THINS": {
        "id": "KEEP_TIMBRE_ON_HIGH",
        "label": "높은 음에서도 원하는 음색 특성 유지",
    },
}


def concerns_need_timbre_goal(concerns: list[Any] | None) -> bool:
    from audio_analyzer.diagnostic.concerns import CONCERN_CATALOG

    ids: list[str] = []
    for item in concerns or []:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            ids.append(str(item.get("id") or item.get("concern_id") or ""))
    for cid in ids:
        if cid in TIMBRE_RELATED_CONCERN_IDS:
            return True
        if str((CONCERN_CATALOG.get(cid) or {}).get("category") or "") == "timbre":
            return True
    return False


def option_for(target_id: str | None) -> Optional[dict[str, Any]]:
    if not target_id:
        return None
    opt = _BY_ID.get(str(target_id).upper())
    return dict(opt) if opt else None


def public_target_timbre_catalog() -> dict[str, Any]:
    return {
        "prompt": "어떤 음색으로 노래하고 싶나요?",
        "helper": "가장 원하는 느낌 하나를 골라주세요.",
        "options": [dict(o) for o in TARGET_TIMBRE_OPTIONS],
        "concern_ids": sorted(TIMBRE_RELATED_CONCERN_IDS),
    }


def normalize_timbre_goal(
    raw: Any,
    *,
    concerns: list[Any] | None = None,
) -> Optional[dict[str, Any]]:
    """Persist a single perceptual target. Genre is never stored as reasoning input."""
    if not concerns_need_timbre_goal(concerns) and not raw:
        return None
    if raw is None:
        return None
    if isinstance(raw, str):
        tid = raw.upper()
        source = "USER_SELECTED"
    elif isinstance(raw, dict):
        tid = str(raw.get("id") or raw.get("timbre_goal_id") or "").upper()
        source = str(raw.get("source") or "USER_SELECTED")
    else:
        return None
    opt = option_for(tid)
    if not opt:
        return None
    if tid == "RECOMMEND_FOR_ME":
        source = "USER_REQUESTED_RECOMMENDATION"
    return {
        "id": tid,
        "label": opt["label"],
        "description": opt["description"],
        "source": source,
    }
