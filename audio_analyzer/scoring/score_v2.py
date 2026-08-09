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
  - metric completeness affects confidence
  - quality warning codes apply axis-specific penalties
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


def _apply_quality_code_penalties(
    area_id: str,
    confidence: float,
    codes: list[str],
) -> tuple[float, list[str]]:
    notes: list[str] = []
    conf = float(confidence)
    for code in codes:
        table = cfg.QUALITY_CODE_PENALTIES.get(code) or {}
        scale = table.get(area_id)
        if scale is None:
            continue
        conf *= float(scale)
        notes.append(code)
    return conf, notes


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
    codes = list(quality.get("codes") or [])

    demucs_hf = bool(
        artifact_flags.get("demucs_high_band_loss_likely")
        or artifact_flags.get("high_band_loss_likely")
    )

    spectral_base = 1.0
    if source_mode == "separated":
        spectral_base *= cfg.SEPARATED_SPECTRAL_CONFIDENCE_SCALE
    if demucs_hf and source_mode == "separated":
        spectral_base *= cfg.DEMUCS_HF_LOSS_CONFIDENCE_SCALE

    areas: list[dict[str, Any]] = []

    # ── 1. stability ──────────────────────────────────────────────────────
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
    stab_conf, qnotes = _apply_quality_code_penalties("stability", stab_conf, codes)
    if qnotes:
        stab_reason = f"{stab_reason}; quality={','.join(qnotes)}"
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

    # ── 2. projection (weighted components + completeness) ────────────────
    spr = acoustic.get("spr_db")
    prom = acoustic.get("singer_formant_prominence_db")
    proj_parts: list[tuple[str, float]] = []
    if spr is not None:
        proj_parts.append(
            (
                "spr",
                score_lower_is_better(
                    float(spr), cfg.PROJECTION["good"], cfg.PROJECTION["weak"]
                ),
            )
        )
    if prom is not None:
        proj_parts.append(
            (
                "singer_formant_prominence",
                score_higher_is_better(
                    float(prom),
                    cfg.PROJECTION["singer_formant_prominence_weak"],
                    cfg.PROJECTION["singer_formant_prominence_good"],
                ),
            )
        )

    n_proj = len(proj_parts)
    completeness = cfg.PROJECTION_COMPLETENESS_CONF.get(n_proj, 0.0)
    proj_conf = 0.85 * spectral_base * completeness
    if n_proj == 0:
        proj_score = None
        proj_reason = "전달력 지표 측정 실패"
    else:
        wsum = 0.0
        numer = 0.0
        for name, val in proj_parts:
            w = float(cfg.PROJECTION_COMPONENT_WEIGHTS.get(name, 0.0))
            numer += val * w
            wsum += w
        proj_score = float(numer / wsum) if wsum > 0 else float(
            sum(v for _, v in proj_parts) / n_proj
        )
        proj_reason = f"스펙트럼 전달 특성 기반 ({n_proj}/2 metrics)"
        if n_proj < 2:
            proj_reason = f"전달력 지표 일부만 측정됨 ({n_proj}/2)"
        if demucs_hf and source_mode == "separated":
            proj_reason += "; Demucs 고역 손실 가능성"
    proj_conf, qnotes = _apply_quality_code_penalties("projection", proj_conf, codes)
    if qnotes:
        proj_reason = f"{proj_reason}; quality={','.join(qnotes)}"
    areas.append(
        _area(
            "projection",
            proj_score,
            proj_conf,
            {
                "spr_db": spr,
                "singer_formant_prominence_db": prom,
                "metrics_available": n_proj,
                "metrics_expected": 2,
            },
            proj_reason,
        )
    )

    # ── 3. resonance ──────────────────────────────────────────────────────
    wg = acoustic.get("weight_gap_db")
    mg = acoustic.get("mouth_gap_db")
    slope = acoustic.get("spectral_slope_db_per_oct")
    res_parts: list[tuple[str, float]] = []
    if wg is not None:
        wcfg = cfg.RESONANCE["weight_gap"]
        res_parts.append(
            (
                "weight_gap",
                score_target_range(
                    float(wg),
                    wcfg["good_min"],
                    wcfg["good_max"],
                    wcfg["bad_min"],
                    wcfg["bad_max"],
                ),
            )
        )
    if mg is not None:
        mcfg = cfg.RESONANCE["mouth_gap"]
        res_parts.append(
            (
                "mouth_gap",
                score_lower_is_better(float(mg), mcfg["good"], mcfg["weak"]),
            )
        )
    if slope is not None:
        scfg = cfg.RESONANCE["spectral_slope"]
        res_parts.append(
            (
                "spectral_slope",
                score_target_range(
                    float(slope),
                    scfg["good_min"],
                    scfg["good_max"],
                    scfg["bad_min"],
                    scfg["bad_max"],
                ),
            )
        )

    n_res = len(res_parts)
    completeness = cfg.RESONANCE_COMPLETENESS_CONF.get(n_res, 0.0)
    res_conf = 0.8 * spectral_base * completeness
    if n_res == 0:
        res_score = None
        res_reason = "공명 지표 측정 실패"
    else:
        wsum = 0.0
        numer = 0.0
        for name, val in res_parts:
            w = float(cfg.RESONANCE_COMPONENT_WEIGHTS.get(name, 0.0))
            numer += val * w
            wsum += w
        res_score = float(numer / wsum) if wsum > 0 else float(
            sum(v for _, v in res_parts) / n_res
        )
        res_reason = f"공명 대역 균형 기반 ({n_res}/3 metrics)"
        if n_res < 3:
            res_reason = f"공명 지표 일부만 측정됨 ({n_res}/3)"
        if demucs_hf and source_mode == "separated":
            res_conf *= 0.65
            res_reason += "; Demucs 저중역 상대 과장 가능성"
    res_conf, qnotes = _apply_quality_code_penalties("resonance", res_conf, codes)
    if qnotes:
        res_reason = f"{res_reason}; quality={','.join(qnotes)}"
    areas.append(
        _area(
            "resonance",
            res_score,
            res_conf,
            {
                "weight_gap_db": wg,
                "mouth_gap_db": mg,
                "spectral_slope_db_per_oct": slope,
                "metrics_available": n_res,
                "metrics_expected": 3,
            },
            res_reason,
        )
    )

    # ── 4. dynamic_control ────────────────────────────────────────────────
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
        if float(dr) < dcfg["good_min"] and float(dr) >= dcfg["bad_min"]:
            dyn_conf *= 0.85
            dyn_reason = "작은 강약 폭은 의도적 표현일 수 있어 단정하지 않음"
    dyn_conf, qnotes = _apply_quality_code_penalties("dynamic_control", dyn_conf, codes)
    if qnotes:
        dyn_reason = f"{dyn_reason}; quality={','.join(qnotes)}"
    areas.append(
        _area(
            "dynamic_control",
            dyn_score,
            dyn_conf,
            {"dynamic_range_db": dr},
            dyn_reason,
        )
    )

    for a in areas:
        if a["confidence"] < cfg.UNKNOWN_CONFIDENCE:
            a["status"] = "unknown"

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
