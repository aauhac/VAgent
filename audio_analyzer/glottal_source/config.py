"""Glottal inverse-filtering configuration (audio-only proxies)."""

from __future__ import annotations

GIF_METHOD = "iaif_proxy_v1"
GIF_METHOD_STATUS = "CONDITIONAL"  # not EGG-validated CQ

# LPC orders (Alku IAIF-style defaults; singing F0 may need lower nv)
NV_DEFAULT = 30
NG_DEFAULT = 3
LEAKY = 0.99

MIN_FRAME_SEC = 0.040
MAX_FRAME_SEC = 0.080
HOP_SEC = 0.020

MIN_VOICED_RATIO = 0.55
MIN_SNR_PROXY_DB = 8.0
MIN_F0_HZ = 70.0
MAX_F0_HZ = 1100.0
MIN_PERIODICITY_DB = 4.0
MIN_HARMONIC_CONF = 0.35

MEASUREMENT_MODE_DEFAULT = "AUDIO_ONLY"
