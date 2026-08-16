# -*- coding: utf-8 -*-
"""Runtime config for Singer Identity (separate from VAgent)."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME = Path(
    os.environ.get("SINGER_ID_RUNTIME", str(REPO_ROOT / "runtime" / "singer_identity"))
)
DEFAULT_OUTPUT = Path(
    os.environ.get("SINGER_ID_OUTPUT", str(REPO_ROOT / "singer_identity_output"))
)
DEFAULT_LABELS = REPO_ROOT / "singer_identity_labels" / "singers.json"
DEFAULT_GATE = REPO_ROOT / "services" / "singer_identity" / "evaluation_gate.yaml"

PREPROCESSING_VERSION = "vocal_segment_v1"
DEFAULT_SR = 16000
SEGMENT_SEC = 3.0
SEGMENT_HOP_SEC = 1.5
MIN_SEGMENT_SEC = 1.5
EMBEDDING_DIM = 192
ENCODER_NAME_BASELINE = "mel_xvector_stats_v1"
MODEL_VERSION = "singer-id-baseline-v1"

# Decision thresholds (calibrated later; defaults conservative for UNKNOWN)
DEFAULT_VERIFY_MATCH = 0.72
DEFAULT_VERIFY_NONMATCH = 0.55
DEFAULT_IDENTIFY_MATCH = 0.72
DEFAULT_IDENTIFY_MARGIN = 0.05
