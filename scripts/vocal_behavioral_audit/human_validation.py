# -*- coding: utf-8 -*-
"""Human vs analyzer validation (post-analysis only)."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

from scripts.vocal_behavioral_audit.artifacts import write_csv, write_json
from scripts.vocal_behavioral_audit.human_labels import (
    AXIS_KEYS,
    load_human_labels,
    normalize_rating,
    resolve_label,
)


def classify_axis_match(human: Optional[str], analyzer: Optional[str]) -> str:
    if human is None:
        return "NOT_LABELED"
    a = str(analyzer or "").upper()
    if a in ("", "UNKNOWN", "UNAVAILABLE", "UNRESOLVED"):
        return "UNAVAILABLE"
    h = str(human).upper()
    if h == a:
        return "MATCH"
    # soft adjacent
    soft = {
        ("HIGH", "MODERATE"),
        ("MODERATE", "HIGH"),
        ("PARTIAL", "DISRUPTED"),
        ("DISRUPTED", "PARTIAL"),
        ("MID", "LOW"),
        ("MID", "HIGH"),
    }
    if (h, a) in soft:
        return "PARTIAL_MATCH"
    return "MISS"


def compare_audio_to_label(
    review: dict[str, Any],
    label: dict[str, Any],
) -> dict[str, Any]:
    canon = review.get("canonical") or {}
    ratings = label.get("ratings") or {}
    rows = []
    for axis in AXIS_KEYS:
        human = normalize_rating(axis, ratings.get(axis))
        block = canon.get(axis) or {}
        analyzer = str(block.get("status") or "").upper() or None
        result = classify_axis_match(human, analyzer)
        rows.append(
            {
                "axis": axis,
                "human": human,
                "analyzer": analyzer,
                "result": result,
            }
        )
    return {
        "name": label.get("name"),
        "intent": list(label.get("intent") or []),
        "confidence": label.get("confidence"),
        "notes": label.get("notes"),
        "axis_comparison": rows,
        "has_miss": any(r["result"] == "MISS" for r in rows),
        "has_match": any(r["result"] == "MATCH" for r in rows),
    }


def run_human_validation(
    *,
    reviews: list[dict[str, Any]],
    labels_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Compare labels AFTER reviews exist. Never mutates reviews' canonical truth."""
    doc = load_human_labels(labels_path)
    labels_used: dict[str, Any] = {}
    per_axis_rows: dict[str, list[dict[str, Any]]] = {k: [] for k in AXIS_KEYS}
    labeled_audios = 0
    misses: list[dict[str, Any]] = []

    for rev in reviews:
        sha = str(rev.get("sha256") or "")
        aid = str(rev.get("audio_id") or "")
        label = resolve_label(doc, sha256=sha, audio_id=aid)
        if not label:
            rev["human_comparison"] = None
            continue
        labeled_audios += 1
        labels_used[sha or aid] = label
        cmp = compare_audio_to_label(rev, label)
        rev["human_comparison"] = cmp
        for row in cmp["axis_comparison"]:
            axis = row["axis"]
            per_axis_rows[axis].append(
                {
                    "audio_id": aid,
                    "sha256": sha,
                    "name": label.get("name"),
                    "human": row["human"],
                    "analyzer": row["analyzer"],
                    "result": row["result"],
                    "intent": ",".join(cmp.get("intent") or []),
                }
            )
            if row["result"] == "MISS":
                misses.append(
                    {
                        "audio_id": aid,
                        "axis": axis,
                        "human": row["human"],
                        "analyzer": row["analyzer"],
                        "intent": cmp.get("intent"),
                    }
                )

    out = output_dir / "human_validation"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "labels_used.json", {"path": str(labels_path), "labels": labels_used})

    coverage = {}
    axis_summaries = {}
    for axis, rows in per_axis_rows.items():
        write_csv(out / f"{axis}.csv", rows)
        labeled_n = sum(1 for r in rows if r.get("human"))
        results = Counter(r["result"] for r in rows if r.get("human"))
        coverage[axis] = labeled_n
        axis_summaries[axis] = {
            "labeled": labeled_n,
            "results": dict(results),
            "directional_agreement": _directional_note(axis, rows),
        }

    # Contrast groups when enough labels
    contrasts = _build_contrasts(per_axis_rows)

    md_lines = [
        "# Human-Labeled Acoustic Validation",
        "",
        f"Labeled audios: **{labeled_audios}**",
        "",
        "## Coverage",
        "",
    ]
    for axis in AXIS_KEYS:
        md_lines.append(f"- {axis}: {coverage.get(axis, 0)}")
    md_lines.extend(["", "## Axis summaries", ""])
    for axis, s in axis_summaries.items():
        md_lines.append(f"### {axis}")
        md_lines.append(f"- labeled: {s['labeled']}")
        md_lines.append(f"- results: `{s['results']}`")
        md_lines.append(f"- note: {s['directional_agreement']}")
        md_lines.append("")
    if contrasts:
        md_lines.extend(["## Contrast groups", ""])
        for name, info in contrasts.items():
            md_lines.append(f"- {name}: {info}")
    if misses:
        md_lines.extend(["## Detector miss candidates", ""])
        for m in misses[:50]:
            md_lines.append(
                f"- `{m['audio_id']}` {m['axis']}: human={m['human']} analyzer={m['analyzer']}"
            )
    (out / "validation_summary.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return {
        "labeled_audios": labeled_audios,
        "coverage": coverage,
        "axis_summaries": axis_summaries,
        "contrasts": contrasts,
        "detector_misses": misses,
        "labels_path": str(labels_path),
    }


def _directional_note(axis: str, rows: list[dict[str, Any]]) -> str:
    labeled = [r for r in rows if r.get("human")]
    if not labeled:
        return "insufficient labels — no quantitative claim"
    if len(labeled) < 3:
        matches = sum(1 for r in labeled if r["result"] == "MATCH")
        return f"case table only (n={len(labeled)}, match={matches})"
    matches = sum(1 for r in labeled if r["result"] in ("MATCH", "PARTIAL_MATCH"))
    return f"directional agreement {matches}/{len(labeled)} (not a calibrated accuracy)"


def _build_contrasts(per_axis_rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    effort = [r for r in per_axis_rows["effort"] if r.get("human")]
    if any(r["human"] == "LOW" for r in effort) and any(r["human"] == "HIGH" for r in effort):
        out["RELAXED_vs_PUSHED"] = {
            "low_n": sum(1 for r in effort if r["human"] == "LOW"),
            "high_n": sum(1 for r in effort if r["human"] == "HIGH"),
        }
    reg = [r for r in per_axis_rows["register_connection"] if r.get("human")]
    if any(r["human"] == "CONNECTED" for r in reg) and any(r["human"] == "DISRUPTED" for r in reg):
        out["CONNECTED_vs_DISRUPTED"] = {
            "connected_n": sum(1 for r in reg if r["human"] == "CONNECTED"),
            "disrupted_n": sum(1 for r in reg if r["human"] == "DISRUPTED"),
        }
    breath = [r for r in per_axis_rows["breathiness"] if r.get("human")]
    if any(r["human"] == "LOW" for r in breath) and any(r["human"] == "HIGH" for r in breath):
        out["LOW_BREATH_vs_HIGH_BREATH"] = {
            "low_n": sum(1 for r in breath if r["human"] == "LOW"),
            "high_n": sum(1 for r in breath if r["human"] == "HIGH"),
        }
    return out
