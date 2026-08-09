"""
llm_formatter.py
----------------
analysis.json 의 전체 결과를 LLM 입력용 간결한 JSON으로 변환한다.

LLM 입력 구조
    summary_features   : 핵심 수치 요약
    frequency_balance  : 대역별 에너지를 "high" / "normal" / "low" 로 표현
    detected_issues    : 감지된 이슈 레이블 목록
    timbre_scores      : 음색 점수 (0~1)
"""

import numpy as np

from audio_analyzer.user_facing_text import build_user_facing_assessment
from audio_analyzer.artifact_filter import filter_preprocessing_artifacts


def format_for_llm(analysis_result: dict) -> dict:
    """
    analysis_result 에서 LLM 에 넣을 핵심 정보만 추려 반환한다.
    """

    audio_meta = analysis_result.get("audio_meta", {})
    waveform = analysis_result.get("waveform_features", {})
    frequency = analysis_result.get("frequency_features", {})
    pitch = analysis_result.get("pitch_features", {})
    timbre = analysis_result.get("timbre_features", {})
    issues = analysis_result.get("detected_issues", [])
    vocal_score = analysis_result.get("vocal_score", {})

    summary_features = {
        "duration_sec": audio_meta.get("duration_sec"),
        "rms_mean": waveform.get("rms_mean"),
        "dynamic_range_db": waveform.get("dynamic_range_db"),
        "spectral_centroid_mean_hz": frequency.get("spectral_centroid_mean_hz"),
        "f0_mean_hz": pitch.get("f0_mean_hz"),
        "f0_std_hz": pitch.get("f0_std_hz"),
        "voiced_ratio": pitch.get("voiced_ratio"),
        "pitch_stability_cents": pitch.get("pitch_stability_cents"),
    }

    frequency_balance = _categorize_band_energies(
        frequency.get("band_energy_db", {})
    )

    issue_events = analysis_result.get("issue_events", [])
    # LLM에는 최대 10개의 핵심 이벤트만 전달 (토큰 절약)
    top_events = sorted(issue_events, key=lambda e: (0 if e.get("severity")=="high" else 1, e.get("start", 0)))[:10]

    # quality_report 에서 분석 신뢰도와 경고만 추출
    qr = analysis_result.get("quality_report", {})
    recording_quality = {
        "echo_level":          qr.get("echo_level"),
        "analysis_confidence": qr.get("analysis_confidence"),
        "denoise_method":      qr.get("denoise_method"),
        "warning":             qr.get("warning"),
    }

    # ── Artifact 필터링 ──────────────────────────────────────────────────
    artifact = filter_preprocessing_artifacts(analysis_result)
    feedback_eligible   = artifact["feedback_eligible"]
    artifact_warnings   = artifact["artifact_warnings"]
    demucs_hf_loss      = artifact["demucs_hf_loss"]
    artifact_notes      = artifact["artifact_notes"]

    # vocal_assessment는 feedback_eligible 이슈만 사용
    vocal_assessment = build_user_facing_assessment(
        detected_issues=feedback_eligible,
        frequency_features=frequency,
        pitch_features=pitch,
    )

    return {
        "summary_features":        summary_features,
        "frequency_balance":       frequency_balance,
        "timbre_scores":           timbre,
        "detected_issues":         issues,          # 전체 (내부 참고용)
        "feedback_eligible_issues": feedback_eligible,
        "artifact_warnings":       artifact_warnings,
        "artifact_notes":          artifact_notes,
        "demucs_hf_loss_detected": demucs_hf_loss,
        "vocal_assessment":        vocal_assessment,
        "vocal_score":             vocal_score,
        "issue_events":            top_events,
        "recording_quality":       recording_quality,
    }


# ---------------------------------------------------------------------------
# 내부 함수
# ---------------------------------------------------------------------------

def _categorize_band_energies(band_energy_db: dict) -> dict:
    """
    각 대역 에너지를 z-score 기반으로 "high" / "normal" / "low" 로 분류한다.

    임계치:
        z > 0.5  → "high"
        z < -0.5 → "low"
        else     → "normal"
    """
    if not band_energy_db:
        return {}

    values = np.array(list(band_energy_db.values()))
    mean_e = float(np.mean(values))
    std_e = float(np.std(values))

    result = {}
    for band, energy in band_energy_db.items():
        if std_e < 1e-6:
            label = "normal"
        else:
            z = (energy - mean_e) / std_e
            if z > 0.5:
                label = "high"
            elif z < -0.5:
                label = "low"
            else:
                label = "normal"
        result[band] = label

    return result
