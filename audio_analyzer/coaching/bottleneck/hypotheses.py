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

    high_eps = [e for e in episodes if e.get("type") == "HIGH_NOTE"]
    concern_eps = [e for e in high_eps if e.get("concern")]
    effort_eps = [
        e
        for e in concern_eps
        if ((e.get("feature_matrix") or {}).get("effort") or {}).get("strain_like", 0) >= 0.4
        or e.get("concern")
    ]
    effort_dim = dims.get("vocal_effort_strain") or {}

    # --- EXCESS_EFFORT_HIGH_NOTE: requires HIGH_NOTE episode + same-episode effort ---
    if effort_eps:
        support = [
            _evidence(
                "effort",
                episode_id=e.get("episode_id"),
                metric_ids=["strain_like", "intensity_overshoot"],
                label="high_note_effort_concern_episode",
            )
            for e in effort_eps[:3]
        ]
        against = []
        if plane.get("firm_high_strain_low") and not plane.get("firm_high_strain_high"):
            against.append("firm_without_same_episode_effort")
        conf = "high" if len(effort_eps) >= 2 else "medium"
        out.append(
            _h(
                "EXCESS_EFFORT_HIGH_NOTE",
                support=support,
                against=against,
                alternatives=["intentional_belt", "mic_proximity", "vowel_shift"],
                confidence=conf,
                why=(
                    "고음 episode에서 effort 관련 복합 증거가 "
                    "같은 구간에 함께 나타났어요."
                ),
                supporting_episode_ids=[e.get("episode_id") for e in effort_eps if e.get("episode_id")],
            )
        )
    elif effort_dim.get("status") in ("OCCASIONAL", "MODERATE", "REPEATED"):
        # Global effort without high-note concern → GENERAL, never HIGH_NOTE-named
        out.append(
            _h(
                "GENERAL_EXCESS_EFFORT",
                support=[
                    _evidence(
                        "effort",
                        metric_ids=["vocal_effort_strain"],
                        label="effort_dimension_elevated",
                    )
                ],
                against=["no_high_note_concern_episode"],
                alternatives=["style_intensity", "recording_gain"],
                confidence="low" if effort_dim.get("status") == "OCCASIONAL" else "medium",
                why="고음 episode 없이 여러 구간에서 effort 패턴이 반복됐어요.",
                supporting_episode_ids=[
                    e.get("episode_id")
                    for e in episodes
                    if ((e.get("feature_matrix") or {}).get("effort") or {}).get("strain_like", 0)
                    >= 0.5
                ][:3],
            )
        )

    # --- EXCESS_FIRMNESS_WITH_STRAIN (same-segment/episode overlap only) ---
    if plane.get("firm_high_strain_high"):
        overlap_eps = [
            e
            for e in high_eps
            if ((e.get("feature_matrix") or {}).get("effort") or {}).get("strain_like", 0) >= 0.4
            and ((e.get("feature_matrix") or {}).get("source") or {}).get("contact_firmness", 0)
            >= 0.4
        ]
        out.append(
            _h(
                "EXCESS_FIRMNESS_WITH_STRAIN",
                support=[
                    _evidence(
                        "source",
                        episode_id=(overlap_eps[0].get("episode_id") if overlap_eps else None),
                        metric_ids=["contact_firmness", "strain_like"],
                        label="firm_and_effort_same_window",
                    )
                ],
                against=[],
                alternatives=["style_intentional_firmness"],
                confidence="medium",
                why="같은 구간에서 단단한 접촉 관련 패턴과 effort 증거가 함께 있어요.",
                supporting_episode_ids=[e.get("episode_id") for e in overlap_eps if e.get("episode_id")],
            )
        )

    # --- AIR_LEAKAGE ---
    leak = dims.get("air_leakage_breathiness") or {}
    if leak.get("status") in ("MODERATE", "HIGH", "OCCASIONAL"):
        out.append(
            _h(
                "AIR_LEAKAGE",
                support=[_evidence("source", metric_ids=["air_leakage"], label="leakage_dimension")],
                against=[],
                alternatives=["style_breathy_aesthetic", "separation_noise"],
                confidence="medium" if leak.get("status") != "OCCASIONAL" else "low",
                why="기류 누출·기식성과 일치할 수 있는 다가족 증거가 있어요.",
                supporting_episode_ids=[],
            )
        )

    # --- REGISTER ---
    reg = dims.get("register_configuration") or {}
    if reg.get("status") == "TRANSITION_EVENTS":
        events = (reg.get("profile") or {}).get("events") or []
        vocal_ok = [
            e
            for e in events
            if (e.get("validity") or {}).get("vocal_specific", True) and not e.get("rejected")
        ]
        reg_eps = [e for e in episodes if e.get("type") == "REGISTER_TRANSITION"]
        if vocal_ok:
            out.append(
                _h(
                    "REGISTER_TRANSITION_DISRUPTION",
                    support=[
                        _evidence(
                            "register",
                            episode_id=(reg_eps[0].get("episode_id") if reg_eps else None),
                            metric_ids=["f0_jump", "source_shift"],
                            label="vocal_specific_register_events",
                        )
                    ],
                    against=[],
                    alternatives=["vibrato_mistaken_as_transition", "accompaniment_bleed"],
                    confidence="medium",
                    why="검증된 보컬 F0·source 변화가 있는 전환 구간이에요.",
                    supporting_episode_ids=[
                        e.get("episode_id") for e in reg_eps if e.get("episode_id")
                    ]
                    or [
                        f"REGISTER_TRANSITION_{float(e.get('start_sec') or 0):.1f}_{float(e.get('end_sec') or 0):.1f}"
                        for e in vocal_ok[:2]
                    ],
                )
            )

    # --- ABRUPT ONSET ---
    onset = dims.get("onset_offset_coordination") or {}
    if onset.get("status") == "ABRUPT_LIKE":
        out.append(
            _h(
                "ABRUPT_ONSET",
                support=[
                    _evidence("onset", metric_ids=["onset_slope"], label="onset_abrupt_multi_evidence")
                ],
                against=[],
                alternatives=["stylistic_attack"],
                confidence="medium",
                why="소리 시작이 급하게 형성되는 패턴이 반복됐어요.",
                supporting_episode_ids=[],
            )
        )

    # --- ROUGHNESS ---
    regu = dims.get("phonation_regularity") or {}
    if regu.get("status") in ("REPEATED_IRREGULAR", "INTERMITTENT"):
        out.append(
            _h(
                "APERIODIC_ROUGHNESS",
                support=[
                    _evidence("regularity", metric_ids=["periodicity", "roughness"], label="regularity_dimension")
                ],
                against=[],
                alternatives=["intentional_distortion"],
                confidence="low" if regu.get("status") == "INTERMITTENT" else "medium",
                why="거칠고 불규칙한 음질 패턴이 관찰됐어요.",
                supporting_episode_ids=[],
            )
        )

    # --- RESONANCE collapse: high-note episodes with resonance cause_hint ---
    res = dims.get("resonance_formant_strategy") or {}
    prof = res.get("profile") or {}
    res_eps = [
        e
        for e in high_eps
        if e.get("cause_hint") in ("RESONANCE", "MIXED")
        or ((e.get("feature_matrix") or {}).get("resonance") or {}).get("energy_2_4k_delta") is not None
        and abs(((e.get("feature_matrix") or {}).get("resonance") or {}).get("energy_2_4k_delta") or 0)
        >= 0.05
    ]
    if (prof.get("mid_presence") == "낮은 편" and (concern_eps or res_eps)) or (
        res_eps and any(e.get("cause_hint") == "RESONANCE" for e in res_eps)
    ):
        targets = res_eps or concern_eps
        out.append(
            _h(
                "RESONANCE_HIGH_NOTE_COLLAPSE",
                support=[
                    _evidence(
                        "resonance",
                        episode_id=(targets[0].get("episode_id") if targets else None),
                        metric_ids=["energy_2_4k_delta", "brightness_delta"],
                        label="mid_presence_low_with_high_note",
                    )
                ],
                against=["source_may_also_explain"],
                alternatives=["mic_eq", "vowel_change"],
                confidence="low",
                why="고음과 함께 중역 존재감이 낮게 측정됐어요 (공명 후보).",
                supporting_episode_ids=[e.get("episode_id") for e in targets if e.get("episode_id")],
            )
        )

    # --- Phrase end ---
    resp = dims.get("respiratory_phonatory_coordination") or {}
    if resp.get("status") == "END_PHRASE_DROP":
        out.append(
            _h(
                "PHRASE_END_SUPPORT_LOSS",
                support=[
                    _evidence(
                        "respiratory",
                        metric_ids=["end_phrase_drop"],
                        label="end_phrase_drop_proxy",
                    )
                ],
                against=[],
                alternatives=["artistic_decrescendo"],
                confidence="low",
                why="구절 끝에서 음량·주기성이 함께 떨어지는 패턴이에요.",
                supporting_episode_ids=[],
            )
        )

    boost = set(bcfg.GOAL_IMPACT_BOOST.get(user_goal) or [])
    for h in out:
        h["cause_family"] = bcfg.CAUSE_FAMILY.get(h["id"], "MIXED")
        h["impact"] = "HIGH" if h["id"] in boost else "MEDIUM"
        if h.get("confidence_label") == "low":
            h["impact"] = "LOW" if h["id"] not in boost else "MEDIUM"
        h["user_title"] = bcfg.USER_TITLES.get(h["id"], h["id"])

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    conf_o = {"high": 0, "medium": 1, "low": 2}
    out.sort(
        key=lambda h: (
            order.get(h.get("impact"), 9),
            conf_o.get(h.get("confidence_label"), 9),
        )
    )
    return out


def _evidence(
    family: str,
    *,
    episode_id: str | None = None,
    segment_ids: list | None = None,
    metric_ids: list | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    return {
        "family": family,
        "episode_id": episode_id,
        "segment_ids": segment_ids or [],
        "metric_ids": metric_ids or [],
        "label": label or family,
    }


def _h(
    bid,
    *,
    support,
    against,
    alternatives,
    confidence,
    why,
    supporting_episode_ids=None,
) -> dict[str, Any]:
    return {
        "id": bid,
        "supporting_evidence": support,
        "contradicting_evidence": against,
        "alternative_explanations": alternatives,
        "supporting_episode_ids": [x for x in (supporting_episode_ids or []) if x],
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
