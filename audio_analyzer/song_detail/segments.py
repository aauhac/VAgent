"""
song_detail/segments.py
-----------------------
Build focus segments from v3 axis.segment_scores + legacy timeline.
"""

from __future__ import annotations

from typing import Any, Optional

from .copy import (
    WORST_FOCUS_THRESHOLD,
    focus_headline,
    focus_message,
    format_mmss,
    practice_for_submetric,
)


def _overlaps(a0: float, a1: float, b0: float, b1: float, *, tol: float = 0.75) -> bool:
    return not (a1 + tol < b0 or b1 + tol < a0)


def _pick_axis_segments(area: dict[str, Any], *, max_n: int = 2) -> list[dict[str, Any]]:
    area_id = area.get("area_id") or ""
    segs = [
        s
        for s in (area.get("segment_scores") or [])
        if s.get("start_sec") is not None
        and s.get("end_sec") is not None
        and s.get("score") is not None
    ]
    if not segs:
        return []
    segs_sorted = sorted(segs, key=lambda s: float(s["score"]))
    picked: list[dict[str, Any]] = []
    # Always include worst if clearly weak
    worst = segs_sorted[0]
    if float(worst["score"]) < WORST_FOCUS_THRESHOLD:
        picked.append(worst)
    for s in segs_sorted:
        if s is worst:
            continue
        if float(s["score"]) >= WORST_FOCUS_THRESHOLD:
            break
        if len(picked) >= max_n:
            break
        # avoid near-duplicate times
        if any(
            _overlaps(
                float(s["start_sec"]),
                float(s["end_sec"]),
                float(p["start_sec"]),
                float(p["end_sec"]),
            )
            for p in picked
        ):
            continue
        picked.append(s)
    out = []
    for s in picked[:max_n]:
        sc = float(s["score"])
        out.append(
            {
                "area_id": area_id,
                "start_sec": float(s["start_sec"]),
                "end_sec": float(s["end_sec"]),
                "score": round(sc, 1),
                "confidence": s.get("confidence"),
                "reason_code": "axis_worst_segment"
                if s is worst
                else "axis_low_segment",
                "headline": focus_headline(area_id),
                "user_message": focus_message(area_id, score=sc),
                "why": focus_message(area_id, score=sc),
                "practice_hint": practice_for_submetric(
                    {
                        "stability": "stability_worst_region",
                        "projection": "projection_worst_segment",
                        "resonance": "resonance_worst_segment",
                        "dynamic_control": "dynamic_worst_segment",
                    }.get(area_id, "")
                ),
                "time_label": f"{format_mmss(s['start_sec'])}–{format_mmss(s['end_sec'])}",
                "source": "v3_segment_scores",
            }
        )
    return out


def build_focus_segments_from_v3(
    score: dict[str, Any],
    *,
    legacy_timeline: Optional[list[dict[str, Any]]] = None,
    max_total: int = 5,
) -> list[dict[str, Any]]:
    """
    Extract focus segments from v3 segment_scores.
    Merge with legacy phonation timeline; avoid duplicates.
    """
    focus: list[dict[str, Any]] = []
    for area in score.get("areas") or []:
        # Even if axis unknown, segment_scores may still be useful
        focus.extend(_pick_axis_segments(area, max_n=2))

    # Prefer lower scores first, then dedupe overlaps across axes
    focus.sort(key=lambda e: (float(e.get("score") or 100), float(e.get("start_sec") or 0)))
    merged: list[dict[str, Any]] = []
    for ev in focus:
        if any(
            _overlaps(
                float(ev["start_sec"]),
                float(ev["end_sec"]),
                float(m["start_sec"]),
                float(m["end_sec"]),
            )
            and m.get("area_id") == ev.get("area_id")
            for m in merged
        ):
            continue
        merged.append(ev)
        if len(merged) >= max_total:
            break

    # Append non-overlapping legacy timeline events
    for ev in legacy_timeline or []:
        if len(merged) >= max_total:
            break
        try:
            a0 = float(ev.get("start_sec"))
            a1 = float(ev.get("end_sec"))
        except (TypeError, ValueError):
            continue
        if any(_overlaps(a0, a1, float(m["start_sec"]), float(m["end_sec"])) for m in merged):
            continue
        merged.append(
            {
                "area_id": ev.get("area_id") or "stability",
                "start_sec": a0,
                "end_sec": a1,
                "score": None,
                "confidence": ev.get("confidence"),
                "reason_code": "phonation_timeline",
                "headline": "지속음에서 불안정이 관측된 구간",
                "user_message": ev.get("user_message") or ev.get("message") or "참고 구간",
                "why": ev.get("user_message") or "",
                "practice_hint": practice_for_submetric("sustain_level_stability"),
                "time_label": f"{format_mmss(a0)}–{format_mmss(a1)}",
                "source": "legacy_timeline",
                "severity": ev.get("severity"),
            }
        )

    # Regression: if any area has clear worst but focus empty, force one
    if not merged:
        for area in score.get("areas") or []:
            temporal = area.get("temporal") or {}
            worst = temporal.get("worst")
            segs = area.get("segment_scores") or []
            if worst is not None and float(worst) < WORST_FOCUS_THRESHOLD and segs:
                forced = _pick_axis_segments(area, max_n=1)
                if forced:
                    return forced
    return merged
