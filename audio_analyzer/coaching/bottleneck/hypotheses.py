"""Hypothesis generation from profile + episodes (multi-family, no single-metric)."""

from __future__ import annotations

from typing import Any

from . import config as bcfg


def rank_hypotheses(
    profile: dict[str, Any],
    episodes: list[dict[str, Any]],
    *,
    user_goal: str = "GENERAL_EASE_AND_CONTROL",
) -> list[dict[str, Any]]:
    dims = profile.get("dimensions") or {}
    plane = profile.get("contact_effort_plane") or {}
    out: list[dict[str, Any]] = []

    # --- EXCESS_EFFORT_HIGH_NOTE ---
    concern_eps = [e for e in episodes if e.get("type") == "HIGH_NOTE" and e.get("concern")]
    effort_dim = dims.get("vocal_effort_strain") or {}
    if concern_eps or effort_dim.get("status") in ("OCCASIONAL", "MODERATE", "REPEATED"):
        support = []
        against = []
        if concern_eps:
            support.append("high_note_effort_concern_episode")
        if effort_dim.get("status") in ("MODERATE", "REPEATED"):
            support.append("effort_dimension_elevated")
        firm_ok = plane.get("firm_high_strain_low")
        if firm_ok and not concern_eps:
            against.append("firm_without_effort_plane")
        conf = "high" if len(support) >= 2 else ("medium" if support else "low")
        out.append(
            _h(
                "EXCESS_EFFORT_HIGH_NOTE",
                support=support,
                against=against,
                alternatives=["intentional_belt", "mic_proximity", "vowel_shift"],
                confidence=conf,
                why=(
                    "고음에서 접촉·주기성은 비교적 유지되지만 "
                    "effort 관련 복합 증거가 함께 나타났어요."
                    if support
                    else ""
                ),
            )
        )

    # --- EXCESS_FIRMNESS_WITH_STRAIN ---
    if plane.get("firm_high_strain_high"):
        out.append(
            _h(
                "EXCESS_FIRMNESS_WITH_STRAIN",
                support=["firm_and_effort_plane"],
                against=[],
                alternatives=["style_intentional_firmness"],
                confidence="medium",
                why="단단한 접촉 관련 패턴과 effort 증거가 함께 있어요.",
            )
        )

    # --- AIR_LEAKAGE ---
    leak = dims.get("air_leakage_breathiness") or {}
    if leak.get("status") in ("MODERATE", "HIGH", "OCCASIONAL"):
        # need multi-family already in fuse_leakage
        out.append(
            _h(
                "AIR_LEAKAGE",
                support=["leakage_dimension"],
                against=[],
                alternatives=["style_breathy_aesthetic", "separation_noise"],
                confidence="medium" if leak.get("status") != "OCCASIONAL" else "low",
                why="기류 누출·기식성과 일치할 수 있는 다가족 증거가 있어요.",
            )
        )

    # --- REGISTER ---
    reg = dims.get("register_configuration") or {}
    if reg.get("status") == "TRANSITION_EVENTS":
        events = (reg.get("profile") or {}).get("events") or []
        vocal_ok = [
            e
            for e in events
            if (e.get("validity") or {}).get("vocal_specific", True)
            and not e.get("rejected")
        ]
        if vocal_ok:
            out.append(
                _h(
                    "REGISTER_TRANSITION_DISRUPTION",
                    support=["vocal_specific_register_events"],
                    against=[],
                    alternatives=["vibrato_mistaken_as_transition", "accompaniment_bleed"],
                    confidence="medium",
                    why="검증된 보컬 F0·source 변화가 있는 전환 구간이에요.",
                )
            )

    # --- ABRUPT ONSET ---
    onset = dims.get("onset_offset_coordination") or {}
    if onset.get("status") == "ABRUPT_LIKE":
        out.append(
            _h(
                "ABRUPT_ONSET",
                support=["onset_abrupt_multi_evidence"],
                against=[],
                alternatives=["stylistic_attack"],
                confidence="medium",
                why="소리 시작이 급하게 형성되는 패턴이 반복됐어요.",
            )
        )

    # --- ROUGHNESS ---
    regu = dims.get("phonation_regularity") or {}
    if regu.get("status") in ("REPEATED_IRREGULAR", "INTERMITTENT"):
        out.append(
            _h(
                "APERIODIC_ROUGHNESS",
                support=["regularity_dimension"],
                against=[],
                alternatives=["intentional_distortion"],
                confidence="low" if regu.get("status") == "INTERMITTENT" else "medium",
                why="거칠고 불규칙한 음질 패턴이 관찰됐어요.",
            )
        )

    # --- RESONANCE collapse on high notes (if mid presence drops in profile text) ---
    res = dims.get("resonance_formant_strategy") or {}
    prof = res.get("profile") or {}
    if prof.get("mid_presence") == "낮은 편" and concern_eps:
        out.append(
            _h(
                "RESONANCE_HIGH_NOTE_COLLAPSE",
                support=["mid_presence_low_with_high_note"],
                against=["source_may_also_explain"],
                alternatives=["mic_eq", "vowel_change"],
                confidence="low",
                why="고음과 함께 중역 존재감이 낮게 측정됐어요 (공명 후보).",
            )
        )

    # --- Phrase end ---
    resp = dims.get("respiratory_phonatory_coordination") or {}
    if resp.get("status") == "END_PHRASE_DROP":
        out.append(
            _h(
                "PHRASE_END_SUPPORT_LOSS",
                support=["end_phrase_drop_proxy"],
                against=[],
                alternatives=["artistic_decrescendo"],
                confidence="low",
                why="구절 끝에서 음량·주기성이 함께 떨어지는 패턴이에요.",
            )
        )

    # Firm alone must NOT create bottleneck
    if plane.get("firm_high_strain_low") and not concern_eps:
        # explicitly mark firmness-without-effort as not a bottleneck
        for h in out:
            if h["id"] == "EXCESS_FIRMNESS_WITH_STRAIN":
                h["support_level"] = "not_supported"

    # Attach cause family + goal impact (does not change observations)
    boost = set(bcfg.GOAL_IMPACT_BOOST.get(user_goal) or [])
    for h in out:
        h["cause_family"] = bcfg.CAUSE_FAMILY.get(h["id"], "MIXED")
        h["impact"] = "HIGH" if h["id"] in boost else "MEDIUM"
        if h.get("confidence_label") == "low":
            h["impact"] = "LOW" if h["id"] not in boost else "MEDIUM"
        h["user_title"] = bcfg.USER_TITLES.get(h["id"], h["id"])

    # Sort by impact then confidence
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    conf_o = {"high": 0, "medium": 1, "low": 2}
    out.sort(
        key=lambda h: (
            order.get(h.get("impact"), 9),
            conf_o.get(h.get("confidence_label"), 9),
        )
    )
    return out


def _h(bid, *, support, against, alternatives, confidence, why) -> dict[str, Any]:
    return {
        "id": bid,
        "supporting_evidence": support,
        "contradicting_evidence": against,
        "alternative_explanations": alternatives,
        "confidence_label": confidence,
        "coaching_confidence": confidence,
        "measurement_confidence": confidence,
        "inference_confidence": confidence,
        "support_level": "high"
        if confidence == "high"
        else ("medium" if confidence == "medium" else "low"),
        "why": why,
        "summary": why,
    }
