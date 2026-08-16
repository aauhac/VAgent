# -*- coding: utf-8 -*-
"""Post-audit finalize: reviews, MD, human validation, baseline reclass."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from audio_analyzer.diagnostic.song_evidence import get_canonical_snapshot

from scripts.vocal_behavioral_audit.artifacts import (
    build_html_report,
    enrich_audio_axes_display,
    write_csv,
    write_json,
)
from scripts.vocal_behavioral_audit.audio_review import build_canonical_review
from scripts.vocal_behavioral_audit.baseline_reclass import reclassify_baseline_dir
from scripts.vocal_behavioral_audit.diagnose import axes_from_snap
from scripts.vocal_behavioral_audit.human_labels import default_labels_path
from scripts.vocal_behavioral_audit.human_validation import run_human_validation
from scripts.vocal_behavioral_audit.markdown_reports import write_all_markdown_reports
from scripts.vocal_behavioral_audit.report_labels import (
    build_duplicate_basename_set,
    display_audio_name,
    short_id,
)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def finalize_validation_bundle(
    *,
    repo_root: Path,
    output_dir: Path,
    songs: Optional[dict[str, Any]] = None,
    assets: Optional[list[Any]] = None,
    analysis_meta: Optional[list[dict[str, Any]]] = None,
    baseline_dir: Optional[Path] = None,
    labels_path: Optional[Path] = None,
    generate_md: bool = True,
    human_validation: bool = True,
    reclassify_baseline: bool = True,
) -> dict[str, Any]:
    """Build reviews/MD/human/baseline artifacts. Human labels read AFTER canonical reviews."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = _load_json(output_dir / "summary.json") or {}
    singles = _load_jsonl(output_dir / "concern_singletons.jsonl")
    targets = _load_jsonl(output_dir / "target_matrix.jsonl")
    if not targets:
        # CSV-only target matrix in some runs — leave empty
        targets = []

    # Rebuild reviews from songs if provided; else from singleton axes (first row per audio)
    reviews: list[dict[str, Any]] = []
    meta_by_id = {m.get("audio_id"): m for m in (analysis_meta or []) if m.get("audio_id")}
    asset_by_id = {}
    if assets:
        for a in assets:
            asset_by_id[getattr(a, "audio_id", None) or a.get("audio_id")] = a

    if songs:
        for aid, song in songs.items():
            snap = get_canonical_snapshot(song)
            axes = axes_from_snap(snap)
            asset = asset_by_id.get(aid)
            path = getattr(asset, "path", None) if asset else None
            sha = getattr(asset, "sha256", None) if asset else None
            if not path:
                # fall back from singleton
                sample = next((r for r in singles if r.get("audio_id") == aid), {})
                path = sample.get("path") or aid
                sha = sample.get("sha256") or aid
            reviews.append(
                build_canonical_review(
                    audio_id=aid,
                    path=str(path),
                    sha256=str(sha or ""),
                    snap=snap,
                    axes=axes,
                    duration_sec=getattr(asset, "duration_sec", None) if asset else None,
                    sample_rate=getattr(asset, "sample_rate", None) if asset else None,
                    analysis_meta=meta_by_id.get(aid),
                )
            )
    else:
        # Reconstruct minimal reviews from singleton first-axes (canonical axes only)
        seen = set()
        for r in singles:
            aid = r.get("audio_id")
            if not aid or aid in seen:
                continue
            seen.add(aid)
            axes = r.get("canonical_axes") or {}
            # synthesize snap-like for review builder
            snap = {
                "effort": {
                    "level": axes.get("effort_status"),
                    "confidence_label": axes.get("effort_confidence"),
                    "reliable_for_preserve": axes.get("effort_reliable"),
                },
                "contact": {"status": axes.get("contact")},
                "breathiness": {"level": axes.get("breathiness")},
                "register": {"status": axes.get("register_connection") or axes.get("register")},
                "source_balance": {"status": axes.get("source_balance")},
                "stability": {"status": axes.get("stability")},
                "timbre": {
                    "presence": 0.3
                    if axes.get("presence") == "LOW"
                    else 0.7
                    if axes.get("presence") == "HIGH"
                    else 0.5
                    if axes.get("presence") == "MID"
                    else None,
                    "brightness": 0.3
                    if axes.get("brightness") == "LOW"
                    else 0.7
                    if axes.get("brightness") == "HIGH"
                    else 0.5
                    if axes.get("brightness") == "MID"
                    else None,
                    "airiness": None,
                    "axes": {},
                },
                "high_note": {"available": axes.get("high_note_available")},
                "availability": axes.get("availability") or {},
            }
            reviews.append(
                build_canonical_review(
                    audio_id=str(aid),
                    path=str(r.get("path") or aid),
                    sha256=str(r.get("sha256") or aid),
                    snap=snap,
                    axes=axes,
                )
            )

    reviews.sort(key=lambda x: str(x.get("audio_id") or ""))

    # Attach human-facing display names (hash never primary when filename exists)
    dups = build_duplicate_basename_set([str(r.get("file") or "") for r in reviews])
    for rev in reviews:
        info = rev.get("audio_info") or {}
        hc = rev.get("human_comparison") or {}
        rev["display_name"] = display_audio_name(
            path=str(rev.get("file") or ""),
            audio_id=str(rev.get("audio_id") or ""),
            sha256=str(rev.get("sha256") or ""),
            original_filename=info.get("original_filename"),
            human_name=hc.get("name"),
            duplicate_basenames=dups,
        )

    # Human validation AFTER reviews (labels never enter analyzer)
    human_summary = {}
    if human_validation:
        lp = labels_path or default_labels_path(repo_root)
        human_summary = run_human_validation(
            reviews=reviews,
            labels_path=lp,
            output_dir=output_dir,
        )

    singleton_by_audio: dict[str, list] = defaultdict(list)
    for r in singles:
        singleton_by_audio[str(r.get("audio_id"))].append(r)

    target_by_audio: dict[str, list] = defaultdict(list)
    # target rows may be in checkpoint/summary only — try CSV
    target_csv = output_dir / "target_matrix.csv"
    if target_csv.exists():
        import csv

        with target_csv.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                target_by_audio[str(row.get("audio_id"))].append(row)

    collapse_by_audio: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    collapse_csv = output_dir / "generic_collapse.csv"
    if collapse_csv.exists():
        import csv

        with collapse_csv.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                audio = str(row.get("audio") or "")
                cls = str(row.get("classification") or "")
                if audio and cls:
                    collapse_by_audio[audio][cls] += 1

    md_info = {}
    if generate_md:
        md_info = write_all_markdown_reports(
            output_dir=output_dir,
            reviews=reviews,
            singleton_by_audio=dict(singleton_by_audio),
            target_by_audio=dict(target_by_audio),
            collapse_by_audio={k: dict(v) for k, v in collapse_by_audio.items()},
        )

    comparison = {}
    if reclassify_baseline:
        bdir = baseline_dir or (repo_root / "audit_output_baseline")
        if bdir.exists():
            comparison = reclassify_baseline_dir(
                bdir,
                output_dir=output_dir,
                after_summary=summary,
            )

    write_json(output_dir / "audio_reviews.json", reviews)

    # Rewrite audio_axes.csv with raw + display columns (presentation only)
    axes_csv = output_dir / "audio_axes.csv"
    axes_rows: list[dict[str, Any]] = []
    if axes_csv.exists():
        import csv as _csv

        with axes_csv.open(encoding="utf-8") as f:
            axes_rows = list(_csv.DictReader(f))
    if not axes_rows:
        for r in reviews:
            c = r.get("canonical") or {}
            axes_rows.append(
                {
                    "audio_id": r.get("audio_id"),
                    "file": r.get("file"),
                    "sha256": r.get("sha256"),
                    "effort_status": (c.get("effort") or {}).get("status"),
                    "contact": (c.get("contact") or {}).get("status"),
                    "breathiness": (c.get("breathiness") or {}).get("status"),
                    "register_connection": (c.get("register_connection") or {}).get("status"),
                    "source_balance": (c.get("source_balance") or {}).get("status"),
                    "stability": (c.get("stability") or {}).get("status"),
                    "presence": (c.get("presence") or {}).get("status"),
                    "brightness": (c.get("brightness") or {}).get("status"),
                }
            )
    by_id = {str(r.get("audio_id")): r for r in reviews}
    enriched = []
    for row in axes_rows:
        aid = str(row.get("audio_id") or "")
        rev = by_id.get(aid) or {}
        enriched.append(
            enrich_audio_axes_display(
                row,
                display_name=rev.get("display_name")
                or display_audio_name(
                    path=str(row.get("file") or rev.get("file") or ""),
                    audio_id=aid,
                    sha256=str(row.get("sha256") or rev.get("sha256") or ""),
                ),
            )
        )
    write_csv(axes_csv, enriched)

    # Enrich summary
    summary = dict(summary)
    summary["validation_bundle"] = {
        "reviews": len(reviews),
        "markdown": md_info,
        "human_validation": human_summary,
        "apples_to_apples": comparison,
    }
    summary["manual_review_queue_count"] = len(md_info.get("manual_review_queue") or [])
    write_json(output_dir / "summary.json", summary)

    # Refresh HTML with MD linkage (filename-first cards)
    path_by = md_info.get("path_by_audio") or {}
    html_cases = []
    for r in reviews:
        aid = str(r.get("audio_id") or "")
        fname = path_by.get(aid)
        html_cases.append(
            {
                "audio_id": aid,
                "display_name": r.get("display_name"),
                "short_id": short_id(aid, str(r.get("sha256") or "")),
                "file": r.get("file"),
                "one_line": r.get("one_line_summary"),
                "one_line_summary": r.get("one_line_summary"),
                "register_connection": (r.get("canonical") or {})
                .get("register_connection", {})
                .get("status"),
                "register_connection_display": (r.get("canonical") or {})
                .get("register_connection", {})
                .get("display"),
                "source_balance": (r.get("canonical") or {}).get("source_balance", {}).get("status"),
                "source_balance_display": (r.get("canonical") or {})
                .get("source_balance", {})
                .get("display"),
                "effort": (r.get("canonical") or {}).get("effort", {}).get("status"),
                "effort_display": (r.get("canonical") or {}).get("effort", {}).get("display"),
                "audit_review_status": r.get("audit_review_status"),
                "human_miss": (r.get("human_comparison") or {}).get("has_miss"),
                "md": fname,
                "md_path": f"audio_reports/{fname}" if fname else None,
                "review_flags": r.get("review_flags"),
            }
        )

    try:
        html = build_html_report(summary, cases_sample=html_cases)
        (output_dir / "report.html").write_text(html, encoding="utf-8")
    except Exception:
        pass

    return {
        "reviews": len(reviews),
        "markdown": md_info,
        "human_validation": human_summary,
        "comparison": comparison,
    }
