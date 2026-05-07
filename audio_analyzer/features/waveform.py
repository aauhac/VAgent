"""
waveform.py
-----------
시간 영역(time-domain) 파형 피처 추출.

추출 항목
    - rms_mean           : 평균 RMS 에너지 (전체 음량)
    - rms_max            : 최대 RMS 에너지
    - peak_amplitude     : 최대 진폭 절댓값
    - dynamic_range_db   : 최대 RMS와 최솟값(음성 구간 내)의 dB 차이
    - silent_ratio       : 전체 구간 중 무음 비율
    - per_second_summary : 초 단위 rms_mean, peak 배열
"""

import numpy as np
import librosa


def extract_waveform_features(y: np.ndarray, sr: int) -> dict:
    """파형 피처를 계산하여 dict로 반환한다."""

    hop_length = 512
    frame_rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]

    rms_mean = float(np.mean(frame_rms))
    rms_max = float(np.max(frame_rms))
    peak_amplitude = float(np.max(np.abs(y)))

    # 무음 구간 비율 (RMS < 5% of max)
    silence_threshold = rms_max * 0.05
    silent_ratio = float(np.mean(frame_rms < silence_threshold))

    # Dynamic range: 음성 구간(무음 제외) rms 최대 - 최소의 dB 차이
    voiced_rms = frame_rms[frame_rms >= silence_threshold]
    if len(voiced_rms) > 0:
        dr_db = float(
            20 * np.log10(np.max(voiced_rms) + 1e-10)
            - 20 * np.log10(np.min(voiced_rms) + 1e-10)
        )
    else:
        dr_db = 0.0

    # 초 단위 요약
    duration_sec = len(y) / sr
    per_second_summary = _compute_per_second_summary(y, sr)

    per_100ms_summary = _compute_per_interval_summary(y, sr, interval_sec=0.1)

    return {
        "rms_mean": round(rms_mean, 6),
        "rms_max": round(rms_max, 6),
        "peak_amplitude": round(peak_amplitude, 6),
        "dynamic_range_db": round(dr_db, 2),
        "silent_ratio": round(silent_ratio, 4),
        "per_100ms_summary": per_100ms_summary,
        "per_second_summary": per_second_summary,
    }


def _compute_per_second_summary(y: np.ndarray, sr: int) -> list[dict]:
    """1초 단위로 rms_mean, peak 를 계산한다."""
    duration_sec = int(len(y) / sr)
    summary = []

    for sec in range(duration_sec):
        start = sec * sr
        end = start + sr
        chunk = y[start:end]
        if len(chunk) == 0:
            continue
        summary.append(
            {
                "second": sec,
                "rms_mean": round(float(np.sqrt(np.mean(chunk ** 2))), 6),
                "peak": round(float(np.max(np.abs(chunk))), 6),
            }
        )

    return summary


def _compute_per_interval_summary(
    y: np.ndarray, sr: int, interval_sec: float = 0.1
) -> list[dict]:
    """interval_sec 단위로 rms_mean, peak 를 계산한다."""
    interval_samples = int(sr * interval_sec)
    summary = []
    n = len(y)
    idx = 0
    while idx < n:
        chunk = y[idx : idx + interval_samples]
        if len(chunk) == 0:
            break
        start_sec = round(idx / sr, 3)
        end_sec = round(min(idx + interval_samples, n) / sr, 3)
        summary.append(
            {
                "start": start_sec,
                "end": end_sec,
                "rms_mean": round(float(np.sqrt(np.mean(chunk ** 2))), 5),
                "peak": round(float(np.max(np.abs(chunk))), 5),
            }
        )
        idx += interval_samples
    return summary
