"""
timbre.py
---------
대역별 에너지를 기반으로 음색 요약 점수(0.0 ~ 1.0)를 계산한다.

각 점수는 해당 대역이 전체 대역 중 상대적으로 얼마나 두드러지는지를
sigmoid(z-score) 방식으로 0~1 로 변환한 값이다.

  0.5 = 평균 수준
  > 0.5 = 해당 특성이 평균보다 강함
  < 0.5 = 해당 특성이 평균보다 약함

점수 항목
    - brightness_score : 고역(1.5k~10kHz) 에너지 비율 → 소리의 밝기
    - warmth_score     : 250~500Hz 에너지 → 따뜻함/몸통감
    - boxiness_score   : 500~800Hz 에너지 → 박스감/항아리 울림
    - presence_score   : 2.5~4kHz 에너지 → 전방 선명도/존재감
    - airiness_score   : 6~10kHz 에너지  → 공기감/개방감
"""

import numpy as np


def extract_timbre_features(frequency_features: dict) -> dict:
    """
    frequency_features['band_energy_db'] 를 이용해 음색 점수를 반환한다.
    """
    band = frequency_features["band_energy_db"]

    energies = list(band.values())
    mean_e = float(np.mean(energies))
    std_e = float(np.std(energies))

    def score(e: float) -> float:
        """z-score → sigmoid → 소수점 3자리 반올림."""
        if std_e < 1e-6:
            return 0.5
        z = (e - mean_e) / std_e
        return round(float(1.0 / (1.0 + np.exp(-z))), 3)

    # 고역 에너지 평균 (밝기)
    high_bands = ["1500_2500", "2500_4000", "4000_6000", "6000_10000"]
    high_mean = float(np.mean([band[b] for b in high_bands if b in band]))

    return {
        "brightness_score": score(high_mean),
        "warmth_score":     score(band.get("250_500",  mean_e)),
        "boxiness_score":   score(band.get("500_800",  mean_e)),
        "presence_score":   score(band.get("2500_4000", mean_e)),
        "airiness_score":   score(band.get("6000_10000", mean_e)),
    }
