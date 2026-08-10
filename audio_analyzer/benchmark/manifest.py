"""
audio_analyzer/benchmark/manifest.py
------------------------------------
Load / validate labeled discrimination manifests.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional

from audio_analyzer.audit.fingerprints import sha256_file

GROUP_RANK = {"beginner": 0, "intermediate": 1, "expert": 2, "unknown": None}

REQUIRED_COLS = [
    "sample_id",
    "file_path",
    "subject_id",
    "group",
    "song_id",
    "source_type",
]


def _truthy(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "t"}


def load_manifest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(
            (line for line in f if line.strip() and not line.lstrip().startswith("#"))
        )
        if not reader.fieldnames:
            return []
        for raw in reader:
            if not raw.get("sample_id") or str(raw.get("sample_id")).startswith("#"):
                continue
            group = (raw.get("group") or "unknown").strip().lower()
            skill_rank = raw.get("skill_rank")
            if skill_rank in (None, ""):
                skill_rank = GROUP_RANK.get(group)
            else:
                try:
                    skill_rank = int(float(skill_rank))
                except ValueError:
                    skill_rank = GROUP_RANK.get(group)
            row = {
                "sample_id": str(raw["sample_id"]).strip(),
                "file_path": str(raw.get("file_path") or "").strip(),
                "subject_id": str(raw.get("subject_id") or "").strip(),
                "group": group,
                "skill_rank": skill_rank,
                "song_id": str(raw.get("song_id") or "").strip(),
                "source_type": str(raw.get("source_type") or "unknown").strip(),
                "recording_device": str(raw.get("recording_device") or "").strip(),
                "has_backing_track": _truthy(raw.get("has_backing_track")),
                "commercial_mastered": _truthy(raw.get("commercial_mastered")),
                "same_song_group": str(raw.get("same_song_group") or "").strip(),
                "notes": str(raw.get("notes") or "").strip(),
            }
            rows.append(row)
    return rows


def load_human_ratings(path: Optional[Path]) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(
            (line for line in f if line.strip() and not line.lstrip().startswith("#"))
        )
        for raw in reader:
            if not raw.get("sample_id"):
                continue
            item = {"sample_id": str(raw["sample_id"]).strip(), "rater_id": str(raw.get("rater_id") or "r1")}
            for k in (
                "overall_skill",
                "stability",
                "projection",
                "resonance",
                "dynamic_control",
            ):
                v = raw.get(k)
                try:
                    item[k] = float(v) if v not in (None, "") else None
                except ValueError:
                    item[k] = None
            item["notes"] = raw.get("notes") or ""
            rows.append(item)
    return rows


def fingerprint_samples(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Attach SHA256; return (rows_with_fp, duplicate_sample_ids)."""
    seen: dict[str, str] = {}
    dupes: list[str] = []
    out = []
    for r in rows:
        item = dict(r)
        p = Path(r["file_path"])
        item["file_exists"] = p.exists()
        if not p.exists():
            item["sha256"] = None
            item["size_bytes"] = None
            item["duplicate_input"] = False
            out.append(item)
            continue
        digest = sha256_file(p)
        item["sha256"] = digest
        item["size_bytes"] = int(p.stat().st_size)
        if digest in seen:
            item["duplicate_input"] = True
            dupes.append(item["sample_id"])
            item["duplicate_of"] = seen[digest]
        else:
            item["duplicate_input"] = False
            item["duplicate_of"] = None
            seen[digest] = item["sample_id"]
        out.append(item)
    return out, dupes


def filter_active(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop duplicates and missing files."""
    return [
        r
        for r in rows
        if r.get("file_exists") and not r.get("duplicate_input") and r.get("group") != "unknown"
    ]


def subject_groups(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["subject_id"], []).append(r["sample_id"])
    return out


def same_song_subset(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Samples that share a non-empty same_song_group with ≥2 groups represented."""
    by_key: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        key = r.get("same_song_group") or ""
        if not key:
            continue
        by_key.setdefault(key, []).append(r)
    out = []
    for key, items in by_key.items():
        groups = {i["group"] for i in items}
        if len(items) >= 2 and len(groups) >= 2:
            out.extend(items)
    return out


def dataset_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups = {"expert": 0, "intermediate": 0, "beginner": 0, "unknown": 0}
    for r in rows:
        g = r.get("group") or "unknown"
        groups[g] = groups.get(g, 0) + 1
    subjects = {r["subject_id"] for r in rows if r.get("subject_id")}
    return {
        "samples": len(rows),
        "subjects": len(subjects),
        **groups,
    }
