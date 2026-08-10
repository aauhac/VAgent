"""Functional Bottleneck Engine — observations → what to change first."""

from __future__ import annotations

from typing import Any, Optional

from . import config as bcfg
from .hypotheses import rank_hypotheses
from .preserve import build_preserve_modify
from .ranker import select_primary


def build_coaching_decision(
    *,
    profile: dict[str, Any],
    episodes: list[dict[str, Any]],
    focus: dict[str, Any],
    user_goal: str = "GENERAL_EASE_AND_CONTROL",
    style_context: str = "unspecified",
) -> dict[str, Any]:
    """
    LEVEL-5 coaching decision.

    Does NOT alter raw observations. Goal/style only affect impact ranking.
    """
    hypotheses = rank_hypotheses(profile, episodes, user_goal=user_goal)
    primary, secondary = select_primary(hypotheses, user_goal=user_goal)
    preserve, modify = build_preserve_modify(profile, episodes, primary)

    target = None
    if focus.get("primary"):
        target = focus["primary"][0]
    elif episodes:
        target = episodes[0]

    exercises = _exercises_for(primary, secondary)
    success = _success_criteria(primary)

    why = []
    if primary:
        why.append(primary.get("why") or primary.get("summary") or "")
    if preserve and modify:
        why.append(
            "접촉·주기성 등 유지할 패턴과 바꿀 effort/진입 패턴을 분리해서 봤어요."
        )

    headline = _headline(primary, preserve, modify)

    return {
        "layer": "LEVEL_5_COACHING_DECISION",
        "user_goal": user_goal,
        "style_context": style_context,
        "headline": headline,
        "primary_bottleneck": primary,
        "secondary_bottlenecks": secondary[:2],
        "hypotheses": hypotheses,
        "preserve": preserve,
        "modify": modify,
        "why": [w for w in why if w],
        "target_episode": {
            "start_sec": (target or {}).get("start_sec"),
            "end_sec": (target or {}).get("end_sec"),
            "episode_id": (target or {}).get("episode_id"),
            "type": (target or {}).get("type"),
            "label": "가장 먼저 바꿔볼 구간" if primary else "참고 구간",
        }
        if target
        else None,
        "best_self_reference": focus.get("best_self_reference"),
        "exercise_plan": exercises,
        "success_criteria": success,
        "inference_confidence": (primary or {}).get("confidence_label") or "low",
        "coaching_confidence": (primary or {}).get("coaching_confidence") or "low",
        "note": "goal/style은 priority만 바꾸며 raw measurement를 변경하지 않습니다.",
    }


def _headline(primary, preserve, modify) -> str:
    if not primary:
        return "이번 녹음에서 뚜렷한 기능 병목 후보는 제한적이에요. 잘 유지된 패턴을 확인하세요."
    bits = [primary.get("user_title") or primary.get("id")]
    if modify:
        bits.append(f"먼저: {modify[0].get('label')}")
    if preserve:
        bits.append(f"유지: {preserve[0].get('label')}")
    return " · ".join(bits)


def _exercises_for(primary, secondary) -> list[dict[str, Any]]:
    from audio_analyzer.coaching.prescription import EXERCISES

    if not primary:
        return []
    bid = primary.get("id")
    mapping = bcfg.BOTTLENECK_EXERCISES.get(bid) or []
    out = []
    for eid in mapping:
        for ex in EXERCISES:
            if ex["exercise_id"] == eid:
                # contraindication: do not weaken contact if preserve says keep firm
                out.append(
                    {
                        "exercise_id": eid,
                        "instructions": ex["instructions"],
                        "duration_sec": ex.get("duration_sec"),
                        "triggered_by": bid,
                        "when_not_to_use": ex.get("when_not_to_use"),
                    }
                )
    return out[:3]


def _success_criteria(primary) -> list[str]:
    if not primary:
        return []
    return list(bcfg.SUCCESS_CRITERIA.get(primary.get("id"), [
        "같은 음높이 범위에서 effort proxy 감소",
        "주기성 유지",
        "거친 음질 증가 없음",
    ]))
