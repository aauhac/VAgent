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
    Target episode comes from primary.supporting_episode_ids — never focus.primary[0] alone.
    """
    hypotheses = rank_hypotheses(profile, episodes, user_goal=user_goal)
    primary, secondary = select_primary(hypotheses, user_goal=user_goal)
    target = _resolve_target_episode(primary, episodes, focus)
    preserve, modify = build_preserve_modify(profile, episodes, primary, target_episode=target)

    # Low primary confidence → measurement suggestion instead of corrective exercise
    primary_conf = (primary or {}).get("confidence_label") or "low"
    if primary and primary_conf == "low":
        exercises = []
        success = [
            "같은 구간을 이어폰으로 다시 녹음해 주세요",
            "반주 없는 순수 보컬 또는 분리 성공 후 재분석",
        ]
        additional = True
    else:
        exercises = _exercises_for(primary, secondary)
        success = _success_criteria(primary)
        additional = False

    # Downgrade coaching confidence if target episode weak
    coaching_conf = (primary or {}).get("coaching_confidence") or "low"
    if target and target.get("validity") and not (target.get("validity") or {}).get(
        "vocal_specific", True
    ):
        coaching_conf = "low"
    if target and (target.get("feature_matrix") or {}).get("validity"):
        if not ((target.get("feature_matrix") or {}).get("validity") or {}).get(
            "vocal_specific", True
        ):
            coaching_conf = "low"

    why = []
    if primary:
        why.append(primary.get("why") or primary.get("summary") or "")
    if preserve and modify:
        why.append(
            "접촉·주기성 등 유지할 패턴과 바꿀 effort/진입 패턴을 분리해서 봤어요."
        )

    # Bottleneck-first focus ranking
    ranked_focus = _rank_focus(primary, secondary, target, focus, episodes)

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
        "target_episode": _public_target(target, primary),
        "best_self_reference": focus.get("best_self_reference"),
        "focus_ranked": ranked_focus,
        "exercise_plan": exercises,
        "success_criteria": success,
        "prefer_additional_measurement": additional,
        "inference_confidence": (primary or {}).get("confidence_label") or "low",
        "coaching_confidence": coaching_conf,
        "note": "goal/style은 priority만 바꾸며 raw measurement를 변경하지 않습니다.",
    }


def _resolve_target_episode(
    primary: Optional[dict[str, Any]],
    episodes: list[dict[str, Any]],
    focus: dict[str, Any],
) -> Optional[dict[str, Any]]:
    if not primary:
        return None
    by_id = {e.get("episode_id"): e for e in episodes if e.get("episode_id")}
    for eid in primary.get("supporting_episode_ids") or []:
        if eid in by_id:
            return by_id[eid]

    bid = primary.get("id")
    if bid == "REGISTER_TRANSITION_DISRUPTION":
        reg = [e for e in episodes if e.get("type") == "REGISTER_TRANSITION"]
        if reg:
            return reg[0]
    if bid == "RESONANCE_HIGH_NOTE_COLLAPSE":
        res = [
            e
            for e in episodes
            if e.get("type") == "HIGH_NOTE"
            and e.get("cause_hint") in ("RESONANCE", "MIXED")
        ]
        if res:
            return res[0]
        high = [e for e in episodes if e.get("type") == "HIGH_NOTE" and e.get("concern")]
        if high:
            return high[0]
    if bid in ("EXCESS_EFFORT_HIGH_NOTE", "EXCESS_FIRMNESS_WITH_STRAIN"):
        high = [e for e in episodes if e.get("type") == "HIGH_NOTE" and e.get("concern")]
        if high:
            return high[0]
    # Do NOT fall back to focus.primary[0] when types mismatch
    return None


def _public_target(target: Optional[dict[str, Any]], primary) -> Optional[dict[str, Any]]:
    if not target:
        return None
    return {
        "start_sec": target.get("start_sec"),
        "end_sec": target.get("end_sec"),
        "local_start_sec": target.get("local_start_sec", target.get("start_sec")),
        "local_end_sec": target.get("local_end_sec", target.get("end_sec")),
        "original_start_sec": target.get("original_start_sec"),
        "original_end_sec": target.get("original_end_sec"),
        "time_origin_sec": target.get("time_origin_sec"),
        "episode_id": target.get("episode_id"),
        "type": target.get("type"),
        "phase_method": target.get("phase_method"),
        "cause_hint": target.get("cause_hint"),
        "label": "가장 먼저 바꿔볼 구간" if primary else "참고 구간",
    }


def _rank_focus(primary, secondary, target, focus, episodes) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if target:
        out.append({**target, "role": "PRIMARY_TARGET"})
    for s in secondary[:1]:
        for eid in s.get("supporting_episode_ids") or []:
            for e in episodes:
                if e.get("episode_id") == eid and e is not target:
                    out.append({**e, "role": "SECONDARY_TARGET"})
                    break
    best = focus.get("best_self_reference")
    if best:
        out.append({**best, "role": "BEST_SELF"})
    return out[:5]


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
    return list(
        bcfg.SUCCESS_CRITERIA.get(
            primary.get("id"),
            [
                "같은 음높이 범위에서 effort proxy 감소",
                "주기성 유지",
                "거친 음질 증가 없음",
            ],
        )
    )
