"""
vocal_quality/engine.py
-----------------------
Compute Vocal Quality / Phonation State Profile from analysis audio.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.scoring.duration_policy_v3 import build_voiced_mask
from audio_analyzer.scoring.segments_v3 import build_windows

from . import config as cfg
from .metrics import segment_observations
from .rules import (
    fuse_breathy,
    fuse_onset,
    fuse_pressed,
    fuse_resonance,
    fuse_rough,
    fuse_transition,
)


def _peak_rms(y: np.ndarray, sr: int) -> float:
    frame = max(1, sr // 10)
    env = np.sqrt(
        np.maximum(np.convolve(y**2, np.ones(frame) / frame, mode="same"), 0)
    )
    return float(np.max(env)) + 1e-9


def build_vocal_segments(
    y: np.ndarray,
    sr: int,
    pitch: dict[str, Any],
) -> list[dict[str, Any]]:
    duration = len(y) / float(sr)
    windows = build_windows(duration, max_windows=cfg.MAX_SEGMENTS)
    peak = _peak_rms(y, sr)
    voiced_mask, hop = build_voiced_mask(pitch, duration_sec=duration)
    segs = []
    for start, end in windows:
        a, b = int(start * sr), int(end * sr)
        chunk = y[a:b]
        if len(chunk) < sr // 4:
            continue
        rms = float(np.sqrt(np.mean(chunk**2)))
        if rms < peak * cfg.MIN_RMS_RATIO:
            continue
        # vocal-dominant proxy via voiced ratio
        obs = segment_observations(y, sr, start, end, pitch)
        if obs["voiced_ratio"] < cfg.MIN_VOICED_RATIO:
            obs["valid"] = False
            obs["invalid_reason"] = "low_voiced_ratio"
        segs.append(obs)
    return segs


def compute_vocal_quality_profile(
    *,
    y: np.ndarray,
    sr: int,
    pitch: dict[str, Any],
    acoustic: Optional[dict[str, Any]] = None,
    quality: Optional[dict[str, Any]] = None,
    source_mode: str = "raw",
    artifact_flags: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    acoustic = acoustic or {}
    quality = quality or {}
    artifact_flags = artifact_flags or {}

    if quality.get("status") == "fail":
        return {
            "available": False,
            "engine_version": cfg.ENGINE_VERSION,
            "reason": "quality_gate_failed",
            "dimensions": {},
            "focus_segments": [],
            "scientific_debug": {"note": "quality fail"},
        }

    segments = build_vocal_segments(np.asarray(y, dtype=np.float32), int(sr), pitch)
    valid = [s for s in segments if s.get("valid")]

    # Spectral/harmonic dims unknown if demucs HF loss likely on separated stems
    spectral_blocked = bool(
        source_mode == "separated"
        and artifact_flags.get("demucs_high_band_loss_likely")
    )

    breathy = fuse_breathy(segments)
    pressed = fuse_pressed(segments, breathy_hits=breathy.get("hit_segment_count") or 0)
    rough = fuse_rough(segments)

    if spectral_blocked:
        # Downgrade spectral-heavy dimensions
        if breathy["status"] not in ("UNKNOWN", "LOW"):
            # keep periodicity-only as intermittent max without spectral family → already required 2 families
            pass
        resonance = {
            "dimension_id": "resonance_timbre",
            "display_name": cfg.DIMENSION_DISPLAY["resonance_timbre"],
            "status": "UNKNOWN",
            "status_label": cfg.STATUS_LABELS["UNKNOWN"],
            "prevalence": "unknown",
            "prevalence_label": cfg.PREVALENCE_LABELS["unknown"],
            "confidence_label": "low",
            "summary": "보컬 분리 고역 손실 가능성으로 공명·음색 프로필을 확정하지 않았어요.",
            "observations": [],
            "focus_segments": [],
            "what_it_may_mean": "",
            "what_we_cannot_know": "인두·비강·후두 위치를 측정하지 않습니다.",
            "practice": [],
            "hidden": True,
            "profile": {},
            "valid_segment_count": len(valid),
            "hit_segment_count": 0,
        }
        # If pressed relied on spectral, force unknown when blocked and only spectral evidence
        if pressed["status"] in ("HIGH", "MODERATE") and source_mode == "separated":
            pressed = {
                **pressed,
                "status": "UNKNOWN",
                "status_label": cfg.STATUS_LABELS["UNKNOWN"],
                "summary": "분리 아티팩트 가능성으로 압착된 음질 경향을 확정하지 않았어요.",
                "hidden": True,
                "focus_segments": [],
            }
    else:
        resonance = fuse_resonance(segments, acoustic)

    onset = fuse_onset(segments)
    transition = fuse_transition(segments, pitch)

    dimensions = {
        "breathy_like": breathy,
        "pressed_like": pressed,
        "rough_like": rough,
        "resonance_timbre": resonance,
        "onset_behavior": onset,
        "register_transition": transition,
    }

    # Headline summary bullets (non-unknown only)
    headlines = []
    for d in dimensions.values():
        if d.get("hidden") or d.get("status") in ("UNKNOWN", "AMBIGUOUS"):
            continue
        if d["dimension_id"] == "resonance_timbre":
            headlines.append(f"{d['display_name']}: {d.get('summary')}")
        else:
            headlines.append(
                f"{d['display_name']} · {d.get('status_label') or d.get('prevalence_label')}"
            )

    focus = []
    for d in dimensions.values():
        for ev in d.get("focus_segments") or []:
            focus.append(ev)
    focus = focus[:6]

    # Sanity warnings (empty-filter all() is True in Python — guard explicitly)
    warnings = []
    decisive = [
        d.get("status")
        for d in dimensions.values()
        if d.get("status") not in ("UNKNOWN", "AMBIGUOUS", None)
    ]
    if decisive and all(s == "HIGH" for s in decisive):
        warnings.append("all_high_profile")
    if decisive and all(s == "LOW" for s in decisive):
        warnings.append("all_low_or_zero_profile")
    confs = [d.get("confidence_label") for d in dimensions.values()]
    if confs and all(c == "high" for c in confs):
        warnings.append("all_confidence_high")
    if not valid:
        warnings.append("no_valid_segments")
    if len(valid) == 1:
        warnings.append("single_valid_segment_only")

    scientific_debug = {
        "engine_version": cfg.ENGINE_VERSION,
        "calibration_status": cfg.CALIBRATION_STATUS,
        "n_segments": len(segments),
        "n_valid": len(valid),
        "source_mode": source_mode,
        "spectral_blocked": spectral_blocked,
        "metric_status": cfg.METRIC_STATUS,
        "segment_sample": [
            {
                "start_sec": s["start_sec"],
                "end_sec": s["end_sec"],
                "valid": s["valid"],
                "observations": s.get("observations"),
            }
            for s in segments[:5]
        ],
    }

    return {
        "available": True,
        "engine_version": cfg.ENGINE_VERSION,
        "calibration_status": cfg.CALIBRATION_STATUS,
        "headline": headlines[:4] or ["이번 녹음에서 확인된 발성 상태 단서가 제한적이에요."],
        "dimensions": dimensions,
        "focus_segments": focus,
        "valid_segment_count": len(valid),
        "total_segment_count": len(segments),
        "warnings": warnings,
        "disclaimer": (
            "이 결과는 녹음된 음성의 음향적 특성을 바탕으로 "
            "발성 음질 경향을 관찰한 연습 참고 정보입니다. "
            "성대 구조·질환·근육 상태를 진단하지 않습니다."
        ),
        "scientific_debug": scientific_debug,
    }


def strip_scientific_debug(profile: dict[str, Any]) -> dict[str, Any]:
    out = dict(profile)
    out.pop("scientific_debug", None)
    return out


def public_dimensions(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Main-body dimensions (hide UNKNOWN)."""
    dims = profile.get("dimensions") or {}
    out = []
    for key in (
        "breathy_like",
        "pressed_like",
        "rough_like",
        "resonance_timbre",
        "onset_behavior",
        "register_transition",
    ):
        d = dims.get(key)
        if not d:
            continue
        if d.get("hidden") or d.get("status") in ("UNKNOWN", "AMBIGUOUS"):
            continue
        pub = {k: v for k, v in d.items() if k != "observations"}
        out.append(pub)
    return out


def excluded_dimensions(profile: dict[str, Any]) -> list[dict[str, Any]]:
    dims = profile.get("dimensions") or {}
    out = []
    for d in dims.values():
        if d.get("hidden") or d.get("status") in ("UNKNOWN", "AMBIGUOUS"):
            out.append(
                {
                    "dimension_id": d.get("dimension_id"),
                    "display_name": d.get("display_name"),
                    "reason": d.get("summary") or "신뢰도 부족",
                }
            )
    return out
