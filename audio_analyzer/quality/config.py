"""
quality/config.py
-----------------
Recording quality gate thresholds (uncalibrated heuristics).
"""

QUALITY_GATE_VERSION = "quality-gate-v1.0"
CALIBRATION_STATUS = "uncalibrated"

# Absolute sample clipping threshold
CLIPPING_ABS_THRESHOLD = 0.995

# Duration
MIN_DURATION_SEC = 3.0
WARN_DURATION_SEC = 5.0
MAX_DURATION_SEC = 180.0

# Silence / voiced
FAIL_SILENT_RATIO = 0.92
WARN_SILENT_RATIO = 0.75
FAIL_VOICED_RATIO = 0.08
WARN_VOICED_RATIO = 0.18
FAIL_VOICED_DURATION_SEC = 1.0
WARN_VOICED_DURATION_SEC = 2.0

# Level (RMS dBFS; 0 dBFS = full scale)
FAIL_RMS_DBFS = -45.0
WARN_RMS_DBFS = -35.0

# Clipping
FAIL_CLIPPING_RATIO = 0.02
WARN_CLIPPING_RATIO = 0.005

# Low-frequency contamination (rumble_ratio_db = rumble - main_body)
# NOTE: pure tones can inflate this ratio because broadband main_body mean
# is diluted — treat as WARN only, never sole FAIL reason.
WARN_RUMBLE_RATIO_DB = -8.0
FAIL_RUMBLE_RATIO_DB = None  # disabled; use warn only

USER_MESSAGES = {
    "fail": "정확한 분석이 어려운 녹음이에요. 더 조용한 곳에서 목소리를 조금 더 크게, 조금 더 길게 불러 다시 시도해 주세요.",
    "warn": "분석은 가능하지만 녹음 조건이 완벽하지 않아요. 결과는 참고용으로 봐 주세요.",
    "pass": "녹음 품질이 분석에 충분해요.",
}
