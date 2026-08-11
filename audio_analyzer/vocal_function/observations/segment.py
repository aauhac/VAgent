"""Level-1 direct acoustic observations for a segment."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.glottal_source import (
    compute_source_params,
    gif_validity,
    inverse_filter_signal,
)
from audio_analyzer.vocal_tract import (
    build_timbre_profile,
    estimate_formants,
    harmonic_formant_alignment,
    spectral_bands,
)
from audio_analyzer.vocal_quality.metrics import segment_observations as vq_obs
from audio_analyzer.vocal_function.evidence.effort_trajectory import (
    extract_micro_intensity_db,
    rms_to_db,
)


def _snr_proxy_db(chunk: np.ndarray) -> float:
    # Crude: peak vs quiet percentile
    rms = float(np.sqrt(np.mean(chunk**2)) + 1e-12)
    quiet = float(np.percentile(np.abs(chunk), 10) + 1e-12)
    return float(20 * np.log10(rms / quiet))


def _f0_stats(pitch: dict[str, Any], start: float, end: float) -> dict[str, Any]:
    """
    F0 summary for a window.

    Dropout MUST use all pitch frames in the window as denominator
    (voiced-only denominator falsely collapses dropout toward 0).
    """
    frames = pitch.get("frame_f0") or []
    vals: list[float] = []
    all_f0: list[Optional[float]] = []
    times: list[float] = []
    for fr in frames:
        t = float(fr.get("time_sec") or 0)
        if not (start <= t <= end):
            continue
        f = fr.get("f0_hz")
        times.append(t)
        if f is not None and float(f) > 0:
            vals.append(float(f))
            all_f0.append(float(f))
        else:
            all_f0.append(None)

    n_all = len(all_f0)
    n_invalid = sum(1 for v in all_f0 if v is None or v <= 0)
    dropout = float(n_invalid / n_all) if n_all else 1.0

    # Octave-jump / tracker artifact cues on voiced sequence
    octave_jumps = 0
    voiced_pairs = 0
    for i in range(1, len(vals)):
        a, b = vals[i - 1], vals[i]
        if a <= 0 or b <= 0:
            continue
        voiced_pairs += 1
        ratio = b / a
        if ratio >= 1.8 or ratio <= (1.0 / 1.8):
            octave_jumps += 1
    octave_jump_ratio = float(octave_jumps / voiced_pairs) if voiced_pairs else 0.0
    tracker_suspect = bool(octave_jump_ratio >= 0.15 and (dropout >= 0.2 or len(vals) < 8))

    if len(vals) < 3:
        return {
            "f0_hz": None,
            "f0_trajectory": [],
            "f0_derivative_mean": None,
            "f0_dropout_ratio": dropout,
            "f0_octave_jump_ratio": round(octave_jump_ratio, 3),
            "f0_tracker_artifact": {
                "suspect": tracker_suspect,
                "octave_jumps": octave_jumps,
                "n_frames": n_all,
                "n_voiced": len(vals),
            },
        }
    arr = np.asarray(vals)
    d = np.diff(arr)
    return {
        "f0_hz": float(np.median(arr)),
        "f0_percentile_local": None,  # filled at song level
        "f0_trajectory": vals[:: max(1, len(vals) // 8)],
        "f0_derivative_mean": float(np.mean(d)),
        "f0_dropout_ratio": dropout,
        "f0_octave_jump_ratio": round(octave_jump_ratio, 3),
        "f0_tracker_artifact": {
            "suspect": tracker_suspect,
            "octave_jumps": octave_jumps,
            "n_frames": n_all,
            "n_voiced": len(vals),
        },
    }


def observe_segment(
    y: np.ndarray,
    sr: int,
    start_sec: float,
    end_sec: float,
    pitch: dict[str, Any],
    *,
    source_mode: str = "raw",
    artifact_flags: Optional[dict[str, Any]] = None,
    y_no_vocals: Optional[np.ndarray] = None,
) -> dict[str, Any]:
    """
    LEVEL 1 observations + LEVEL 2 proxies for one segment.
    Never mixes coaching conclusions.
    """
    from audio_analyzer.vocal_function.evidence_gate import (
        normalize_artifact_flags,
        segment_vocal_evidence,
    )

    artifact_flags = normalize_artifact_flags(artifact_flags)
    a, b = int(start_sec * sr), int(end_sec * sr)
    chunk = y[max(0, a) : min(len(y), b)]
    base = vq_obs(y, sr, start_sec, end_sec, pitch)
    base_obs = dict(base.get("observations") or {})
    f0s = _f0_stats(pitch, start_sec, end_sec)
    f0 = f0s.get("f0_hz") or base.get("median_f0_hz")

    bands = spectral_bands(chunk, sr) if len(chunk) > 64 else {}
    formants = estimate_formants(chunk, sr, f0_hz=f0) if len(chunk) > 64 else {"valid": False}
    align = (
        harmonic_formant_alignment(chunk, sr, f0, formants.get("formants_hz") or [])
        if f0 and formants.get("valid")
        else {"available": False}
    )

    voiced_ratio = float(base.get("voiced_ratio") or 0)
    period_db = base_obs.get("periodicity_primary_db")
    snr = _snr_proxy_db(chunk) if len(chunk) else 0.0
    rms = float(base.get("rms") or 0)
    vocal_dominant = voiced_ratio >= 0.55 and rms > 0
    sep_art = bool(
        artifact_flags.get("high_freq_loss")
        or artifact_flags.get("separation_bleed")
        or artifact_flags.get("separation_artifact")
    )

    gate = gif_validity(
        voiced_ratio=voiced_ratio,
        snr_proxy_db=snr,
        f0_hz=f0,
        periodicity_db=float(period_db) if period_db is not None else None,
        harmonic_confidence=0.5 if (period_db or 0) > 8 else 0.2,
        vocal_dominant=vocal_dominant,
        separation_artifact=sep_art and source_mode == "separated",
        formant_confidence=formants.get("confidence"),
    )

    source: dict[str, Any] = {"valid": False}
    if gate["valid"] and len(chunk) > int(0.06 * sr):
        gif = inverse_filter_signal(chunk, sr, f0_hz=f0)
        if gif.get("valid") and gif.get("glottal_flow") is not None:
            source = compute_source_params(gif["glottal_flow"], sr, f0_hz=f0)
            source["gif_method"] = gif.get("method")
        else:
            source = {"valid": False, "reason": gif.get("reason")}
    else:
        source = {"valid": False, "reason": "gif_validity_gate", "gate": gate}

    env = np.sqrt(
        np.convolve(chunk**2, np.ones(max(1, sr // 50)) / max(1, sr // 50), mode="same")
        + 1e-12
    )
    if len(env) > 10:
        peak_i = int(np.argmax(env))
        rise = env[: peak_i + 1]
        lo, hi = 0.1 * env[peak_i], 0.9 * env[peak_i]
        i0 = next((i for i, v in enumerate(rise) if v >= lo), 0)
        i1 = next((i for i, v in enumerate(rise) if v >= hi), peak_i)
        onset_rise_sec = (i1 - i0) / float(sr)
        decay = env[peak_i:]
        j0 = next((i for i, v in enumerate(decay) if v <= hi), 0)
        j1 = next((i for i, v in enumerate(decay) if v <= lo), len(decay) - 1)
        offset_decay_sec = (j1 - j0) / float(sr)
    else:
        onset_rise_sec = None
        offset_decay_sec = None

    observations = {
        **base_obs,
        "rms": rms,
        "intensity_db": rms_to_db(rms),
        "intensity_micro": extract_micro_intensity_db(chunk, sr) if len(chunk) > 64 else {},
        **f0s,
        **bands,
        "onset_rise_sec": onset_rise_sec,
        "offset_decay_sec": offset_decay_sec,
        "snr_proxy_db": snr,
    }
    # Flatten tracker artifact for roughness consumers
    art = f0s.get("f0_tracker_artifact") or {}
    observations["f0_tracker_artifact"] = art
    preliminary = {
        "voiced_ratio": voiced_ratio,
        "observations": observations,
    }
    vocal_evidence = segment_vocal_evidence(
        y_vocals=y,
        sr=sr,
        start_sec=start_sec,
        end_sec=end_sec,
        pitch=pitch,
        segment_obs=preliminary,
        y_no_vocals=y_no_vocals,
        artifact_flags=artifact_flags,
    )

    # Formant restricted if not vocal-specific
    if not vocal_evidence.get("vocal_specific"):
        formants = {
            **formants,
            "valid": False,
            "reason": "FORMANT_EVENT_RESTRICTED",
            "restricted": True,
        }

    # Legacy global valid (strict) — used for contact/register-like dims
    global_valid = (
        bool(base.get("valid", True))
        and vocal_dominant
        and bool(vocal_evidence.get("vocal_specific"))
    )
    seg_out = {
        "start_sec": start_sec,
        "end_sec": end_sec,
        "valid": global_valid,
        "voiced_ratio": voiced_ratio,
        "level": 1,
        "vocal_evidence": vocal_evidence,
        "observations": observations,
        "level2_proxies": {
            "glottal_source": source,
            "gif_gate": gate,
            "formants": formants,
            "harmonic_formant_alignment": align,
            "timbre": build_timbre_profile(bands, formants.get("confidence")),
        },
        "rms": rms,
    }
    from audio_analyzer.vocal_function.validity import build_validity_by_dimension

    seg_out["validity_by_dimension"] = build_validity_by_dimension(seg_out)
    return seg_out
