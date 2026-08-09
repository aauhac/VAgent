"""
quality/gate.py
---------------
Recording quality gate — runs before vocal skill scoring.

Quality FAIL ⇒ score.available = false (never score 0 as "low skill").
Provides machine-readable `codes` alongside human `reasons`.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from . import config as cfg


def _rms_dbfs(y: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(y.astype(np.float64))) + 1e-20))
    return float(20.0 * np.log10(rms + 1e-20))


def _clipping_ratio(y: np.ndarray, threshold: float = cfg.CLIPPING_ABS_THRESHOLD) -> float:
    if len(y) == 0:
        return 1.0
    return float(np.mean(np.abs(y) >= threshold))


def _silent_ratio(y: np.ndarray, sr: int) -> float:
    if len(y) == 0:
        return 1.0
    hop = 512
    frame = max(1, hop)
    n = len(y)
    energies = []
    for start in range(0, n, hop):
        chunk = y[start : start + frame]
        energies.append(float(np.sqrt(np.mean(np.square(chunk)) + 1e-20)))
    if not energies:
        return 1.0
    arr = np.asarray(energies)
    thr = float(np.max(arr)) * 0.05 + 1e-12
    return float(np.mean(arr < thr))


def evaluate_quality(
    y: np.ndarray,
    sr: int,
    *,
    voiced_ratio: Optional[float] = None,
    voiced_duration_sec: Optional[float] = None,
    rumble_ratio_db: Optional[float] = None,
) -> dict[str, Any]:
    """
    Returns:
      status, confidence, reasons, codes, metrics, user_message
    """
    duration_sec = float(len(y) / max(sr, 1))
    rms_dbfs = _rms_dbfs(y)
    clip_ratio = _clipping_ratio(y)
    silent = _silent_ratio(y, sr)

    if voiced_ratio is None:
        voiced_ratio = max(0.0, 1.0 - silent) * 0.5
    if voiced_duration_sec is None:
        voiced_duration_sec = float(voiced_ratio) * duration_sec

    metrics = {
        "duration_sec": round(duration_sec, 3),
        "rms_dbfs": round(rms_dbfs, 2),
        "clipping_ratio": round(clip_ratio, 5),
        "silent_ratio": round(silent, 4),
        "voiced_ratio": round(float(voiced_ratio), 4),
        "voiced_duration_sec": round(float(voiced_duration_sec), 3),
        "rumble_ratio_db": None if rumble_ratio_db is None else round(float(rumble_ratio_db), 2),
    }

    fail_reasons: list[str] = []
    warn_reasons: list[str] = []
    fail_codes: list[str] = []
    warn_codes: list[str] = []

    def _add(level: str, code: str, msg: str) -> None:
        if level == "fail":
            fail_codes.append(code)
            fail_reasons.append(msg)
        else:
            warn_codes.append(code)
            warn_reasons.append(msg)

    if duration_sec < cfg.MIN_DURATION_SEC:
        _add("fail", "SHORT_DURATION", f"녹음이 너무 짧음 ({duration_sec:.1f}s < {cfg.MIN_DURATION_SEC}s)")
    elif duration_sec < cfg.WARN_DURATION_SEC:
        _add("warn", "SHORT_DURATION", f"녹음이 다소 짧음 ({duration_sec:.1f}s)")

    if duration_sec > cfg.MAX_DURATION_SEC:
        _add("warn", "LONG_DURATION", f"녹음이 매우 김 ({duration_sec:.1f}s) - 일부만 분석될 수 있음")

    if silent >= cfg.FAIL_SILENT_RATIO:
        _add("fail", "HIGH_SILENCE", f"무음 비율이 과도함 ({silent:.2f})")
    elif silent >= cfg.WARN_SILENT_RATIO:
        _add("warn", "HIGH_SILENCE", f"무음 비율이 높음 ({silent:.2f})")

    if float(voiced_ratio) < cfg.FAIL_VOICED_RATIO:
        _add("fail", "LOW_VOICED_RATIO", f"유성음 비율이 너무 낮음 ({voiced_ratio:.2f})")
    elif float(voiced_ratio) < cfg.WARN_VOICED_RATIO:
        _add("warn", "LOW_VOICED_RATIO", f"유성음 비율이 낮음 ({voiced_ratio:.2f})")

    if float(voiced_duration_sec) < cfg.FAIL_VOICED_DURATION_SEC:
        _add(
            "fail",
            "SHORT_VOICED_DURATION",
            f"분석 가능한 유성음 구간이 부족함 ({voiced_duration_sec:.2f}s)",
        )
    elif float(voiced_duration_sec) < cfg.WARN_VOICED_DURATION_SEC:
        _add(
            "warn",
            "SHORT_VOICED_DURATION",
            f"유성음 구간이 짧음 ({voiced_duration_sec:.2f}s)",
        )

    if clip_ratio >= cfg.FAIL_CLIPPING_RATIO:
        _add("fail", "CLIPPING", f"클리핑이 과도함 ({clip_ratio:.3f})")
    elif clip_ratio >= cfg.WARN_CLIPPING_RATIO:
        _add("warn", "CLIPPING", f"클리핑 가능성 ({clip_ratio:.3f})")

    if rms_dbfs <= cfg.FAIL_RMS_DBFS:
        _add("fail", "LOW_LEVEL", f"녹음 레벨이 너무 작음 ({rms_dbfs:.1f} dBFS)")
    elif rms_dbfs <= cfg.WARN_RMS_DBFS:
        _add("warn", "LOW_LEVEL", f"녹음 레벨이 낮음 ({rms_dbfs:.1f} dBFS)")

    if rumble_ratio_db is not None and cfg.WARN_RUMBLE_RATIO_DB is not None:
        if rumble_ratio_db >= cfg.WARN_RUMBLE_RATIO_DB:
            _add("warn", "RUMBLE", f"저역 잡음이 다소 높음 ({rumble_ratio_db:.1f} dB)")
        if cfg.FAIL_RUMBLE_RATIO_DB is not None and rumble_ratio_db >= cfg.FAIL_RUMBLE_RATIO_DB:
            _add("fail", "RUMBLE", f"저역 잡음/오염이 심함 ({rumble_ratio_db:.1f} dB)")

    # de-dupe codes while preserving order
    def _uniq(seq: list[str]) -> list[str]:
        seen = set()
        out = []
        for x in seq:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    fail_codes = _uniq(fail_codes)
    warn_codes = _uniq(warn_codes)

    if fail_reasons:
        status = "fail"
        confidence = 0.15
        reasons = fail_reasons + warn_reasons
        codes = fail_codes + [c for c in warn_codes if c not in fail_codes]
    elif warn_reasons:
        status = "warn"
        confidence = 0.65
        reasons = warn_reasons
        codes = warn_codes
    else:
        status = "pass"
        confidence = 0.92
        reasons = []
        codes = []

    if status == "warn" and "CLIPPING" in codes:
        confidence = min(confidence, 0.55)

    return {
        "status": status,
        "confidence": round(float(confidence), 3),
        "reasons": reasons,
        "codes": codes,
        "metrics": metrics,
        "user_message": cfg.USER_MESSAGES[status],
        "version": cfg.QUALITY_GATE_VERSION,
        "calibration_status": cfg.CALIBRATION_STATUS,
    }
