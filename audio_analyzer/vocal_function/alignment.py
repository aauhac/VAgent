"""Time-aligned stem clipping and timestamp origin helpers."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.scoring.duration_policy_v3 import slice_audio


def slice_aligned_stems(
    *,
    y_vocals_full: np.ndarray,
    y_no_vocals_full: Optional[np.ndarray],
    sr: int,
    start_sec: float,
    end_sec: float,
) -> dict[str, Any]:
    """
    Apply the SAME original-time window to vocals and no_vocals.

    Prevents comparing vocals[clip] against no_vocals[0:clip_len].
    """
    start_sec = float(start_sec)
    end_sec = float(end_sec)
    vocals_clip = slice_audio(y_vocals_full, sr, start_sec, end_sec)
    no_vocals_clip = None
    if y_no_vocals_full is not None and len(y_no_vocals_full) > 0:
        # Match lengths if stems differ slightly
        n = len(y_vocals_full)
        yn = np.asarray(y_no_vocals_full, dtype=np.float32)
        if len(yn) != n:
            if len(yn) > n:
                yn = yn[:n]
            else:
                yn = np.pad(yn, (0, n - len(yn)))
        no_vocals_clip = slice_audio(yn, sr, start_sec, end_sec)
        # Ensure same sample count as vocals clip
        if len(no_vocals_clip) != len(vocals_clip):
            m = min(len(no_vocals_clip), len(vocals_clip))
            no_vocals_clip = no_vocals_clip[:m]
            vocals_clip = vocals_clip[:m]
    return {
        "clip_start_sec": start_sec,
        "clip_end_sec": end_sec,
        "vocals_clip": vocals_clip,
        "no_vocals_clip": no_vocals_clip,
        "sample_rate": sr,
    }


def attach_time_fields(
    event: dict[str, Any],
    *,
    time_origin_sec: float,
) -> dict[str, Any]:
    """Add local_* and original_* timestamps (analysis-local vs original file)."""
    out = dict(event)
    local_s = float(event.get("start_sec") if event.get("local_start_sec") is None else event["local_start_sec"])
    local_e = float(event.get("end_sec") if event.get("local_end_sec") is None else event["local_end_sec"])
    origin = float(time_origin_sec or 0.0)
    out["local_start_sec"] = local_s
    out["local_end_sec"] = local_e
    out["time_origin_sec"] = origin
    out["original_start_sec"] = round(origin + local_s, 3)
    out["original_end_sec"] = round(origin + local_e, 3)
    # Keep start_sec/end_sec as local for internal math; UI should prefer original_*
    out["start_sec"] = local_s
    out["end_sec"] = local_e
    return out


def build_time_context(
    *,
    duration_policy: dict[str, Any],
    original_duration_sec: float,
) -> dict[str, Any]:
    start = float(duration_policy.get("start_sec") or 0.0)
    end = float(duration_policy.get("end_sec") or original_duration_sec)
    return {
        "analysis_time_origin_sec": start,
        "analysis_clip_start_sec": start,
        "analysis_clip_end_sec": end,
        "original_duration_sec": float(original_duration_sec),
        "truncated": bool(duration_policy.get("truncated")),
        "policy": duration_policy.get("policy"),
    }
