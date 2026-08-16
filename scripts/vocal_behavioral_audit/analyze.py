# -*- coding: utf-8 -*-
"""Analyze-once cache for behavioral audit (isolated runtime)."""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any, Optional

from scripts.vocal_behavioral_audit.discovery import AudioAsset


def _has_vf(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    if isinstance(payload.get("vocal_function_profile"), dict) and payload["vocal_function_profile"]:
        return True
    report = payload.get("report") or {}
    if isinstance(report, dict) and isinstance(report.get("vocal_function_profile"), dict):
        return bool(report["vocal_function_profile"])
    return any(
        k in payload
        for k in (
            "effort_assessment",
            "timbre_profile",
            "dimensions",
            "vocal_type_profile",
        )
    )


def cache_paths(cache_root: Path, sha256: str) -> dict[str, Path]:
    d = cache_root / sha256
    return {
        "dir": d,
        "analysis": d / "analysis.json",
        "meta": d / "meta.json",
        "error": d / "error.json",
    }


def load_cached_analysis(
    cache_root: Path,
    sha256: str,
    *,
    analysis_version_key: str = "FUNCTIONAL",
) -> Optional[dict[str, Any]]:
    paths = cache_paths(cache_root, sha256)
    if not paths["analysis"].exists():
        return None
    try:
        data = json.loads(paths["analysis"].read_text(encoding="utf-8"))
    except Exception:
        return None
    if not _has_vf(data):
        return None
    if paths["meta"].exists():
        try:
            meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
            if meta.get("analysis_version_key") and meta["analysis_version_key"] != analysis_version_key:
                return None
        except Exception:
            pass
    return data


def try_load_hint(hint: Optional[str]) -> Optional[dict[str, Any]]:
    if not hint:
        return None
    p = Path(hint)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if _has_vf(data) else None


def save_analysis_cache(
    cache_root: Path,
    sha256: str,
    analysis: dict[str, Any],
    *,
    source: str,
    analysis_version_key: str = "FUNCTIONAL",
) -> Path:
    paths = cache_paths(cache_root, sha256)
    paths["dir"].mkdir(parents=True, exist_ok=True)
    paths["analysis"].write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["meta"].write_text(
        json.dumps(
            {
                "sha256": sha256,
                "source": source,
                "analysis_version_key": analysis_version_key,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return paths["analysis"]


def run_production_analysis(
    audio_path: str | Path,
    *,
    audit_runtime: Path,
    recording_id: str,
) -> dict[str, Any]:
    """Call production analyze_audio once into isolated .audit_runtime."""
    from audio_analyzer.pipeline import analyze_audio

    out_dir = audit_runtime / recording_id
    out_dir.mkdir(parents=True, exist_ok=True)
    return analyze_audio(
        str(audio_path),
        output_dir=str(out_dir),
        recording_id=recording_id,
        analysis_mode="FUNCTIONAL",
        input_mode="VOCAL_ONLY",
        separate=False,
        generate_visuals=False,
        build_preview=False,
        include_feedback=False,
    )


def get_or_analyze(
    asset: AudioAsset,
    *,
    cache_root: Path,
    audit_runtime: Path,
    force_reanalyze: bool = False,
) -> tuple[Optional[dict[str, Any]], dict[str, Any]]:
    """Return (analysis, meta). analysis is None on failure."""
    meta: dict[str, Any] = {
        "audio_id": asset.audio_id,
        "sha256": asset.sha256,
        "path": asset.path,
        "cache_hit": False,
        "hint_hit": False,
        "analyzed": False,
        "error": None,
    }
    if not force_reanalyze:
        cached = load_cached_analysis(cache_root, asset.sha256)
        if cached is not None:
            meta["cache_hit"] = True
            return cached, meta
        hinted = try_load_hint(asset.analysis_json_hint)
        if hinted is not None:
            save_analysis_cache(
                cache_root,
                asset.sha256,
                hinted,
                source=f"hint:{asset.analysis_json_hint}",
            )
            meta["hint_hit"] = True
            return hinted, meta

    try:
        analysis = run_production_analysis(
            asset.path,
            audit_runtime=audit_runtime,
            recording_id=asset.audio_id,
        )
        save_analysis_cache(
            cache_root,
            asset.sha256,
            analysis,
            source="analyze_audio",
        )
        meta["analyzed"] = True
        return analysis, meta
    except Exception as e:
        err = {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "path": asset.path,
            "sha256": asset.sha256,
        }
        paths = cache_paths(cache_root, asset.sha256)
        paths["dir"].mkdir(parents=True, exist_ok=True)
        paths["error"].write_text(json.dumps(err, ensure_ascii=False, indent=2), encoding="utf-8")
        meta["error"] = str(e)
        return None, meta
