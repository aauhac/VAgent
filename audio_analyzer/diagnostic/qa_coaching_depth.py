"""QA Coaching Depth v9 — direct-action cue ladders + Korean user copy.

QA must tell the user WHAT to do next (HOW), not only abstract advice.
Functional/control QA reuses Coaching Protocol entry steps.
DESCRIPTIVE does not force generic A/B.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from audio_analyzer.diagnostic.coaching_protocol import build_coaching_protocol
from audio_analyzer.diagnostic.question_semantics import (
    TYPE_CONTROL,
    TYPE_DESCRIPTIVE,
    TYPE_FUNCTIONAL,
    TYPE_PERCEPTUAL,
    TYPE_SAFETY,
)

# Standalone abstract phrases banned as the only action
ABSTRACT_STANDALONE = (
    "소리 중심을 유지하세요",
    "소리 중심을 유지",
    "연결을 매끄럽게 하세요",
    "연결을 매끄럽게",
    "원하는 느낌에 가깝게",
    "원하는 느낌에 가까운",
    "원하는 느낌으로",
    "더 또렷하게 불러보세요",
    "더 편하게 불러보세요",
    "질감을 탐색",
    "존재감을 유지하세요",
    "표현을 비교하세요",
    "표현을 바꿔보세요",
    "현재 패턴 유지",
    "조금 작은 강도로 비교해보세요",
    "같은 구절을 두 가지 방식으로 비교하세요",
    "우선 짧은 구절에서 원하는 느낌에 가까운 표현을 비교해보세요",
)

_ANATOMY_BANNED = (
    "연구개",
    "후두를",
    "후두가",
    "성대 붙",
    "성대를 붙",
    "복압",
    "혀뿌리",
    "목근육이 긴장",
)


# ---------------------------------------------------------------------------
# Motor cue ladders (first cue = entry; alternate = if no change)
# ---------------------------------------------------------------------------

CUE_LADDERS: dict[str, list[dict[str, Any]]] = {
    "REGISTER": [
        {
            "id": "LIP_TRILL",
            "instruction": (
                "립트릴로 편안한 중음에서 위쪽 음역까지 작은 강도로 천천히 이어 올리세요. "
                "끊기는 지점에서는 음량을 더 키우지 말고 연결되는 범위까지만 올라가세요."
            ),
            "repetitions": "3~5회",
            "success": "끊김·갑작스러운 변화가 줄고 음량·힘이 갑자기 커지지 않음",
            "if_no_change": "같은 음형을 빨대 발성으로 바꿔 다시 연결해보세요. 안 되면 음역 범위를 줄이세요.",
            "song_transfer": "잘 되면 편한 모음 → 가사 모음 → 짧은 실제 구절 순으로 옮기세요.",
        },
        {
            "id": "STRAW",
            "instruction": "빨대 발성으로 같은 작은 강도로 음역을 이어 올리기를 반복하세요.",
            "repetitions": "3회",
            "success": "전환이 덜 갑작스러움",
            "if_no_change": "편하게 이어지는 모음으로 옮겨보세요.",
            "song_transfer": "연결이 유지되면 짧은 가사 구절로 돌아오세요.",
        },
        {
            "id": "VOWEL_GLIDE",
            "instruction": "같은 음형을 '우'처럼 편하게 이어지는 모음으로 옮겨 연결해보세요.",
            "repetitions": "3회",
            "success": "립트릴과 비슷한 연결 유지",
            "if_no_change": "가사의 모음만 연결해보세요.",
            "song_transfer": "모음 연결이 되면 짧은 실제 가사로 옮기세요.",
        },
    ],
    "STABILITY": [
        {
            "id": "HOLD_1S",
            "instruction": (
                "흔들리는 음을 길게 버티지 마세요. "
                "먼저 편한 음높이에서 1~2초만 짧게 유지하세요."
            ),
            "repetitions": "3~5회",
            "success": "짧은 구간에서 음정·소리 흔들림이 줄어듦",
            "if_no_change": "더 편한 음높이에서 같은 짧은 유지를 반복하세요.",
            "song_transfer": "흔들림이 줄면 2~3초 → 3음 짧은 패턴 → 짧은 구절 순으로 옮기세요.",
        },
        {
            "id": "HOLD_2_3",
            "instruction": "같은 음을 2~3초로 조금 늘려 유지하세요. 흔들림이 커지면 다시 짧게.",
            "repetitions": "3회",
            "success": "2~3초에서도 흔들림 감소",
            "if_no_change": "3음 짧은 패턴으로 옮겨보세요.",
            "song_transfer": "짧은 구절에 적용한 뒤 원곡으로 돌아오세요.",
        },
    ],
    "PRESENCE": [
        {
            "id": "SHORT_VOWEL",
            "instruction": (
                "편한 중음에서 짧은 모음을 1~2초 유지하세요. "
                "음량을 키우지 않고 소리가 중간에 흐려지지 않는 강도를 찾은 뒤, "
                "같은 강도로 2~3음 연결하세요."
            ),
            "repetitions": "2~3회",
            "success": "중역 존재감이 유지되고 음량·힘이 갑자기 커지지 않음",
            "if_no_change": "짧은 2~3음 패턴에서도 같은 강도로 유지해보세요.",
            "song_transfer": "유지되는 강도를 짧은 원곡 구절에 적용하세요.",
        },
    ],
    "BREATHINESS": [
        {
            "id": "SHORT_SUSTAIN",
            "instruction": (
                "짧은 한 음 유지에서 숨이 먼저 과하게 새지 않는 쪽을 찾아보세요. "
                "숨을 갑자기 막으려 하지 마세요."
            ),
            "repetitions": "2~3회",
            "success": "숨 섞임이 줄고 힘·접촉이 갑자기 늘지 않음",
            "if_no_change": "짧은 모음 패턴으로 같은 방식으로 반복하세요.",
            "song_transfer": "유지되는 쪽을 짧은 구절에 적용하세요.",
        },
    ],
    "EFFORT": [
        {
            "id": "EASY_RANGE",
            "instruction": (
                "문제가 생기는 음보다 한두 음 낮은 편한 위치에서 시작하세요. "
                "작은~중간 강도로 짧은 구절을 부른 뒤, "
                "같은 음량을 유지한 채 문제 음역으로 한 음씩 올라가세요."
            ),
            "repetitions": "2~3회",
            "success": "같은 편안함이 유지되고 밀기 감소",
            "if_no_change": "같은 강도를 유지한 채 문제 음역까지 천천히 접근하세요.",
            "song_transfer": "편안한 강도가 잡히면 문제 구절만 짧게 적용하세요.",
        },
    ],
    "BRIGHT_CLEAR": [
        {
            "id": "CV_CLARITY",
            "instruction": (
                "편한 중음의 짧은 구절에서 음량은 그대로 두고 "
                "자음 시작을 조금 더 분명하게 하세요. "
                "모음을 오래 눌러 끌지 말고 다음 음으로 또렷하게 이어주세요."
            ),
            "repetitions": "2~3회",
            "success": "같은 음량에서도 더 선명하게 들림",
            "if_no_change": (
                "같은 음형을 현재 편하게 밝게 들리는 모음으로 짧게 연습해보고 "
                "더 자연스러운 쪽을 실제 가사에 적용하세요."
            ),
            "song_transfer": "좋아진 표현을 짧은 구절에 옮긴 뒤 원래 가사로 돌아오세요.",
        },
        {
            "id": "VOWEL_SHAPE",
            "instruction": (
                "같은 음높이·같은 음량에서 모음 형태만 조금 바꾼 두 버전을 짧게 불러보세요. "
                "특정 모음이 정답이라고 단정하지 말고, 현재 편하게 선명하게 들리는 쪽을 고르세요."
            ),
            "repetitions": "각 2~3회",
            "success": "어느 쪽이 더 선명한지 구분됨",
            "if_no_change": "짧은 구절에서 음량 유지 + 명료도만 유지해보세요.",
            "song_transfer": "선택한 모음 느낌을 원래 가사에 짧게 적용하세요.",
        },
    ],
    "DENSE_SOLID": [
        {
            "id": "CENTER_HOLD",
            "instruction": (
                "편한 중음에서 한 음을 1~2초 짧게 유지하세요. "
                "음량을 키우지 않은 채 소리가 중간에 흐려지지 않도록 같은 강도로 끝까지 유지하세요. "
                "접촉을 억지로 더 단단하게 만들지 마세요."
            ),
            "repetitions": "2~3회",
            "success": "밀도감이 유지되고 힘이 더 들어가지 않음",
            "if_no_change": "2~3음 짧은 패턴으로 같은 음량 고정 유지를 옮기세요.",
            "song_transfer": "유지되는 강도를 짧은 원곡 구절에 적용하세요.",
        },
    ],
    "SOFT_SWEET": [
        {
            "id": "SMOOTH_PHRASE",
            "instruction": (
                "작은~중간 강도에서 짧은 구절을 2~3회 부르세요. "
                "음절 사이를 급하게 끊지 말고 매끄럽게 같은 편안한 강도로 이어주세요. "
                "숨을 일부러 더 섞지 마세요."
            ),
            "repetitions": "2~3회",
            "success": "거칠게 끊기지 않고 힘이 더 들어가지 않음",
            "if_no_change": "더 짧은 구절만 골라 같은 강도로 이어보세요.",
            "song_transfer": "편안한 연결을 원래 가사에 짧게 적용하세요.",
        },
    ],
    "AIRY_DELICATE": [
        {
            "id": "DELICATE",
            "instruction": (
                "작은 강도에서 짧은 구절을 섬세하게 부르세요. "
                "숨을 일부러 많이 새게 만들지 말고, 소리가 중간에 사라지면 중단하세요."
            ),
            "success": "섬세함이 유지되고 숨이 과하게 새지 않음",
            "if_no_change": "더 짧은 구간만 골라 같은 작은 강도로 반복하세요.",
        },
    ],
    "INTENSE_DISTINCT": [
        {
            "id": "TEXTURE",
            "instruction": (
                "짧은 구절에서 음량은 그대로 두고 "
                "자음 시작과 리듬의 대비를 조금 더 분명하게 해보세요."
            ),
            "repetitions": "2~3회",
            "success": "개성이 더 느껴지고 음량이 갑자기 커지지 않음",
            "if_no_change": "같은 음량에서 질감만 조금 더 분명한 표현을 짧게 연습하세요.",
        },
    ],
    "NASAL_PERCEPT": [
        {
            "id": "ISOLATE",
            "instruction": (
                "콧소리처럼 느껴지는 모음·음절 하나만 골라, "
                "같은 음높이·같은 음량으로 2~3회 짧게 반복하세요. "
                "자음 뒤 모음을 길게 누르지 말고 조금 더 분명하게 시작한 뒤 "
                "바로 다음 음으로 연결하세요."
            ),
            "repetitions": "2~3회",
            "success": "콧소리처럼 느껴지는 인상이 줄어듦",
            "if_no_change": (
                "같은 음형에서 모음 형태를 조금 바꿔보세요 "
                "(예: 아↔어/에). 특정 모음이 정답이라고 단정하지 말고 "
                "현재 편하게 더 자연스럽게 들리는 쪽을 고르세요."
            ),
            "song_transfer": "좋아진 방식을 문제 음절 → 짧은 구절 → 원래 가사 순으로 적용하세요.",
        },
    ],
    "MUFFLED": [
        {
            "id": "ARTIC_CONNECT",
            "instruction": (
                "답답하게 느껴지는 한 구절을 편한 음량으로 2~3번 부르세요. "
                "자음 시작을 조금 더 분명하게 하고, "
                "모음을 길게 눌러 끌지 말고 다음 음으로 또렷하게 이어주세요."
            ),
            "repetitions": "2~3회",
            "success": "답답한 느낌이 줄어듦",
            "if_no_change": (
                "그래도 답답하면 같은 음형을 '에'나 '이'처럼 "
                "현재 편하게 선명하게 들리는 모음으로 "
                "2~3번 부른 뒤 원래 가사로 돌아오세요."
            ),
            "song_transfer": "좋아진 표현을 짧은 원곡 구절에 그대로 적용해보세요.",
        },
    ],
    "THIN": [
        {
            "id": "VOWEL_REGISTER",
            "instruction": (
                "얇게 느껴지는 구절에서 먼저 '우'처럼 편하게 이어지는 모음으로 "
                "중음에서 위쪽 음역까지 3회 천천히 연결해보세요. "
                "음이 올라가도 음량을 키우지 마세요. "
                "끊기지 않고 이어지면 같은 움직임을 원래 가사로 바꿔보세요."
            ),
            "repetitions": "3회",
            "success": "얇게 느껴지는 인상이 줄어듦",
            "if_no_change": (
                "그래도 얇게 느껴지면 음역 범위를 조금 줄여 "
                "편한 중음부터 다시 연결하세요."
            ),
            "song_transfer": "연결이 유지되면 원래 가사에 같은 움직임을 적용하세요.",
        },
    ],
    "DYNAMICS": [
        {
            "id": "SMALL_DYN",
            "instruction": (
                "편한 강도로 짧은 구절을 유지한 뒤, "
                "같은 구절에 작은 강약 변화만 추가해보세요. 처음부터 큰 소리로 연습하지 마세요."
            ),
            "success": "강약 변화 중 음높이·안정·힘이 유지됨",
            "if_no_change": "더 짧은 구간에서만 작은 강약을 시도하세요.",
        },
    ],
    "PHRASE_END": [
        {
            "id": "SHORT_END",
            "instruction": "조금 짧은 구절부터 끝까지 같은 편안함을 유지하세요. 길게 세게 버티지 마세요.",
            "success": "끝음에서 소리가 갑자기 약해지지 않음",
            "if_no_change": "더 짧은 끝 구간만 반복한 뒤 길이를 조금씩 늘리세요.",
        },
    ],
    "HIGH_NOTE_ACCESS": [
        {
            "id": "EASY_CLIMB",
            "instruction": (
                "편한 중음에서 작은 강도로 시작해, "
                "세게 밀지 않은 채 위쪽 음역으로 한 음씩 범위를 넓혀보세요. "
                "닿기 어려운 지점에서는 음량을 키우지 마세요."
            ),
            "repetitions": "3~5회",
            "success": "고음 접근이 조금 더 편해지고 힘·음량이 갑자기 커지지 않음",
            "if_no_change": "음역 범위를 줄이고 더 작은 강도로 다시 시도하세요.",
            "song_transfer": "편한 범위가 잡히면 짧은 원곡 구절에 적용하세요.",
        },
    ],
    "VIBRATO": [
        {
            "id": "NATURAL",
            "instruction": "억지로 크게 만들지 말고, 짧은 지속음에서 자연스러운 흔들림이 생기는지 확인하세요.",
            "success": "자연스러운 흔들림 유지, 불편 없음",
            "if_no_change": "더 짧은 지속만 유지한 채 확인하세요.",
        },
    ],
}


def _effort_level(snap: dict[str, Any]) -> str:
    return str((snap.get("effort") or {}).get("level") or "").upper()


def _reg(snap: dict[str, Any]) -> str:
    st = str((snap.get("register") or {}).get("status") or "").upper()
    if st in ("DISRUPTED", "UNSTABLE", "TRANSITION_EVENTS", "BREAK"):
        return "DISRUPTED"
    if st in ("PARTIAL", "MIXED", "INSUFFICIENT"):
        return "PARTIAL"
    if st in ("CONNECTED", "SMOOTH", "STABLE"):
        return "CONNECTED"
    return "UNKNOWN"


def _breath(snap: dict[str, Any]) -> str:
    return str((snap.get("breathiness") or {}).get("level") or "").upper()


def _presence_bucket(snap: dict[str, Any]) -> str:
    p = (snap.get("timbre") or {}).get("presence")
    try:
        v = float(p) if p is not None else None
    except (TypeError, ValueError):
        v = None
    if v is None:
        return "UNAVAILABLE"
    if v <= 0.42:
        return "LOW"
    if v >= 0.58:
        return "HIGH"
    return "MID"


def _brightness_bucket(snap: dict[str, Any]) -> str:
    b = (snap.get("timbre") or {}).get("brightness")
    try:
        v = float(b) if b is not None else None
    except (TypeError, ValueError):
        v = None
    if v is None:
        return "UNAVAILABLE"
    if v <= 0.42:
        return "LOW"
    if v >= 0.58:
        return "HIGH"
    return "MID"


def _stab_ok(snap: dict[str, Any]) -> Optional[bool]:
    st = str((snap.get("stability") or {}).get("status") or "").upper()
    if not st or st == "UNKNOWN":
        return None
    if st in ("STABLE", "LOW", "NORMAL", "OK_PROXY"):
        return True
    if st in ("UNSTABLE", "HIGH", "IRREGULAR"):
        return False
    return None


def _goal_id(timbre_goal: Any) -> Optional[str]:
    if isinstance(timbre_goal, str) and timbre_goal:
        return timbre_goal.upper()
    if isinstance(timbre_goal, dict):
        return str(timbre_goal.get("id") or "").upper() or None
    return None


def ladder_cue(family: str, index: int = 0) -> dict[str, Any]:
    ladder = CUE_LADDERS.get(family) or []
    if not ladder:
        return {}
    return dict(ladder[min(index, len(ladder) - 1)])


def pick_perceptual_family(concern_id: str, snap: dict[str, Any]) -> str:
    cid = str(concern_id or "").upper()
    if cid == "HIGH_NOTE_CANNOT_REACH":
        if _reg(snap) in ("DISRUPTED", "PARTIAL"):
            return "REGISTER"
        if _effort_level(snap) in ("HIGH", "MODERATE"):
            return "EFFORT"
        if _stab_ok(snap) is False:
            return "STABILITY"
        return "HIGH_NOTE_ACCESS"
    if cid.startswith("HIGH_NOTE") or cid in ("REGISTER_CONNECTION_DIFFICULT",):
        if _reg(snap) in ("DISRUPTED", "PARTIAL"):
            return "REGISTER"
        if _effort_level(snap) in ("HIGH", "MODERATE"):
            return "EFFORT"
        if cid == "HIGH_NOTE_UNSTABLE" and _stab_ok(snap) is False:
            return "STABILITY"
        # Flips / connection difficulty: register protocol is the semantic default
        return "REGISTER"
    if cid == "VOICE_TOO_NASAL_PERCEPT":
        return "NASAL_PERCEPT"
    if cid == "VOICE_TOO_DARK_MUFFLED":
        if _brightness_bucket(snap) == "LOW":
            return "BRIGHT_CLEAR"
        if _presence_bucket(snap) == "LOW":
            return "PRESENCE"
        return "MUFFLED"
    if cid in ("VOICE_TOO_THIN", "HIGH_NOTE_THINS"):
        if _breath(snap) == "HIGH":
            return "BREATHINESS"
        if _presence_bucket(snap) == "LOW":
            return "PRESENCE"
        if _reg(snap) == "DISRUPTED":
            return "REGISTER"
        # PARTIAL / other: concrete vowel→register action (not abstract "소리 중심")
        return "THIN"
    if cid == "VOICE_TOO_BREATHY":
        # Concern is breathiness-perception; do not collapse onto THIN ladder
        return "BREATHINESS"
    if cid == "VOICE_TOO_SHARP":
        return "SOFT_SWEET"
    if cid == "VOICE_ROUGH":
        if _stab_ok(snap) is False:
            return "STABILITY"
        if _breath(snap) == "HIGH":
            return "BREATHINESS"
        contact = str((snap.get("contact") or {}).get("status") or "").upper()
        if contact == "FIRM":
            return "SOFT_SWEET"
        return "STABILITY"
    if cid == "TIMBRE_CHANGES_HIGH":
        return "REGISTER" if _reg(snap) in ("DISRUPTED", "PARTIAL") else "BRIGHT_CLEAR"
    if cid in ("PITCH_UNSTABLE", "VIBRATO_UNSTABLE"):
        return "STABILITY"
    if cid == "DYNAMICS_DIFFICULT":
        if _effort_level(snap) in ("HIGH", "MODERATE"):
            return "EFFORT"
        return "DYNAMICS"
    if cid == "PHRASE_END_WEAK":
        if _stab_ok(snap) is False:
            return "STABILITY"
        if _breath(snap) == "HIGH":
            return "BREATHINESS"
        return "PHRASE_END"
    return "MUFFLED"


def pick_target_family(target_id: Optional[str]) -> str:
    tid = str(target_id or "").upper()
    mapping = {
        "BRIGHT_CLEAR": "BRIGHT_CLEAR",
        "DENSE_SOLID": "DENSE_SOLID",
        "SOFT_SWEET": "SOFT_SWEET",
        "LIGHT_CLEAR": "BRIGHT_CLEAR",
        "WARM_FULL": "DENSE_SOLID",
        "AIRY_DELICATE": "AIRY_DELICATE",
        "INTENSE_DISTINCT": "INTENSE_DISTINCT",
    }
    return mapping.get(tid, "SOFT_SWEET")


def observed_profile_sentences(snap: dict[str, Any]) -> list[str]:
    bits: list[str] = []
    breath = _breath(snap)
    if breath == "LOW":
        bits.append("숨 섞임이 적은 편")
    elif breath == "HIGH":
        bits.append("숨 섞임이 두드러지는 편")
    stab = _stab_ok(snap)
    if stab is True:
        bits.append("발성 안정성이 유지되는 편")
    elif stab is False:
        bits.append("안정성이 떨어지는 구간이 있는 편")
    pb = _presence_bucket(snap)
    if pb == "HIGH":
        bits.append("중역 존재감이 비교적 분명한 편")
    elif pb == "LOW":
        bits.append("중역 존재감이 다소 낮은 편")
    bb = _brightness_bucket(snap)
    if bb == "HIGH":
        bits.append("밝기가 밝은 쪽에 가까운 편")
    elif bb == "LOW":
        bits.append("밝기가 어두운 쪽에 가까운 편")
    reg = _reg(snap)
    if reg == "CONNECTED":
        bits.append("성구 연결이 비교적 자연스러운 편")
    elif reg == "PARTIAL":
        bits.append("성구 연결이 일부 구간에서만 이어지는 편")
    elif reg == "DISRUPTED":
        bits.append("성구 전환이 급격한 편")
    effort = _effort_level(snap)
    if effort in ("HIGH", "MODERATE"):
        bits.append("일부 구간에서 힘 사용이 증가하는 편")
    elif effort == "LOW" and (snap.get("effort") or {}).get("available"):
        bits.append("힘 사용이 낮은 편")
    return bits[:5]


def descriptive_impression(bits: list[str]) -> str:
    joined = "·".join(bits[:3]) if bits else "관찰된 음색 특징"
    if any("숨 섞임이 적" in b for b in bits) and any("안정" in b for b in bits):
        return "이 조합은 가볍고 정돈된 인상과 함께 나타날 수 있습니다."
    if any("어두운" in b for b in bits) or any("존재감이 다소 낮" in b for b in bits):
        return "이 조합은 다소 답답하거나 무게감 있는 인상과 관련될 수 있습니다."
    if any("밝은" in b for b in bits):
        return "이 조합은 비교적 선명하거나 밝은 인상과 관련될 수 있습니다."
    return f"이 조합({joined})은 현재 음색 인상과 관련될 수 있습니다."


def is_abstract_only(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return True
    # Has concrete HOW markers?
    how_markers = (
        "립트릴",
        "빨대",
        "1~2초",
        "2~3초",
        "3~5회",
        "자음",
        "모음",
        "음량",
        "이어 올리",
        "립트릴",
        "구절을",
        "짧게",
        "한 번",
        "두 번째",
        "비교",
        "유지한 뒤",
        "유지하세요",
    )
    has_how = any(m in t for m in how_markers) and len(t) > 40
    if "원하는 느낌" in t and not has_how:
        return True
    for bad in ABSTRACT_STANDALONE:
        if t == bad or t.rstrip(".") == bad.rstrip("."):
            return True
        if bad in t and not has_how:
            return True
    return False


def contains_anatomy(text: str) -> bool:
    return any(b in str(text or "") for b in _ANATOMY_BANNED)


def build_descriptive_depth(
    snap: dict[str, Any],
    *,
    timbre_goal: Any = None,
) -> dict[str, Any]:
    bits = observed_profile_sentences(snap)
    impression = descriptive_impression(bits)
    if bits:
        observed_text = "이번 노래의 음색은 " + ", ".join(bits) + "이에요."
    else:
        observed_text = "이번 노래에서 뚜렷하게 잡힌 음색 축은 제한적이에요."
    interpretation = f"{observed_text} {impression}".strip()
    tid = _goal_id(timbre_goal)
    target_cue = None
    what = ""
    if tid and tid != "RECOMMEND_FOR_ME":
        fam = pick_target_family(tid)
        cue = ladder_cue(fam, 0)
        target_cue = cue
        what = str(cue.get("instruction") or "")
        label_lead = {
            "BRIGHT_CLEAR": "밝고 선명한 쪽을 원한다면",
            "DENSE_SOLID": "밀도 있고 단단한 쪽을 원한다면",
            "SOFT_SWEET": "부드럽고 감미로운 쪽을 원한다면",
            "AIRY_DELICATE": "공기감 있고 여린 쪽을 원한다면",
            "INTENSE_DISTINCT": "강렬하고 개성 있는 쪽을 원한다면",
            "LIGHT_CLEAR": "가볍고 맑은 쪽을 원한다면",
            "WARM_FULL": "따뜻하고 풍성한 쪽을 원한다면",
        }.get(tid, "원하는 음색 방향을 위해")
        if what:
            interpretation = f"{interpretation} {label_lead} {what}".strip()
    return {
        "interpretation": interpretation,
        "what_to_change": what,
        "comparison": None,
        "force_comparison": False,
        "target_cue": target_cue,
        "observed_axes": bits,
        "cue_family": pick_target_family(tid) if tid else None,
        "if_no_change": (target_cue or {}).get("if_no_change"),
        "success_cues": dedupe_success_cues([str((target_cue or {}).get("success") or "힘이 더 들어가지 않음")]) if target_cue else [],
    }



def koreanize_user_copy(text: str) -> str:
    """Replace English user-facing tokens with Korean (ids untouched upstream)."""
    t = str(text or "")
    if not t:
        return t
    # Longer phrases first
    reps = (
        ("same pitch", "같은 음높이"),
        ("Same pitch", "같은 음높이"),
        ("pitch·", "음높이·"),
        ("pitch·안정", "음높이·안정"),
        ("pitch/stability", "음높이·안정"),
        ("pitch", "음높이"),
        ("phrase legato", "구절을 이어서"),
        ("짧은 phrase", "짧은 구절"),
        ("실제 phrase", "실제 구절"),
        ("원곡 phrase", "원곡 구절"),
        ("phrase에서", "구절에서"),
        ("phrase", "구절"),
        ("짧은 glide", "음역을 이어 올리기"),
        ("작은 강도 glide", "작은 강도로 음역을 이어 올리기"),
        ("glide하세요", "이어 올리세요"),
        ("glide를", "이어 올리기를"),
        ("glide", "이어 올리기"),
        ("짧은 sustain", "짧은 한 음 유지"),
        ("sustain에서", "한 음 유지에서"),
        ("sustain", "한 음 유지"),
        ("onset", "소리 시작"),
        ("덜 몰려 들리는", "더 자연스럽게 들리는"),
        ("덜 몰려", "콧소리처럼 느껴지는 인상이 덜한"),
        ("힘 증가 없음", "힘이 더 들어가지 않음"),
        ("음량 증가 없음", "음량이 갑자기 커지지 않음"),
        ("2\\~", "2~"),
        ("3\\~", "3~"),
        ("1\\~", "1~"),
    )
    for a, b in reps:
        t = t.replace(a, b)
    return t


def _success_cue_key(cue: str) -> str:
    t = koreanize_user_copy(str(cue or "")).strip().lower()
    t = t.replace(" ", "").replace("·", "").replace(",", "").replace(".", "")
    # Semantic buckets
    effort_keys = ("힘증가없음", "힘이더들어가지않음", "힘이늘지않음", "힘사용은늘지않음", "힘·불편감이늘지않음", "힘이나불편감이늘지않음")
    volume_keys = ("음량증가없음", "음량이갑자기커지지않음", "음량급증없음", "음량을키우지않음")
    thin_keys = ("얇은인상감소", "얇게느껴지는인상이줄어듦", "얇게느껴지는인상이줄")
    muffled_keys = ("답답한느낌이줄어듦", "답답한느낌이줄")
    clarity_keys = ("더또렷하게들림", "더선명하게들림", "같은음량에서도더또렷", "같은음량에서도더선명")
    nasal_keys = ("콧소리처럼느껴지는인상감소", "콧소리처럼느껴지는인상이줄어듦")
    for bucket, keys in (
        ("effort", effort_keys),
        ("volume", volume_keys),
        ("thin", thin_keys),
        ("muffled", muffled_keys),
        ("clarity", clarity_keys),
        ("nasal", nasal_keys),
    ):
        if any(k in t for k in keys):
            return bucket
    return t


def dedupe_success_cues(cues: list[str] | None, *, family: str = "") -> list[str]:
    """Exact + semantic dedup for user-facing success cues."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in cues or []:
        s = koreanize_user_copy(str(raw or "").strip())
        if not s:
            continue
        # Split compound "A, B" into parts when clearly duplicated themes
        parts = [p.strip() for p in s.replace("，", ",").split(",") if p.strip()]
        if len(parts) > 1 and any(
            _success_cue_key(p) in ("effort", "volume") for p in parts
        ):
            for p in parts:
                key = _success_cue_key(p)
                if key in seen:
                    continue
                seen.add(key)
                out.append(p)
            continue
        key = _success_cue_key(s)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    # Ensure family-specific canonical set when thin/muffled/nasal leave only 1 cue
    defaults = {
        "THIN": [
            "얇게 느껴지는 인상이 줄어듦",
            "음량이 갑자기 커지지 않음",
            "힘이나 불편감이 늘지 않음",
        ],
        "MUFFLED": [
            "답답한 느낌이 줄어듦",
            "같은 음량에서도 더 또렷하게 들림",
            "힘이나 불편감이 늘지 않음",
        ],
        "BRIGHT_CLEAR": [
            "답답한 느낌이 줄어듦",
            "같은 음량에서도 더 또렷하게 들림",
            "힘이나 불편감이 늘지 않음",
        ],
        "NASAL_PERCEPT": [
            "콧소리처럼 느껴지는 인상이 줄어듦",
            "원래 음높이에서도 자연스럽게 이어짐",
            "힘이나 불편감이 늘지 않음",
        ],
    }
    fam = str(family or "").upper()
    if fam in defaults and len(out) < 3:
        for d in defaults[fam]:
            key = _success_cue_key(d)
            if key not in seen:
                seen.add(key)
                out.append(d)
    return out[:4]


def build_prescription(
    *,
    instruction: str,
    alternate: str = "",
    success: str | list[str] | None = None,
    repetitions: str = "",
    song_transfer: str = "",
    cue: dict[str, Any] | None = None,
    qtype: str = "",
    cue_family: str = "",
    concern_id: str = "",
) -> dict[str, Any] | None:
    """User-facing prescription (UX v9). Comparison stays internal."""
    cue = cue or {}
    instruction = koreanize_user_copy(str(instruction or cue.get("instruction") or "").strip())
    if not instruction or is_abstract_only(instruction):
        return None
    if qtype == TYPE_SAFETY:
        return None
    # Concern-specific entry framing (shared primitive OK; entry wording should differ)
    _ENTRY_FRAME = {
        "VOICE_TOO_BREATHY": "숨 섞임이 과해지지 않는 쪽으로, ",
        "VOICE_TOO_THIN": "얇게 느껴지지 않는 쪽으로, ",
        "VOICE_TOO_SHARP": "날카로움이 덜한 쪽으로, ",
        "VOICE_ROUGH": "거친 인상이 덜한 쪽으로, ",
        "VOICE_TOO_DARK_MUFFLED": "답답·어두운 인상이 덜한 쪽으로, ",
        "VOICE_TOO_NASAL_PERCEPT": "콧소리처럼 들리지 않는 쪽으로, ",
        "HIGH_NOTE_THINS": "고음에서 얇아지지 않는 쪽으로, ",
        "TIMBRE_CHANGES_HIGH": "고음 음색이 급격히 바뀌지 않는 쪽으로, ",
        "OTHER_CONCERN": "지금 궁금한 표현을 기준으로, ",
        "THROAT_EFFORT": "목으로 밀지 않는 쪽으로, ",
        "LOUD_VOICE_DIFFICULT": "큰 소리에서도 편한 쪽으로, ",
        "VOCAL_FATIGUE": "피로가 덜 쌓이는 쪽으로, ",
        "AFTER_SINGING_FATIGUE": "부른 뒤 피로가 덜한 쪽으로, ",
        "HIGH_NOTE_TOO_EFFORTFUL": "고음에서 힘을 덜 쓰는 쪽으로, ",
        "PITCH_UNSTABLE": "음정이 덜 흔들리는 쪽으로, ",
        "HIGH_NOTE_UNSTABLE": "고음 흔들림이 덜한 쪽으로, ",
        "VIBRATO_UNSTABLE": "자연스러운 흔들림이 유지되는 쪽으로, ",
        "REGISTER_CONNECTION_DIFFICULT": "중·고음 연결이 끊기지 않는 쪽으로, ",
        "HIGH_NOTE_FLIPS": "뒤집힘이 덜한 쪽으로, ",
        "HIGH_NOTE_CANNOT_REACH": "고음 접근이 편한 쪽으로, ",
    }
    frame = _ENTRY_FRAME.get(str(concern_id or "").upper())
    if frame and frame not in instruction:
        instruction = frame + instruction
    # Only show repetitions when cue provides a meaningful count (not forced everywhere)
    reps = koreanize_user_copy(str(repetitions or cue.get("repetitions") or "").strip())
    alt = koreanize_user_copy(str(alternate or cue.get("if_no_change") or "").strip())
    transfer = koreanize_user_copy(str(song_transfer or cue.get("song_transfer") or "").strip())
    if not transfer:
        transfer = "좋아진 방식을 짧은 원곡 구절에 적용해보세요."
    cues: list[str] = []
    if isinstance(success, list):
        cues = [str(s) for s in success if s]
    elif success:
        cues = [str(success)]
    elif cue.get("success"):
        cues = [str(cue.get("success"))]
    if not cues:
        cues = ["목표 음색에 더 가깝고 힘·음량이 갑자기 커지지 않음"]
    # Concern-specific success lead (shared primitive OK; success should differ by question)
    _SUCCESS_LEAD = {
        "HIGH_NOTE_FLIPS": "뒤집힘·갑작스러운 전환이 줄어듦",
        "HIGH_NOTE_CANNOT_REACH": "고음 접근이 조금 더 편해짐",
        "REGISTER_CONNECTION_DIFFICULT": "중·고음 연결이 더 이어짐",
        "HIGH_NOTE_UNSTABLE": "고음에서 흔들림이 줄어듦",
        "HIGH_NOTE_TOO_EFFORTFUL": "같은 음높이에서 밀기가 줄어듦",
        "HIGH_NOTE_THINS": "고음에서 얇게 느껴지는 인상이 줄어듦",
        "VOICE_ROUGH": "거친 인상이 줄어듦",
        "VOICE_TOO_SHARP": "날카로운 인상이 줄어듦",
        "VOICE_TOO_BREATHY": "숨 섞임 인상이 줄어듦",
        "VOICE_TOO_THIN": "얇게 느껴지는 인상이 줄어듦",
        "VOICE_TOO_DARK_MUFFLED": "답답·어두운 인상이 줄어듦",
        "VOICE_TOO_NASAL_PERCEPT": "콧소리처럼 들리는 인상이 줄어듦",
        "DYNAMICS_DIFFICULT": "강약 변화 중 안정이 유지됨",
        "PHRASE_END_WEAK": "끝음이 갑자기 약해지지 않음",
        "PITCH_UNSTABLE": "음정 흔들림이 줄어듦",
        "VIBRATO_UNSTABLE": "비브라토 흔들림이 자연스럽게 유지됨",
        "THROAT_EFFORT": "목 쪽 힘으로 밀지 않게 됨",
        "LOUD_VOICE_DIFFICULT": "큰 소리에서도 불편이 덜함",
        "VOCAL_FATIGUE": "짧은 연습 후 피로감이 덜함",
        "AFTER_SINGING_FATIGUE": "부른 뒤 피로감이 덜함",
        "TIMBRE_CHANGES_HIGH": "고음에서 음색 변화가 덜 급격함",
        "OTHER_CONCERN": "목표한 표현이 조금 더 분명해짐",
        "TIMBRE_DISSATISFIED": "목표 음색에 더 가까워짐",
    }
    lead = _SUCCESS_LEAD.get(str(concern_id or "").upper())
    if lead and lead not in cues:
        cues = [lead] + cues
    fam = str(cue_family or cue.get("family") or "")
    cues = dedupe_success_cues(cues, family=fam)
    out: dict[str, Any] = {
        "title": "이렇게 해보세요",
        "instruction": instruction,
        "success_cues": cues[:4],
        "song_transfer": transfer,
    }
    if reps:
        out["repetitions"] = reps
    if alt:
        out["alternate"] = {
            "title": "그래도 잘 안 되면",
            "instruction": alt,
        }
    return out


def attach_prescription_fields(
    depth: dict[str, Any],
    *,
    qtype: str,
    concern_id: str = "",
) -> dict[str, Any]:
    """Ensure depth carries a prescription object when applicable."""
    depth = dict(depth or {})
    if qtype == TYPE_SAFETY:
        return depth
    cue = depth.get("target_cue") if isinstance(depth.get("target_cue"), dict) else {}
    if not cue and depth.get("cue_family"):
        cue = ladder_cue(str(depth.get("cue_family")), 0)
    instruction = str(depth.get("what_to_change") or (cue or {}).get("instruction") or "")
    # DESCRIPTIVE without target cue: no prescription block required
    if qtype == TYPE_DESCRIPTIVE and not instruction:
        depth["prescription"] = None
        return depth
    cmp = depth.get("comparison") if isinstance(depth.get("comparison"), dict) else {}
    cid = str(concern_id or depth.get("concern_id") or "")
    presc = build_prescription(
        instruction=instruction,
        alternate=str(depth.get("if_no_change") or (cmp or {}).get("if_not_better") or ""),
        success=depth.get("success_cues") or (cmp or {}).get("success_condition"),
        repetitions=str((cue or {}).get("repetitions") or ""),
        song_transfer=str((cue or {}).get("song_transfer") or ""),
        cue=cue or None,
        qtype=qtype,
        cue_family=str(depth.get("cue_family") or ""),
        concern_id=cid,
    )
    depth["prescription"] = presc
    return depth


def build_perceptual_depth(
    concern_id: str,
    snap: dict[str, Any],
    *,
    interpretation: str = "",
) -> dict[str, Any]:
    fam = pick_perceptual_family(concern_id, snap)
    cue = ladder_cue(fam, 0)
    alt = str(cue.get("if_no_change") or "")
    instruction = str(cue.get("instruction") or "")
    success = str(cue.get("success") or "목표 표현이 개선되고 힘이 더 들어가지 않음")
    # Hypothesis lead (1 sentence) — keep caller interpretation if concrete
    hyp = str(interpretation or "").strip()
    if not hyp or is_abstract_only(hyp):
        if fam == "NASAL_PERCEPT":
            hyp = (
                "콧소리가 직접 측정된 것은 아니에요. "
                "특정 모음·음절만 골라 같은 음높이에서 소리 시작을 조절해보는 게 좋아요."
            )
        elif fam in ("MUFFLED", "BRIGHT_CLEAR"):
            hyp = (
                "이번 노래에서는 밝기가 어두운 쪽으로 나타나 "
                "답답한 인상과 관련됐을 가능성이 있어요."
            )
        elif fam == "THIN":
            hyp = (
                "숨을 더 막기보다, 얇게 느껴지는 구절을 "
                "편한 모음으로 중음에서 위쪽까지 연결해보는 게 우선이에요."
            )
        elif fam == "BREATHINESS":
            hyp = "숨이 과하게 섞이는 짧은 구간부터 다루는 것이 우선이에요."
        elif fam == "REGISTER":
            hyp = "음역이 바뀔 때 연결이 급격히 달라지는 쪽을 먼저 다루는 것이 우선이에요."
        elif fam == "PRESENCE":
            hyp = "중역 존재감이 흐려지는 짧은 구간부터 다루는 것이 우선이에요."
        else:
            hyp = "관련 구간을 짧게 골라 구체적인 발음·연결 방식으로 다루는 게 우선이에요."

    instruction = koreanize_user_copy(instruction)
    alt = koreanize_user_copy(alt)
    hyp = koreanize_user_copy(hyp)
    success_list = dedupe_success_cues([success], family=fam)

    comparison = {
        "comparison_family": f"PERCEPT_{fam}",
        "baseline_label": "평소 방식",
        "baseline_instruction": "평소 부르는 방식으로 한 번",
        "variant_label": "연습 방식",
        "variant_instruction": instruction,
        "success_condition": success,
        "if_better": "그 발음·연결 방식을 유지하세요.",
        "if_not_better": alt or "더 짧은 문제 구간만 따로 다시 해보세요.",
        "A": "평소 부르는 방식으로 한 번",
        "B": instruction,
        "success": success,
        "lead": hyp,
        "alternate_cue": alt,
    }
    return {
        "interpretation": hyp,
        "what_to_change": instruction,
        "comparison": comparison,
        "force_comparison": True,
        "cue_family": fam,
        "target_cue": cue,
        "success_cues": success_list,
        "if_no_change": alt,
    }


def build_functional_control_depth(
    *,
    focus: str,
    snap: dict[str, Any],
    concern_id: str,
    interpretation: str = "",
    timbre_goal: Any = None,
) -> dict[str, Any]:
    """Reuse Coaching Protocol entry for FUNCTIONAL / CONTROL questions."""
    from audio_analyzer.diagnostic.coaching_primitives import resolve_comparison_family

    protocol = build_coaching_protocol(
        focus,
        snap=snap,
        concern_ids=[concern_id] if concern_id else None,
        target_timbre=timbre_goal,
    )
    entry = protocol.get("entry_step") or (protocol.get("steps") or [{}])[0]
    instruction = str(entry.get("instruction") or "")
    reps = str(entry.get("repetitions") or "")
    if reps and reps not in instruction:
        instruction = f"{instruction} ({reps})".strip()
    success = ", ".join((entry.get("success_cues") or [])[:3]) or "힘 증가 없이 연결·안정 개선"
    next_p = str(entry.get("next_preview") or protocol.get("if_better") or "다음 단계로 진행")
    regress = str(entry.get("regress_preview") or protocol.get("if_worse") or "한 단계 쉬운 범위로")
    hyp = str(interpretation or "").strip() or str(protocol.get("reason") or "")
    # Ensure HOW present
    if is_abstract_only(instruction):
        fam = "REGISTER" if "REGISTER" in str(focus).upper() else "STABILITY"
        if "EFFORT" in str(focus).upper():
            fam = "EFFORT"
        elif "PRESENCE" in str(focus).upper():
            fam = "PRESENCE"
        instruction = str(ladder_cue(fam, 0).get("instruction") or instruction)

    family_id = resolve_comparison_family(concern_id, primary_focus=focus) or (
        f"PROTOCOL_{protocol.get('protocol_id')}"
    )
    comparison = {
        "comparison_family": family_id,
        "baseline_label": "평소 방식",
        "baseline_instruction": "평소대로 해당 구절을 한 번",
        "variant_label": "첫 연습",
        "variant_instruction": instruction,
        "success_condition": success,
        "if_better": f"잘 되면 → {next_p}",
        "if_not_better": f"잘 안 되면 → {regress}",
        "A": "평소대로 해당 구절을 한 번",
        "B": instruction,
        "success": success,
        "lead": hyp,
        "from_protocol": True,
    }
    return {
        "interpretation": hyp,
        "what_to_change": instruction,
        "comparison": comparison,
        "force_comparison": True,
        "success_cues": list(entry.get("success_cues") or [success]),
        "coaching_protocol_ref": {
            "protocol_id": protocol.get("protocol_id"),
            "primary_focus": protocol.get("primary_focus"),
            "entry_level": protocol.get("entry_level") or 1,
            "entry_id": entry.get("id"),
            "next_preview": next_p,
            "regress_preview": regress,
            "version": protocol.get("version"),
        },
        "protocol": protocol,
    }


def apply_qa_depth_contract(
    hyp: dict[str, Any],
    snap: dict[str, Any],
    *,
    timbre_goal: Any = None,
) -> dict[str, Any]:
    """Mutate-safe: return depth fields for finalize_actionable_qa."""
    from audio_analyzer.diagnostic.question_semantics import semantics_for

    out = dict(hyp or {})
    concern_id = str(out.get("concern_id") or out.get("concern") or "")
    sem = semantics_for(concern_id) if concern_id else {}
    qtype = str(out.get("question_type") or sem.get("type") or "")
    focus = str(out.get("primary_focus") or sem.get("fallback_focus") or "MAINTAIN")
    out["question_type"] = qtype or out.get("question_type")
    snap = snap or {}

    if qtype == TYPE_SAFETY or focus == "SAFETY":
        out["qa_depth"] = {"contract": "SAFETY", "force_comparison": False, "prescription": None}
        return out

    if qtype == TYPE_DESCRIPTIVE:
        depth = attach_prescription_fields(
            build_descriptive_depth(snap, timbre_goal=timbre_goal),
            qtype=qtype,
            concern_id=concern_id,
        )
        out["interpretation"] = depth["interpretation"]
        out["what_to_change"] = depth["what_to_change"]
        out["qa_depth"] = depth
        out["qa_depth"]["contract"] = "DESCRIPTIVE"
        if depth.get("prescription"):
            out["prescription"] = depth["prescription"]
        return out

    if qtype == TYPE_PERCEPTUAL:
        depth = attach_prescription_fields(
            build_perceptual_depth(
                concern_id,
                snap,
                interpretation=str(out.get("interpretation") or ""),
            ),
            qtype=qtype,
            concern_id=concern_id,
        )
        out["interpretation"] = depth["interpretation"]
        out["what_to_change"] = depth["what_to_change"]
        out["qa_depth"] = depth
        out["qa_depth"]["contract"] = "PERCEPTUAL"
        out["prescription"] = depth.get("prescription")
        return out

    functional_focuses = {
        "REGISTER_CONNECTION",
        "EFFORT",
        "STABILITY",
        "HIGH_NOTE",
        "PRESENCE",
        "BRIGHTNESS",
        "BREATHINESS",
        "DYNAMICS",
        "CONTACT",
        "PHRASE_ENDURANCE",
        "VIBRATO_CONTROL",
    }
    if qtype in (TYPE_FUNCTIONAL, TYPE_CONTROL) or focus in functional_focuses:
        depth = attach_prescription_fields(
            build_functional_control_depth(
                focus=focus,
                snap=snap,
                concern_id=concern_id,
                interpretation=str(out.get("interpretation") or ""),
                timbre_goal=timbre_goal,
            ),
            qtype=qtype or TYPE_FUNCTIONAL,
            concern_id=concern_id,
        )
        out["interpretation"] = depth["interpretation"]
        out["what_to_change"] = depth["what_to_change"]
        out["qa_depth"] = depth
        out["qa_depth"]["contract"] = (
            "FUNCTIONAL" if qtype == TYPE_FUNCTIONAL or focus in ("REGISTER_CONNECTION", "EFFORT", "HIGH_NOTE") else "CONTROL"
        )
        out["coaching_protocol_ref"] = depth.get("coaching_protocol_ref")
        out["prescription"] = depth.get("prescription")
        return out

    # OTHER / fallback — still require concrete cue by concern family
    depth = attach_prescription_fields(
        build_perceptual_depth(concern_id or "OTHER_CONCERN", snap),
        qtype=TYPE_PERCEPTUAL,
        concern_id=concern_id,
    )
    out["qa_depth"] = {**depth, "contract": "OTHER"}
    if is_abstract_only(str(out.get("what_to_change") or "")):
        out["what_to_change"] = depth["what_to_change"]
    out["prescription"] = depth.get("prescription")
    return out


def audit_report_coherence(snap: dict[str, Any], goal: dict[str, Any]) -> dict[str, Any]:
    """Debug-only coherence checks. Never shown in production UI."""
    issues: list[str] = []
    effort = _effort_level(snap)
    mode = str(goal.get("mode") or "")
    focus = str(goal.get("primary_focus") or "")
    if effort in ("HIGH", "MODERATE") and mode == "STYLE" and focus in ("STYLE", "TIMBRE"):
        issues.append("STYLE_WITH_HIGH_EFFORT")
    reg = _reg(snap)
    if reg == "CONNECTED" and focus == "REGISTER_CONNECTION" and "DISRUPT" in str(goal):
        issues.append("REGISTER_STATE_MISMATCH")
    breath = _breath(snap)
    # Placeholder for QA breath contradiction checked elsewhere
    return {
        "canonical_consistency": {
            "effort": "FAIL" if "STYLE_WITH_HIGH_EFFORT" in issues else "PASS",
            "register": "FAIL" if "REGISTER_STATE_MISMATCH" in issues else "PASS",
            "breathiness": "PASS",
            "presence": "PASS",
            "brightness": "PASS",
        },
        "issues": issues,
        "effort_level": effort,
        "goal_mode": mode,
        "goal_focus": focus,
        "register": reg,
        "breathiness": breath,
    }


def strip_abstract_actions(text: str) -> str:
    t = str(text or "").strip()
    for bad in ABSTRACT_STANDALONE:
        if t == bad or t.rstrip(".") == bad.rstrip("."):
            return ""
    return t
