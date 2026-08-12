"""Task instruction compliance checks (diagnostic protocol v1.2)."""

from __future__ import annotations

from typing import Any

import numpy as np


def _duration_sec(y: np.ndarray, sr: int) -> float:
    if y is None or sr <= 0:
        return 0.0
    return float(len(y) / sr)


def _rms_envelope(y: np.ndarray, sr: int, win_sec: float = 0.05) -> np.ndarray:
    win = max(8, int(win_sec * sr))
    hop = max(4, win // 2)
    vals = []
    for i in range(0, max(1, len(y) - win + 1), hop):
        w = y[i : i + win]
        vals.append(float(np.sqrt(np.mean(w.astype(float) ** 2) + 1e-12)))
    return np.asarray(vals, dtype=float) if vals else np.asarray([0.0])


def check_sustain_compliance(
    y: np.ndarray,
    sr: int,
    *,
    pitch: dict[str, Any] | None = None,
    min_sec: float = 3.0,
) -> dict[str, Any]:
    dur = _duration_sec(y, sr)
    voiced = float((pitch or {}).get("voiced_ratio") or 0.0)
    sustained_frac = voiced  # proxy under controlled sustain
    ok = dur >= min_sec and sustained_frac >= 0.35
    reasons = []
    if dur < min_sec:
        reasons.append("too_short")
    if sustained_frac < 0.35:
        reasons.append("insufficient_sustained_phonation")
    return {
        "task_family": "sustain",
        "ok": ok,
        "duration_sec": round(dur, 3),
        "sustained_phonation_fraction": round(sustained_frac, 3),
        "reasons": reasons,
    }


def check_siren_compliance(
    y: np.ndarray,
    sr: int,
    *,
    pitch: dict[str, Any] | None = None,
    min_span_cents: float = 400.0,
) -> dict[str, Any]:
    dur = _duration_sec(y, sr)
    frame_f0 = [f.get("f0_hz") for f in ((pitch or {}).get("frame_f0") or []) if f.get("f0_hz")]
    span = None
    if len(frame_f0) >= 8:
        span = float(1200 * np.log2((max(frame_f0) + 1e-10) / (min(frame_f0) + 1e-10)))
    ok = dur >= 3.5 and span is not None and span >= min_span_cents
    reasons = []
    if dur < 3.5:
        reasons.append("too_short")
    if span is None or span < min_span_cents:
        reasons.append("insufficient_pitch_span")
    return {
        "task_family": "siren",
        "ok": ok,
        "duration_sec": round(dur, 3),
        "pitch_span_cents": None if span is None else round(span, 1),
        "reasons": reasons,
    }


def check_dynamic_swell_compliance(
    y: np.ndarray,
    sr: int,
    *,
    min_sec: float = 3.0,
    min_rise_db: float = 3.0,
    min_fall_db: float = 2.5,
) -> dict[str, Any]:
    dur = _duration_sec(y, sr)
    env = _rms_envelope(y, sr)
    env_db = 20.0 * np.log10(np.maximum(env, 1e-12))
    reasons = []
    if dur < min_sec:
        reasons.append("too_short")
    if len(env_db) < 6:
        reasons.append("envelope_too_short")
        return {
            "task_family": "dynamic_swell",
            "ok": False,
            "duration_sec": round(dur, 3),
            "rise_db": None,
            "fall_db": None,
            "reasons": reasons,
        }
    n = len(env_db)
    # thirds: soft → loud → soft
    a, b, c = env_db[: n // 3], env_db[n // 3 : 2 * n // 3], env_db[2 * n // 3 :]
    pre = float(np.percentile(a, 40)) if len(a) else None
    mid = float(np.percentile(b, 75)) if len(b) else None
    post = float(np.percentile(c, 30)) if len(c) else None
    rise = None if pre is None or mid is None else float(mid - pre)
    fall = None if mid is None or post is None else float(mid - post)
    if rise is None or rise < min_rise_db:
        reasons.append("insufficient_intensity_rise")
    if fall is None or fall < min_fall_db:
        reasons.append("insufficient_intensity_fall")
    ok = not reasons
    return {
        "task_family": "dynamic_swell",
        "ok": ok,
        "duration_sec": round(dur, 3),
        "rise_db": None if rise is None else round(rise, 2),
        "fall_db": None if fall is None else round(fall, 2),
        "reasons": reasons,
    }


def check_high_note_sustain_compliance(
    y: np.ndarray,
    sr: int,
    *,
    pitch: dict[str, Any] | None = None,
    song_median_f0_hz: float | None = None,
) -> dict[str, Any]:
    """Sustain compliance + optional elevation vs song mid F0."""
    base = check_sustain_compliance(y, sr, pitch=pitch)
    reasons = list(base.get("reasons") or [])
    f0s = []
    for fr in (pitch or {}).get("frame_f0") or []:
        f = fr.get("f0_hz")
        if f is not None and float(f) > 0:
            f0s.append(float(f))
    med = float(np.median(f0s)) if len(f0s) >= 5 else None
    elevated = None
    if med is not None and song_median_f0_hz and song_median_f0_hz > 0:
        # ≥1.5 semitones above song median
        elevated = med >= float(song_median_f0_hz) * (2.0 ** (1.5 / 12.0))
        if not elevated:
            reasons.append("pitch_not_elevated_vs_song_mid")
    ok = bool(base.get("ok")) and (elevated is not False)
    return {
        **base,
        "task_family": "high_note_sustain",
        "ok": ok,
        "median_f0_hz": None if med is None else round(med, 2),
        "pitch_elevated_vs_song": elevated,
        "reasons": reasons,
        # Task completion alone never resolves — evidence path must also pass
        "completion_alone_insufficient": True,
    }


def check_task_compliance(
    task_id: str,
    y: np.ndarray,
    sr: int,
    *,
    pitch: dict[str, Any] | None = None,
    song_median_f0_hz: float | None = None,
) -> dict[str, Any]:
    if task_id in ("sustain_a", "sustain_i"):
        return check_sustain_compliance(y, sr, pitch=pitch)
    if task_id == "high_note_sustain_a":
        return check_high_note_sustain_compliance(
            y, sr, pitch=pitch, song_median_f0_hz=song_median_f0_hz
        )
    if task_id == "siren":
        return check_siren_compliance(y, sr, pitch=pitch)
    if task_id == "dynamic_swell":
        return check_dynamic_swell_compliance(y, sr)
    return {"task_family": "unknown", "ok": False, "reasons": ["unknown_task"]}
