"""Server-side analysis history — DB SoT when DATABASE_URL set; runtime only in non-prod fallback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ..config import database_url, get_runtime_dir, is_production
from ..entitlements import get_entitlement_provider
from ..jobs.runner import validate_analysis_id


def _read_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _meta_path(runtime_dir: Path, analysis_id: str) -> Path:
    return runtime_dir / analysis_id / "analysis_meta.json"


def write_analysis_meta(
    analysis_id: str,
    *,
    user_id: str,
    filename: str | None = None,
    analysis_mode: str | None = None,
    input_mode: str | None = None,
    separate: bool | None = None,
    runtime_dir: Path | None = None,
) -> None:
    if not validate_analysis_id(analysis_id):
        return
    base = runtime_dir or get_runtime_dir()
    path = _meta_path(base, analysis_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_json(path) or {}
    payload = {
        **existing,
        "analysis_id": analysis_id,
        "user_id": user_id,
        "original_filename": filename or existing.get("original_filename"),
        "analysis_mode": analysis_mode or existing.get("analysis_mode"),
        "input_mode": input_mode or existing.get("input_mode"),
        "separate": separate if separate is not None else existing.get("separate"),
    }
    if "created_at" not in payload:
        from datetime import datetime, timezone

        payload["created_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def list_user_history(
    user_id: str,
    *,
    limit: int = 50,
    runtime_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Production / DATABASE_URL: PostgreSQL only (no runtime history fallback).
    Development without DB: runtime directory scan.
    """
    if database_url():
        from ..db.analysis_repo import list_analyses_for_subject

        return list_analyses_for_subject(user_id, limit=limit)

    if is_production():
        raise RuntimeError("production history requires DATABASE_URL")

    return _list_from_runtime(user_id, limit=limit, runtime_dir=runtime_dir)


def _list_from_runtime(
    user_id: str,
    *,
    limit: int = 50,
    runtime_dir: Path | None = None,
) -> list[dict[str, Any]]:
    base = runtime_dir or get_runtime_dir()
    ents = get_entitlement_provider(base)
    items: list[dict[str, Any]] = []

    if not base.exists():
        return []

    for child in base.iterdir():
        if not child.is_dir():
            continue
        analysis_id = child.name
        if not validate_analysis_id(analysis_id):
            continue
        meta = _read_json(_meta_path(base, analysis_id)) or {}
        owner = meta.get("user_id")
        if owner and owner != user_id:
            continue
        if not owner and user_id not in ("demo-user", "anon", "dev-user"):
            continue

        status_doc = _read_json(child / "job_status.json") or {}
        pub = _read_json(child / "public_result.json") or {}
        status = status_doc.get("status") or ("completed" if pub else None)
        if not status:
            continue
        error_code = None
        if str(status).lower() in ("queued", "analyzing"):
            if not (child / "public_result.json").exists():
                status = "failed"
                error_code = "INTERRUPTED_RESTART"
        if status_doc.get("error") == "INTERRUPTED_RESTART" or status_doc.get("stage") == "interrupted_restart":
            status = "failed"
            error_code = "INTERRUPTED_RESTART"

        try:
            access = ents.analysis_access(user_id, analysis_id)
        except Exception:
            access = {
                "song_detail_unlocked": False,
                "diagnostic_unlocked": False,
                "diagnostic_session_id": None,
            }
        vt = (pub.get("vocal_type_teaser") or pub.get("vocal_type_profile") or {}) if pub else {}
        items.append(
            {
                "analysis_id": analysis_id,
                "created_at": meta.get("created_at") or status_doc.get("updated_at"),
                "filename": meta.get("original_filename"),
                "status": status,
                "vocal_type": vt.get("display_name") if isinstance(vt, dict) else None,
                "song_detail_unlocked": bool(access.get("song_detail_unlocked")),
                "diagnostic_unlocked": bool(access.get("diagnostic_unlocked")),
                "diagnostic_session_id": access.get("diagnostic_session_id"),
                "error_code": error_code,
                "artifact_missing": bool(status == "completed" and not pub and not (child / "analysis.json").exists()),
            }
        )

    def _sort_key(row: dict[str, Any]) -> str:
        return str(row.get("created_at") or row.get("analysis_id") or "")

    items.sort(key=_sort_key, reverse=True)
    return items[: max(1, min(limit, 200))]
