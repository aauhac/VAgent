"""
audio_analyzer/benchmark/stats.py
---------------------------------
Non-parametric discrimination statistics (no sklearn required).
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np


def _finite_pairs(
    x: Sequence[Any], y: Sequence[Any]
) -> tuple[np.ndarray, np.ndarray]:
    xa, ya = [], []
    for a, b in zip(x, y):
        if a is None or b is None:
            continue
        try:
            fa, fb = float(a), float(b)
        except (TypeError, ValueError):
            continue
        if np.isfinite(fa) and np.isfinite(fb):
            xa.append(fa)
            ya.append(fb)
    return np.asarray(xa, dtype=float), np.asarray(ya, dtype=float)


def spearman_rho(x: Sequence[Any], y: Sequence[Any]) -> dict[str, Any]:
    xa, ya = _finite_pairs(x, y)
    n = int(len(xa))
    if n < 3:
        return {"rho": None, "n": n, "p_approx": None}
    rx = _rankdata(xa)
    ry = _rankdata(ya)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    denom = float(np.sqrt(np.sum(rx**2) * np.sum(ry**2)))
    if denom <= 1e-12:
        return {"rho": 0.0, "n": n, "p_approx": None}
    rho = float(np.sum(rx * ry) / denom)
    # Approximate two-sided p via Student-t (small-N: do not over-interpret)
    if abs(rho) >= 1.0 - 1e-12:
        p = 0.0
    else:
        t = rho * np.sqrt((n - 2) / max(1e-12, 1 - rho**2))
        # crude normal approx for |t|
        p = float(2 * (1 - _norm_cdf(abs(t))))
    return {"rho": rho, "n": n, "p_approx": p}


def _rankdata(a: np.ndarray) -> np.ndarray:
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(1, len(a) + 1, dtype=float)
    # average ties
    sorted_a = a[order]
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sorted_a[j + 1] == sorted_a[i]:
            j += 1
        if j > i:
            avg = (i + j + 2) / 2.0  # 1-based ranks average
            ranks[order[i : j + 1]] = avg
        i = j + 1
    return ranks


def _norm_cdf(z: float) -> float:
    # Abramowitz & Stegun approximation
    z = float(z)
    t = 1.0 / (1.0 + 0.2316419 * abs(z))
    d = 0.3989423 * np.exp(-z * z / 2)
    p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))))
    return 1.0 - p if z > 0 else p


def roc_auc(scores: Sequence[Any], labels_pos: Sequence[Any]) -> dict[str, Any]:
    """
    ROC AUC for binary labels (1 = positive / expert, 0 = negative / beginner).
    Auto-flips direction if inverted AUC < 0.5 after trying both.
    """
    s, y = _finite_pairs(scores, labels_pos)
    n = int(len(s))
    if n < 2:
        return {"auc": None, "n": n, "direction": "n/a", "n_pos": 0, "n_neg": 0}
    y = (y > 0.5).astype(int)
    n_pos = int(np.sum(y == 1))
    n_neg = int(np.sum(y == 0))
    if n_pos == 0 or n_neg == 0:
        return {"auc": None, "n": n, "direction": "n/a", "n_pos": n_pos, "n_neg": n_neg}

    def _auc(vals: np.ndarray) -> float:
        order = np.argsort(vals, kind="mergesort")
        ranks = np.empty(len(vals), dtype=float)
        ranks[order] = np.arange(1, len(vals) + 1, dtype=float)
        # tie average
        sorted_v = vals[order]
        i = 0
        while i < len(vals):
            j = i
            while j + 1 < len(vals) and sorted_v[j + 1] == sorted_v[i]:
                j += 1
            if j > i:
                avg = (i + j + 2) / 2.0
                ranks[order[i : j + 1]] = avg
            i = j + 1
        sum_ranks_pos = float(np.sum(ranks[y == 1]))
        return (sum_ranks_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)

    auc_up = _auc(s)
    auc_dn = _auc(-s)
    if auc_up >= auc_dn:
        return {
            "auc": float(auc_up),
            "n": n,
            "direction": "higher_better",
            "n_pos": n_pos,
            "n_neg": n_neg,
        }
    return {
        "auc": float(auc_dn),
        "n": n,
        "direction": "lower_better",
        "n_pos": n_pos,
        "n_neg": n_neg,
    }


def cliffs_delta(x: Sequence[Any], y: Sequence[Any]) -> dict[str, Any]:
    """Cliff's delta: P(x>y) - P(x<y). x=expert group, y=beginner group."""
    xa = np.asarray([float(v) for v in x if v is not None and np.isfinite(float(v))], dtype=float)
    ya = np.asarray([float(v) for v in y if v is not None and np.isfinite(float(v))], dtype=float)
    if len(xa) == 0 or len(ya) == 0:
        return {"delta": None, "n_x": len(xa), "n_y": len(ya)}
    # Efficient pairwise via sorting
    more = less = 0
    for a in xa:
        more += int(np.sum(a > ya))
        less += int(np.sum(a < ya))
    n = len(xa) * len(ya)
    delta = (more - less) / float(n) if n else None
    return {"delta": None if delta is None else float(delta), "n_x": len(xa), "n_y": len(ya)}


def bootstrap_ci(
    values_a: Sequence[Any],
    values_b: Sequence[Any],
    *,
    stat: str = "auc",
    n_boot: int = 200,
    seed: int = 0,
    subjects_a: Optional[Sequence[Any]] = None,
    subjects_b: Optional[Sequence[Any]] = None,
) -> dict[str, Any]:
    """
    Bootstrap 95% CI.
    For AUC: values_a = scores, values_b = binary labels (or expert/beginner scores via labels).
    For cliffs: values_a = expert scores, values_b = beginner scores.
    Subject-aware: resample unique subjects when provided.
    """
    rng = np.random.default_rng(seed)
    stats = []

    if stat == "auc":
        s, y = _finite_pairs(values_a, values_b)
        if len(s) < 4:
            return {"lo": None, "hi": None, "n_boot": 0}
        subjects = None
        if subjects_a is not None:
            subjects = [subjects_a[i] for i in range(len(values_a)) if i < len(s)]
            # fallback sample-level if lengths mismatch
            if len(subjects) != len(s):
                subjects = None
        for _ in range(n_boot):
            if subjects is not None:
                uniq = list(dict.fromkeys(subjects))
                chosen = rng.choice(uniq, size=len(uniq), replace=True)
                idx = [i for i, sub in enumerate(subjects) if sub in set(chosen)]
                if len(idx) < 4:
                    continue
                ss, yy = s[idx], y[idx]
            else:
                idx = rng.integers(0, len(s), size=len(s))
                ss, yy = s[idx], y[idx]
            res = roc_auc(ss, yy)
            if res["auc"] is not None:
                stats.append(res["auc"])
    elif stat == "cliffs":
        xa = [float(v) for v in values_a if v is not None and np.isfinite(float(v))]
        ya = [float(v) for v in values_b if v is not None and np.isfinite(float(v))]
        if len(xa) < 2 or len(ya) < 2:
            return {"lo": None, "hi": None, "n_boot": 0}
        for _ in range(n_boot):
            xb = rng.choice(xa, size=len(xa), replace=True)
            yb = rng.choice(ya, size=len(ya), replace=True)
            d = cliffs_delta(xb, yb)["delta"]
            if d is not None:
                stats.append(d)
    elif stat == "spearman":
        s, y = _finite_pairs(values_a, values_b)
        if len(s) < 4:
            return {"lo": None, "hi": None, "n_boot": 0}
        for _ in range(n_boot):
            idx = rng.integers(0, len(s), size=len(s))
            r = spearman_rho(s[idx], y[idx])["rho"]
            if r is not None:
                stats.append(r)
    else:
        raise ValueError(stat)

    if not stats:
        return {"lo": None, "hi": None, "n_boot": 0}
    arr = np.sort(np.asarray(stats, dtype=float))
    lo = float(np.quantile(arr, 0.025))
    hi = float(np.quantile(arr, 0.975))
    return {"lo": lo, "hi": hi, "n_boot": len(stats), "mean": float(np.mean(arr))}


def group_describe(values: Sequence[Any]) -> dict[str, Any]:
    arr = np.asarray(
        [float(v) for v in values if v is not None and np.isfinite(float(v))],
        dtype=float,
    )
    if len(arr) == 0:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "std": None,
            "q25": None,
            "q75": None,
            "iqr": None,
        }
    q25, q75 = np.quantile(arr, [0.25, 0.75])
    return {
        "n": int(len(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "q25": float(q25),
        "q75": float(q75),
        "iqr": float(q75 - q25),
    }


def monotonic_by_group(
    beginner: Sequence[Any],
    intermediate: Sequence[Any],
    expert: Sequence[Any],
    *,
    higher_better: bool = True,
) -> dict[str, Any]:
    meds = []
    for g in (beginner, intermediate, expert):
        d = group_describe(g)
        meds.append(d["median"])
    if any(m is None for m in meds):
        return {"monotonic_order": False, "medians": meds, "reason": "missing_group"}
    b, i, e = meds
    if higher_better:
        ok = b <= i <= e or (b < e and i is not None)
        # strict-ish: expert median >= intermediate >= beginner
        ok = (e >= i) and (i >= b)
    else:
        ok = (e <= i) and (i <= b)
    return {"monotonic_order": bool(ok), "medians": {"beginner": b, "intermediate": i, "expert": e}}


def saturation_rate(values: Sequence[Any], *, threshold: float = 95.0) -> dict[str, Any]:
    arr = [float(v) for v in values if v is not None and np.isfinite(float(v))]
    if not arr:
        return {"rate": None, "n": 0, "n_sat": 0}
    n_sat = sum(1 for v in arr if v >= threshold)
    return {"rate": n_sat / len(arr), "n": len(arr), "n_sat": n_sat}


def within_between_variance(
    values: Sequence[Any],
    subjects: Sequence[Any],
    groups: Sequence[Any],
) -> dict[str, Any]:
    rows = [
        (float(v), s, g)
        for v, s, g in zip(values, subjects, groups)
        if v is not None and np.isfinite(float(v))
    ]
    if len(rows) < 4:
        return {"within_var": None, "between_group_var": None, "ratio": None}
    # within subject
    by_sub: dict[Any, list[float]] = {}
    for v, s, _g in rows:
        by_sub.setdefault(s, []).append(v)
    within = []
    for vals in by_sub.values():
        if len(vals) >= 2:
            within.append(float(np.var(vals, ddof=1)))
    within_var = float(np.mean(within)) if within else None
    by_g: dict[Any, list[float]] = {}
    for v, _s, g in rows:
        by_g.setdefault(g, []).append(v)
    means = [float(np.mean(v)) for v in by_g.values() if v]
    between = float(np.var(means, ddof=1)) if len(means) >= 2 else None
    ratio = None
    if within_var is not None and between is not None and within_var > 1e-12:
        ratio = between / within_var
    return {"within_var": within_var, "between_group_var": between, "ratio": ratio}
