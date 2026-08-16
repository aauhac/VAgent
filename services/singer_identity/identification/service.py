# -*- coding: utf-8 -*-
from __future__ import annotations

import numpy as np

from services.singer_identity.config import DEFAULT_IDENTIFY_MARGIN, DEFAULT_IDENTIFY_MATCH
from services.singer_identity.inference.encoder import cosine_similarity
from services.singer_identity.registry.store import SingerRegistry
from services.singer_identity.schemas.models import IdentifyCandidate, IdentifyResponse


def identify_embedding(
    registry: SingerRegistry,
    embedding: np.ndarray,
    *,
    match_thr: float = DEFAULT_IDENTIFY_MATCH,
    margin_thr: float = DEFAULT_IDENTIFY_MARGIN,
    top_k: int = 5,
    model_version: str = "",
) -> IdentifyResponse:
    singers = registry.list_singers()
    scored: list[IdentifyCandidate] = []
    for s in singers:
        cent = registry.get_centroid(s["singer_id"])
        if cent is None:
            continue
        sim = cosine_similarity(embedding, cent)
        scored.append(
            IdentifyCandidate(
                singer_id=s["singer_id"],
                display_name=s.get("display_name") or s["singer_id"],
                similarity=sim,
            )
        )
    scored.sort(key=lambda c: -c.similarity)
    top = scored[:top_k]
    if not top:
        return IdentifyResponse(
            decision="UNKNOWN",
            top_match=None,
            candidates=[],
            margin=None,
            model_version=model_version,
        )
    top1 = top[0]
    top2 = top[1] if len(top) > 1 else None
    margin = (top1.similarity - top2.similarity) if top2 else top1.similarity
    # Never force match below threshold
    if top1.similarity < match_thr:
        return IdentifyResponse(
            decision="UNKNOWN",
            top_match=top1,
            candidates=top,
            margin=margin,
            model_version=model_version,
        )
    if top2 is not None and margin < margin_thr:
        return IdentifyResponse(
            decision="UNCERTAIN",
            top_match=top1,
            candidates=top,
            margin=margin,
            model_version=model_version,
        )
    return IdentifyResponse(
        decision="MATCH",
        top_match=top1,
        candidates=top,
        margin=margin,
        model_version=model_version,
    )
