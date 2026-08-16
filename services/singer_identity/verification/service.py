# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

import numpy as np

from services.singer_identity.config import DEFAULT_VERIFY_MATCH, DEFAULT_VERIFY_NONMATCH
from services.singer_identity.inference.encoder import cosine_similarity, l2_normalize
from services.singer_identity.registry.store import SingerRegistry
from services.singer_identity.schemas.models import VerifyResponse


def _decision(sim: float, *, match_thr: float, nonmatch_thr: float) -> str:
    if sim >= match_thr:
        return "MATCH"
    if sim <= nonmatch_thr:
        return "NON_MATCH"
    return "UNCERTAIN"


def _k2_max_similarity(registry: SingerRegistry, singer_id: str, query: np.ndarray) -> Optional[float]:
    """Experimental multi-prototype K2 score from enrollment embeddings only (shadow)."""
    try:
        from sklearn.cluster import AgglomerativeClustering
    except ImportError:
        return None
    pairs = registry._list_recording_embeddings(singer_id)
    if len(pairs) < 2:
        return None
    embs = [l2_normalize(e) for _, e in pairs]
    stacked = np.stack(embs, axis=0)
    k = 2 if len(embs) >= 2 else 1
    if k == 1:
        proto = l2_normalize(np.mean(stacked, axis=0))
        return float(cosine_similarity(query, proto))
    sim = stacked @ stacked.T
    dist = np.clip(1.0 - sim, 0.0, 2.0)
    np.fill_diagonal(dist, 0.0)
    labels = AgglomerativeClustering(n_clusters=k, metric="precomputed", linkage="average").fit_predict(dist)
    protos = []
    for c in range(k):
        idxs = [i for i in range(len(embs)) if int(labels[i]) == c]
        if not idxs:
            continue
        protos.append(l2_normalize(np.mean(stacked[idxs], axis=0)))
    if not protos:
        return None
    return float(max(cosine_similarity(query, p) for p in protos))


def verify_embedding(
    registry: SingerRegistry,
    embedding: np.ndarray,
    candidate_singer_id: str,
    *,
    match_thr: float = DEFAULT_VERIFY_MATCH,
    nonmatch_thr: float = DEFAULT_VERIFY_NONMATCH,
    model_version: str = "",
    include_shadow_k2: bool = False,
) -> VerifyResponse:
    """
    Production decision uses CENTROID only.
    Optional shadow_k2 fields are experimental and must not drive user-facing decisions.
    """
    query = l2_normalize(embedding)
    cent = registry.get_centroid(candidate_singer_id)
    if cent is None:
        return VerifyResponse(
            match=False,
            singer_id=candidate_singer_id,
            similarity=0.0,
            decision="UNCERTAIN",
            threshold=match_thr,
            model_version=model_version,
            strategy="CENTROID",
        )
    sim = float(cosine_similarity(query, cent))
    decision = _decision(sim, match_thr=match_thr, nonmatch_thr=nonmatch_thr)
    shadow_sim = None
    shadow_dec = None
    if include_shadow_k2:
        shadow_sim = _k2_max_similarity(registry, candidate_singer_id, query)
        if shadow_sim is not None:
            shadow_dec = _decision(shadow_sim, match_thr=match_thr, nonmatch_thr=nonmatch_thr)
    return VerifyResponse(
        match=decision == "MATCH",
        singer_id=candidate_singer_id,
        similarity=sim,
        decision=decision,  # type: ignore[arg-type]
        threshold=match_thr,
        model_version=model_version,
        strategy="CENTROID",
        shadow_k2_similarity=shadow_sim,
        shadow_k2_decision=shadow_dec,  # type: ignore[arg-type]
        shadow_strategy="K2" if shadow_sim is not None else None,
        shadow_does_not_affect_production_decision=True,
    )
