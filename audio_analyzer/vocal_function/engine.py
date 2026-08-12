"""Vocal Function Engine v2.1 — Functional Vocal Physiology & Technique."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.scoring.segments_v3 import build_windows
from audio_analyzer.vocal_function import config as cfg
from audio_analyzer.vocal_function.alignment import attach_time_fields
from audio_analyzer.vocal_function.episodes.builder import (
    build_generic_episodes_from_segments,
    build_high_note_episodes,
    build_register_episodes,
    find_best_self_reference,
    pick_focus_episodes,
)
from audio_analyzer.vocal_function.evidence.families import (
    effort_like,
    firmer_like,
    leakage_like,
    rough_like,
)
from audio_analyzer.vocal_function.evidence_gate import normalize_artifact_flags
from audio_analyzer.vocal_function.observations.segment import observe_segment
from audio_analyzer.vocal_function.rules import fusion as rules
from audio_analyzer.coaching.bottleneck import build_coaching_decision


def _baseline_from_segments(segments: list[dict[str, Any]]) -> dict[str, Any]:
    """Prefer global-valid segments; fall back to vocal-presence to reduce healthy-subset bias."""
    from audio_analyzer.vocal_evidence.phonation_quality import vocal_presence_ok

    valid = [s for s in segments if s.get("valid")]
    if len(valid) < 3:
        valid = [s for s in segments if vocal_presence_ok(s)]
    if not valid:
        return {}
    f0s = [
        (s.get("observations") or {}).get("f0_hz")
        for s in valid
        if (s.get("observations") or {}).get("f0_hz")
    ]
    rmss = [
        (s.get("observations") or {}).get("rms")
        for s in valid
        if (s.get("observations") or {}).get("rms") is not None
    ]
    e24s = [
        (s.get("observations") or {}).get("energy_2_4k")
        for s in valid
        if (s.get("observations") or {}).get("energy_2_4k") is not None
    ]
    mfdrs = []
    for s in valid:
        src = ((s.get("level2_proxies") or {}).get("glottal_source") or {})
        if src.get("valid") and src.get("estimated_mfdr_norm_proxy") is not None:
            mfdrs.append(float(src["estimated_mfdr_norm_proxy"]))
    out: dict[str, Any] = {}
    if f0s:
        out["f0_hz"] = float(np.median(f0s))
    if rmss:
        out["rms"] = float(np.median(rmss))
    if mfdrs:
        out["mfdr_norm"] = float(np.median(mfdrs))
    if e24s:
        out["energy_24k"] = float(np.median(e24s))
    out["n_baseline_segments"] = len(valid)
    out["baseline_selection"] = (
        "global_valid" if any(s.get("valid") for s in valid) and len([s for s in segments if s.get("valid")]) >= 3
        else "vocal_presence_fallback"
    )
    return out


def compute_contact_effort_plane(
    segments: list[dict[str, Any]],
    baseline: dict[str, Any],
    episodes: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Same-segment co-occurrence — never global firm_n>0 && effort_n>0."""
    from audio_analyzer.vocal_function.validity import dim_valid

    firm_segments: list[dict[str, Any]] = []
    effort_segments: list[dict[str, Any]] = []
    for i, s in enumerate(segments):
        if dim_valid(s, "glottal_contact") and firmer_like(s, baseline):
            firm_segments.append(s)
        pre = segments[i - 1] if i > 0 else None
        post = segments[i + 1] if i + 1 < len(segments) else None
        if dim_valid(s, "effort") and effort_like(s, baseline, pre=pre, post=post):
            effort_segments.append(s)

    firm_keys = {(float(s["start_sec"]), float(s["end_sec"])) for s in firm_segments}
    effort_keys = {(float(s["start_sec"]), float(s["end_sec"])) for s in effort_segments}
    overlap_keys = firm_keys & effort_keys
    firm_n = len(firm_keys)
    effort_n = len(effort_keys)
    overlap_n = len(overlap_keys)
    denom_union = max(1, len(firm_keys | effort_keys))
    denom_firm = max(1, firm_n)
    denom_effort = max(1, effort_n)

    ep_overlap_n = 0
    if episodes:
        for e in episodes:
            fm = e.get("feature_matrix") or {}
            firm = ((fm.get("source") or {}).get("contact_firmness") or 0) >= 0.4
            effort = ((fm.get("effort") or {}).get("strain_like") or 0) >= 0.4
            if firm and effort:
                ep_overlap_n += 1

    firm_high_strain_high = overlap_n > 0 or ep_overlap_n > 0
    firm_high_strain_low = firm_n > 0 and overlap_n == 0 and ep_overlap_n == 0

    return {
        "firm_segments": firm_n,
        "effort_segments": effort_n,
        "firm_effort_overlap_segments": overlap_n,
        "firm_effort_overlap_ratio": round(overlap_n / denom_union, 3),
        "firm_without_effort_ratio": round((firm_n - overlap_n) / denom_firm, 3),
        "effort_without_firm_ratio": round((effort_n - overlap_n) / denom_effort, 3),
        "episode_firm_effort_overlap": ep_overlap_n,
        "firm_high_strain_low": firm_high_strain_low,
        "firm_high_strain_high": firm_high_strain_high,
        "firm_low_strain_low": firm_n == 0 and effort_n == 0,
        "distinguishes_firm_vs_strain": True,
        "co_occurrence_method": "same_segment_or_episode",
    }


def analyze_high_note_events(
    segments: list[dict[str, Any]],
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    """Raw high-note windows — only vocal-specific valid F0 frames."""
    valid = [
        s
        for s in segments
        if s.get("valid") and (s.get("vocal_evidence") or {}).get("vocal_specific", True)
    ]
    f0s = [
        (s.get("observations") or {}).get("f0_hz")
        for s in valid
        if (s.get("observations") or {}).get("f0_hz")
    ]
    if len(f0s) < 3:
        return []
    thr = float(np.percentile(f0s, 80))
    events = []
    for i, s in enumerate(valid):
        f0 = (s.get("observations") or {}).get("f0_hz")
        if not f0 or f0 < thr:
            continue
        ve = s.get("vocal_evidence") or {}
        if not ve.get("vocal_specific", True):
            continue
        if (ve.get("accompaniment_match") or 0) >= 0.7:
            events.append(
                {
                    "start_sec": s["start_sec"],
                    "end_sec": s["end_sec"],
                    "rejected": True,
                    "reason_code": "HIGH_NOTE_EVENT_REJECTED",
                    "detail": "accompaniment_contamination",
                }
            )
            continue

        before = valid[i - 1] if i > 0 else None
        after = valid[i + 1] if i + 1 < len(valid) else None

        firm = firmer_like(s, baseline)
        pre = valid[i - 1] if i > 0 else None
        after = valid[i + 1] if i + 1 < len(valid) else None
        effort = effort_like(s, baseline, pre=pre, post=after)
        period = (s.get("observations") or {}).get("periodicity_primary_db")
        rough = (
            (s.get("observations") or {}).get("f0_frame_period_perturbation_proxy_percent")
            or 0
        ) >= 2.5
        recovery_fast = True
        if after and effort_like(
            after,
            baseline,
            pre=s,
            post=valid[i + 2] if i + 2 < len(valid) else None,
        ):
            recovery_fast = False

        if firm and not effort and (period or 0) >= 8 and not rough and recovery_fast:
            conclusion = (
                "단단한 발성 상태는 관찰되지만, 이번 구간에서 과도한 effort와 "
                "일치하는 증거는 강하지 않았어요."
            )
            concern = False
        elif firm and effort:
            conclusion = (
                "고음에서 힘이 과도하게 증가한 발성과 일치할 수 있는 "
                "복합적인 음향 패턴이 관찰됐어요."
            )
            concern = True
        elif effort:
            conclusion = (
                "고음 진입에서 과도한 effort와 일치할 수 있는 "
                "복합 음향 변화가 나타났어요."
            )
            concern = True
        else:
            conclusion = "고음 구간 관찰."
            concern = False

        events.append(
            {
                "start_sec": s["start_sec"],
                "end_sec": s["end_sec"],
                "f0_hz": f0,
                "f0_percentile": 80,
                "contact_profile_during": "firmer_like" if firm else "lighter_or_mid",
                "effort_during": "elevated" if effort else "not_elevated",
                "periodicity": period,
                "roughness": rough,
                "recovery_fast": recovery_fast,
                "concern": concern,
                "conclusion": conclusion,
                "limitation": "실제 후두 근육 긴장을 직접 측정한 것은 아닙니다.",
                "validity": ve,
                "rejected": False,
                "observations": s.get("observations"),
                "level2_proxies": s.get("level2_proxies"),
                "before": {
                    "firm": firmer_like(before, baseline) if before else None,
                    "effort": effort_like(before, baseline) if before else None,
                },
                "after": {
                    "firm": firmer_like(after, baseline) if after else None,
                    "effort": effort_like(after, baseline) if after else None,
                },
            }
        )
    return [e for e in events if not e.get("rejected")]


def compute_vocal_function_profile(
    *,
    y: np.ndarray,
    sr: int,
    pitch: dict[str, Any],
    acoustic: Optional[dict[str, Any]] = None,
    quality: Optional[dict[str, Any]] = None,
    optional_analysis: Optional[dict[str, Any]] = None,
    source_mode: str = "raw",
    artifact_flags: Optional[dict[str, Any]] = None,
    style_goal: str = "unspecified",
    technique_goal: Optional[str] = None,
    personal_baseline: Optional[dict[str, Any]] = None,
    y_no_vocals: Optional[np.ndarray] = None,
    user_goal: str = "GENERAL_EASE_AND_CONTROL",
    time_origin_sec: float = 0.0,
    functional_quality: str = "FULL",
    separation_note: Optional[str] = None,
    input_mode: str = "AUTO",
) -> dict[str, Any]:
    acoustic = acoustic or {}
    quality = quality or {}
    artifact_flags = normalize_artifact_flags(artifact_flags)
    optional_analysis = optional_analysis or {}
    input_mode = (input_mode or "AUTO").upper()

    if quality.get("status") == "fail":
        return {
            "available": False,
            "engine_version": cfg.FUNCTION_ENGINE_VERSION,
            "reason": "quality_gate_failed",
            "functional_quality": "UNAVAILABLE",
            "input_mode": input_mode,
        }

    if functional_quality == "UNAVAILABLE":
        return {
            "available": False,
            "engine_version": cfg.FUNCTION_ENGINE_VERSION,
            "report_version": cfg.REPORT_VERSION,
            "functional_quality": "UNAVAILABLE",
            "reason": "separation_required_failed",
            "user_message": separation_note
            or (
                "반주와 보컬을 충분히 분리하지 못해 "
                "일부 기능적 발성 분석은 제공하지 않았어요."
            ),
            "headline": [
                "반주와 보컬을 충분히 분리하지 못해 일부 기능적 발성 분석은 제공하지 않았어요."
            ],
            "analysis_time_origin_sec": float(time_origin_sec or 0),
            "input_mode": input_mode,
        }

    duration = len(y) / float(sr)
    windows = build_windows(duration, max_windows=24)
    segments = [
        observe_segment(
            y,
            sr,
            float(a),
            float(b),
            pitch,
            source_mode=source_mode,
            artifact_flags=artifact_flags,
            y_no_vocals=y_no_vocals,
        )
        for a, b in windows
    ]
    valid = [s for s in segments if s.get("valid")]
    baseline = personal_baseline or _baseline_from_segments(segments)

    contact = rules.fuse_contact(segments, baseline_obs=baseline)
    leakage = rules.fuse_leakage(segments)
    effort = rules.fuse_effort(segments, baseline_obs=baseline)
    regularity = rules.fuse_regularity(segments)
    vibrato_raw = optional_analysis.get("vibrato") or {}
    register = rules.fuse_register(segments, pitch, vibrato=vibrato_raw)
    onset = rules.fuse_onset_offset(segments)
    vibrato = rules.fuse_vibrato(optional_analysis)
    resonance = rules.fuse_resonance(segments)
    respiratory = rules.fuse_respiratory(segments)
    economy = rules.fuse_economy(segments, effort)

    # LIMITED (mixed path missing contrast): cap dims — NOT for FULL_VOCAL_ONLY
    if functional_quality == "LIMITED" and input_mode != "VOCAL_ONLY":
        for d in (contact, leakage, effort, register, resonance):
            d["confidence_label"] = "low"
            d["status"] = "UNKNOWN"
            d["hidden"] = True
            d["summary"] = "분리 제약이 있어 이번엔 판단하지 않았어요."

    dimensions = {
        "glottal_contact_profile": contact,
        "air_leakage_breathiness": leakage,
        "vocal_effort_strain": effort,
        "phonation_regularity": regularity,
        "register_configuration": register,
        "onset_offset_coordination": onset,
        "vibrato_control": vibrato,
        "resonance_formant_strategy": resonance,
        "respiratory_phonatory_coordination": respiratory,
        "phonatory_economy_proxy": economy,
    }

    raw_high = analyze_high_note_events(segments, baseline)
    origin = float(time_origin_sec or 0.0)
    high_note_episodes = [
        attach_time_fields(e, time_origin_sec=origin)
        for e in build_high_note_episodes(raw_high, all_segments=segments)
    ]
    reg_events = (register.get("profile") or {}).get("events") or []
    register_episodes = [
        attach_time_fields(e, time_origin_sec=origin)
        for e in build_register_episodes(reg_events, all_segments=segments)
    ]

    leakage_episodes = [
        attach_time_fields(e, time_origin_sec=origin)
        for e in build_generic_episodes_from_segments(
            segments,
            episode_type="AIR_LEAKAGE",
            predicate=leakage_like,
            all_segments=segments,
        )
    ]
    roughness_episodes = [
        attach_time_fields(e, time_origin_sec=origin)
        for e in build_generic_episodes_from_segments(
            segments,
            episode_type="ROUGHNESS",
            predicate=rough_like,
            all_segments=segments,
        )
    ]
    onset_episodes = [
        attach_time_fields(e, time_origin_sec=origin)
        for e in build_generic_episodes_from_segments(
            segments,
            episode_type="ABRUPT_ONSET",
            predicate=lambda s: ((s.get("observations") or {}).get("onset_slope_db_per_sec") or 0)
            >= 80,
            all_segments=segments,
            gap_sec=0.4,
        )
    ]
    # Trajectory-aware effort elevation keys (PRE/DURING/POST)
    effort_elevated_keys = set()
    for i, s in enumerate(segments):
        pre = segments[i - 1] if i > 0 else None
        post = segments[i + 1] if i + 1 < len(segments) else None
        if effort_like(s, baseline, pre=pre, post=post):
            effort_elevated_keys.add((float(s["start_sec"]), float(s["end_sec"])))

    effort_episodes = [
        attach_time_fields(e, time_origin_sec=origin)
        for e in build_generic_episodes_from_segments(
            segments,
            episode_type="GENERAL_EFFORT",
            predicate=lambda s: (float(s["start_sec"]), float(s["end_sec"]))
            in effort_elevated_keys,
            all_segments=segments,
        )
    ]
    phrase_end_episodes = [
        attach_time_fields(e, time_origin_sec=origin)
        for e in build_generic_episodes_from_segments(
            segments,
            episode_type="PHRASE_END_DROP",
            predicate=lambda s: (
                ((s.get("observations") or {}).get("rms") is not None)
                and baseline.get("rms")
                and float(s["observations"]["rms"]) < float(baseline["rms"]) * 0.45
                and ((s.get("observations") or {}).get("periodicity_primary_db") or 99) <= 8
            ),
            all_segments=segments,
        )
    ]

    episodes = (
        high_note_episodes
        + register_episodes
        + leakage_episodes
        + roughness_episodes
        + onset_episodes
        + effort_episodes
        + phrase_end_episodes
    )
    best_self = find_best_self_reference(high_note_episodes)
    if best_self:
        best_self = attach_time_fields(best_self, time_origin_sec=origin)
    focus = pick_focus_episodes(high_note_episodes, best_self=best_self)

    contact_effort_plane = compute_contact_effort_plane(segments, baseline, episodes)

    from audio_analyzer.vocal_function.criteria_matrix import build_criteria_matrix
    from audio_analyzer.vocal_function.profiles import (
        build_high_note_function_profile,
        build_timbre_profile_v211,
        partition_pitch_regions,
    )

    criteria_matrix = build_criteria_matrix(
        dimensions=dimensions,
        segments=segments,
        episodes=episodes,
    )

    mid_segs, high_segs, _pitch_ctx = partition_pitch_regions(segments)
    high_note_function_profile = build_high_note_function_profile(
        segments=segments,
        dimensions=dimensions,
        baseline=baseline,
        episodes=episodes,
        input_mode=input_mode,
        functional_quality=functional_quality,
    )
    timbre_profile = build_timbre_profile_v211(
        segments=segments,
        mid_segments=mid_segs,
        high_segments=high_segs,
        input_mode=input_mode,
        functional_quality=functional_quality,
    )

    from audio_analyzer.vocal_function.derived import (
        build_effort_assessment,
        check_effort_report_consistency,
        effort_display_bundle,
    )

    effort_assessment = build_effort_assessment(
        effort,
        episodes=episodes,
        high_note_profile=high_note_function_profile,
        valid_segment_count=len(valid),
    )
    # Attach canonical assessment to effort dimension (shared SoT)
    effort["effort_assessment"] = effort_assessment
    effort["display"] = effort_display_bundle(effort_assessment)
    # Presentation continuum for profile axis (explicit display_position)
    effort["display_continuum_0_to_1"] = effort_assessment.get("display_continuum")
    if effort.get("summary") in ("안정", "중간", "일부 증가", "반복적인 과도 증가"):
        effort["summary"] = effort_assessment.get("label") or effort.get("summary")

    profile_partial = {
        "dimensions": dimensions,
        "contact_effort_plane": contact_effort_plane,
        "criteria_matrix": criteria_matrix,
        "high_note_function_profile": high_note_function_profile,
        "timbre_profile": timbre_profile,
        "effort_assessment": effort_assessment,
    }
    coaching_decision = build_coaching_decision(
        profile=profile_partial,
        episodes=episodes,
        focus=focus,
        user_goal=user_goal or technique_goal or "GENERAL_EASE_AND_CONTROL",
        style_context=style_goal or "unspecified",
        criteria_matrix=criteria_matrix,
    )
    te = coaching_decision.get("target_episode")
    if te and te.get("original_start_sec") is None:
        coaching_decision["target_episode"] = attach_time_fields(te, time_origin_sec=origin)
    # Recompute best-self vs primary target when available
    if coaching_decision.get("target_episode"):
        tgt_id = coaching_decision["target_episode"].get("episode_id")
        tgt = next((e for e in episodes if e.get("episode_id") == tgt_id), None)
        if tgt:
            bs2 = find_best_self_reference(episodes, target=tgt)
            if bs2:
                coaching_decision["best_self_reference"] = attach_time_fields(
                    bs2, time_origin_sec=origin
                )

    from audio_analyzer.coach_profile import compute_vocal_type_profile

    vocal_type_profile = compute_vocal_type_profile(
        segments=segments,
        dimensions=dimensions,
        episodes=episodes,
        baseline=baseline,
        coaching_decision=coaching_decision,
        criteria_matrix=criteria_matrix,
        user_goal=user_goal or technique_goal or "GENERAL_EASE_AND_CONTROL",
    )

    from audio_analyzer.audit.consistency import apply_consistency_patches

    vocal_type_profile, coaching_decision, _cons = apply_consistency_patches(
        vocal_type=vocal_type_profile,
        coaching_decision=coaching_decision,
        report={
            "criteria_matrix": criteria_matrix,
            "dimensions": dimensions,
            "effort_assessment": effort_assessment,
        },
    )
    effort_consistency = check_effort_report_consistency(
        assessment=effort_assessment,
        coaching_decision=coaching_decision,
        dimensions=dimensions,
    )
    vocal_type_profile.setdefault("warnings", [])
    for issue in _cons.get("issues") or []:
        if issue.get("severity") == "ERROR":
            vocal_type_profile["warnings"].append(f"CONSISTENCY_{issue['id'].upper()}")
    for issue in effort_consistency:
        if issue.get("severity") in ("ERROR", "WARN"):
            tag = f"EFFORT_CONSISTENCY_{issue['id'].upper()}"
            if tag not in vocal_type_profile["warnings"]:
                vocal_type_profile["warnings"].append(tag)

    headlines = [coaching_decision.get("headline")] if coaching_decision.get("headline") else []
    if vocal_type_profile.get("display_name") and vocal_type_profile.get("type_id") != "UNRESOLVED":
        headlines.insert(0, vocal_type_profile.get("display_name"))
    for d in dimensions.values():
        if d.get("hidden") or d.get("confidence_label") == "low":
            continue
        headlines.append(f"{d['display_name']}: {d.get('summary')}")

    warnings = list(vocal_type_profile.get("warnings") or [])
    for w in vocal_type_profile.get("warnings") or []:
        if w.startswith("HEAD_CHEST") and w not in warnings:
            warnings.append(w)
    statuses = [
        d.get("status")
        for d in dimensions.values()
        if not d.get("hidden") and d.get("confidence_label") != "low"
    ]
    if len(statuses) >= 3 and len(set(statuses)) == 1:
        warnings.append("FUNCTION_PROFILE_COLLAPSE_WARNING")
    if functional_quality == "LIMITED":
        warnings.append("FUNCTIONAL_QUALITY_LIMITED")
    for issue in _cons.get("issues") or []:
        if issue.get("severity") in ("ERROR", "WARN"):
            tag = f"CONSISTENCY_{issue['id'].upper()}"
            if tag not in warnings:
                warnings.append(tag)

    rejected_reg = (register.get("profile") or {}).get("rejected_events") or []

    quality_badge = {
        "FULL": "기능 분석 범위: 충분",
        "FULL_MIXED": "기능 분석 범위: 충분",
        "FULL_VOCAL_ONLY": "입력 신호 상태: 분석 가능",
        "LIMITED": "일부 기능 분석만 가능",
        "UNAVAILABLE": "기능 분석 제한",
    }.get(functional_quality, "참고")
    quality_badge_note = (
        "분석 가능 범위는 충분하지만 항목별 신뢰도는 다를 수 있어요."
        if functional_quality in ("FULL", "FULL_MIXED", "FULL_VOCAL_ONLY")
        else None
    )

    scientific_debug = {
        "engine_version": cfg.FUNCTION_ENGINE_VERSION,
        "n_segments": len(segments),
        "n_valid": len(valid),
        "baseline": baseline,
        "user_goal": user_goal,
        "contact_effort_plane": contact_effort_plane,
        "raw_high_note_windows": raw_high,
        "rejected_register_events": rejected_reg,
        "has_no_vocals_contrast": y_no_vocals is not None,
        "time_origin_sec": origin,
        "functional_quality": functional_quality,
        "input_mode": input_mode,
        "breathiness_coverage": leakage.get("breathiness_coverage"),
        "roughness_coverage": regularity.get("roughness_coverage"),
        "effort_assessment": effort_assessment,
        "effort_consistency_issues": effort_consistency,
        # Full segment list for offline paired audits (stripped from public report)
        "segments": segments,
    }

    return {
        "available": True,
        "engine_version": cfg.FUNCTION_ENGINE_VERSION,
        "report_version": cfg.REPORT_VERSION,
        "functional_quality": functional_quality,
        "quality_badge": quality_badge,
        "quality_badge_note": quality_badge_note,
        "input_mode": input_mode,
        "separation_note": separation_note,
        "calibration_status": "uncalibrated_directional",
        "measurement_mode": cfg.MEASUREMENT_MODE,
        "headline": [h for h in headlines[:5] if h],
        "dimensions": dimensions,
        "high_note_function_profile": high_note_function_profile,
        "timbre_profile": timbre_profile,
        "high_note_events": [
            {
                "start_sec": e["start_sec"],
                "end_sec": e["end_sec"],
                "local_start_sec": e.get("local_start_sec", e["start_sec"]),
                "local_end_sec": e.get("local_end_sec", e["end_sec"]),
                "original_start_sec": e.get("original_start_sec"),
                "original_end_sec": e.get("original_end_sec"),
                "time_origin_sec": e.get("time_origin_sec", origin),
                "episode_id": e.get("episode_id"),
                "concern": e.get("concern"),
                "conclusion": e.get("conclusion"),
                "n_merged_windows": e.get("n_merged_windows"),
                "feature_matrix": e.get("feature_matrix"),
                "phase_method": e.get("phase_method"),
                "phase_confidence": e.get("phase_confidence"),
                "cause_hint": e.get("cause_hint"),
            }
            for e in (focus.get("primary") or []) + (focus.get("secondary") or [])
        ],
        "episodes": episodes,
        "focus_episodes": focus,
        "coaching_decision": coaching_decision,
        "contact_effort_plane": contact_effort_plane,
        "criteria_matrix": criteria_matrix,
        "effort_assessment": effort_assessment,
        "effort_consistency_audit": {
            "ok": not any(i.get("severity") == "WARN" for i in effort_consistency),
            "issues": effort_consistency,
        },
        "vocal_type_profile": vocal_type_profile,
        "personal_baseline": baseline,
        "style_goal": style_goal,
        "technique_goal": technique_goal,
        "user_goal": user_goal,
        "valid_segment_count": len(valid),
        "total_segment_count": len(segments),
        "analysis_time_origin_sec": origin,
        "warnings": warnings,
        "layers": {
            "0": "VOCAL_EVIDENCE_GATE",
            "1": "DIRECT_ACOUSTIC_OBSERVATIONS",
            "2": "GLOTTAL_SOURCE_VOCAL_TRACT_PROXIES",
            "3": "FUNCTIONAL_STATE_ESTIMATE",
            "4": "EPISODES_BOTTLENECKS",
            "5": "COACHING_DECISION",
            "6": "VOCAL_TYPE_COACH_PROFILE",
        },
        "disclaimer": (
            "이 분석은 음향 기반 기능 추정이며 해부학적/의학적 진단이 아닙니다."
        ),
        "scientific_debug": scientific_debug,
    }
