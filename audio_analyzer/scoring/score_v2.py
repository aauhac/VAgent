"""
scoring/score_v2.py
-------------------
4-axis vocal skill scoring (v2).

Axes:
  stability / projection / resonance / dynamic_control

Rules:
  - vibrato is optional analysis only (no overall weight)
  - low_noise / rumble belongs to quality, not skill score
  - unknown confidence never becomes strength
  - global pitch variance is NEVER used
"""

from __future__ import annotations

from typing import Any, Optional

from . import config_v2 as cfg


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def score_lower_is_better(value: float, good: float, weak: float) -> float:
    if value <= good:
        return 100.0
    if value >= weak:
        return 0.0
    return clamp(100.0 * (weak - value) / (weak - good))


def score_higher_is_better(value: float, weak: float, good: float) -> float:
    if value >= good:
        return 100.0
    if value <= weak:
        return 0.0
    return clamp(100.0 * (value - weak) / (good - weak))


def score_target_range(
    value: float,
    good_min: float,
    good_max: float,
    bad_min: float,
    bad_max: float,
) -> float:
    if good_min <= value <= good_max:
        return 100.0
    if value < good_min:
        if value <= bad_min:
            return 0.0
        return clamp(100.0 * (value - bad_min) / (good_min - bad_min))
    if value >= bad_max:
        return 0.0
    return clamp(100.0 * (bad_max - value) / (bad_max - good_max))


def status_from_score(score: Optional[float], confidence: float) -> str:
    if score is None or confidence < cfg.UNKNOWN_CONFIDENCE:
        return "unknown"
    if score >= cfg.STATUS_THRESHOLDS["excellent"]:
        return "excellent"
    if score >= cfg.STATUS_THRESHOLDS["good"]:
        return "good"
    if score >= cfg.STATUS_THRESHOLDS["normal"]:
        return "normal"
    return "needs_work"


def overall_label(score: float) -> str:
    for threshold, label in cfg.OVERALL_LABELS:
        if score >= threshold:
            return label
    return cfg.OVERALL_LABELS[-1][1]


def _area(
    area_id: str,
    score: Optional[float],
    confidence: float,
    evidence: dict[str, Any],
    confidence_reason: str,
) -> dict[str, Any]:
    st = status_from_score(score, confidence)
    return {
        "area_id": area_id,
        "display_name": cfg.AREA_DISPLAY[area_id],
        "score": None if score is None else round(float(score), 1),
        "status": st,
        "confidence": round(float(confidence), 3),
        "confidence_reason": confidence_reason,
        "weight": cfg.AREA_WEIGHTS[area_id],
        "evidence": evidence,
    }


def compute_score_v2(
    *,
    phonation: dict[str, Any],
    acoustic: dict[str, Any],
    waveform: dict[str, Any],
    quality: dict[str, Any],
    source_mode: str = "raw",
    artifact_flags: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Compute 4-axis vocal skill score.

    If quality.status == fail, caller should skip this and return unavailable.
    """
    artifact_flags = artifact_flags or {}
    spectral_scale = 1.0
    if source_mode == "separated":
        spectral_scale *= cfg.SEPARATED_SPECTRAL_CONFIDENCE_SCALE
    if artifact_flags.get("high_band_loss_likely"):
        spectral_scale *= 0.55
    if quality.get("status") == "warn":
        spectral_scale *= 0.85

    areas: list[dict[str, Any]] = []

    # ── 1. stability (local sustained residual) ───────────────────────────
    residual = phonation.get("median_residual_std_cents")
    sustain_n = int(phonation.get("sustained_count") or 0)
    stab_conf = 0.9
    stab_reason = "지속음 구간 기반 국소 안정성"
    if residual is None or sustain_n < 1:
        stab_score = None
        stab_conf = 0.1
        stab_reason = "충분히 긴 지속음이 없어 안정성을 신뢰하기 어려움"
    else:
        stab_score = score_lower_is_better(
            float(residual), cfg.STABILITY["good"], cfg.STABILITY["weak"]
        )
        if sustain_n < 2:
            stab_conf *= 0.7
            stab_reason = "지속음 구간이 적어 신뢰도 하향"
    areas.append(
        _area(
            "stability",
            stab_score,
            stab_conf,
            {
                "median_residual_std_cents": residual,
                "sustained_count": sustain_n,
                "median_rms_variation_db": phonation.get("median_rms_variation_db"),
            },
            stab_reason,
        )
    )

    # ── 2. projection (SPR + singer formant prominence) ───────────────────
    spr = acoustic.get("spr_db")
    prom = acoustic.get("singer_formant_prominence_db")
    proj_conf = 0.85 * spectral_scale
    proj_reason = "스펙트럼 전달 특성 기반"
    if spr is None and prom is None:
        proj_score = None
        proj_conf = 0.1
        proj_reason = "전달력 지표 측정 실패"
    else:
        parts = []
        if spr is not None:
            parts.append(
                score_lower_is_better(
                    float(spr), cfg.PROJECTION["good"], cfg.PROJECTION["weak"]
                )
            )
        if prom is not None:
            parts.append(
                score_higher_is_better(
                    float(prom),
                    cfg.PROJECTION["singer_formant_prominence_weak"],
                    cfg.PROJECTION["singer_formant_prominence_good"],
                )
            )
        proj_score = float(sum(parts) / len(parts))
        if proj_conf < cfg.UNKNOWN_CONFIDENCE:
            proj_reason = "분리/고역 손실 가능성으로 전달력 측정이 불확실함"
    areas.append(
        _area(
            "projection",
            proj_score,
            proj_conf,
            {"spr_db": spr, "singer_formant_prominence_db": prom},
            proj_reason,
        )
    )

    # ── 3. resonance ──────────────────────────────────────────────────────
    wg = acoustic.get("weight_gap_db")
    mg = acoustic.get("mouth_gap_db")
    slope = acoustic.get("spectral_slope_db_per_oct")
    res_conf = 0.8 * spectral_scale
    res_reason = "공명 대역 균형 기반"
    parts = []
    if wg is not None:
        wcfg = cfg.RESONANCE["weight_gap"]
        parts.append(
            score_target_range(
                float(wg), wcfg["good_min"], wcfg["good_max"], wcfg["bad_min"], wcfg["bad_max"]
            )
        )
    if mg is not None:
        mcfg = cfg.RESONANCE["mouth_gap"]
        parts.append(score_lower_is_better(float(mg), mcfg["good"], mcfg["weak"]))
    if slope is not None:
        scfg = cfg.RESONANCE["spectral_slope"]
        parts.append(
            score_target_range(
                float(slope),
                scfg["good_min"],
                scfg["good_max"],
                scfg["bad_min"],
                scfg["bad_max"],
            )
        )
    if not parts:
        res_score = None
        res_conf = 0.1
        res_reason = "공명 지표 측정 실패"
    else:
        res_score = float(sum(parts) / len(parts))
        if artifact_flags.get("relative_low_mid_inflation_likely"):
            res_conf *= 0.65
            res_reason = "저중역 상대 과장 가능성으로 신뢰도 하향"
    areas.append(
        _area(
            "resonance",
            res_score,
            res_conf,
            {
                "weight_gap_db": wg,
                "mouth_gap_db": mg,
                "spectral_slope_db_per_oct": slope,
            },
            res_reason,
        )
    )

    # ── 4. dynamic_control (target range, not higher-is-better) ───────────
    dr = waveform.get("dynamic_range_db")
    dyn_conf = 0.75
    dyn_reason = "강약 폭은 곡/표현에 따라 달라 잠정 범위로 해석"
    if dr is None:
        dyn_score = None
        dyn_conf = 0.1
        dyn_reason = "다이나믹 레인지 측정 실패"
    else:
        dcfg = cfg.DYNAMIC_CONTROL
        dyn_score = score_target_range(
            float(dr),
            dcfg["good_min"],
            dcfg["good_max"],
            dcfg["bad_min"],
            dcfg["bad_max"],
        )
        # Soften extremes: intentional soft singing shouldn't be harshly punished
        if float(dr) < dcfg["good_min"] and float(dr) >= dcfg["bad_min"]:
            dyn_conf *= 0.85
            dyn_reason = "작은 강약 폭은 의도적 표현일 수 있어 단정하지 않음"
    areas.append(
        _area(
            "dynamic_control",
            dyn_score,
            dyn_conf,
            {"dynamic_range_db": dr},
            dyn_reason,
        )
    )

    # Force unknown when confidence too low — never treat as good
    for a in areas:
        if a["confidence"] < cfg.UNKNOWN_CONFIDENCE:
            a["status"] = "unknown"

    # Overall aggregation
    numer = 0.0
    denom = 0.0
    reliable_areas = 0
    for a in areas:
        if a["score"] is None:
            continue
        if a["confidence"] < cfg.MIN_AREA_CONFIDENCE or a["status"] == "unknown":
            continue
        w = float(a["weight"]) * float(a["confidence"])
        numer += float(a["score"]) * w
        denom += w
        reliable_areas += 1

    if reliable_areas < cfg.MIN_AREAS_FOR_OVERALL or denom <= 0:
        return {
            "available": False,
            "version": cfg.SCORE_VERSION,
            "calibration_status": cfg.CALIBRATION_STATUS,
            "overall": None,
            "label": None,
            "areas": areas,
            "reason": "신뢰할 수 있는 측정 영역이 부족함",
            "strengths": [],
            "priority_issues": [],
        }

    overall = round(numer / denom, 1)

    strengths = []
    priority = []
    for a in areas:
        if (
            a["status"] in ("excellent", "good")
            and a["confidence"] >= cfg.STRENGTH_MIN_CONFIDENCE
            and a["score"] is not None
            and float(a["score"]) >= cfg.STRENGTH_MIN_SCORE
        ):
            strengths.append(
                {
                    "area_id": a["area_id"],
                    "display_name": a["display_name"],
                    "score": a["score"],
                    "status": a["status"],
                }
            )
        if a["status"] == "needs_work" and a["score"] is not None:
            priority.append(
                {
                    "area_id": a["area_id"],
                    "display_name": a["display_name"],
                    "score": a["score"],
                    "status": a["status"],
                }
            )

    strengths.sort(key=lambda x: x["score"], reverse=True)
    priority.sort(key=lambda x: x["score"])

    return {
        "available": True,
        "version": cfg.SCORE_VERSION,
        "calibration_status": cfg.CALIBRATION_STATUS,
        "overall": overall,
        "label": overall_label(overall),
        "areas": areas,
        "strengths": strengths[:3],
        "priority_issues": priority[:3],
        "reason": None,
    }
