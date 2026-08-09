"""
vocal_score.py
--------------
영역별 보컬 점수(0~100)와 전체 완성도 점수를 계산한다.
"""

from __future__ import annotations

from typing import Any, Optional
import numpy as np

from .vocal_score_config import VOCAL_SCORE_CONFIG
from .acoustic_metrics import compute_core_acoustic_metrics
from .feedback_templates import get_area_feedback


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


def score_target_range(value: float, good_min: float, good_max: float, bad_min: float, bad_max: float) -> float:
    if good_min <= value <= good_max:
        return 100.0
    if value < good_min:
        if value <= bad_min:
            return 0.0
        return clamp(100.0 * (value - bad_min) / (good_min - bad_min))
    if value > good_max:
        if value >= bad_max:
            return 0.0
        return clamp(100.0 * (bad_max - value) / (bad_max - good_max))
    return 0.0


def score_center(value: float, target: float, tolerance: float, max_distance: float) -> float:
    distance = abs(value - target)
    if distance <= tolerance:
        return 100.0
    if distance >= max_distance:
        return 0.0
    return clamp(100.0 * (max_distance - distance) / (max_distance - tolerance))


def score_label(score: float) -> str:
    if score >= 85:
        return "매우 안정적"
    if score >= 70:
        return "좋은 편"
    if score >= 55:
        return "개선 가능성이 큰 보통 수준"
    if score >= 40:
        return "우선 개선이 필요한 수준"
    return "녹음 또는 발성 조건을 다시 확인할 필요가 있음"


def area_status(score: Optional[float], confidence: float) -> str:
    if score is None:
        return "excluded"
    if confidence < 0.35:
        return "unreliable"
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 55:
        return "normal"
    return "needs_work"


def base_confidence() -> float:
    return 1.0


def adjust_confidence(area_id: str, artifact_report: dict, quality_report: dict) -> tuple[float, str]:
    confidence = base_confidence()
    reasons: list[str] = []

    analysis_conf = quality_report.get("analysis_confidence")
    if isinstance(analysis_conf, (int, float)) and float(analysis_conf) < 0.7:
        confidence *= 0.7
        reasons.append("전체 분석 신뢰도 낮음")

    if artifact_report.get("high_band_loss_likely"):
        if area_id in ("lyric_projection", "singer_formant", "air_release", "spectral_slope"):
            confidence *= 0.55
            reasons.append("고역 손실 가능성")

    if artifact_report.get("relative_low_mid_inflation_likely"):
        if area_id in ("vocal_weight", "mouth_resonance"):
            confidence *= 0.65
            reasons.append("저중역 상대 과장 가능성")

    if area_id == "vibrato" and not artifact_report.get("f0_tracking_reliable", True):
        confidence *= 0.0
        reasons.append("F0 추적 신뢰도 낮음")

    if not reasons:
        reasons.append("특별한 신뢰도 하향 요인 없음")

    return float(confidence), ", ".join(reasons)


def build_area_score(
    area_id: str,
    score: Optional[float],
    value: Optional[float],
    metric_name: str,
    target_text: str,
    confidence: float,
    confidence_reason: str,
    feedback: str,
    practice: list[str],
) -> dict:
    config = VOCAL_SCORE_CONFIG[area_id]
    return {
        "area_id": area_id,
        "display_name": config["display_name"],
        "score": None if score is None else round(float(score), 1),
        "status": area_status(score, confidence),
        "metric_name": metric_name,
        "value": None if value is None else round(float(value), 3),
        "target": target_text,
        "weight": config["weight"],
        "confidence": round(float(confidence), 2),
        "confidence_reason": confidence_reason,
        "feedback_hint": feedback,
        "practice": practice,
    }


def compute_overall_score(area_scores: list[dict]) -> tuple[float, list[dict]]:
    numerator = 0.0
    denominator = 0.0
    adjustments = []

    for item in area_scores:
        score = item.get("score")
        weight = float(item.get("weight", 0.0))
        confidence = float(item.get("confidence", 1.0))

        if score is None:
            adjustments.append({
                "area_id": item["area_id"],
                "reason": "score 없음으로 평균 제외",
                "confidence": confidence,
            })
            continue

        if confidence <= 0.0:
            adjustments.append({
                "area_id": item["area_id"],
                "reason": item.get("confidence_reason", "신뢰도 0"),
                "confidence": confidence,
            })
            continue

        effective_weight = weight * confidence
        numerator += float(score) * effective_weight
        denominator += effective_weight

        if confidence < 0.8:
            adjustments.append({
                "area_id": item["area_id"],
                "reason": item.get("confidence_reason", ""),
                "confidence": confidence,
            })

    if denominator <= 0:
        return 0.0, adjustments

    return round(numerator / denominator, 1), adjustments


def select_priority_areas(area_scores: list[dict], limit: int = 3) -> list[str]:
    candidates = []
    for item in area_scores:
        score = item.get("score")
        conf = float(item.get("confidence", 1.0))
        if score is None or conf < 0.35:
            continue
        if item.get("status") in ("needs_work", "normal"):
            candidates.append(item)
    candidates.sort(key=lambda x: x["score"])
    return [x["area_id"] for x in candidates[:limit]]


def select_strength_areas(area_scores: list[dict], limit: int = 3) -> list[str]:
    candidates = []
    for item in area_scores:
        score = item.get("score")
        conf = float(item.get("confidence", 1.0))
        if score is None or conf < 0.5:
            continue
        if float(score) >= 70:
            candidates.append(item)
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return [x["area_id"] for x in candidates[:limit]]


def compute_vibrato_features(pitch_features: dict) -> dict:
    frame_f0 = pitch_features.get("frame_f0", [])
    if not frame_f0:
        return {"vibrato_available": False, "reason": "frame_f0 없음"}

    times = []
    hz_values = []
    for frame in frame_f0:
        hz = frame.get("f0_hz")
        t = frame.get("time_sec")
        if hz is None or t is None or hz <= 0:
            continue
        times.append(float(t))
        hz_values.append(float(hz))

    if len(hz_values) < 30:
        return {"vibrato_available": False, "reason": "유효 F0 프레임 부족"}

    times_np = np.array(times)
    hz_np = np.array(hz_values)
    duration = float(times_np[-1] - times_np[0])
    if duration < 0.8:
        return {"vibrato_available": False, "reason": "길게 유지된 음이 부족함"}

    median_hz = float(np.median(hz_np))
    cents = 1200.0 * np.log2((hz_np + 1e-10) / (median_hz + 1e-10))
    cents = np.clip(cents, -300, 300)
    depth_cents = float(np.percentile(cents, 95) - np.percentile(cents, 5)) / 2.0

    dt = float(np.median(np.diff(times_np)))
    if dt <= 0:
        return {"vibrato_available": False, "reason": "time step 계산 실패"}

    mod_signal = cents - float(np.mean(cents))
    spectrum = np.abs(np.fft.rfft(mod_signal))
    freqs = np.fft.rfftfreq(len(mod_signal), d=dt)

    mask = (freqs >= 3.0) & (freqs <= 8.0)
    if not np.any(mask):
        return {"vibrato_available": False, "reason": "3~8Hz vibrato 후보 없음"}

    sub_freqs = freqs[mask]
    sub_spec = spectrum[mask]
    peak_idx = int(np.argmax(sub_spec))
    rate_hz = float(sub_freqs[peak_idx])

    regularity = float(np.max(sub_spec) / (np.mean(sub_spec) + 1e-10))
    regularity = min(1.0, regularity / 5.0)

    return {
        "vibrato_available": True,
        "vibrato_rate_hz": rate_hz,
        "vibrato_depth_cents": depth_cents,
        "vibrato_regularity": regularity,
        "reason": "",
    }


def _build_artifact_report(frequency_features: dict, pitch_features: dict, quality_report: dict) -> dict:
    band = frequency_features.get("band_energy_db", {})
    low_mid = band.get("80_250")
    presence = band.get("2500_4000")
    air = band.get("6000_10000")

    high_band_loss_likely = False
    if low_mid is not None and air is not None and (low_mid - air) > 14.0:
        high_band_loss_likely = True
    if presence is not None and air is not None and (presence - air) > 10.0:
        high_band_loss_likely = True

    relative_low_mid_inflation_likely = high_band_loss_likely

    psc = pitch_features.get("pitch_stability_cents")
    f0_tracking_reliable = psc is not None and float(psc) < 900.0

    return {
        "high_band_loss_likely": high_band_loss_likely,
        "relative_low_mid_inflation_likely": relative_low_mid_inflation_likely,
        "f0_tracking_reliable": f0_tracking_reliable,
        "analysis_confidence": quality_report.get("analysis_confidence"),
    }


def compute_vocal_score(
    y: Any,
    sr: int,
    frequency_features: dict,
    pitch_features: dict,
    waveform_features: dict,
    artifact_report: Optional[dict] = None,
    quality_report: Optional[dict] = None,
) -> dict:
    artifact_report = artifact_report or _build_artifact_report(
        frequency_features=frequency_features,
        pitch_features=pitch_features,
        quality_report=quality_report or {},
    )
    quality_report = quality_report or {}

    acoustic = compute_core_acoustic_metrics(y, sr)
    vibrato = compute_vibrato_features(pitch_features)

    area_scores: list[dict] = []

    # low_noise
    area_id = "low_noise"
    cfg = VOCAL_SCORE_CONFIG[area_id]
    value = acoustic.get("rumble_ratio_db")
    conf, reason = adjust_confidence(area_id, artifact_report, quality_report)
    score = None if value is None else score_lower_is_better(float(value), cfg["good"], cfg["weak"])
    fb, practice = get_area_feedback(area_id, score)
    area_scores.append(build_area_score(area_id, score, value, cfg["metric"], cfg["target_text"], conf, reason, fb, practice))

    # vocal_weight
    area_id = "vocal_weight"
    cfg = VOCAL_SCORE_CONFIG[area_id]
    value = acoustic.get("weight_gap_db")
    conf, reason = adjust_confidence(area_id, artifact_report, quality_report)
    score = None if value is None else score_target_range(float(value), cfg["good_min"], cfg["good_max"], cfg["bad_min"], cfg["bad_max"])
    fb, practice = get_area_feedback(area_id, score)
    area_scores.append(build_area_score(area_id, score, value, cfg["metric"], cfg["target_text"], conf, reason, fb, practice))

    # mouth_resonance
    area_id = "mouth_resonance"
    cfg = VOCAL_SCORE_CONFIG[area_id]
    value = acoustic.get("mouth_gap_db")
    conf, reason = adjust_confidence(area_id, artifact_report, quality_report)
    score = None if value is None else score_lower_is_better(float(value), cfg["good"], cfg["weak"])
    fb, practice = get_area_feedback(area_id, score)
    area_scores.append(build_area_score(area_id, score, value, cfg["metric"], cfg["target_text"], conf, reason, fb, practice))

    # lyric_projection
    area_id = "lyric_projection"
    cfg = VOCAL_SCORE_CONFIG[area_id]
    value = acoustic.get("spr_db")
    conf, reason = adjust_confidence(area_id, artifact_report, quality_report)
    score = None if value is None else score_lower_is_better(float(value), cfg["good"], cfg["weak"])
    fb, practice = get_area_feedback(area_id, score)
    area_scores.append(build_area_score(area_id, score, value, cfg["metric"], cfg["target_text"], conf, reason, fb, practice))

    # singer_formant
    area_id = "singer_formant"
    cfg = VOCAL_SCORE_CONFIG[area_id]
    conf, reason = adjust_confidence(area_id, artifact_report, quality_report)
    center = acoustic.get("singer_formant_center_hz")
    prominence = acoustic.get("singer_formant_prominence_db")
    if center is None or prominence is None:
        score = None
        value = None
    else:
        center_score = score_center(float(center), cfg["target_center_hz"], cfg["tolerance_hz"], cfg["max_distance_hz"])
        prom_score = score_higher_is_better(float(prominence), cfg["prominence_weak_db"], cfg["prominence_good_db"])
        score = 0.6 * center_score + 0.4 * prom_score
        value = float(center)
    fb, practice = get_area_feedback(area_id, score)
    area_scores.append(build_area_score(area_id, score, value, cfg["metric"], cfg["target_text"], conf, reason, fb, practice))

    # air_release
    area_id = "air_release"
    cfg = VOCAL_SCORE_CONFIG[area_id]
    value = acoustic.get("air_ratio_db")
    conf, reason = adjust_confidence(area_id, artifact_report, quality_report)
    score = None if value is None else score_target_range(float(value), cfg["good_min"], cfg["good_max"], cfg["bad_min"], cfg["bad_max"])
    fb, practice = get_area_feedback(area_id, score)
    area_scores.append(build_area_score(area_id, score, value, cfg["metric"], cfg["target_text"], conf, reason, fb, practice))

    # spectral_slope
    area_id = "spectral_slope"
    cfg = VOCAL_SCORE_CONFIG[area_id]
    value = acoustic.get("spectral_slope_db_per_oct")
    conf, reason = adjust_confidence(area_id, artifact_report, quality_report)
    score = None if value is None else score_target_range(float(value), cfg["good_min"], cfg["good_max"], cfg["bad_min"], cfg["bad_max"])
    fb, practice = get_area_feedback(area_id, score)
    area_scores.append(build_area_score(area_id, score, value, cfg["metric"], cfg["target_text"], conf, reason, fb, practice))

    # vibrato
    area_id = "vibrato"
    cfg = VOCAL_SCORE_CONFIG[area_id]
    conf, reason = adjust_confidence(area_id, artifact_report, quality_report)
    if not vibrato.get("vibrato_available"):
        score = None
        value = None
        conf = 0.0
        reason = vibrato.get("reason", "vibrato 분석 불가")
    else:
        rate = float(vibrato.get("vibrato_rate_hz", 0.0))
        depth = float(vibrato.get("vibrato_depth_cents", 0.0))
        reg = float(vibrato.get("vibrato_regularity", 0.0))
        rate_score = score_target_range(rate, cfg["rate_good_min"], cfg["rate_good_max"], cfg["rate_bad_min"], cfg["rate_bad_max"])
        depth_score = score_target_range(depth, cfg["depth_good_min_cents"], cfg["depth_good_max_cents"], cfg["depth_bad_min_cents"], cfg["depth_bad_max_cents"])
        score = (0.45 * rate_score) + (0.35 * depth_score) + (0.20 * reg * 100.0)
        value = rate
    fb, practice = get_area_feedback(area_id, score)
    area_scores.append(build_area_score(area_id, score, value, cfg["metric"], cfg["target_text"], conf, reason, fb, practice))

    overall, adjustments = compute_overall_score(area_scores)

    return {
        "overall_score": overall,
        "score_label": score_label(overall),
        "area_scores": area_scores,
        "priority_areas": select_priority_areas(area_scores),
        "strength_areas": select_strength_areas(area_scores),
        "confidence_adjustments": adjustments,
        "raw_metrics": {
            **acoustic,
            **vibrato,
        },
    }
