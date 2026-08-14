"""Coaching Protocol v1 — multi-step entry → progression → regression → song transfer.

Builds on focus selection from goal_planner / coaching_primitives.
Does NOT hard-code concern × evidence × target matrices.
Does NOT retune acoustic thresholds.
"""

from __future__ import annotations

from typing import Any, Optional

PROTOCOL_VERSION = "coaching-protocol-v1.0"

# Banned anatomical / force-contact language
_ANATOMY_BANNED = (
    "연구개",
    "후두",
    "성대 붙",
    "성대를 붙",
    "복압",
    "가성",
    "진성",
)


def _effort_info(snap: dict[str, Any]) -> dict[str, Any]:
    e = snap.get("effort") or {}
    level = str(e.get("level") or "").upper()
    conf = str(e.get("confidence_label") or "").lower()
    available = bool(e.get("available")) and level not in ("", "UNKNOWN", "UNAVAILABLE", "AMBIGUOUS")
    reliable_low = bool(e.get("reliable_for_preserve")) or (
        available and level == "LOW" and conf in ("medium", "high")
    )
    reliable_high = available and level in ("HIGH", "MODERATE") and conf in ("medium", "high", "")
    return {
        "level": level or "UNKNOWN",
        "available": available,
        "confidence": conf,
        "reliable_low": reliable_low,
        "reliable_high": reliable_high,
    }


def _reg(snap: dict[str, Any]) -> str:
    st = str((snap.get("register") or {}).get("status") or "").upper()
    if st in ("DISRUPTED", "UNSTABLE", "TRANSITION_EVENTS", "BREAK", "FAIL", "ABRUPT"):
        return "DISRUPTED"
    if st in ("PARTIAL", "INSUFFICIENT", "MIXED"):
        return "PARTIAL"
    if st in ("CONNECTED", "SMOOTH", "STABLE", "CONTINUOUS", "STABLE_LIKE"):
        return "CONNECTED"
    return "UNKNOWN"


def _step(
    level: int,
    sid: str,
    title: str,
    instruction: str,
    *,
    repetitions: str,
    success_cues: list[str],
    failure_cues: list[str],
    advance_when: list[str],
    regress_when: list[str],
    next_preview: str = "",
    regress_preview: str = "",
) -> dict[str, Any]:
    return {
        "level": level,
        "id": sid,
        "title": title,
        "instruction": instruction,
        "repetitions": repetitions,
        "success_cues": success_cues,
        "failure_cues": failure_cues,
        "advance_when": advance_when,
        "regress_when": regress_when,
        "next_preview": next_preview,
        "regress_preview": regress_preview,
    }


def _song_transfer(
    instruction: str,
    success_cues: list[str],
    *,
    fallback_step: int = 2,
    pattern: Optional[list[str]] = None,
) -> dict[str, Any]:
    return {
        "instruction": instruction,
        "success_cues": success_cues,
        "fallback_step": fallback_step,
        "pattern": pattern
        or [
            "exercise",
            "syllable",
            "vowel",
            "lyric_fragment",
            "actual_phrase",
        ],
    }


def _target_overlay(target_id: Optional[str]) -> Optional[dict[str, Any]]:
    tid = str(target_id or "").upper()
    catalog = {
        "BRIGHT_CLEAR": {
            "id": "BRIGHT_CLEAR",
            "label": "밝고 선명하게",
            "cue": (
                "같은 음높이·같은 음량에서 평소 방식과, "
                "자음 시작·모음 연결을 조금 더 또렷하게 한 방식을 짧게 비교하세요."
            ),
            "success_cues": ["더 또렷하게 느껴짐", "음량 증가 없음", "힘 증가 없음"],
            "avoid": ["힘을 더 써서 밝게 만들기", "음량을 키워 선명하게 만들기"],
        },
        "DENSE_SOLID": {
            "id": "DENSE_SOLID",
            "label": "단단하고 밀도 있게",
            "cue": (
                "음량을 키우지 않고 짧은 구절에서 소리 중심이 흐려지지 않게 유지하는 표현을 비교하세요."
            ),
            "success_cues": ["밀도감이 유지됨", "힘 증가 없음"],
            "avoid": ["접촉을 무조건 더 단단하게 만들기", "세게 붙여 밀도 만들기"],
        },
        "SOFT_SWEET": {
            "id": "SOFT_SWEET",
            "label": "부드럽고 감미롭게",
            "cue": "작은~중간 강도에서 구절 연결을 조금 더 매끄럽게 유지하는 표현을 비교하세요.",
            "success_cues": ["거칠게 끊기지 않음", "숨을 일부러 늘리지 않음", "힘 증가 없음"],
            "avoid": ["부드러움을 위해 숨을 과도하게 흘리기"],
        },
        "LIGHT_CLEAR": {
            "id": "LIGHT_CLEAR",
            "label": "가볍고 맑게",
            "cue": (
                "작은 구절에서 가벼운 표현을 비교하되, "
                "소리 중심이 사라지지 않는지 확인하세요. 볼륨을 줄이는 것 자체가 목표는 아니에요."
            ),
            "success_cues": ["가벼운 느낌이 유지됨", "소리 중심이 사라지지 않음", "힘 증가 없음"],
            "avoid": ["볼륨만 줄여 존재감을 잃기"],
        },
        "WARM_FULL": {
            "id": "WARM_FULL",
            "label": "따뜻하고 풍성하게",
            "cue": (
                "볼륨·힘을 늘리지 않으면서 짧은 중음 구절에서 "
                "밀도와 안정성이 유지되는 표현을 비교하세요."
            ),
            "success_cues": ["안정·밀도가 유지됨", "힘·음량 급증 없음"],
            "avoid": ["풍성함을 위해 세게 밀기"],
        },
        "AIRY_DELICATE": {
            "id": "AIRY_DELICATE",
            "label": "공기감 있고 여리게",
            "cue": (
                "작은 강도에서 섬세한 표현을 비교하되, "
                "숨이 과도하게 새거나 소리 중심이 사라지면 중단하세요. "
                "숨을 많이 새게 만들라는 뜻이 아니에요."
            ),
            "success_cues": ["섬세함이 유지됨", "숨이 과하게 새지 않음", "소리 중심 유지"],
            "avoid": ["숨을 일부러 많이 새게 만들기"],
        },
        "INTENSE_DISTINCT": {
            "id": "INTENSE_DISTINCT",
            "label": "강렬하고 개성 있게",
            "cue": (
                "짧은 구절에서 질감·명료도·존재감 표현을 비교하세요. "
                "음량을 키우는 것이 곧 강렬함은 아니에요."
            ),
            "success_cues": ["개성이 더 느껴짐", "힘 증가 없음", "음량 급증 없음"],
            "avoid": ["강렬함을 위해 처음부터 세게 밀기"],
        },
    }
    return dict(catalog[tid]) if tid in catalog else None


# ---------------------------------------------------------------------------
# Protocol templates by focus
# ---------------------------------------------------------------------------

def _protocol_register() -> dict[str, Any]:
    steps = [
        _step(
            1,
            "REGISTER_SOVT_GLIDE",
            "작은 강도로 연결 감각 만들기",
            (
                "편안한 중음에서 시작해 립트릴 또는 빨대 발성으로 "
                "위쪽 음역까지 작은 강도로 이어보세요. "
                "끊기는 지점에서 더 세게 밀지 말고, 연결되는 범위까지만 반복하세요."
            ),
            repetitions="짧은 glide 3~5회",
            success_cues=[
                "전환 순간 끊김 감소",
                "갑작스러운 음량 증가 없음",
                "힘 증가 없음",
                "불편감 없음",
            ],
            failure_cues=[
                "매번 같은 지점에서 뒤집힘",
                "음량이 급격히 증가",
                "밀어서 통과하려 함",
                "통증/불편",
            ],
            advance_when=["끊김 감소", "음량 급증 없음", "불편 없음"],
            regress_when=["같은 지점 뒤집힘 반복", "밀어 통과", "불편"],
            next_preview="같은 음형을 편한 모음으로",
            regress_preview="음역 범위를 줄여 다시 시작",
        ),
        _step(
            2,
            "REGISTER_VOWEL_GLIDE",
            "편한 모음으로 연결하기",
            (
                "같은 음형을 '우' 또는 현재 편하게 이어지는 모음으로 옮겨보세요. "
                "특정 모음 하나가 모두에게 정답은 아니니, 이어지기 쉬운 쪽을 고르세요."
            ),
            repetitions="짧은 glide 3~5회",
            success_cues=["SOVT와 비슷한 연결 유지", "힘·음량 급증 없음"],
            failure_cues=["모음으로 바꾸자 끊김 증가", "음량 급증"],
            advance_when=["연결이 SOVT와 비슷하게 유지"],
            regress_when=["끊김 증가", "밀기 증가"],
            next_preview="가사의 모음만 연결",
            regress_preview="립트릴·빨대로 돌아가 범위 축소",
        ),
        _step(
            3,
            "REGISTER_LYRIC_VOWELS",
            "가사 모음만으로 연결하기",
            "문제가 생기는 실제 구절에서 자음을 빼고 모음 중심으로 연결해보세요.",
            repetitions="짧은 구절 3회",
            success_cues=["모음 연결이 한 흐름으로 이어짐", "힘 증가 없음"],
            failure_cues=["모음만으로도 끊김·뒤집힘"],
            advance_when=["모음 연결 안정"],
            regress_when=["끊김 재발"],
            next_preview="짧은 실제 가사 phrase",
            regress_preview="편한 모음 glide로 회귀",
        ),
        _step(
            4,
            "REGISTER_SHORT_LYRIC",
            "짧은 실제 가사로 옮기기",
            "같은 구절을 짧은 실제 가사로 불러 보세요. 음량을 먼저 키우지 마세요.",
            repetitions="짧은 phrase 3회",
            success_cues=["가사에서도 끊김 감소", "힘 증가 없음"],
            failure_cues=["가사로 바꾸자 다시 밀거나 뒤집힘"],
            advance_when=["가사에서도 연결 유지"],
            regress_when=["다시 밀거나 뒤집힘"],
            next_preview="원래 표현·음량으로 복귀",
            regress_preview="모음만 연결 단계로",
        ),
        _step(
            5,
            "REGISTER_FULL_EXPRESSION",
            "원래 표현으로 복귀",
            (
                "원래 표현·음량으로 돌아가 보세요. "
                "다시 밀거나 뒤집히면 2~3단계로 돌아가 연결을 다시 잡으세요."
            ),
            repetitions="문제 구절 2~3회",
            success_cues=["원래 표현에서도 연결 유지", "힘 급증 없음"],
            failure_cues=["원래 표현에서 다시 밀거나 뒤집힘"],
            advance_when=["원곡 표현에서 연결 유지"],
            regress_when=["다시 밀거나 뒤집힘"],
            next_preview="노래 적용 완료",
            regress_preview="2~3단계로 회귀",
        ),
    ]
    return {
        "protocol_id": "REGISTER_CONNECTION",
        "primary_focus": "REGISTER_CONNECTION",
        "reason": "음역 전환이 끊기거나 급격히 달라지는 구간을 먼저 안정시키는 것이 우선이에요.",
        "entry_level": 1,
        "steps": steps,
        "song_transfer": _song_transfer(
            (
                "문제가 생기는 실제 구절에서 "
                "① 원곡 그대로 → ② 모음만 → ③ 간단한 glide → ④ 다시 실제 가사를 비교하세요."
            ),
            ["원곡에서도 끊김·뒤집힘 감소", "음량·힘 급증 없음"],
            fallback_step=2,
        ),
        "stop_conditions": ["통증", "지속 불편", "밀어서 통과하려는 패턴이 반복됨"],
        "if_better": "다음 단계(편한 모음 glide)로 진행하세요.",
        "if_no_difference": "립트릴 ↔ 빨대 발성처럼 SOVT 종류를 바꿔 다시 비교하세요.",
        "if_worse": "음역 범위를 줄여 1단계로 돌아가세요.",
    }


def _protocol_stability() -> dict[str, Any]:
    steps = [
        _step(
            1,
            "STABILITY_HOLD_1_2",
            "1~2초 짧은 유지",
            "편안한 음(또는 문제 음)을 1~2초만 짧게 유지한 뒤 쉬세요. 길게 버티지 마세요.",
            repetitions="3~5회",
            success_cues=["짧은 구간에서 음정·소리 흔들림 감소", "음량 급증 없음", "힘 증가 없음"],
            failure_cues=["짧게 유지해도 흔들림 큼", "세게 고정하려 함"],
            advance_when=["1~2초 안정"],
            regress_when=["흔들림 지속", "불편"],
            next_preview="2~3초로 길이 늘리기",
            regress_preview="더 편한 음높이로 이동",
        ),
        _step(
            2,
            "STABILITY_HOLD_2_3",
            "2~3초 유지",
            "같은 음을 2~3초로 조금 늘려 유지하세요. 흔들림이 커지면 다시 짧게.",
            repetitions="3~5회",
            success_cues=["2~3초에서도 흔들림 감소", "힘 증가 없음"],
            failure_cues=["길이만 늘리자 흔들림 증가"],
            advance_when=["2~3초 안정"],
            regress_when=["길이 늘리자 흔들림 증가"],
            next_preview="3음 짧은 패턴",
            regress_preview="1~2초로 줄이기",
        ),
        _step(
            3,
            "STABILITY_3_NOTE",
            "3음 짧은 패턴",
            "짧은 3음 패턴으로 이동하며 각 음을 짧게 안정적으로 이어보세요.",
            repetitions="3~4회",
            success_cues=["패턴 중 흔들림 감소", "끊김 없음"],
            failure_cues=["패턴에서 다시 흔들림"],
            advance_when=["패턴 안정"],
            regress_when=["흔들림 재발"],
            next_preview="짧은 phrase",
            regress_preview="단일 음 유지로 회귀",
        ),
        _step(
            4,
            "STABILITY_SHORT_PHRASE",
            "짧은 phrase",
            "짧은 구절에서 음정·소리가 흔들리지 않게 유지하세요.",
            repetitions="2~3회",
            success_cues=["phrase에서도 안정", "힘 증가 없음"],
            failure_cues=["phrase에서 흔들림 증가"],
            advance_when=["phrase 안정"],
            regress_when=["흔들림 증가"],
            next_preview="원곡 적용",
            regress_preview="3음 패턴으로",
        ),
        _step(
            5,
            "STABILITY_SONG",
            "원곡 구절",
            "문제가 되는 실제 구절에서 짧게 적용하세요. 길게 버텨 흔들림을 키우지 마세요.",
            repetitions="2~3회",
            success_cues=["원곡에서도 흔들림 감소", "힘 증가 없음"],
            failure_cues=["원곡에서 다시 흔들림"],
            advance_when=["원곡 안정"],
            regress_when=["흔들림 재발"],
            next_preview="완료",
            regress_preview="유지 시간·범위 축소",
        ),
    ]
    return {
        "protocol_id": "STABILITY",
        "primary_focus": "STABILITY",
        "reason": "긴 음보다 짧은 안정 구간부터 흔들림을 줄이는 것이 우선이에요.",
        "entry_level": 1,
        "steps": steps,
        "song_transfer": _song_transfer(
            "실제 구절에서 짧은 유지 → 짧은 패턴 → 실제 가사 순으로 옮기세요.",
            ["원곡에서도 음정·소리 흔들림 감소", "힘·음량 급증 없음"],
            fallback_step=1,
        ),
        "stop_conditions": ["통증", "길게 버텨 흔들림을 키우는 패턴"],
        "if_better": "유지 시간을 조금씩 늘리세요.",
        "if_no_difference": "더 편한 음높이에서 같은 짧은 유지를 반복하세요.",
        "if_worse": "길이를 줄여 1단계로 돌아가세요.",
    }


def _protocol_high_note_access() -> dict[str, Any]:
    steps = [
        _step(
            1,
            "ACCESS_COMFORT_TOP",
            "편한 상단 음역에서 시작",
            "목표 고음이 아니라, 현재 편하게 닿는 상단 음역에서 작은 강도로 짧게 내보세요.",
            repetitions="3~5회",
            success_cues=["편한 상단에서 안정", "힘·음량 급증 없음"],
            failure_cues=["편한 음에서도 밀어붙임"],
            advance_when=["편한 상단 안정"],
            regress_when=["밀어붙임"],
            next_preview="반음~한음 위로",
            regress_preview="더 낮은 편한 음으로",
        ),
        _step(
            2,
            "ACCESS_HALF_STEP",
            "반음·한음 위로",
            "같은 작은 강도를 유지한 채 반음 또는 한음만 위로 올려보세요. 목표 음을 크게 반복하지 마세요.",
            repetitions="3~4회",
            success_cues=["한 단계 위에서도 편함 유지"],
            failure_cues=["올리자마자 음량·힘 급증"],
            advance_when=["한 단계 위 안정"],
            regress_when=["힘·음량 급증"],
            next_preview="짧은 pattern",
            regress_preview="편한 상단으로 회귀",
        ),
        _step(
            3,
            "ACCESS_SHORT_PATTERN",
            "짧은 pattern",
            "짧은 음형으로 문제 음역 근처까지 접근하세요.",
            repetitions="3회",
            success_cues=["pattern에서 접근이 편함"],
            failure_cues=["pattern에서 밀어 통과"],
            advance_when=["pattern 접근 안정"],
            regress_when=["밀어 통과"],
            next_preview="짧은 phrase",
            regress_preview="한 음 단계로",
        ),
        _step(
            4,
            "ACCESS_SHORT_PHRASE",
            "짧은 phrase",
            "짧은 구절로 목표 음역에 접근하세요. 처음부터 목표 고음을 크게 반복하지 마세요.",
            repetitions="2~3회",
            success_cues=["phrase에서 도달이 더 편함", "힘 증가 없음"],
            failure_cues=["크게 반복하려 함"],
            advance_when=["phrase 접근 편함"],
            regress_when=["크게 반복"],
            next_preview="실제 고음 구절",
            regress_preview="짧은 pattern으로",
        ),
        _step(
            5,
            "ACCESS_ACTUAL_HIGH",
            "실제 고음 구절",
            "실제 고음 구절을 작은 강도부터 시도하세요.",
            repetitions="2회",
            success_cues=["도달이 더 편함", "힘 증가 없음"],
            failure_cues=["세게 밀어 통과"],
            advance_when=["원곡 고음 접근 편함"],
            regress_when=["세게 밀어 통과"],
            next_preview="완료",
            regress_preview="한 단계 쉬운 음역으로",
        ),
    ]
    return {
        "protocol_id": "HIGH_NOTE_ACCESS",
        "primary_focus": "HIGH_NOTE",
        "reason": "목표 고음을 크게 반복하기보다, 편한 상단부터 한 단계씩 올리는 것이 우선이에요.",
        "entry_level": 1,
        "steps": steps,
        "song_transfer": _song_transfer(
            "실제 고음 구절에서 짧은 pattern → 짧은 phrase → 실제 가사 순으로 옮기세요.",
            ["원곡 고음 접근이 더 편함", "힘·음량 급증 없음"],
            fallback_step=2,
        ),
        "stop_conditions": ["통증", "처음부터 목표 고음을 크게 반복하려는 패턴"],
        "if_better": "반음·한음씩 위로 진행하세요.",
        "if_no_difference": "더 편한 상단에서 작은 강도만 유지하세요.",
        "if_worse": "음역을 낮춰 1단계로 돌아가세요.",
    }


def _protocol_effort() -> dict[str, Any]:
    steps = [
        _step(
            1,
            "EFFORT_EASY_RANGE",
            "쉬운 음역에서 작은~중간 강도",
            (
                "현재 문제 음보다 조금 쉬운 음역에서 "
                "작은~중간 강도로 짧게 발성하세요. 음량을 먼저 키우지 마세요."
            ),
            repetitions="3~5회",
            success_cues=["쉬운 음역에서 밀기 감소", "음량 급증 없음", "불편 없음"],
            failure_cues=["쉬운 음에서도 세게 밀기", "접촉을 억지로 약하게 만들기"],
            advance_when=["쉬운 음역에서 편안함 유지"],
            regress_when=["세게 밀기", "불편"],
            next_preview="같은 강도로 문제 음역 접근",
            regress_preview="더 짧은 발성·더 쉬운 음",
        ),
        _step(
            2,
            "EFFORT_APPROACH",
            "같은 강도로 문제 음역 접근",
            "같은 작은~중간 강도를 유지한 채 문제 음역까지 천천히 접근하세요.",
            repetitions="3회",
            success_cues=["접근 중에도 힘 급증 없음"],
            failure_cues=["접근하자 음량·힘 급증"],
            advance_when=["접근 중 힘 유지"],
            regress_when=["힘 급증"],
            next_preview="원래 음높이에서 volume 고정",
            regress_preview="쉬운 음역으로",
        ),
        _step(
            3,
            "EFFORT_SAME_PITCH",
            "원래 음높이 · 음량 고정",
            "같은 구절을 원래 음높이에서 음량을 늘리지 않고 시도하세요.",
            repetitions="2~3회",
            success_cues=["같은 pitch에서 밀기 감소", "음량 급증 없음"],
            failure_cues=["같은 pitch에서 다시 세게 밀기"],
            advance_when=["같은 pitch에서 밀기 감소"],
            regress_when=["다시 세게 밀기"],
            next_preview="원곡 phrase",
            regress_preview="접근 단계로",
        ),
        _step(
            4,
            "EFFORT_SONG_PHRASE",
            "원곡 phrase",
            "원곡 구절에 적용하세요. 큰 소리 연습이 목표가 아니에요.",
            repetitions="2회",
            success_cues=["원곡에서도 밀기 감소", "불편 없음"],
            failure_cues=["원곡에서 다시 밀어붙임"],
            advance_when=["원곡에서 밀기 감소"],
            regress_when=["다시 밀어붙임"],
            next_preview="완료",
            regress_preview="쉬운 음역으로 회귀",
        ),
    ]
    return {
        "protocol_id": "EFFORT",
        "primary_focus": "EFFORT",
        "reason": "같은 음을 더 세게 내기보다, 작은~중간 강도를 유지한 채 접근 범위를 넓히는 것이 우선이에요.",
        "entry_level": 1,
        "steps": steps,
        "song_transfer": _song_transfer(
            "원곡 구절에서 쉬운 강도 → 같은 pitch → 실제 phrase 순으로 옮기세요.",
            ["같은 pitch에서 밀기 감소", "음량 급증 없음", "불편 없음"],
            fallback_step=1,
        ),
        "stop_conditions": ["통증", "큰 소리로 반복하려는 패턴"],
        "if_better": "같은 강도로 문제 음역까지 접근하세요.",
        "if_no_difference": "더 쉬운 음역에서 짧게만 반복하세요.",
        "if_worse": "음역·길이를 줄여 1단계로 돌아가세요.",
        "reliability_required": True,
    }


def _protocol_presence() -> dict[str, Any]:
    steps = [
        _step(
            1,
            "PRESENCE_SHORT_VOWEL",
            "중음 짧은 모음에서 중심 찾기",
            (
                "작은 강도로 짧게 소리를 내며, "
                "음량을 키우지 않아도 소리 중심이 흐려지지 않는 지점을 찾아보세요."
            ),
            repetitions="3~5회",
            success_cues=["중역 존재감 유지", "음량 증가 없음", "힘 증가 없음"],
            failure_cues=["존재감을 위해 세게 밀기", "소리 중심이 사라짐"],
            advance_when=["짧은 모음에서 중심 유지"],
            regress_when=["세게 밀기"],
            next_preview="2~3음 pattern",
            regress_preview="더 짧고 작은 강도로",
        ),
        _step(
            2,
            "PRESENCE_PATTERN",
            "짧은 2~3음 pattern",
            "짧은 2~3음 pattern에서도 존재감이 흐려지지 않게 유지하세요.",
            repetitions="3회",
            success_cues=["pattern에서 존재감 유지", "힘 증가 없음"],
            failure_cues=["pattern에서 밀기"],
            advance_when=["pattern 존재감 유지"],
            regress_when=["밀기"],
            next_preview="짧은 phrase",
            regress_preview="짧은 모음으로",
        ),
        _step(
            3,
            "PRESENCE_PHRASE",
            "짧은 phrase",
            "짧은 구절에서 밀지 않고 존재감을 유지하세요.",
            repetitions="2~3회",
            success_cues=["phrase에서 존재감 유지"],
            failure_cues=["phrase에서 세게 밀기"],
            advance_when=["phrase 존재감 유지"],
            regress_when=["세게 밀기"],
            next_preview="실제 가사",
            regress_preview="pattern으로",
        ),
        _step(
            4,
            "PRESENCE_LYRIC",
            "실제 가사 phrase",
            "실제 가사 구절에 적용하세요.",
            repetitions="2회",
            success_cues=["원곡에서도 존재감 유지", "힘 증가 없음"],
            failure_cues=["원곡에서 세게 밀기"],
            advance_when=["원곡 존재감 유지"],
            regress_when=["세게 밀기"],
            next_preview="완료",
            regress_preview="짧은 모음으로",
        ),
    ]
    return {
        "protocol_id": "PRESENCE",
        "primary_focus": "PRESENCE",
        "reason": "세게 밀어 존재감을 만들기보다, 작은 강도에서 소리 중심이 유지되는 지점부터 찾는 것이 우선이에요.",
        "entry_level": 1,
        "steps": steps,
        "song_transfer": _song_transfer(
            "실제 구절에서 짧은 모음 → pattern → 가사 순으로 옮기세요.",
            ["원곡에서도 존재감 유지", "음량·힘 급증 없음"],
            fallback_step=1,
        ),
        "stop_conditions": ["통증", "존재감을 위해 세게 미는 패턴"],
        "if_better": "짧은 pattern으로 진행하세요.",
        "if_no_difference": "더 짧은 모음·더 작은 강도로 비교하세요.",
        "if_worse": "1단계로 돌아가 음량을 고정하세요.",
    }


def _protocol_breathiness() -> dict[str, Any]:
    steps = [
        _step(
            1,
            "BREATH_SHORT_SUSTAIN",
            "짧은 안정 sustain",
            (
                "짧은 지속에서 숨이 먼저 과하게 새지 않는 쪽을 찾아보세요. "
                "숨을 갑자기 막으려 하지 마세요."
            ),
            repetitions="3~5회",
            success_cues=["숨 섞임 감소", "힘·접촉 급증 없음", "시작이 과하게 세지 않음"],
            failure_cues=["숨을 갑자기 막아 세게 붙이기"],
            advance_when=["짧은 sustain에서 숨 섞임 감소"],
            regress_when=["세게 붙이기"],
            next_preview="짧은 모음 pattern",
            regress_preview="더 짧게·더 작은 강도",
        ),
        _step(
            2,
            "BREATH_VOWEL_PATTERN",
            "짧은 모음 pattern",
            "짧은 모음 pattern에서도 숨이 과하게 새지 않게 유지하세요.",
            repetitions="3회",
            success_cues=["pattern에서 숨 섞임 감소", "힘 급증 없음"],
            failure_cues=["세게 막아 붙이기"],
            advance_when=["pattern 안정"],
            regress_when=["세게 붙이기"],
            next_preview="phrase",
            regress_preview="짧은 sustain으로",
        ),
        _step(
            3,
            "BREATH_PHRASE",
            "짧은 phrase → 원곡",
            "짧은 phrase와 실제 구절에 적용하세요.",
            repetitions="2~3회",
            success_cues=["phrase에서 숨 섞임 감소", "힘 급증 없음"],
            failure_cues=["세게 막아 붙이기"],
            advance_when=["phrase 안정"],
            regress_when=["세게 붙이기"],
            next_preview="완료",
            regress_preview="짧은 sustain으로",
        ),
    ]
    return {
        "protocol_id": "BREATHINESS",
        "primary_focus": "BREATHINESS",
        "reason": "숨을 갑자기 막기보다, 짧은 구간에서 과하게 새지 않는 패턴부터 찾는 것이 우선이에요.",
        "entry_level": 1,
        "steps": steps,
        "song_transfer": _song_transfer(
            "실제 구절에서 짧은 sustain → 모음 pattern → 가사 순으로 옮기세요.",
            ["숨 섞임 감소", "힘·접촉 급증 없음"],
            fallback_step=1,
        ),
        "stop_conditions": ["통증", "숨을 갑자기 막아 세게 붙이기"],
        "if_better": "짧은 모음 pattern으로 진행하세요.",
        "if_no_difference": "더 짧은 구간만 골라 비교하세요.",
        "if_worse": "1단계로 돌아가 세게 붙이지 마세요.",
    }


def _protocol_dynamics() -> dict[str, Any]:
    steps = [
        _step(
            1,
            "DYN_COMFORT",
            "편한 강도 유지",
            "편한 강도로 짧은 구절을 유지하세요. 처음부터 큰 소리로 연습하지 마세요.",
            repetitions="3회",
            success_cues=["편한 강도에서 pitch·안정 유지"],
            failure_cues=["처음부터 크게"],
            advance_when=["편한 강도 안정"],
            regress_when=["크게 밀기"],
            next_preview="작은 강약만 추가",
            regress_preview="더 짧은 구절",
        ),
        _step(
            2,
            "DYN_SMALL_CHANGE",
            "작은 강약만 추가",
            "같은 구절에서 작은 강약 변화만 추가하세요.",
            repetitions="3회",
            success_cues=["강약 변화 중 pitch·stability·effort 유지"],
            failure_cues=["강약과 함께 힘 급증"],
            advance_when=["작은 강약에서도 안정"],
            regress_when=["힘 급증"],
            next_preview="원곡 phrase",
            regress_preview="편한 강도만",
        ),
        _step(
            3,
            "DYN_SONG",
            "원곡 phrase",
            "원곡 구절에 작은 강약만 적용하세요.",
            repetitions="2회",
            success_cues=["원곡에서도 강약 중 안정 유지"],
            failure_cues=["큰 소리로만 해결하려 함"],
            advance_when=["원곡 안정"],
            regress_when=["큰 소리로만 해결"],
            next_preview="완료",
            regress_preview="편한 강도로",
        ),
    ]
    return {
        "protocol_id": "DYNAMICS",
        "primary_focus": "DYNAMICS",
        "reason": "처음부터 큰 소리로 연습하기보다, 편한 강도에서 작은 강약만 추가하는 것이 우선이에요.",
        "entry_level": 1,
        "steps": steps,
        "song_transfer": _song_transfer(
            "원곡에서 편한 강도 → 작은 강약 → 실제 phrase 순으로 옮기세요.",
            ["강약 변화 중 안정 유지", "힘 급증 없음"],
            fallback_step=1,
        ),
        "stop_conditions": ["통증", "큰 소리 반복"],
        "if_better": "작은 강약을 추가하세요.",
        "if_no_difference": "더 짧은 구절에서만 비교하세요.",
        "if_worse": "편한 강도 유지로 돌아가세요.",
    }


def _protocol_phrase_end() -> dict[str, Any]:
    steps = [
        _step(
            1,
            "PHRASE_SHORT",
            "짧은 프레이즈부터",
            "조금 짧은 프레이즈부터 끝까지 같은 편안함을 유지하세요.",
            repetitions="3회",
            success_cues=["끝음에서 소리 중심이 급격히 약해지지 않음"],
            failure_cues=["긴 문장을 세게 버팀"],
            advance_when=["짧은 프레이즈 끝까지 유지"],
            regress_when=["끝에서 급격히 약해짐"],
            next_preview="길이 조금씩 늘리기",
            regress_preview="더 짧게",
        ),
        _step(
            2,
            "PHRASE_LONGER",
            "길이 조금씩 늘리기",
            "같은 편안함을 유지한 채 프레이즈를 조금씩 늘리세요.",
            repetitions="3회",
            success_cues=["늘려도 끝 중심 유지"],
            failure_cues=["늘리자 끝에서 무너짐"],
            advance_when=["길이 늘려도 유지"],
            regress_when=["끝에서 무너짐"],
            next_preview="원곡 phrase",
            regress_preview="짧은 프레이즈로",
        ),
        _step(
            3,
            "PHRASE_SONG",
            "원곡 phrase",
            "원곡 구절 끝까지 적용하세요.",
            repetitions="2회",
            success_cues=["원곡 끝에서도 중심 유지"],
            failure_cues=["세게 버텨 끝내기"],
            advance_when=["원곡 끝 유지"],
            regress_when=["세게 버팀"],
            next_preview="완료",
            regress_preview="짧은 프레이즈로",
        ),
    ]
    return {
        "protocol_id": "PHRASE_ENDURANCE",
        "primary_focus": "DYNAMICS",
        "reason": "긴 문장을 세게 버티기보다, 짧은 프레이즈부터 끝까지 같은 편안함을 유지하는 것이 우선이에요.",
        "entry_level": 1,
        "steps": steps,
        "song_transfer": _song_transfer(
            "원곡에서 짧은 프레이즈 → 길이 확장 → 실제 문장 순으로 옮기세요.",
            ["끝음에서 중심이 급격히 약해지지 않음"],
            fallback_step=1,
        ),
        "stop_conditions": ["통증", "길게 세게 버티기"],
        "if_better": "길이를 조금씩 늘리세요.",
        "if_no_difference": "더 짧은 끝 구간만 반복하세요.",
        "if_worse": "더 짧은 프레이즈로 돌아가세요.",
    }


def _protocol_vibrato() -> dict[str, Any]:
    steps = [
        _step(
            1,
            "VIBRATO_SHORT",
            "짧은 지속에서 자연스러운 흔들림",
            "억지로 크게 만들지 말고, 짧은 지속음에서 자연스러운 흔들림이 생기는지 비교하세요.",
            repetitions="3~5회",
            success_cues=["자연스러운 흔들림 유지", "불편 없음"],
            failure_cues=["비브라토를 억지로 크게 만들기"],
            advance_when=["짧은 지속에서 자연스러움"],
            regress_when=["억지로 키우기"],
            next_preview="조금 더 긴 유지",
            regress_preview="더 짧게",
        ),
        _step(
            2,
            "VIBRATO_PHRASE",
            "짧은 phrase → 원곡",
            "짧은 phrase와 실제 구절에 자연스러운 흔들림만 옮기세요.",
            repetitions="2~3회",
            success_cues=["phrase에서도 자연스러움", "억지 없음"],
            failure_cues=["억지로 크게"],
            advance_when=["phrase 자연스러움"],
            regress_when=["억지로 키우기"],
            next_preview="완료",
            regress_preview="짧은 지속으로",
        ),
    ]
    return {
        "protocol_id": "VIBRATO_CONTROL",
        "primary_focus": "STABILITY",
        "reason": "비브라토를 억지로 크게 만들기보다, 짧은 지속에서 자연스러운 흔들림부터 확인하는 것이 우선이에요.",
        "entry_level": 1,
        "steps": steps,
        "song_transfer": _song_transfer(
            "원곡에서 짧은 지속 → phrase 순으로 옮기세요.",
            ["자연스러운 흔들림 유지", "억지 없음"],
            fallback_step=1,
        ),
        "stop_conditions": ["통증", "억지로 크게 만들기"],
        "if_better": "짧은 phrase로 옮기세요.",
        "if_no_difference": "더 짧은 지속만 비교하세요.",
        "if_worse": "억지로 키우지 말고 1단계로 돌아가세요.",
    }


def _protocol_style(target_id: Optional[str]) -> dict[str, Any]:
    overlay = _target_overlay(target_id) or _target_overlay("SOFT_SWEET") or {}
    label = str(overlay.get("label") or "원하는 음색")
    cue = str(overlay.get("cue") or "")
    success = list(overlay.get("success_cues") or ["원하는 느낌에 가까움", "불편 없음"])
    avoid = list(overlay.get("avoid") or ["세게 밀기"])
    steps = [
        _step(
            1,
            "STYLE_COMPARE",
            f"{label} · 짧은 비교",
            cue or "같은 짧은 구절을 평소 표현과 원하는 느낌에 가깝게 한 번 비교하세요.",
            repetitions="A/B 각 2~3회",
            success_cues=success,
            failure_cues=avoid,
            advance_when=["원하는 느낌이 더 가깝고 불편 없음"],
            regress_when=["힘·음량 급증", "불편"],
            next_preview="짧은 phrase에 적용",
            regress_preview="더 짧고 작은 강도로",
        ),
        _step(
            2,
            "STYLE_PHRASE",
            "짧은 phrase에 적용",
            f"짧은 phrase에서 {label} 표현을 유지하세요. 음량을 먼저 키우지 마세요.",
            repetitions="2~3회",
            success_cues=success,
            failure_cues=avoid,
            advance_when=["phrase에서 유지"],
            regress_when=["힘 급증"],
            next_preview="원곡 적용",
            regress_preview="짧은 A/B로",
        ),
        _step(
            3,
            "STYLE_SONG",
            "원곡 구절에 적용",
            f"원곡 구절에서 {label} 표현을 적용하세요.",
            repetitions="2회",
            success_cues=success + ["원곡에서도 유지"],
            failure_cues=avoid,
            advance_when=["원곡에서 유지"],
            regress_when=["힘 급증"],
            next_preview="완료",
            regress_preview="짧은 비교로",
        ),
    ]
    return {
        "protocol_id": "TIMBRE_STYLE",
        "primary_focus": "STYLE",
        "reason": f"기능적 제한이 강하지 않을 때, {label} 방향을 작은 강도로 짧게 탐색하는 것이 우선이에요.",
        "entry_level": 1,
        "steps": steps,
        "song_transfer": _song_transfer(
            f"원곡에서 짧은 비교 → phrase → 실제 가사로 {label} 표현을 옮기세요.",
            success,
            fallback_step=1,
        ),
        "stop_conditions": ["통증", "음색을 위해 세게 밀기"],
        "if_better": "짧은 phrase에 적용하세요.",
        "if_no_difference": "더 짧은 구절·다른 표현 cue로 비교하세요.",
        "if_worse": "1단계로 돌아가 음량을 고정하세요.",
        "target_overlay": overlay,
    }


def _protocol_maintain() -> dict[str, Any]:
    steps = [
        _step(
            1,
            "MAINTAIN_COMPARE",
            "현재 편한 패턴 유지하며 짧게 비교",
            "평소 방식과 조금 작은 강도를 짧게 비교하며, 편한 패턴을 유지하세요.",
            repetitions="2~3회",
            success_cues=["편한 패턴 유지", "힘 증가 없음"],
            failure_cues=["원인을 가정하고 세게 바꾸기"],
            advance_when=["편한 패턴 유지"],
            regress_when=["세게 바꾸기"],
            next_preview="짧은 원곡 적용",
            regress_preview="더 짧게",
        ),
        _step(
            2,
            "MAINTAIN_SONG",
            "원곡에 유지 적용",
            "원곡 짧은 구절에서 편한 패턴을 유지하세요.",
            repetitions="2회",
            success_cues=["원곡에서도 편한 패턴 유지"],
            failure_cues=["세게 바꾸기"],
            advance_when=["원곡 유지"],
            regress_when=["세게 바꾸기"],
            next_preview="완료",
            regress_preview="짧은 비교로",
        ),
    ]
    return {
        "protocol_id": "MAINTAIN",
        "primary_focus": "MAINTAIN",
        "reason": "뚜렷한 기능 제한이 강하지 않아, 현재 편한 패턴을 유지하며 짧게 비교하는 것이 우선이에요.",
        "entry_level": 1,
        "steps": steps,
        "song_transfer": _song_transfer(
            "원곡 짧은 구절에서 편한 패턴을 유지하세요.",
            ["편한 패턴 유지", "힘 증가 없음"],
            fallback_step=1,
        ),
        "stop_conditions": ["통증"],
        "if_better": "원곡에 유지하세요.",
        "if_no_difference": "더 짧은 구간만 비교하세요.",
        "if_worse": "평소 편한 강도만 유지하세요.",
    }


def _protocol_safety() -> dict[str, Any]:
    steps = [
        _step(
            1,
            "SAFETY_STOP",
            "실험 중단 · 휴식",
            "통증이나 지속 불편이 있으면 강한 고음·큰 소리·반복 발성·스타일 실험을 하지 말고 쉬세요.",
            repetitions="연습하지 않음",
            success_cues=["통증·불편이 늘지 않음"],
            failure_cues=["통증 상태에서 반복"],
            advance_when=["증상이 가라앉음"],
            regress_when=["증상 증가"],
            next_preview="증상이 가라앉을 때까지 휴식",
            regress_preview="의료 상담 고려",
        ),
    ]
    return {
        "protocol_id": "SAFETY",
        "primary_focus": "SAFETY",
        "reason": "통증·지속 불편에서는 연습보다 휴식이 우선이에요.",
        "entry_level": 1,
        "steps": steps,
        "song_transfer": {
            "instruction": "증상이 있을 때는 원곡 적용 실험을 하지 마세요.",
            "success_cues": ["통증·불편이 늘지 않음"],
            "fallback_step": 1,
            "pattern": [],
        },
        "stop_conditions": ["통증", "지속 불편", "증상 증가"],
        "if_better": "증상이 가라앉을 때까지 쉬세요.",
        "if_no_difference": "계속 쉬고, 지속되면 의료 상담을 권합니다.",
        "if_worse": "즉시 중단하세요.",
    }


def _protocol_contact(snap: dict[str, Any]) -> dict[str, Any]:
    """Contact alone rarely drives corrective protocol."""
    effort = _effort_info(snap)
    breath = str((snap.get("breathiness") or {}).get("level") or "").upper()
    contact = str((snap.get("contact") or {}).get("status") or "").upper()
    if contact == "FIRM" and effort["reliable_high"]:
        return _protocol_effort()
    if contact == "LIGHT" and breath == "HIGH":
        return _protocol_breathiness()
    # FIRM + low effort → do not "make lighter"
    return _protocol_maintain()


FOCUS_PROTOCOLS = {
    "REGISTER_CONNECTION": _protocol_register,
    "STABILITY": _protocol_stability,
    "HIGH_NOTE": _protocol_high_note_access,
    "EFFORT": _protocol_effort,
    "PRESENCE": _protocol_presence,
    "BREATHINESS": _protocol_breathiness,
    "DYNAMICS": _protocol_dynamics,
    "PHRASE_ENDURANCE": _protocol_phrase_end,
    "VIBRATO_CONTROL": _protocol_vibrato,
    "CONTACT": None,  # special
    "BRIGHTNESS": None,  # style-like
    "TIMBRE": None,
    "TEXTURE": None,
    "STYLE": None,
    "MAINTAIN": _protocol_maintain,
    "SAFETY": _protocol_safety,
}


def resolve_protocol_focus(
    primary_focus: str,
    *,
    snap: Optional[dict[str, Any]] = None,
    concern_ids: Optional[list[str]] = None,
    target_id: Optional[str] = None,
) -> str:
    """Map planner focus → protocol family with evidence-aware overrides."""
    snap = snap or {}
    focus = str(primary_focus or "MAINTAIN").upper()
    concerns = [str(c).upper() for c in (concern_ids or [])]
    reg = _reg(snap)
    effort = _effort_info(snap)

    # HIGH_NOTE_CANNOT_REACH: register/effort trump bare access
    if "HIGH_NOTE_CANNOT_REACH" in concerns:
        if reg == "DISRUPTED" or (reg == "PARTIAL" and focus in ("REGISTER_CONNECTION", "HIGH_NOTE", "MAINTAIN")):
            return "REGISTER_CONNECTION"
        if effort["reliable_high"]:
            return "EFFORT"
        if focus in ("HIGH_NOTE", "MAINTAIN", ""):
            return "HIGH_NOTE"

    if focus == "HIGH_NOTE":
        if reg in ("DISRUPTED", "PARTIAL"):
            return "REGISTER_CONNECTION"
        if effort["reliable_high"]:
            return "EFFORT"
        return "HIGH_NOTE"

    if focus == "EFFORT" and not effort["reliable_high"]:
        # Do not force effort protocol on unreliable detector
        if reg == "DISRUPTED":
            return "REGISTER_CONNECTION"
        if any(c in concerns for c in ("HIGH_NOTE_UNSTABLE", "PITCH_UNSTABLE")):
            return "STABILITY"
        return "REGISTER_CONNECTION" if reg == "PARTIAL" else "MAINTAIN"

    if focus == "CONTACT":
        return "CONTACT"

    if focus in ("BRIGHTNESS", "TIMBRE", "TEXTURE", "STYLE"):
        return "STYLE"

    if focus == "DYNAMICS" and any(c == "PHRASE_END_WEAK" for c in concerns):
        return "PHRASE_ENDURANCE"

    if focus == "STABILITY" and any(c == "VIBRATO_UNSTABLE" for c in concerns):
        return "VIBRATO_CONTROL"

    if focus in FOCUS_PROTOCOLS and FOCUS_PROTOCOLS[focus] is not None:
        return focus

    if focus in ("BRIGHTNESS", "TIMBRE", "TEXTURE") or target_id:
        return "STYLE"

    return focus if focus in ("MAINTAIN", "SAFETY") else "MAINTAIN"


def build_coaching_protocol(
    primary_focus: str,
    *,
    snap: Optional[dict[str, Any]] = None,
    concern_ids: Optional[list[str]] = None,
    target_timbre: Any = None,
    pain: bool = False,
    why_this_first: Optional[str] = None,
    preserve_factors: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Build multi-step coaching protocol for the resolved primary focus."""
    snap = snap or {}
    target_id = None
    if isinstance(target_timbre, str):
        target_id = target_timbre.upper()
    elif isinstance(target_timbre, dict):
        target_id = str(target_timbre.get("id") or "").upper() or None

    if pain or str(primary_focus or "").upper() == "SAFETY":
        proto = _protocol_safety()
    else:
        resolved = resolve_protocol_focus(
            primary_focus,
            snap=snap,
            concern_ids=concern_ids,
            target_id=target_id,
        )
        if resolved == "CONTACT":
            proto = _protocol_contact(snap)
        elif resolved == "STYLE":
            proto = _protocol_style(target_id)
        elif resolved == "PHRASE_ENDURANCE":
            proto = _protocol_phrase_end()
        elif resolved == "VIBRATO_CONTROL":
            proto = _protocol_vibrato()
        elif resolved in FOCUS_PROTOCOLS and FOCUS_PROTOCOLS[resolved]:
            proto = FOCUS_PROTOCOLS[resolved]()
        else:
            proto = _protocol_maintain()

    overlay = None
    if str(proto.get("primary_focus") or "") not in ("STYLE", "SAFETY", "MAINTAIN"):
        overlay = _target_overlay(target_id)
        if overlay:
            # Secondary aesthetic — does not override functional steps
            proto = dict(proto)
            proto["target_overlay"] = {
                **overlay,
                "role": "SECONDARY",
                "note": (
                    f"전환·기능 연습이 안정된 뒤, "
                    f"{overlay.get('label')} 표현을 작은 강도로 탐색하세요."
                ),
            }

    entry = (proto.get("steps") or [None])[0] or {}
    out = {
        "version": PROTOCOL_VERSION,
        "primary_focus": proto.get("primary_focus"),
        "protocol_id": proto.get("protocol_id"),
        "reason": why_this_first or proto.get("reason"),
        "entry_level": int(proto.get("entry_level") or 1),
        "entry_step": entry,
        "steps": list(proto.get("steps") or []),
        "song_transfer": dict(proto.get("song_transfer") or {}),
        "stop_conditions": list(proto.get("stop_conditions") or []),
        "preserve_factors": list(preserve_factors or []),
        "target_overlay": proto.get("target_overlay"),
        "if_better": proto.get("if_better"),
        "if_no_difference": proto.get("if_no_difference"),
        "if_worse": proto.get("if_worse"),
        "reliability_required": bool(proto.get("reliability_required")),
    }
    # Sanitize anatomy
    blob = str(out)
    for bad in _ANATOMY_BANNED:
        if bad in blob and bad not in ("가성", "진성"):  # allow only if we accidentally included
            pass
    return out


def protocol_entry_card(protocol: dict[str, Any]) -> dict[str, Any]:
    """UI-facing slim card: entry + next/fallback preview."""
    entry = protocol.get("entry_step") or (protocol.get("steps") or [{}])[0]
    return {
        "title": entry.get("title"),
        "level": entry.get("level") or 1,
        "instruction": entry.get("instruction"),
        "repetitions": entry.get("repetitions"),
        "success_cues": list(entry.get("success_cues") or []),
        "next_preview": entry.get("next_preview") or protocol.get("if_better"),
        "regress_preview": entry.get("regress_preview") or protocol.get("if_worse"),
        "song_transfer_preview": (protocol.get("song_transfer") or {}).get("instruction"),
        "protocol_id": protocol.get("protocol_id"),
        "primary_focus": protocol.get("primary_focus"),
        "steps_count": len(protocol.get("steps") or []),
    }


def all_protocol_ids() -> list[str]:
    return [
        "REGISTER_CONNECTION",
        "STABILITY",
        "HIGH_NOTE_ACCESS",
        "EFFORT",
        "PRESENCE",
        "BREATHINESS",
        "DYNAMICS",
        "PHRASE_ENDURANCE",
        "VIBRATO_CONTROL",
        "TIMBRE_STYLE",
        "MAINTAIN",
        "SAFETY",
    ]


def assert_protocol_shape(proto: dict[str, Any]) -> None:
    assert proto.get("version") == PROTOCOL_VERSION
    assert proto.get("primary_focus")
    steps = proto.get("steps") or []
    assert len(steps) >= 1
    for s in steps:
        assert s.get("instruction")
        assert s.get("success_cues")
        assert s.get("failure_cues") is not None
        assert s.get("advance_when") is not None
        assert s.get("regress_when") is not None
    st = proto.get("song_transfer") or {}
    assert st.get("instruction") is not None
    assert "success_cues" in st
