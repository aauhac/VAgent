"""Vocal Function Engine v2 — Functional Vocal Physiology & Technique."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.scoring.segments_v3 import build_windows
from audio_analyzer.vocal_function import config as cfg
from audio_analyzer.vocal_function.episodes.builder import (
    build_high_note_episodes,
    build_register_episodes,
    find_best_self_reference,
    pick_focus_episodes,
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
    return {
        "f0_hz": float(np.median(f0s)) if f0s else None,
        "rms": float(np.median(rmss)) if rmss else None,
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
        from audio_analyzer.vocal_function.evidence.families import (
            effort_like,
            firmer_like,
        )

        firm = firmer_like(s)
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
                "before": {
                    "firm": firmer_like(before) if before else None,
                    "effort": effort_like(before, baseline) if before else None,
                },
                "after": {
                    "firm": firmer_like(after) if after else None,
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
    high_note_episodes = build_high_note_episodes(raw_high)
    reg_events = (register.get("profile") or {}).get("events") or []
    register_episodes = build_register_episodes(reg_events)
    episodes = high_note_episodes + register_episodes
    best_self = find_best_self_reference(high_note_episodes)
    focus = pick_focus_episodes(high_note_episodes, best_self=best_self)

    firm_n = (contact.get("profile") or {}).get("firmer_segments") or 0
    effort_n = (effort.get("profile") or {}).get("effort_hit_segments") or 0
    contact_effort_plane = {
        "firm_high_strain_low": firm_n > 0 and effort_n == 0,
        "firm_high_strain_high": firm_n > 0 and effort_n > 0,
        "firm_low_strain_low": firm_n == 0 and effort_n == 0,
        "firm_low_leakage": (leakage.get("status") in ("MODERATE", "HIGH")),
        "distinguishes_firm_vs_strain": True,
    }

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

    rejected_reg = (register.get("profile") or {}).get("rejected_events") or []

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
    }

    return {
        "available": True,
        "engine_version": cfg.FUNCTION_ENGINE_VERSION,
        "report_version": cfg.REPORT_VERSION,
        "calibration_status": "uncalibrated_directional",
        "measurement_mode": cfg.MEASUREMENT_MODE,
        "headline": [h for h in headlines[:5] if h],
        "dimensions": dimensions,
        "high_note_events": [
            {
                "start_sec": e["start_sec"],
                "end_sec": e["end_sec"],
                "episode_id": e.get("episode_id"),
                "concern": e.get("concern"),
                "conclusion": e.get("conclusion"),
                "n_merged_windows": e.get("n_merged_windows"),
                "feature_matrix": e.get("feature_matrix"),
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
