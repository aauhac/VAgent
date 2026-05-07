"""
frequency.py
------------
주파수 영역 피처 추출.

추출 항목
    - spectral_centroid_mean_hz  : 스펙트럼 무게중심 (소리 밝기 지표)
    - spectral_bandwidth_mean_hz : 스펙트럼 대역폭
    - spectral_rolloff_mean_hz   : 85% 에너지 롤오프 주파수
    - dominant_frequency_hz      : 전체 스펙트럼에서 가장 강한 주파수
    - band_energy_db             : 보컬 분석 핵심 대역별 평균 dB 에너지
"""

import numpy as np
import librosa


# 분석 대역 정의 (Hz)
BANDS: dict[str, tuple[int, int]] = {
    "80_250":    (80,   250),
    "250_500":   (250,  500),
    "500_800":   (500,  800),
    "800_1500":  (800,  1500),
    "1500_2500": (1500, 2500),
    "2500_4000": (2500, 4000),
    "4000_6000": (4000, 6000),
    "6000_10000":(6000, 10000),
}


def extract_frequency_features(y: np.ndarray, sr: int) -> dict:
    """주파수 피처를 계산하여 dict로 반환한다."""

    # STFT → 파워 스펙트로그램
    n_fft = 2048
    hop_length = 512
    D = librosa.stft(y, n_fft=n_fft, hop_length=hop_length)
    S_power = np.abs(D) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    # Spectral centroid, bandwidth, rolloff
    centroid = librosa.feature.spectral_centroid(S=np.abs(D), sr=sr)[0]
    bandwidth = librosa.feature.spectral_bandwidth(S=np.abs(D), sr=sr)[0]
    rolloff = librosa.feature.spectral_rolloff(S=np.abs(D), sr=sr, roll_percent=0.85)[0]

    # 대역별 에너지 (dB)
    band_energy_db = {
        band: _band_energy_db(S_power, freqs, low, high)
        for band, (low, high) in BANDS.items()
    }

    # 가장 강한 주파수 (전체 평균 스펙트럼에서)
    mean_spectrum = S_power.mean(axis=1)
    dominant_idx = int(np.argmax(mean_spectrum))
    dominant_freq = float(freqs[dominant_idx])

    return {
        "spectral_centroid_mean_hz": round(float(np.mean(centroid)), 2),
        "spectral_bandwidth_mean_hz": round(float(np.mean(bandwidth)), 2),
        "spectral_rolloff_mean_hz": round(float(np.mean(rolloff)), 2),
        "dominant_frequency_hz": round(dominant_freq, 2),
        "band_energy_db": {k: round(v, 2) for k, v in band_energy_db.items()},
    }


def _band_energy_db(
    S_power: np.ndarray,
    freqs: np.ndarray,
    low_hz: int,
    high_hz: int,
) -> float:
    """특정 주파수 대역의 평균 파워를 dB로 반환한다."""
    mask = (freqs >= low_hz) & (freqs < high_hz)
    if not mask.any():
        return -80.0
    band_power = float(S_power[mask, :].mean())
    return 10.0 * np.log10(band_power + 1e-10)
