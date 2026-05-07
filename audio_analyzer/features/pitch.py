"""
pitch.py
--------
Pitch / F0 피처 추출.

librosa.pyin 을 사용해 프레임 단위 F0를 추출하고
전체 통계와 pitch stability 를 계산한다.

추출 항목
    - f0_mean_hz             : 유효 voiced 구간 평균 F0
    - f0_min_hz              : 유효 voiced 구간 최솟값
    - f0_max_hz              : 유효 voiced 구간 최댓값
    - f0_std_hz              : 유효 voiced 구간 표준편차
    - voiced_ratio           : 전체 프레임 중 유성음 비율 (pYIN 기준)
    - pitch_stability_cents  : 유효 voiced 구간 F0의 cent 단위 표준편차
                               (값이 클수록 음이 불안정)
                               무음·스파이크·옥타브 점프 제거 후 계산
    - frame_f0               : 프레임별 (time_sec, f0_hz) 목록
                               unvoiced/필터링 프레임은 f0_hz = null
"""

import numpy as np
import librosa
from typing import Optional


# pYIN 파라미터
FMIN = librosa.note_to_hz("C2")   # ~65 Hz
FMAX = librosa.note_to_hz("C7")   # ~2093 Hz

# F0 유효 범위 (보컬 chest/head voice)
F0_VALID_MIN_HZ = 70.0
F0_VALID_MAX_HZ = 1100.0   # 1100Hz 초과는 whistle/노이즈로 간주

# 무음 프레임 제외 임계치 (최대 RMS 대비 비율)
RMS_VOICED_THRESHOLD_RATIO = 0.04   # max_rms의 4% 미만이면 무음으로 간주

# 옥타브 점프 필터 (이전 프레임 대비 700cents 이상 변화 = 약 3.5semitone 이상)
OCTAVE_JUMP_CENTS = 700.0


def extract_pitch_features(y: np.ndarray, sr: int) -> dict:
    """Pitch 피처를 계산하여 dict로 반환한다."""

    hop_length = 512

    # pYIN: NaN = unvoiced
    f0, voiced_flag, _voiced_probs = librosa.pyin(
        y,
        fmin=FMIN,
        fmax=FMAX,
        sr=sr,
        hop_length=hop_length,
    )

    frame_times = librosa.frames_to_time(
        np.arange(len(f0)), sr=sr, hop_length=hop_length
    )

    # 프레임별 RMS 계산 (무음 구간 필터링용)
    frame_rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    # f0와 frame_rms 길이 맞춤
    min_len = min(len(f0), len(frame_rms))
    f0 = f0[:min_len]
    voiced_flag = voiced_flag[:min_len]
    frame_times = frame_times[:min_len]
    frame_rms = frame_rms[:min_len]

    rms_threshold = float(np.max(frame_rms)) * RMS_VOICED_THRESHOLD_RATIO + 1e-9

    # ── F0 유효성 필터링 ────────────────────────────────────────────────────
    # pYIN voiced_flag + RMS + 범위 필터 적용
    valid_mask = (
        voiced_flag
        & (frame_rms >= rms_threshold)
        & (~np.isnan(f0))
        & (f0 >= F0_VALID_MIN_HZ)
        & (f0 <= F0_VALID_MAX_HZ)
    )

    # 옥타브 점프 추가 필터 (연속 프레임 간 700cents 초과 변화 제거)
    valid_indices = np.where(valid_mask)[0]
    if len(valid_indices) > 1:
        prev_hz = None
        for idx in valid_indices:
            hz = f0[idx]
            if prev_hz is not None:
                cents_jump = abs(1200.0 * np.log2(hz / prev_hz + 1e-10))
                if cents_jump > OCTAVE_JUMP_CENTS:
                    valid_mask[idx] = False  # 점프 프레임 제거
                    prev_hz = None
                    continue
            prev_hz = hz

    voiced_f0_filtered = f0[valid_mask]

    # voiced_ratio: pYIN 원본 기준 (RMS 필터 이전, 기존 호환성 유지)
    voiced_ratio = float(np.mean(voiced_flag))

    if len(voiced_f0_filtered) == 0:
        # frame_f0 목록은 valid_mask 기준 null 처리
        frame_f0 = [
            {
                "time_sec": round(float(t), 3),
                "f0_hz": round(float(f0[i]), 2) if valid_mask[i] else None,
            }
            for i, t in enumerate(frame_times)
        ]
        return {
            "f0_mean_hz": None,
            "f0_min_hz": None,
            "f0_max_hz": None,
            "f0_std_hz": None,
            "voiced_ratio": round(voiced_ratio, 4),
            "pitch_stability_cents": None,
            "frame_f0": frame_f0,
        }

    # pitch stability: 필터링된 F0로만 계산 (스파이크/무음 제외)
    ref_hz = float(np.mean(voiced_f0_filtered))
    f0_cents = 1200.0 * np.log2(voiced_f0_filtered / ref_hz + 1e-10)
    pitch_stability_cents = float(np.std(f0_cents))

    # 프레임별 F0 목록: valid_mask False → None
    frame_f0 = [
        {
            "time_sec": round(float(t), 3),
            "f0_hz": round(float(f0[i]), 2) if valid_mask[i] else None,
        }
        for i, t in enumerate(frame_times)
    ]

    return {
        "f0_mean_hz": round(float(np.mean(voiced_f0_filtered)), 2),
        "f0_min_hz": round(float(np.min(voiced_f0_filtered)), 2),
        "f0_max_hz": round(float(np.max(voiced_f0_filtered)), 2),
        "f0_std_hz": round(float(np.std(voiced_f0_filtered)), 2),
        "voiced_ratio": round(voiced_ratio, 4),
        "pitch_stability_cents": round(pitch_stability_cents, 2),
        "frame_f0": frame_f0,
    }
