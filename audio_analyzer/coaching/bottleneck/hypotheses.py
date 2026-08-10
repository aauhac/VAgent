"""Hypothesis generation v2.2 — localized episodes required for coachable claims."""

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
    measurement: list[dict[str, Any]] = []

    by_type: dict[str, list] = {}
    for e in episodes:
        by_type.setdefault(e.get("type") or "OTHER", []).append(e)

    high_eps = by_type.get("HIGH_NOTE") or []
    concern_eps = [e for e in high_eps if e.get("concern")]
    effort_high_eps = [
        e
        for e in concern_eps
        if ((e.get("feature_matrix") or {}).get("effort") or {}).get("strain_like", 0) >= 0.4
        or ((e.get("feature_matrix") or {}).get("shifts") or {}).get("effort_shift", 0) >= 0.4
    ]
    general_effort_eps = by_type.get("GENERAL_EFFORT") or []
    leak_eps = by_type.get("AIR_LEAKAGE") or []
    rough_eps = by_type.get("ROUGHNESS") or []
    onset_eps = by_type.get("ABRUPT_ONSET") or []
    phrase_eps = by_type.get("PHRASE_END_DROP") or []
    reg_eps = by_type.get("REGISTER_TRANSITION") or []

    effort_dim = dims.get("vocal_effort_strain") or {}

    # --- EXCESS_EFFORT_HIGH_NOTE ---
    if effort_high_eps:
        out.append(
            _h(
                "EXCESS_EFFORT_HIGH_NOTE",
                support=[
                    _evidence(
                        "effort",
                        episode_id=e.get("episode_id"),
                        metric_ids=["effort_shift", "intensity_delta_db", "strain_like"],
                        label="high_note_effort_episode",
                    )
                    for e in effort_high_eps[:3]
                ],
                against=[],
                alternatives=["intentional_belt", "mic_proximity", "vowel_shift"],
                confidence="high" if len(effort_high_eps) >= 2 else "medium",
                why=_why_effort_high(effort_high_eps[0]),
                supporting_episode_ids=[e.get("episode_id") for e in effort_high_eps if e.get("episode_id")],
            )
        )
    elif effort_dim.get("status") in ("OCCASIONAL", "MODERATE", "REPEATED"):
        if general_effort_eps:
            out.append(
                _h(
                    "GENERAL_EXCESS_EFFORT",
                    support=[
                        _evidence(
                            "effort",
                            episode_id=e.get("episode_id"),
                            metric_ids=["strain_like", "effort_shift"],
                            label="general_effort_episode",
                        )
                        for e in general_effort_eps[:3]
                    ],
                    against=["no_high_note_concern_episode"],
                    alternatives=["style_intensity", "recording_gain"],
                    confidence="medium",
                    why="여러 구간에서 effort 관련 패턴이 반복됐어요.",
                    supporting_episode_ids=[
                        e.get("episode_id") for e in general_effort_eps if e.get("episode_id")
                    ],
                )
            )
        else:
            measurement.append(
                {
                    "issue": "effort",
                    "reason": "effort 차원은 높지만 국소 episode를 찾지 못했어요.",
                    "recommended_task": "strong_sustain_or_high_siren",
                    "eligibility": "NEEDS_MEASUREMENT",
                }
            )

    # --- EXCESS_FIRMNESS_WITH_STRAIN ---
    if plane.get("firm_high_strain_high"):
        overlap_eps = [
            e
            for e in (effort_high_eps or high_eps or general_effort_eps)
            if ((e.get("feature_matrix") or {}).get("effort") or {}).get("strain_like", 0) >= 0.4
            and ((e.get("feature_matrix") or {}).get("source") or {}).get("contact_firmness", 0)
            >= 0.4
        ]
        if overlap_eps:
            out.append(
                _h(
                    "EXCESS_FIRMNESS_WITH_STRAIN",
                    support=[
                        _evidence(
                            "source",
                            episode_id=overlap_eps[0].get("episode_id"),
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
        if leak_eps:
            out.append(
                _h(
                    "AIR_LEAKAGE",
                    support=[
                        _evidence(
                            "source",
                            episode_id=leak_eps[0].get("episode_id"),
                            metric_ids=["air_leakage", "h1_h2", "periodicity"],
                            label="leakage_episode",
                        )
                    ],
                    against=[],
                    alternatives=["style_breathy_aesthetic", "separation_noise"],
                    confidence="medium" if leak.get("status") != "OCCASIONAL" else "low",
                    why="기류 누출·기식성과 일치할 수 있는 다가족 증거가 특정 구간에 있어요.",
                    supporting_episode_ids=[e.get("episode_id") for e in leak_eps if e.get("episode_id")],
                )
            )
        else:
            measurement.append(
                {
                    "issue": "breathiness",
                    "reason": "기식성 경향은 있으나 국소 구간을 특정하지 못했어요.",
                    "recommended_task": "sustain_a_soft",
                    "eligibility": "NEEDS_MEASUREMENT",
                }
            )

    # --- REGISTER ---
    reg = dims.get("register_configuration") or {}
    if reg.get("status") == "TRANSITION_EVENTS" and reg_eps:
        out.append(
            _h(
                "REGISTER_TRANSITION_DISRUPTION",
                support=[
                    _evidence(
                        "register",
                        episode_id=reg_eps[0].get("episode_id"),
                        metric_ids=["f0_delta_cents", "source_shift", "f0_continuity"],
                        label="vocal_specific_register_events",
                    )
                ],
                against=[],
                alternatives=["vibrato_mistaken_as_transition", "accompaniment_bleed"],
                confidence="medium",
                why="검증된 보컬 F0·source 변화가 있는 전환 구간이에요.",
                supporting_episode_ids=[e.get("episode_id") for e in reg_eps if e.get("episode_id")],
            )
        )
    elif reg.get("status") == "TRANSITION_EVENTS":
        measurement.append(
            {
                "issue": "register",
                "reason": "전환 신호는 있으나 재생 가능한 episode가 없어요.",
                "recommended_task": "siren_five_tone",
                "eligibility": "NEEDS_MEASUREMENT",
            }
        )

    # --- ABRUPT ONSET ---
    onset = dims.get("onset_offset_coordination") or {}
    if onset.get("status") == "ABRUPT_LIKE":
        if onset_eps:
            out.append(
                _h(
                    "ABRUPT_ONSET",
                    support=[
                        _evidence(
                            "onset",
                            episode_id=onset_eps[0].get("episode_id"),
                            metric_ids=["onset_slope"],
                            label="onset_abrupt_episode",
                        )
                    ],
                    against=[],
                    alternatives=["stylistic_attack"],
                    confidence="medium",
                    why="소리 시작이 급하게 형성되는 패턴이 특정 구간에 나타났어요.",
                    supporting_episode_ids=[e.get("episode_id") for e in onset_eps if e.get("episode_id")],
                )
            )
        else:
            measurement.append(
                {
                    "issue": "onset",
                    "reason": "급격한 onset 경향은 있으나 구간을 특정하지 못했어요.",
                    "recommended_task": "balanced_onset_hum",
                    "eligibility": "NEEDS_MEASUREMENT",
                }
            )

    # --- ROUGHNESS ---
    regu = dims.get("phonation_regularity") or {}
    if regu.get("status") in ("REPEATED_IRREGULAR", "INTERMITTENT"):
        if rough_eps:
            out.append(
                _h(
                    "APERIODIC_ROUGHNESS",
                    support=[
                        _evidence(
                            "regularity",
                            episode_id=rough_eps[0].get("episode_id"),
                            metric_ids=["periodicity", "roughness"],
                            label="roughness_episode",
                        )
                    ],
                    against=[],
                    alternatives=["intentional_distortion"],
                    confidence="low" if regu.get("status") == "INTERMITTENT" else "medium",
                    why="거칠고 불규칙한 음질 패턴이 특정 구간에 관찰됐어요.",
                    supporting_episode_ids=[e.get("episode_id") for e in rough_eps if e.get("episode_id")],
                )
            )
        else:
            measurement.append(
                {
                    "issue": "roughness",
                    "reason": "불규칙 음질 경향은 있으나 국소 episode가 없어요.",
                    "recommended_task": "sovt_straw",
                    "eligibility": "NEEDS_MEASUREMENT",
                }
            )

    # --- RESONANCE: direction-aware ---
    presence_loss_eps = [
        e
        for e in high_eps
        if e.get("cause_hint") in ("RESONANCE_PRESENCE_LOSS", "RESONANCE")
        or (
            ((e.get("feature_matrix") or {}).get("resonance") or {}).get("energy_2_4k_delta") is not None
            and float(((e.get("feature_matrix") or {}).get("resonance") or {}).get("energy_2_4k_delta"))
            <= -0.04
        )
    ]
    sharpness_eps = [
        e
        for e in high_eps
        if e.get("cause_hint") == "RESONANCE_EXCESS_SHARPNESS"
        or (
            ((e.get("feature_matrix") or {}).get("resonance") or {}).get("energy_2_4k_delta") is not None
            and float(((e.get("feature_matrix") or {}).get("resonance") or {}).get("energy_2_4k_delta"))
            >= 0.04
            and abs(
                float(
                    ((e.get("feature_matrix") or {}).get("resonance") or {}).get(
                        "spectral_centroid_delta"
                    )
                    or 0
                )
            )
            >= 150
        )
    ]
    if presence_loss_eps:
        out.append(
            _h(
                "RESONANCE_HIGH_NOTE_COLLAPSE",
                support=[
                    _evidence(
                        "resonance",
                        episode_id=presence_loss_eps[0].get("episode_id"),
                        metric_ids=["energy_2_4k_delta", "brightness_delta"],
                        label="presence_loss_high_note",
                    )
                ],
                against=["source_may_also_explain"],
                alternatives=["mic_eq", "vowel_change"],
                confidence="medium",
                why="고음에서 중역(2–4k) 존재감이 이전 구간보다 낮아졌어요.",
                supporting_episode_ids=[
                    e.get("episode_id") for e in presence_loss_eps if e.get("episode_id")
                ],
            )
        )
    elif sharpness_eps:
        out.append(
            _h(
                "RESONANCE_MID_PRESENCE_LOSS",  # reuse id map — sharpness as mid strategy
                support=[
                    _evidence(
                        "resonance",
                        episode_id=sharpness_eps[0].get("episode_id"),
                        metric_ids=["energy_2_4k_delta", "centroid_delta"],
                        label="excess_sharpness_candidate",
                    )
                ],
                against=["may_be_aesthetic"],
                alternatives=["style_bright_belt", "mic_eq"],
                confidence="low",
                why="고음에서 밝기·2–4k가 함께 올라가는 패턴이에요 (표현 의도일 수 있어요).",
                supporting_episode_ids=[
                    e.get("episode_id") for e in sharpness_eps if e.get("episode_id")
                ],
            )
        )

    # --- Phrase end ---
    resp = dims.get("respiratory_phonatory_coordination") or {}
    if resp.get("status") == "END_PHRASE_DROP":
        if phrase_eps:
            out.append(
                _h(
                    "PHRASE_END_SUPPORT_LOSS",
                    support=[
                        _evidence(
                            "respiratory",
                            episode_id=phrase_eps[0].get("episode_id"),
                            metric_ids=["rms", "periodicity"],
                            label="phrase_end_episode",
                        )
                    ],
                    against=[],
                    alternatives=["artistic_decrescendo"],
                    confidence="medium",
                    why="구절 끝에서 음량·주기성이 함께 떨어지는 구간이 있어요.",
                    supporting_episode_ids=[
                        e.get("episode_id") for e in phrase_eps if e.get("episode_id")
                    ],
                )
            )
        else:
            measurement.append(
                {
                    "issue": "phrase_end",
                    "reason": "구절 끝 지지 약화 신호는 있으나 국소화하지 못했어요.",
                    "recommended_task": "messa_di_voce_short",
                    "eligibility": "NEEDS_MEASUREMENT",
                }
            )

    # Goal affects IMPACT only — never confidence/eligibility
    boost = set(bcfg.GOAL_IMPACT_BOOST.get(user_goal) or [])
    for h in out:
        h["cause_family"] = bcfg.CAUSE_FAMILY.get(h["id"], "MIXED")
        h["impact"] = "HIGH" if h["id"] in boost else "MEDIUM"
        if h.get("confidence_label") == "low":
            h["impact"] = "LOW" if h["id"] not in boost else "MEDIUM"
            # low remains low confidence — ranker will exclude from primary
        h["user_title"] = bcfg.USER_TITLES.get(h["id"], h["id"])
        h["eligibility"] = (
            "COACHABLE"
            if (
                h.get("confidence_label") in ("medium", "high")
                and (h.get("supporting_episode_ids") or [])
            )
            else "NEEDS_MEASUREMENT"
        )

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    conf_o = {"high": 0, "medium": 1, "low": 2}
    out.sort(
        key=lambda h: (
            order.get(h.get("impact"), 9),
            conf_o.get(h.get("confidence_label"), 9),
        )
    )
    # attach measurement candidates on profile side via special marker
    for m in measurement:
        m["eligibility"] = "NEEDS_MEASUREMENT"
    # stash for build_coaching_decision via hypotheses meta
    for h in out:
        h.setdefault("_measurement_sidecar", measurement)
    if out:
        out[0]["_all_measurement_candidates"] = measurement
    elif measurement:
        # placeholder so decision layer can read them
        out.append(
            {
                "id": "_MEASUREMENT_ONLY",
                "supporting_evidence": [],
                "supporting_episode_ids": [],
                "confidence_label": "low",
                "eligibility": "NEEDS_MEASUREMENT",
                "impact": "LOW",
                "support_level": "not_supported",
                "_all_measurement_candidates": measurement,
                "why": "",
                "summary": "",
                "user_title": "",
                "alternative_explanations": [],
                "contradicting_evidence": [],
            }
        )
    return out


def _why_effort_high(ep: dict[str, Any]) -> str:
    fm = ep.get("feature_matrix") or {}
    eff = fm.get("effort") or {}
    reg = fm.get("regularity") or {}
    start = ep.get("original_start_sec", ep.get("start_sec"))
    end = ep.get("original_end_sec", ep.get("end_sec"))
    bits = []
    if start is not None and end is not None:
        bits.append(f"{float(start):.0f}–{float(end):.0f}초 고음에서")
    idb = eff.get("intensity_delta_db")
    if idb is not None:
        bits.append(f"이전보다 음량이 약 {idb:+.1f} dB")
    if (eff.get("effort_shift") or 0) >= 0.4 or (eff.get("strain_like") or 0) >= 0.4:
        bits.append("effort 관련 패턴이 함께 나타났어요")
    if (reg.get("periodicity") or 0) >= 8 and not reg.get("roughness"):
        bits.append("주기성은 비교적 유지됐습니다")
    if not bits:
        return "고음 episode에서 effort 관련 복합 증거가 같은 구간에 나타났어요."
    return ". ".join(bits) + "."


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
