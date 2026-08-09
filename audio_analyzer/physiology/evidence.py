"""
evidence.py
-----------
Evidence fusion by independent families (not raw metric counts).

CPP proxy + HNR proxy share PERIODICITY — counting both as two sensors is forbidden.
"""

from __future__ import annotations

from typing import Any, Optional

from .literature_registry import METRIC_AUDIT

# Canonical family map (fallback if metric not in audit)
FAMILY_BY_METRIC = {
    mid: meta["evidence_family"] for mid, meta in METRIC_AUDIT.items()
}
FAMILY_BY_METRIC["rms_variation_db"] = "temporal_stability"
FAMILY_BY_METRIC["voiced_dropout_count"] = "register_continuity"
FAMILY_BY_METRIC["local_instability_event_count"] = "temporal_stability"
FAMILY_BY_METRIC["f0_displacement_cents_during_swell"] = "intensity_coordination"
# Legacy aliases accepted when reading older session JSON
LEGACY_METRIC_ALIASES = {
    "cpp_db": "cepstral_prominence_proxy_db",
    "hnr_ac_db": "hnr_ac_proxy_db",
    "h1_h2_db": "raw_h1_h2_proxy_db",
    "local_jitter_percent": "f0_frame_period_perturbation_proxy_percent",
    "local_shimmer_percent": "amplitude_window_shimmer_proxy_percent",
}


def canonicalize_metric_id(metric_id: str) -> str:
    return LEGACY_METRIC_ALIASES.get(metric_id, metric_id)


def family_for(metric_id: str) -> str:
    mid = canonicalize_metric_id(metric_id)
    return FAMILY_BY_METRIC.get(mid, "other")


def index_observations(task_results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_id: dict[str, list[dict[str, Any]]] = {}
    for tr in task_results:
        for obs in tr.get("observations") or []:
            if not obs.get("valid"):
                continue
            mid = canonicalize_metric_id(obs["metric_id"])
            item = dict(obs)
            item["metric_id"] = mid
            by_id.setdefault(mid, []).append(item)
    return by_id


def mean_valid(obs_list: list[dict[str, Any]]) -> Optional[float]:
    vals = [float(o["value"]) for o in obs_list if o.get("value") is not None]
    if not vals:
        return None
    return float(sum(vals) / len(vals))


def build_evidence_bundle(task_results: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = index_observations(task_results)
    by_metric = {
        mid: {
            "n": len(items),
            "mean": mean_valid(items),
            "tasks": sorted({i.get("source_task") for i in items if i.get("source_task")}),
            "items": items,
            "family": family_for(mid),
        }
        for mid, items in by_id.items()
    }

    by_family: dict[str, dict[str, Any]] = {}
    for mid, block in by_metric.items():
        fam = block["family"]
        slot = by_family.setdefault(
            fam,
            {"metrics": [], "means": {}, "tasks": set(), "n_obs": 0},
        )
        slot["metrics"].append(mid)
        if block["mean"] is not None:
            slot["means"][mid] = block["mean"]
        slot["tasks"].update(block["tasks"])
        slot["n_obs"] += block["n"]

    for fam, slot in by_family.items():
        slot["tasks"] = sorted(slot["tasks"])
        # Representative value: prefer cepstral over HNR within periodicity
        if fam == "periodicity":
            slot["representative"] = slot["means"].get("cepstral_prominence_proxy_db")
            if slot["representative"] is None:
                slot["representative"] = next(iter(slot["means"].values()), None)
        else:
            vals = list(slot["means"].values())
            slot["representative"] = float(sum(vals) / len(vals)) if vals else None

    # Cross-vowel consistency for sustain tasks
    cross_vowel = _cross_vowel_consistency(by_metric)

    return {
        "by_metric": by_metric,
        "by_family": by_family,
        "task_count": len(task_results),
        "independent_family_count": len(by_family),
        "cross_vowel": cross_vowel,
    }


def _cross_vowel_consistency(by_metric: dict) -> dict[str, Any]:
    """Compare sustain_a vs sustain_i means for shared metrics."""
    out: dict[str, Any] = {"consistent_metrics": [], "inconsistent_metrics": []}
    for mid, block in by_metric.items():
        by_task: dict[str, list[float]] = {}
        for item in block["items"]:
            tid = item.get("source_task")
            if tid in ("sustain_a", "sustain_i") and item.get("value") is not None:
                by_task.setdefault(tid, []).append(float(item["value"]))
        if "sustain_a" in by_task and "sustain_i" in by_task:
            ma = sum(by_task["sustain_a"]) / len(by_task["sustain_a"])
            mi = sum(by_task["sustain_i"]) / len(by_task["sustain_i"])
            # relative disagreement
            denom = max(abs(ma), abs(mi), 1e-6)
            rel = abs(ma - mi) / denom
            if rel < 0.35:
                out["consistent_metrics"].append(mid)
            else:
                out["inconsistent_metrics"].append(mid)
    return out


def families_present(bundle: dict[str, Any], needed: list[str]) -> list[str]:
    have = set((bundle.get("by_family") or {}).keys())
    return [f for f in needed if f in have]


def count_independent_families(bundle: dict[str, Any], families: list[str]) -> int:
    return len(families_present(bundle, families))
