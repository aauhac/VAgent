"""Functional Bottleneck Engine v2.2 — localized coaching decisions."""

from __future__ import annotations

from typing import Any, Optional

from . import config as bcfg
from .hypotheses import rank_hypotheses
from .preserve import build_preserve_modify
from .ranker import collect_measurement_candidates, select_primary


def build_coaching_decision(
    *,
    profile: dict[str, Any],
    episodes: list[dict[str, Any]],
    focus: dict[str, Any],
    user_goal: str = "GENERAL_EASE_AND_CONTROL",
    style_context: str = "unspecified",
    criteria_matrix: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    from audio_analyzer.vocal_function.criteria_matrix import (
        attach_primary_criteria_explanation,
        build_candidate_comparison,
    )

    hypotheses = rank_hypotheses(profile, episodes, user_goal=user_goal)
    measurement_candidates = collect_measurement_candidates(hypotheses)
    # strip internal markers from public hyp list
    public_hyps = [h for h in hypotheses if h.get("id") != "_MEASUREMENT_ONLY"]
    for h in public_hyps:
        h.pop("_all_measurement_candidates", None)
        h.pop("_measurement_sidecar", None)

    primary, secondary = select_primary(
        public_hyps, user_goal=user_goal, criteria_matrix=criteria_matrix
    )
    target = _resolve_target_episode(primary, episodes, focus)

    # Hard rule: no target → no primary
    if primary and not target:
        measurement_candidates.append(
            {
                "issue": primary.get("id"),
                "reason": "병목 후보는 있으나 재생 가능한 target episode가 없어요.",
                "recommended_task": "additional_measurement",
                "eligibility": "NEEDS_MEASUREMENT",
            }
        )
        primary = None

    # Target vocal validity
    if primary and target:
        valid = (target.get("feature_matrix") or {}).get("validity") or target.get("validity") or {}
        if valid.get("vocal_specific") is False:
            measurement_candidates.append(
                {
                    "issue": primary.get("id"),
                    "reason": "target 구간의 vocal validity가 부족해요.",
                    "recommended_task": "re_record_with_headphones",
                    "eligibility": "NEEDS_MEASUREMENT",
                }
            )
            primary = None
            target = None

    # Register core span must exist (or be derivable from a short episode)
    if primary and target and target.get("type") == "REGISTER_TRANSITION":
        core = target.get("core_evidence_span") or {}
        if core.get("start_sec") is None:
            s = float(target.get("start_sec") or 0)
            e = float(target.get("end_sec") or s)
            # Compact transitions can use the episode itself as core
            if (e - s) <= 4.0 + 1e-6:
                target = {
                    **target,
                    "core_evidence_span": {
                        "start_sec": s,
                        "end_sec": e,
                        "duration_sec": max(0.0, e - s),
                        "source": "episode_as_core",
                    },
                    "phrase_span": {"start_sec": s, "end_sec": e},
                }
            else:
                measurement_candidates.append(
                    {
                        "issue": primary.get("id"),
                        "reason": "음역 전환 core evidence span이 없어요.",
                        "recommended_task": "additional_measurement",
                        "eligibility": "NEEDS_MEASUREMENT",
                    }
                )
                primary = None
                target = None

    preserve, modify = build_preserve_modify(profile, episodes, primary, target_episode=target)
    # Attach timestamps on modify items
    if target:
        for m in modify:
            m.setdefault("episode_id", target.get("episode_id"))
            m.setdefault("original_start_sec", target.get("original_start_sec"))
            m.setdefault("original_end_sec", target.get("original_end_sec"))
            m.setdefault("local_start_sec", target.get("local_start_sec", target.get("start_sec")))
            m.setdefault("local_end_sec", target.get("local_end_sec", target.get("end_sec")))
            core = target.get("core_evidence_span") or {}
            if core.get("start_sec") is not None:
                m["core_evidence_span"] = core

    primary_conf = (primary or {}).get("confidence_label") or "low"
    if primary and primary_conf == "low":
        exercises = []
        success = []
        additional = True
        primary = None
    elif primary:
        exercises = _exercises_for(primary, secondary)
        success = _success_criteria(primary)
        additional = False
    else:
        exercises = []
        success = []
        additional = True

    coaching_conf = (primary or {}).get("coaching_confidence") or "low"
    why_struct = _structured_why(primary, target, preserve, profile=profile)
    why = []
    if why_struct.get("supporting"):
        why.extend(
            w["text"] if isinstance(w, dict) else w for w in why_struct["supporting"]
        )
    if why_struct.get("preserved"):
        why.append(
            "유지: "
            + "; ".join(
                w["text"] if isinstance(w, dict) else w for w in why_struct["preserved"]
            )
        )
    if why_struct.get("scope_note"):
        why.append(why_struct["scope_note"])

    ranked_focus = _rank_focus(primary, secondary, target, focus, episodes)
    headline = _headline(primary, preserve, modify)

    primary = attach_primary_criteria_explanation(primary, criteria_matrix or [])
    candidate_comparison = build_candidate_comparison(criteria_matrix or [], public_hyps)

    return {
        "layer": "LEVEL_5_COACHING_DECISION",
        "user_goal": user_goal,
        "style_context": style_context,
        "headline": headline,
        "primary_bottleneck": primary,
        "secondary_bottlenecks": secondary[:2],
        "hypotheses": public_hyps,
        "candidate_comparison": candidate_comparison,
        "preserve": preserve,
        "modify": modify,
        "why": [w for w in why if w],
        "why_structured": why_struct,
        "target_episode": _public_target(target, primary),
        "best_self_reference": focus.get("best_self_reference"),
        "focus_ranked": ranked_focus,
        "exercise_plan": exercises,
        "success_criteria": success,
        "prefer_additional_measurement": additional or not primary,
        "measurement_candidates": measurement_candidates,
        "needs_confirmation": [m for m in measurement_candidates],
        "inference_confidence": (primary or {}).get("confidence_label") or "low",
        "coaching_confidence": coaching_conf if primary else "low",
        "note": "goal/style은 priority만 바꾸며 raw measurement·confidence를 변경하지 않습니다.",
        "no_primary_message": (
            None
            if primary
            else "이번 녹음에서는 우선적으로 교정해야 할 뚜렷한 기능적 병목은 찾지 못했어요."
        ),
    }


def _structured_why(primary, target, preserve, profile=None) -> dict[str, Any]:
    supporting: list[dict[str, str]] = []
    preserved: list[dict[str, str]] = []
    contradicting: list[dict[str, str]] = []
    scope_note = None
    dims = (profile or {}).get("dimensions") or {}
    regularity = dims.get("phonation_regularity") or {}

    def _item(text: str, scope: str) -> dict[str, str]:
        return {"text": text, "scope": scope}

    if primary:
        supporting.append(
            _item(primary.get("why") or primary.get("summary") or "", "GLOBAL")
        )
        # Primary criteria explanation
        for c in primary.get("satisfied_criteria") or []:
            supporting.append(
                _item(f"✓ {c.get('label')} ({c.get('availability')})", "CORE_SPAN")
            )
        if target:
            fm = target.get("feature_matrix") or {}
            eff = fm.get("effort") or {}
            if eff.get("intensity_delta_db") is not None:
                supporting.append(
                    _item(
                        f"이전 대비 intensity {eff['intensity_delta_db']:+.1f} dB",
                        "TARGET_EPISODE",
                    )
                )
            rec = fm.get("recovery") or {}
            if rec.get("returned_to_baseline") is False:
                supporting.append(
                    _item("이후 구간에서 상태 복귀가 느렸어요", "TARGET_EPISODE")
                )
            elif rec.get("returned_to_baseline") is True:
                preserved.append(
                    _item("이후 구간에서 비교적 빨리 회복", "TARGET_EPISODE")
                )
            reg = fm.get("regularity") or {}
            if (reg.get("periodicity") or 0) >= 8 and not reg.get("roughness"):
                preserved.append(
                    _item(
                        "해당 전환 구간에서는 주기성이 비교적 유지됐어요.",
                        "TARGET_EPISODE",
                    )
                )
            if not reg.get("roughness"):
                preserved.append(
                    _item(
                        "해당 전환 구간에서는 거친 음질 증가가 뚜렷하지 않았어요.",
                        "TARGET_EPISODE",
                    )
                )
            # Global vs target scope separation
            if (regularity.get("status") or "").upper() in (
                "REPEATED_IRREGULAR",
                "INTERMITTENT",
            ) and not reg.get("roughness"):
                scope_note = (
                    "곡 전체에서는 일부 불규칙한 구간이 있었지만, "
                    "이번에 선택된 음역 전환 구간에서는 "
                    "거친 음질 증가가 뚜렷하지 않았어요."
                )
        for a in primary.get("alternative_explanations") or []:
            contradicting.append(_item(str(a), "GLOBAL"))
    for p in preserve or []:
        if p.get("label"):
            scope = "TARGET_EPISODE" if p.get("episode_id") else "GLOBAL"
            preserved.append(_item(p["label"], scope))
    return {
        "supporting": [s for s in supporting if s.get("text")],
        "preserved": list({p["text"]: p for p in preserved if p.get("text")}.values()),
        "contradicting": contradicting,
        "scope_note": scope_note,
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
    type_map = {
        "REGISTER_TRANSITION_DISRUPTION": "REGISTER_TRANSITION",
        "AIR_LEAKAGE": "AIR_LEAKAGE",
        "APERIODIC_ROUGHNESS": "ROUGHNESS",
        "ABRUPT_ONSET": "ABRUPT_ONSET",
        "PHRASE_END_SUPPORT_LOSS": "PHRASE_END_DROP",
        "GENERAL_EXCESS_EFFORT": "GENERAL_EFFORT",
        "EXCESS_EFFORT_HIGH_NOTE": "HIGH_NOTE",
        "RESONANCE_HIGH_NOTE_COLLAPSE": "HIGH_NOTE",
        "EXCESS_FIRMNESS_WITH_STRAIN": "HIGH_NOTE",
    }
    want = type_map.get(bid)
    if want:
        for e in episodes:
            if e.get("type") == want:
                return e
    return None


def _public_target(target: Optional[dict[str, Any]], primary) -> Optional[dict[str, Any]]:
    if not target:
        return None
    from audio_analyzer.audit.consistency import core_span_label

    core = target.get("core_evidence_span") or {}
    origin = float(target.get("time_origin_sec") or 0)
    core_label = core_span_label(primary, target)
    core_pub = None
    if core.get("start_sec") is not None:
        cs = float(core["start_sec"])
        ce = float(core.get("end_sec") or cs)
        core_pub = {
            "start_sec": cs,
            "end_sec": ce,
            "local_start_sec": cs,
            "local_end_sec": ce,
            "original_start_sec": cs + origin if target.get("original_start_sec") is not None else core.get("original_start_sec"),
            "original_end_sec": ce + origin if target.get("original_end_sec") is not None else core.get("original_end_sec"),
            "duration_sec": core.get("duration_sec"),
            "label": core_label,
        }
        if target.get("original_start_sec") is not None and target.get("start_sec") is not None:
            delta = float(target["original_start_sec"]) - float(target["start_sec"])
            core_pub["original_start_sec"] = cs + delta
            core_pub["original_end_sec"] = ce + delta

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
        "phase_confidence": target.get("phase_confidence"),
        "cause_hint": target.get("cause_hint"),
        "phrase_span": target.get("phrase_span")
        or {"start_sec": target.get("start_sec"), "end_sec": target.get("end_sec")},
        "core_evidence_span": core_pub,
        "core_events": target.get("core_events") or [],
        "n_merged_windows": target.get("n_merged_windows"),
        "label": "가장 먼저 바꿔볼 구간" if primary else "참고 구간",
        "core_label": core_label,
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
