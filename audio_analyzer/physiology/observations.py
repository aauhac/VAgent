"""
physiology/observations.py
--------------------------
Acoustic Observation Layer — facts only, no anatomy assertions.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.features.phonation import extract_phonation_features
from audio_analyzer.features.pitch import extract_pitch_features
from audio_analyzer.quality import evaluate_quality

from . import metrics as M
from .config import METRIC_VERSION
from .validity import perturbation_allowed, sustained_vowel_conditions


def observe_sustained_task(
    y: np.ndarray,
    sr: int,
    *,
    task_id: str,
    attempt: int = 1,
) -> dict[str, Any]:
    pitch = extract_pitch_features(y, sr)
    phon = extract_phonation_features(y, sr, pitch)
    quality = evaluate_quality(
        y,
        sr,
        voiced_ratio=pitch.get("voiced_ratio"),
        voiced_duration_sec=float(pitch.get("voiced_ratio") or 0) * (len(y) / sr),
    )
    cond = sustained_vowel_conditions(y, sr, pitch_features=pitch, quality=quality)
    f0 = cond.get("f0_mean_hz")
    vib = phon.get("vibrato") or {}
    residual = phon.get("median_residual_std_cents")

    observations: list[dict[str, Any]] = []

    def add(m: dict[str, Any]) -> None:
        m["attempts_used"] = [attempt]
        observations.append(m)

    # Cepstral prominence PROXY (not CPPS)
    cpp = M.compute_cepstral_prominence_proxy_db(y, sr, f0_hz=f0) if cond["ok"] else None
    add(
        M._metric(
            "cepstral_prominence_proxy_db",
            cpp,
            unit="dB",
            valid=cond["ok"] and cpp is not None,
            confidence=0.75 if cond["ok"] and cpp is not None else 0.1,
            source_task=task_id,
            measurement_condition="sustained_vowel_stable",
            notes=([] if cond["ok"] else cond["reasons"])
            + ["proxy_not_praat_cpps", "not_glottal_closure"],
        )
    )

    # Autocorr HNR PROXY (not Praat-identical)
    hnr = M.compute_hnr_ac_proxy_db(y, sr, f0_hz=f0) if cond["ok"] else None
    add(
        M._metric(
            "hnr_ac_proxy_db",
            hnr,
            unit="dB",
            valid=cond["ok"] and hnr is not None,
            confidence=0.7 if cond["ok"] and hnr is not None else 0.1,
            source_task=task_id,
            measurement_condition="sustained_vowel_stable",
            notes=([] if cond["ok"] else cond["reasons"])
            + ["proxy_not_praat_hnr", "same_periodicity_family_as_cepstral"],
        )
    )

    # Raw H1-H2 PROXY (NOT H1*-H2*)
    h1h2 = M.compute_raw_h1_h2_proxy_db(y, sr, f0) if cond["ok"] else None
    add(
        M._metric(
            "raw_h1_h2_proxy_db",
            h1h2,
            unit="dB",
            valid=cond["ok"] and h1h2 is not None,
            confidence=0.45 if cond["ok"] and h1h2 is not None else 0.1,
            source_task=task_id,
            measurement_condition="sustained_vowel_harmonic_visible_uncorrected",
            notes=["raw_not_formant_corrected", "not_open_quotient", "vowel_confounded"]
            + ([] if cond["ok"] else cond["reasons"]),
        )
    )

    tilt = M.compute_spectral_tilt_db_per_oct(y, sr) if cond["ok"] else None
    add(
        M._metric(
            "spectral_tilt_db_per_oct",
            tilt,
            unit="dB/oct",
            valid=cond["ok"] and tilt is not None,
            confidence=0.5 if cond["ok"] and tilt is not None else 0.1,
            source_task=task_id,
            measurement_condition="sustained_vowel",
            notes=([] if cond["ok"] else cond["reasons"]) + ["tract_and_source_confounded"],
        )
    )

    add(
        M._metric(
            "sustained_residual_f0_cents",
            residual,
            unit="cents",
            valid=residual is not None and (phon.get("sustained_count") or 0) >= 1,
            confidence=0.85 if residual is not None else 0.1,
            source_task=task_id,
            measurement_condition="local_sustained_region",
        )
    )

    add(
        M._metric(
            "rms_variation_db",
            phon.get("median_rms_variation_db"),
            unit="dB",
            valid=phon.get("median_rms_variation_db") is not None,
            confidence=0.8 if phon.get("median_rms_variation_db") is not None else 0.1,
            source_task=task_id,
            measurement_condition="local_sustained_region_p90_p20",
        )
    )

    # Perturbation proxies — never on song/siren; only strict sustained
    allow, notes = perturbation_allowed(
        residual, bool(vib.get("available")), cond, task_id=task_id
    )
    frame_f0 = pitch.get("frame_f0") or []
    times = np.asarray([f["time_sec"] for f in frame_f0], dtype=float)
    f0s = np.asarray(
        [np.nan if f.get("f0_hz") is None else float(f["f0_hz"]) for f in frame_f0],
        dtype=float,
    )
    jitter = (
        M.compute_f0_frame_period_perturbation_proxy_percent(times, f0s) if allow else None
    )
    shimmer = (
        M.compute_amplitude_window_shimmer_proxy_percent(y, sr, float(f0))
        if allow and f0
        else None
    )
    add(
        M._metric(
            "f0_frame_period_perturbation_proxy_percent",
            jitter,
            unit="%",
            valid=allow and jitter is not None,
            confidence=0.4 if allow and jitter is not None else 0.05,
            source_task=task_id,
            measurement_condition="stable_sustained_no_vibrato_frame_f0_only",
            notes=notes + ["not_clinical_cycle_jitter"],
        )
    )
    add(
        M._metric(
            "amplitude_window_shimmer_proxy_percent",
            shimmer,
            unit="%",
            valid=allow and shimmer is not None,
            confidence=0.35 if allow and shimmer is not None else 0.05,
            source_task=task_id,
            measurement_condition="stable_sustained_no_vibrato_fixed_window",
            notes=notes + ["not_clinical_cycle_shimmer"],
        )
    )

    onset = M.compute_onset_slope_db_per_sec(y, sr)
    release = M.compute_release_drop_db(y, sr)
    add(
        M._metric(
            "onset_slope_db_per_sec",
            onset,
            unit="dB/s",
            valid=onset is not None and quality.get("status") != "fail",
            confidence=0.7 if onset is not None else 0.1,
            source_task=task_id,
            measurement_condition="voiced_onset_window",
        )
    )
    add(
        M._metric(
            "release_drop_db",
            release,
            unit="dB",
            valid=release is not None and quality.get("status") != "fail",
            confidence=0.7 if release is not None else 0.1,
            source_task=task_id,
            measurement_condition="tail_window",
        )
    )

    return {
        "task_id": task_id,
        "attempt": attempt,
        "quality": quality,
        "observations": observations,
        "phonation_summary": {
            "sustained_count": phon.get("sustained_count"),
            "median_residual_std_cents": residual,
            "vibrato": vib,
        },
        "metric_version": METRIC_VERSION,
    }


def observe_siren_task(y: np.ndarray, sr: int, *, attempt: int = 1) -> dict[str, Any]:
    pitch = extract_pitch_features(y, sr)
    phon = extract_phonation_features(y, sr, pitch)
    quality = evaluate_quality(
        y,
        sr,
        voiced_ratio=pitch.get("voiced_ratio"),
        voiced_duration_sec=float(pitch.get("voiced_ratio") or 0) * (len(y) / sr),
    )
    # F0 continuity: fraction of voiced frames with small consecutive jumps
    frame_f0 = pitch.get("frame_f0") or []
    f0s = [f.get("f0_hz") for f in frame_f0]
    voiced = [v for v in f0s if v is not None and v > 0]
    continuity = None
    dropouts = 0
    if len(voiced) >= 10:
        jumps = []
        for i in range(1, len(f0s)):
            a, b = f0s[i - 1], f0s[i]
            if a is None or b is None:
                dropouts += 1
                continue
            cents = abs(1200 * np.log2((b + 1e-10) / (a + 1e-10)))
            jumps.append(cents)
        continuity = float(np.mean(np.asarray(jumps) < 120.0)) if jumps else None

    # IMPORTANT: do not treat global melody F0 change as phonation instability
    instability_events = phon.get("instability_events") or []

    obs = [
        M._metric(
            "f0_continuity_ratio",
            continuity,
            unit="ratio",
            valid=continuity is not None,
            confidence=0.75 if continuity is not None else 0.1,
            source_task="siren",
            measurement_condition="pitch_glide_task",
            attempts_used=[attempt],
            notes=["global_f0_change_is_expected_not_instability"],
        ),
        M._metric(
            "voiced_dropout_count",
            float(dropouts),
            unit="count",
            valid=True,
            confidence=0.7,
            source_task="siren",
            measurement_condition="pitch_glide_task",
            attempts_used=[attempt],
        ),
        M._metric(
            "local_instability_event_count",
            float(len(instability_events)),
            unit="count",
            valid=True,
            confidence=0.7,
            source_task="siren",
            measurement_condition="local_sustained_only",
            attempts_used=[attempt],
            notes=["siren_global_movement_excluded"],
        ),
    ]
    return {
        "task_id": "siren",
        "attempt": attempt,
        "quality": quality,
        "observations": obs,
        "metric_version": METRIC_VERSION,
    }


def observe_dynamic_swell_task(y: np.ndarray, sr: int, *, attempt: int = 1) -> dict[str, Any]:
    quality = evaluate_quality(y, sr)
    smooth = M.compute_envelope_smoothness(y, sr)
    pitch = extract_pitch_features(y, sr)
    f0_disp = None
    frame_f0 = [f.get("f0_hz") for f in (pitch.get("frame_f0") or []) if f.get("f0_hz")]
    if len(frame_f0) >= 5:
        f0_disp = float(
            1200 * np.log2((max(frame_f0) + 1e-10) / (min(frame_f0) + 1e-10))
        )
    obs = [
        M._metric(
            "envelope_smoothness_index",
            smooth,
            unit="index",
            valid=smooth is not None and quality.get("status") != "fail",
            confidence=0.7 if smooth is not None else 0.1,
            source_task="dynamic_swell",
            measurement_condition="intensity_swell_task",
            attempts_used=[attempt],
            notes=["custom_heuristic_not_standard_named_metric"],
        ),
        M._metric(
            "f0_displacement_cents_during_swell",
            f0_disp,
            unit="cents",
            valid=f0_disp is not None,
            confidence=0.65 if f0_disp is not None else 0.1,
            source_task="dynamic_swell",
            measurement_condition="intensity_swell_task",
            attempts_used=[attempt],
        ),
    ]
    return {
        "task_id": "dynamic_swell",
        "attempt": attempt,
        "quality": quality,
        "observations": obs,
        "metric_version": METRIC_VERSION,
    }
