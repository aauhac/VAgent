"""
vocal_score_config.py
---------------------
보컬 음색 영역별 기준값과 가중치를 관리한다.

주의:
- 아래 기준값은 v1 초기값이다.
- 이후 reference dataset(median/IQR)으로 반드시 보정해야 한다.
"""

VOCAL_SCORE_AREAS = [
    "low_noise",
    "vocal_weight",
    "mouth_resonance",
    "lyric_projection",
    "singer_formant",
    "air_release",
    "spectral_slope",
    "vibrato",
]

VOCAL_SCORE_CONFIG = {
    "low_noise": {
        "display_name": "저역 잡음",
        "metric": "rumble_ratio_db",
        "weight": 0.07,
        "good": -25.0,
        "weak": -15.0,
        "direction": "lower_is_better",
        "target_text": "-25dB 이하일수록 좋음",
    },
    "vocal_weight": {
        "display_name": "소리의 무게",
        "metric": "weight_gap_db",
        "weight": 0.12,
        "good_min": -6.0,
        "good_max": 10.0,
        "bad_min": -16.0,
        "bad_max": 18.0,
        "direction": "target_range",
        "target_text": "-6~10dB 범위가 적절",
    },
    "mouth_resonance": {
        "display_name": "입 안에 머무는 느낌",
        "metric": "mouth_gap_db",
        "weight": 0.12,
        "good": 6.0,
        "weak": 12.0,
        "direction": "lower_is_better",
        "target_text": "6dB 이하일수록 좋음",
    },
    "lyric_projection": {
        "display_name": "가사 전달력",
        "metric": "spr_db",
        "weight": 0.22,
        "good": 22.6,
        "weak": 30.7,
        "direction": "lower_is_better",
        "target_text": "SPR 22.6dB에 가까울수록 좋음",
    },
    "singer_formant": {
        "display_name": "보컬 전달력 중심",
        "metric": "singer_formant_center_hz",
        "weight": 0.15,
        "target_center_hz": 3000.0,
        "tolerance_hz": 300.0,
        "max_distance_hz": 900.0,
        "prominence_good_db": 6.0,
        "prominence_weak_db": 0.0,
        "direction": "center_plus_prominence",
        "target_text": "2.8~3.2kHz 근처의 peak가 뚜렷할수록 좋음",
    },
    "air_release": {
        "display_name": "소리 끝의 여유",
        "metric": "air_ratio_db",
        "weight": 0.07,
        "good_min": -22.0,
        "good_max": -8.0,
        "bad_min": -30.0,
        "bad_max": -3.0,
        "direction": "target_range",
        "target_text": "-22~-8dB 범위가 적절",
    },
    "spectral_slope": {
        "display_name": "전체 밝기 균형",
        "metric": "spectral_slope_db_per_oct",
        "weight": 0.13,
        "good_min": -16.0,
        "good_max": -8.0,
        "bad_min": -22.0,
        "bad_max": -4.0,
        "direction": "target_range",
        "target_text": "-16~-8dB/oct 범위가 적절",
    },
    "vibrato": {
        "display_name": "비브라토 안정성",
        "metric": "vibrato_rate_hz",
        "weight": 0.12,
        "rate_good_min": 5.2,
        "rate_good_max": 5.8,
        "rate_bad_min": 3.5,
        "rate_bad_max": 7.5,
        "depth_good_min_cents": 50.0,
        "depth_good_max_cents": 150.0,
        "depth_bad_min_cents": 10.0,
        "depth_bad_max_cents": 250.0,
        "direction": "vibrato_range",
        "target_text": "길게 유지되는 음에서 5.2~5.8Hz 근처가 안정적",
    },
}

STATUS_LABELS = {
    "excellent": "매우 좋음",
    "good": "좋은 편",
    "normal": "보통",
    "needs_work": "개선 필요",
    "unreliable": "참고용",
    "excluded": "분석 제외",
}
