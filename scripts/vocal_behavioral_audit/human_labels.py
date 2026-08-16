# -*- coding: utf-8 -*-
"""Human audio labels — evaluation only, never fed into analyzer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


AXIS_KEYS = (
    "effort",
    "register_connection",
    "breathiness",
    "brightness",
    "presence",
)


def default_labels_path(repo_root: Path) -> Path:
    return repo_root / "audit_labels" / "human_audio_labels.json"


def load_human_labels(path: Path) -> dict[str, Any]:
    """Load label manifest keyed by full SHA-256 (or short id aliases)."""
    if not path.exists():
        return {"version": "human-audio-labels-v1", "labels": {}}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "labels" in raw:
        return raw
    # bare sha -> label map
    return {"version": "human-audio-labels-v1", "labels": raw}


def resolve_label(
    labels_doc: dict[str, Any],
    *,
    sha256: str,
    audio_id: str = "",
) -> Optional[dict[str, Any]]:
    lab = (labels_doc or {}).get("labels") or {}
    if sha256 and sha256 in lab:
        return dict(lab[sha256])
    if audio_id and audio_id in lab:
        return dict(lab[audio_id])
    # short sha prefix
    for k, v in lab.items():
        if sha256 and (sha256.startswith(k) or k.startswith(sha256[:12])):
            return dict(v)
    return None


def normalize_rating(axis: str, value: Any) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip().upper()
    if not v or v in ("NULL", "NONE", "N/A", "UNKNOWN"):
        return None
    # soft aliases from older manifests
    aliases = {
        "HIGHEST": "HIGH",
        "LOW_OR_WEAK": "LOW",
        "LOW_OR_OCCASIONAL": "LOW",
        "LIGHT_OR_MID": None,  # not a primary validation axis rating
        "FIRM_POSSIBLE": None,
        "FIRM_OR_MID": None,
        "LIGHT": None,
    }
    if v in aliases:
        return aliases[v]
    return v
