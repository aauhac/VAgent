# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from services.singer_identity.inference.encoder import SingerEncoder
from services.singer_identity.registry.store import SingerRegistry


def enroll_audio_files(
    registry: SingerRegistry,
    encoder: SingerEncoder,
    singer_id: str,
    paths: list[str | Path],
    *,
    split: str = "ENROLLMENT",
) -> dict[str, Any]:
    import hashlib

    recordings = []
    for path in paths:
        p = Path(path)
        data = p.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        result = encoder.encode_path(str(p), audio_id=sha[:12], sha256=sha)
        if not result.embedding:
            continue
        rec = registry.add_recording(
            singer_id,
            embedding=np.asarray(result.embedding, dtype=np.float32),
            audio_sha256=sha,
            filename=p.name,
            split=split,
            quality=result.quality,
            model_version=result.model_version,
        )
        recordings.append(rec)
    profile = registry.get_profile(singer_id) or {}
    meta = registry.get_singer(singer_id) or {}
    n = int(profile.get("recording_count") or 0)
    if n >= 3:
        pq = "GOOD"
    elif n >= 1:
        pq = "LOW_CONFIDENCE"
    else:
        pq = "EMPTY"
    return {
        "singer_id": singer_id,
        "display_name": meta.get("display_name"),
        "recording_count": n,
        "profile_quality": pq,
        "model_version": encoder.model_version,
        "within_similarity": profile.get("within_singer_similarity") or {},
        "recordings": recordings,
    }
