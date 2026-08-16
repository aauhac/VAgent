# -*- coding: utf-8 -*-
"""Agglomerative / threshold clustering without fixed K."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np


def cosine_matrix(embeddings: np.ndarray) -> np.ndarray:
    x = embeddings.astype(np.float64)
    norms = np.linalg.norm(x, axis=1, keepdims=True) + 1e-12
    x = x / norms
    return x @ x.T


def cluster_embeddings(
    embeddings: np.ndarray,
    *,
    distance_threshold: float = 0.35,
    min_cluster_size: int = 1,
) -> dict[str, Any]:
    """Agglomerative clustering on cosine distance; unresolved if singleton weak.

    distance_threshold: merge if cosine distance < threshold (i.e. sim > 1-thr).
    """
    n = embeddings.shape[0]
    if n == 0:
        return {"labels": [], "n_clusters": 0, "unresolved": []}
    sim = cosine_matrix(embeddings)
    dist = np.clip(1.0 - sim, 0.0, 2.0)
    try:
        from sklearn.cluster import AgglomerativeClustering

        # sklearn >=1.2 metric=; older affinity=
        try:
            model = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=distance_threshold,
                metric="precomputed",
                linkage="average",
            )
        except TypeError:
            model = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=distance_threshold,
                affinity="precomputed",
                linkage="average",
            )
        labels = model.fit_predict(dist)
    except Exception:
        # Connected components fallback on similarity graph
        thr_sim = 1.0 - distance_threshold
        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for i in range(n):
            for j in range(i + 1, n):
                if sim[i, j] >= thr_sim:
                    union(i, j)
        roots = {find(i) for i in range(n)}
        root_map = {r: k for k, r in enumerate(sorted(roots))}
        labels = np.array([root_map[find(i)] for i in range(n)], dtype=int)

    labels = np.asarray(labels, dtype=int)
    # Mark unresolved: clusters with size < min_cluster_size OR weak internal cohesion
    unresolved: list[int] = []
    final = labels.copy()
    next_u = -1
    for cid in sorted(set(labels.tolist())):
        idx = np.where(labels == cid)[0]
        if len(idx) < min_cluster_size:
            for i in idx:
                final[i] = next_u
                unresolved.append(int(i))
                next_u -= 1
            continue
        if len(idx) == 1:
            # singleton: keep as cluster but flag low confidence externally
            pass
        else:
            within = sim[np.ix_(idx, idx)]
            # off-diagonal mean
            mask = ~np.eye(len(idx), dtype=bool)
            mean_within = float(within[mask].mean()) if mask.any() else 1.0
            if mean_within < 0.45:
                for i in idx:
                    final[i] = next_u
                    unresolved.append(int(i))
                    next_u -= 1

    # Relabel non-negative clusters to 0..K-1
    pos = sorted({int(c) for c in final.tolist() if c >= 0})
    remap = {c: i for i, c in enumerate(pos)}
    out_labels = []
    for c in final.tolist():
        if c < 0:
            out_labels.append(-1)  # UNRESOLVED
        else:
            out_labels.append(remap[c])
    return {
        "labels": out_labels,
        "n_clusters": len(pos),
        "unresolved_indices": [i for i, c in enumerate(out_labels) if c < 0],
        "similarity": sim,
        "distance_threshold": distance_threshold,
    }


def cluster_stats(
    labels: list[int],
    sim: np.ndarray,
    names: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    names = names or [str(i) for i in range(len(labels))]
    stats = []
    clusters = sorted({c for c in labels if c >= 0})
    for cid in clusters:
        idx = [i for i, c in enumerate(labels) if c == cid]
        within = []
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                within.append(float(sim[idx[a], idx[b]]))
        # nearest external
        external = []
        for i in idx:
            for j, c in enumerate(labels):
                if c != cid and c >= 0:
                    external.append(float(sim[i, j]))
        mean_within = float(np.mean(within)) if within else 1.0
        min_within = float(np.min(within)) if within else 1.0
        nearest_ext = float(np.max(external)) if external else 0.0
        sep = mean_within - nearest_ext
        stats.append(
            {
                "cluster_id": f"speaker_{cid+1:03d}",
                "member_count": len(idx),
                "members": [names[i] for i in idx],
                "member_indices": idx,
                "mean_within_similarity": mean_within,
                "min_within_similarity": min_within,
                "nearest_external_similarity": nearest_ext,
                "separation_margin": sep,
                "confidence": "HIGH"
                if len(idx) >= 3 and sep >= 0.08
                else "MEDIUM"
                if len(idx) >= 2 and sep >= 0.03
                else "LOW",
            }
        )
    return stats
