"""Server-side analysis history — DB SoT when DATABASE_URL set; runtime only in non-prod fallback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ..config import database_url, get_runtime_dir, is_production
from ..diagnostic.service import validate_session_id
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


def _empty_history(limit: int, offset: int) -> dict[str, Any]:
    return {
        "items": [],
        "unlinked_diagnostics": [],
        "has_more": False,
        "offset": offset,
        "limit": limit,
        "total_analyses": 0,
    }


def list_user_history(
    user_id: str,
    *,
    limit: int = 20,
    offset: int = 0,
    runtime_dir: Path | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """
    Production / DATABASE_URL: PostgreSQL only (no runtime history fallback).
    Development without DB: runtime directory scan.
    """
    if database_url():
        from ..db.analysis_repo import list_analyses_for_subject

        return list_analyses_for_subject(
            user_id, limit=limit, offset=offset, provider=provider
        )

    if is_production():
        raise RuntimeError("production history requires DATABASE_URL")

    return _list_from_runtime(
        user_id, limit=limit, offset=offset, runtime_dir=runtime_dir, provider=provider
    )


def _vocal_type_from_public(pub: dict[str, Any] | None) -> str | None:
    if not isinstance(pub, dict):
        return None
    from audio_analyzer.coach_profile.public_presentation import public_vocal_type_label

    vt = pub.get("vocal_type_teaser") or pub.get("vocal_type_profile") or pub.get("vocal_type")
    if isinstance(vt, dict):
        return public_vocal_type_label(
            resolution_state=vt.get("resolution_state") or pub.get("vocal_type_resolution_state"),
            display_name=vt.get("display_name"),
            base_type=vt.get("base_type"),
            type_id=vt.get("type_id"),
            available=vt.get("available"),
        )
    if isinstance(vt, str) and vt.strip():
        return public_vocal_type_label(display_name=vt.strip())
    return None


def _serialize_file_session(sid: str, blob: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": sid,
        "status": blob.get("status"),
        "created_at": blob.get("created_at"),
        "completed_at": blob.get("completed_at"),
    }


def _list_from_runtime(
    user_id: str,
    *,
    limit: int = 20,
    offset: int = 0,
    runtime_dir: Path | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    base = runtime_dir or get_runtime_dir()
    ents = get_entitlement_provider(base)
    items: list[dict[str, Any]] = []
    cap = max(1, min(limit, 200))
    skip = max(0, offset)

    if not base.exists():
        return _empty_history(cap, skip)

    analysis_ids: list[str] = []
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
        analysis_ids.append(analysis_id)

    linked: dict[str, list[dict[str, Any]]] = {aid: [] for aid in analysis_ids}
    unlinked: list[dict[str, Any]] = []
    sess_root = base / "diagnostic_sessions"
    if sess_root.exists():
        for child in sess_root.iterdir():
            if not child.is_dir():
                continue
            sid = child.name
            if not validate_session_id(sid):
                continue
            blob = _read_json(child / "session.json") or {}
            owner = blob.get("user_id")
            if owner and owner != user_id:
                continue
            if not owner and user_id not in ("demo-user", "anon", "dev-user"):
                continue
            src = blob.get("source_analysis_id")
            rec = _serialize_file_session(sid, blob)
            if src and str(src) in linked:
                linked[str(src)].append(rec)
            else:
                # Unlinked sessions have no analysis to inherit an entitlement from, so
                # they must carry their own or stay hidden.
                try:
                    paid = ents.has_session_unlock(user_id, sid, provider=provider)
                except Exception:
                    paid = False
                if paid:
                    unlinked.append(rec)

    for analysis_id in analysis_ids:
        child = base / analysis_id
        meta = _read_json(_meta_path(base, analysis_id)) or {}
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
            access = ents.analysis_access(user_id, analysis_id, provider=provider)
        except Exception:
            access = {
                "song_detail_unlocked": False,
                "diagnostic_unlocked": False,
                "diagnostic_session_id": None,
            }
        pointer = access.get("diagnostic_session_id")
        unlocked = bool(access.get("diagnostic_unlocked"))
        # Unpaid sessions are workspaces, not products: hide them from history entirely.
        sessions = list(linked.get(analysis_id) or []) if unlocked else []
        if pointer and not any(s.get("session_id") == pointer for s in sessions):
            sessions.append(
                {
                    "session_id": pointer,
                    "status": "COMPLETED",
                    "created_at": None,
                    "completed_at": None,
                }
            )
            unlinked = [u for u in unlinked if u.get("session_id") != pointer]
        sessions.sort(key=lambda s: str(s.get("completed_at") or s.get("created_at") or ""), reverse=True)
        primary = None
        completed = [s for s in sessions if str(s.get("status") or "").upper() == "COMPLETED"]
        if completed:
            primary = completed[0].get("session_id")
        elif sessions:
            primary = sessions[0].get("session_id")

        items.append(
            {
                "analysis_id": analysis_id,
                "created_at": meta.get("created_at") or status_doc.get("updated_at"),
                "filename": meta.get("original_filename"),
                "status": status,
                "vocal_type": _vocal_type_from_public(pub),
                "song_detail_unlocked": bool(access.get("song_detail_unlocked")),
                "diagnostic_unlocked": unlocked,
                "diagnostic_session_id": primary,
                "diagnostic_sessions": sessions,
                "error_code": error_code,
                "artifact_missing": bool(
                    status == "completed" and not pub and not (child / "analysis.json").exists()
                ),
            }
        )

    def _sort_key(row: dict[str, Any]) -> str:
        return str(row.get("created_at") or row.get("analysis_id") or "")

    items.sort(key=_sort_key, reverse=True)
    page = items[skip : skip + cap]
    return {
        "items": page,
        "unlinked_diagnostics": unlinked,
        "has_more": skip + cap < len(items),
        "offset": skip,
        "limit": cap,
        "total_analyses": len(items),
    }
