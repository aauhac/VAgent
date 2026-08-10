"""
audio_analyzer/benchmark/verdicts.py
------------------------------------
Feature / axis verdicts from discrimination statistics (no score retuning).
"""

from __future__ import annotations

from typing import Any, Optional


def classify_feature_verdict(stats: dict[str, Any]) -> dict[str, Any]:
    """
    stats keys expected:
      auc, rho, cliffs_delta, saturation_rate,
      source_auc or source_rho, mapping_auc, raw_auc,
      unknown_rate, n, n_expert, n_beginner
    """
    n = int(stats.get("n") or 0)
    n_e = int(stats.get("n_expert") or 0)
    n_b = int(stats.get("n_beginner") or 0)
    if n < 8 or n_e < 3 or n_b < 3:
        return {
            "verdict": "INSUFFICIENT_DATA",
            "reasons": ["small_n"],
        }

    auc = stats.get("auc")
    rho = stats.get("rho")
    sat = stats.get("saturation_rate")
    src_auc = stats.get("source_auc")
    raw_auc = stats.get("raw_auc")
    mapped_auc = stats.get("mapped_auc", auc)
    unknown_rate = stats.get("unknown_rate") or 0.0
    vocal_better = stats.get("vocal_better")

    reasons: list[str] = []

    if sat is not None and float(sat) >= 0.70:
        reasons.append("high_saturation")
    if unknown_rate >= 0.50:
        reasons.append("high_missingness")
    if src_auc is not None and auc is not None and float(src_auc) - float(auc) >= 0.15:
        reasons.append("source_confound")
    if (
        raw_auc is not None
        and mapped_auc is not None
        and float(raw_auc) - float(mapped_auc) >= 0.12
    ):
        reasons.append("mapping_saturation")

    disc = False
    if auc is not None and float(auc) >= 0.70:
        disc = True
        reasons.append("auc_ge_0.70")
    if rho is not None and abs(float(rho)) >= 0.35:
        disc = True
        reasons.append("abs_rho_ge_0.35")

    raw_strong = raw_auc is not None and float(raw_auc) >= 0.70

    if "source_confound" in reasons and not disc:
        return {"verdict": "RESTRICT", "reasons": reasons}
    if "high_saturation" in reasons and (auc is None or float(auc) < 0.60) and not raw_strong:
        return {"verdict": "REDESIGN", "reasons": reasons}
    # Raw discriminates but mapping compresses → calibration candidate (do not retune here)
    if "mapping_saturation" in reasons and (disc or raw_strong):
        return {"verdict": "CALIBRATION_CANDIDATE", "reasons": reasons}
    if disc and "source_confound" not in reasons:
        if vocal_better:
            return {"verdict": "KEEP_VOCAL_ONLY", "reasons": reasons + ["vocal_better"]}
        return {"verdict": "KEEP", "reasons": reasons}
    if disc and "source_confound" in reasons:
        return {"verdict": "RESTRICT", "reasons": reasons}
    if auc is not None and float(auc) < 0.55 and (rho is None or abs(float(rho)) < 0.15):
        return {"verdict": "REMOVE", "reasons": reasons + ["near_chance"]}
    return {"verdict": "REDESIGN", "reasons": reasons or ["weak_discrimination"]}


def axis_calibration_readiness(axis_stats: dict[str, Any]) -> str:
    """
    axis_stats: auc, rho, unknown_rate, n, n_expert, n_beginner, source_confound, redesign
    """
    n = int(axis_stats.get("n") or 0)
    if n < 20:
        return "NOT_READY"
    if axis_stats.get("redesign"):
        return "REDESIGN_REQUIRED"
    unk = float(axis_stats.get("unknown_rate") or 0)
    if unk >= 0.4:
        return "NOT_READY"
    if axis_stats.get("source_confound"):
        return "NOT_READY"
    auc = axis_stats.get("auc")
    rho = axis_stats.get("rho")
    if auc is not None and float(auc) >= 0.70:
        return "READY"
    if (auc is not None and float(auc) >= 0.60) or (
        rho is not None and abs(float(rho)) >= 0.30
    ):
        return "PARTIAL"
    return "NOT_READY"


def mapping_loss_label(raw_auc: Optional[float], mapped_auc: Optional[float]) -> str:
    if raw_auc is None or mapped_auc is None:
        return "UNKNOWN"
    d = float(raw_auc) - float(mapped_auc)
    if d >= 0.12:
        return "MAPPING_LOSS"
    if d <= -0.05:
        return "MAPPING_HELPS"
    return "SIMILAR"


def vocal_benefit_label(auc_raw: Optional[float], auc_vocal: Optional[float]) -> str:
    if auc_raw is None or auc_vocal is None:
        return "NO_DIFFERENCE"
    d = float(auc_vocal) - float(auc_raw)
    if d >= 0.05:
        return "VOCAL_BETTER"
    if d <= -0.05:
        return "RAW_BETTER"
    return "NO_DIFFERENCE"
