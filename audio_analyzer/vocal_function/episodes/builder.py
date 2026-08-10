"""Episode builder — merge overlapping windows into coaching episodes."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np


def merge_overlapping(
    windows: list[dict[str, Any]],
    *,
    gap_sec: float = 0.75,
    type_key: str = "type",
) -> list[dict[str, Any]]:
    """Merge overlapping/adjacent windows of the same type into episodes."""
    if not windows:
        return []
    ordered = sorted(windows, key=lambda w: float(w.get("start_sec") or 0))
    episodes: list[dict[str, Any]] = []
    cur = dict(ordered[0])
    cur["members"] = [ordered[0]]
    for w in ordered[1:]:
        same = (w.get(type_key) or cur.get(type_key)) == cur.get(type_key)
        if same and float(w.get("start_sec") or 0) <= float(cur.get("end_sec") or 0) + gap_sec:
            cur["end_sec"] = max(float(cur["end_sec"]), float(w.get("end_sec") or 0))
            cur["members"].append(w)
            # escalate concern if any member concerned
            if w.get("concern"):
                cur["concern"] = True
        else:
            episodes.append(_finalize(cur))
            cur = dict(w)
            cur["members"] = [w]
    episodes.append(_finalize(cur))
    return episodes


def _finalize(ep: dict[str, Any]) -> dict[str, Any]:
    members = ep.get("members") or [ep]
    start = float(ep.get("start_sec") or 0)
    end = float(ep.get("end_sec") or start)
    dur = max(1e-6, end - start)
    # Phase boundaries: ENTRY / PEAK / SUSTAIN / EXIT / RECOVERY
    phases = {
        "ENTRY": (start, start + 0.2 * dur),
        "PEAK": (start + 0.2 * dur, start + 0.45 * dur),
        "SUSTAIN": (start + 0.45 * dur, start + 0.75 * dur),
        "EXIT": (start + 0.75 * dur, start + 0.9 * dur),
        "RECOVERY": (start + 0.9 * dur, end),
    }
    # Aggregate from members
    efforts = [1 if m.get("effort_during") == "elevated" or m.get("concern") else 0 for m in members]
    periods = [m.get("periodicity") for m in members if m.get("periodicity") is not None]
    firms = [1 if m.get("contact_profile_during") == "firmer_like" else 0 for m in members]
    feature_matrix = {
        "source": {
            "contact_firmness": float(np.mean(firms)) if firms else None,
            "air_leakage": None,
            "naq_proxy": None,
            "oq_proxy": None,
            "h1_h2_proxy": None,
        },
        "effort": {
            "strain_like": float(np.mean(efforts)) if efforts else 0.0,
            "intensity_overshoot": None,
            "source_compression": float(np.mean(firms)) if firms else None,
            "persistence": float(np.mean(efforts[-2:])) if len(efforts) >= 2 else float(np.mean(efforts) if efforts else 0),
        },
        "regularity": {
            "periodicity": float(np.median(periods)) if periods else None,
            "roughness": any(m.get("roughness") for m in members),
            "dropout": False,
        },
        "register": {},
        "resonance": {},
        "onset": {},
        "recovery": {
            "fast": all(m.get("recovery_fast", True) for m in members),
        },
        "validity": {
            "vocal_specific": all(
                (m.get("validity") or {}).get("vocal_specific", True) for m in members
            ),
            "n_windows": len(members),
        },
    }
    return {
        "episode_id": f"{ep.get('type', 'EP')}_{start:.1f}_{end:.1f}",
        "type": ep.get("type") or "HIGH_NOTE",
        "start_sec": start,
        "end_sec": end,
        "phases": {k: {"start_sec": v[0], "end_sec": v[1]} for k, v in phases.items()},
        "feature_matrix": feature_matrix,
        "concern": bool(ep.get("concern")),
        "conclusion": ep.get("conclusion")
        or (members[-1].get("conclusion") if members else ""),
        "n_merged_windows": len(members),
        "members": [
            {"start_sec": m.get("start_sec"), "end_sec": m.get("end_sec")} for m in members
        ],
    }


def build_high_note_episodes(
    raw_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tagged = [{**e, "type": "HIGH_NOTE"} for e in raw_events]
    return merge_overlapping(tagged, gap_sec=0.75)


def build_register_episodes(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tagged = [{**e, "type": "REGISTER_TRANSITION"} for e in events]
    return merge_overlapping(tagged, gap_sec=0.5)


def pick_focus_episodes(
    episodes: list[dict[str, Any]],
    *,
    best_self: Optional[dict[str, Any]] = None,
    max_primary: int = 2,
    max_secondary: int = 2,
) -> dict[str, Any]:
    """Rank episodes for UX — not dump all windows."""
    primary = [e for e in episodes if e.get("concern")][:max_primary]
    secondary = [e for e in episodes if not e.get("concern")][:max_secondary]
    if not primary and episodes:
        primary = episodes[:1]
        secondary = episodes[1 : 1 + max_secondary]
    out = {
        "primary": primary,
        "secondary": secondary,
        "best_self_reference": best_self,
    }
    return out


def find_best_self_reference(
    episodes: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Within-song better high-note example (lower effort, higher periodicity)."""
    if len(episodes) < 2:
        return None
    scored = []
    for e in episodes:
        fm = e.get("feature_matrix") or {}
        effort = ((fm.get("effort") or {}).get("strain_like") or 0)
        period = ((fm.get("regularity") or {}).get("periodicity") or 0) or 0
        scored.append((effort - period / 20.0, e))
    scored.sort(key=lambda t: t[0])
    best = scored[0][1]
    worst = scored[-1][1]
    if best is worst:
        return None
    if (best.get("feature_matrix") or {}).get("effort", {}).get("strain_like", 1) >= (
        worst.get("feature_matrix") or {}
    ).get("effort", {}).get("strain_like", 0):
        # best not clearly better
        if not worst.get("concern"):
            return None
    return {
        **best,
        "role": "BEST_SELF_REFERENCE",
        "compare_against": worst.get("episode_id"),
        "coaching_hint": (
            f"{best['start_sec']:.0f}초 구간의 느낌과 비슷하게 "
            f"{worst['start_sec']:.0f}초 고음을 접근해보세요."
        ),
    }
