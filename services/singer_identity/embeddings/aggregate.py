# -*- coding: utf-8 -*-
"""Segment embedding aggregation (robust mean, outlier rejection)."""

from __future__ import annotations

from typing import Optional

import numpy as np


def l2_normalize(v: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    n = float(np.linalg.norm(v))
    if n < eps:
        return v.astype(np.float32)
    return (v / n).astype(np.float32)


def aggregate_segment_embeddings(
    embeddings: list[np.ndarray],
    weights: Optional[list[float]] = None,
    *,
    outlier_z: float = 1.5,
) -> tuple[Optional[np.ndarray], int]:
    if not embeddings:
        return None, 0
    mats = np.stack([l2_normalize(e) for e in embeddings], axis=0)
    w = np.asarray(weights if weights is not None else [1.0] * len(embeddings), dtype=np.float64)
    w = np.clip(w, 1e-3, None)
    # Centroid for outlier detection
    c0 = l2_normalize(np.average(mats, axis=0, weights=w))
    sims = mats @ c0
    med = float(np.median(sims))
    mad = float(np.median(np.abs(sims - med))) + 1e-6
    keep = sims >= (med - outlier_z * 1.4826 * mad)
    if not np.any(keep):
        keep = np.ones(len(mats), dtype=bool)
    mats_k = mats[keep]
    w_k = w[keep]
    agg = l2_normalize(np.average(mats_k, axis=0, weights=w_k))
    return agg.astype(np.float32), int(mats_k.shape[0])
