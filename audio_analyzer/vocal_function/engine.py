"""Vocal Function Engine v2.1 — Functional Vocal Physiology & Technique."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.scoring.segments_v3 import build_windows
from audio_analyzer.vocal_function import config as cfg
from audio_analyzer.vocal_function.alignment import attach_time_fields
from audio_analyzer.vocal_function.episodes.builder import (
    build_high_note_episodes,
    build_register_episodes,
    find_best_self_reference,
    pick_focus_episodes,
)
from audio_analyzer.vocal_function.evidence.families import (
    effort_like,
    effort_secondary_signs,
    firmer_like,
)
from audio_analyzer.vocal_function.evidence_gate import normalize_artifact_flags
from audio_analyzer.vocal_function.observations.segment import observe_segment
from audio_analyzer.vocal_function.rules import fusion as rules
from audio_analyzer.coaching.bottleneck import build_coaching_decision


def _baseline_from_segments(segments: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [s for s in segments if s.get("valid")]
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
    mfdrs = []
    for s in valid:
        src = ((s.get("level2_proxies") or {}).get("glottal_source") or {})
        if src.get("valid") and src.get("estimated_mfdr_norm_proxy") is not None:
            mfdrs.append(float(src["estimated_mfdr_norm_proxy"]))
    return {
        "f0_hz": float(np.median(f0s)) if f0s else None,
        "rms": float(np.median(rmss)) if rmss else None,
        "mfdr_norm": float(np.median(mfdrs)) if mfdrs else None,
    }


def compute_contact_effort_plane(
    segments: list[dict[str, Any]],
    baseline: dict[str, Any],
    episodes: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Same-segment co-occurrence — never global firm_n>0 && effort_n>0."""
    firm_segments: list[dict[str, Any]] = []
    effort_segments: list[dict[str, Any]] = []
    for s in segments:
        if not s.get("valid"):
            continue
        if firmer_like(s, baseline):
            firm_segments.append(s)
        # Plane effort axis uses secondary signs (independent of firm)
        if effort_secondary_signs(s, baseline) or effort_like(s, baseline):
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
        effort = effort_like(s, baseline)
        period = (s.get("observations") or {}).get("periodicity_primary_db")
        rough = (
            (s.get("observations") or {}).get("f0_frame_period_perturbation_proxy_percent")
            or 0
        ) >= 2.5
        recovery_fast = True
        if after and effort_like(after, baseline):
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
) -> dict[str, Any]:
    acoustic = acoustic or {}
    quality = quality or {}
    artifact_flags = normalize_artifact_flags(artifact_flags)
    optional_analysis = optional_analysis or {}

    if quality.get("status") == "fail":
        return {
            "available": False,
            "engine_version": cfg.FUNCTION_ENGINE_VERSION,
            "reason": "quality_gate_failed",
            "functional_quality": "UNAVAILABLE",
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

    contact = rules.fuse_contact(segments)
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

    # LIMITED: cap vocal-specific dims when no_vocals missing
    if functional_quality == "LIMITED":
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
        for e in build_high_note_episodes(raw_high)
    ]
    reg_events = (register.get("profile") or {}).get("events") or []
    register_episodes = [
        attach_time_fields(e, time_origin_sec=origin)
        for e in build_register_episodes(reg_events)
    ]
    episodes = high_note_episodes + register_episodes
    best_self = find_best_self_reference(high_note_episodes)
    if best_self:
        best_self = attach_time_fields(best_self, time_origin_sec=origin)
    focus = pick_focus_episodes(high_note_episodes, best_self=best_self)

    contact_effort_plane = compute_contact_effort_plane(segments, baseline, episodes)

    profile_partial = {
        "dimensions": dimensions,
        "contact_effort_plane": contact_effort_plane,
    }
    coaching_decision = build_coaching_decision(
        profile=profile_partial,
        episodes=episodes,
        focus=focus,
        user_goal=user_goal or technique_goal or "GENERAL_EASE_AND_CONTROL",
        style_context=style_goal or "unspecified",
    )
    # Ensure target has original times
    te = coaching_decision.get("target_episode")
    if te and te.get("original_start_sec") is None:
        coaching_decision["target_episode"] = attach_time_fields(
            te, time_origin_sec=origin
        )

    headlines = [coaching_decision.get("headline")] if coaching_decision.get("headline") else []
    for d in dimensions.values():
        if d.get("hidden") or d.get("confidence_label") == "low":
            continue
        headlines.append(f"{d['display_name']}: {d.get('summary')}")

    warnings = []
    statuses = [
        d.get("status")
        for d in dimensions.values()
        if not d.get("hidden") and d.get("confidence_label") != "low"
    ]
    if len(statuses) >= 3 and len(set(statuses)) == 1:
        warnings.append("FUNCTION_PROFILE_COLLAPSE_WARNING")
    if functional_quality == "LIMITED":
        warnings.append("FUNCTIONAL_QUALITY_LIMITED")

    rejected_reg = (register.get("profile") or {}).get("rejected_events") or []

    quality_badge = {
        "FULL": "충분",
        "LIMITED": "일부 기능 분석만 가능",
        "UNAVAILABLE": "기능 분석 제한",
    }.get(functional_quality, "참고")

    scientific_debug = {
        "engine_version": cfg.FUNCTION_ENGINE_VERSION,
        "metric_registry_version": cfg.METRIC_REGISTRY_VERSION,
        "rule_version": cfg.RULE_VERSION,
        "literature_version": cfg.LITERATURE_VERSION,
        "measurement_mode": cfg.MEASUREMENT_MODE,
        "n_segments": len(segments),
        "n_valid": len(valid),
        "baseline": baseline,
        "style_goal": style_goal,
        "technique_goal": technique_goal,
        "user_goal": user_goal,
        "metric_grades": cfg.METRIC_GRADES,
        "segment_sample": segments[:3],
        "contact_effort_plane": contact_effort_plane,
        "raw_high_note_windows": raw_high,
        "rejected_register_events": rejected_reg,
        "has_no_vocals_contrast": y_no_vocals is not None,
        "time_origin_sec": origin,
        "functional_quality": functional_quality,
    }

    return {
        "available": True,
        "engine_version": cfg.FUNCTION_ENGINE_VERSION,
        "report_version": cfg.REPORT_VERSION,
        "functional_quality": functional_quality,
        "quality_badge": quality_badge,
        "separation_note": separation_note,
        "calibration_status": "uncalibrated_directional",
        "measurement_mode": cfg.MEASUREMENT_MODE,
        "headline": [h for h in headlines[:5] if h],
        "dimensions": dimensions,
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
                "cause_hint": e.get("cause_hint"),
            }
            for e in (focus.get("primary") or []) + (focus.get("secondary") or [])
        ],
        "episodes": episodes,
        "focus_episodes": focus,
        "coaching_decision": coaching_decision,
        "contact_effort_plane": contact_effort_plane,
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
        },
        "disclaimer": (
            "이 분석은 음향 기반 기능 추정이며 해부학적/의학적 진단이 아닙니다."
        ),
        "scientific_debug": scientific_debug,
    }
