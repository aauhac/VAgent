"""Ownership helpers for analysis resources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ..config import get_environment, get_runtime_dir
from ..jobs.runner import validate_analysis_id


def read_analysis_meta(analysis_id: str, runtime_dir: Path | None = None) -> Optional[dict[str, Any]]:
    if not validate_analysis_id(analysis_id):
        return None
    base = runtime_dir or get_runtime_dir()
    path = base / analysis_id / "analysis_meta.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def can_access_analysis(user_id: str, analysis_id: str, runtime_dir: Path | None = None) -> bool:
    """
    Ownership gate.

    Prefer PostgreSQL ownership when DATABASE_URL is set.
    Else analysis_meta.json; legacy missing meta only for local demo identities.
    """
    uid = (user_id or "").strip() or "anon"

    try:
        from ..db.analysis_repo import analysis_owned_by, db_enabled

        if db_enabled():
            owned = analysis_owned_by(analysis_id, uid)
            if owned is not None:
                return owned
            # DB enabled but row missing: fall through to file meta for legacy import gap
    except Exception:
        if get_environment() == "production":
            return False

    meta = read_analysis_meta(analysis_id, runtime_dir)
    if meta and meta.get("user_id"):
        return str(meta["user_id"]) == uid
    if get_environment() == "production":
        return False
    return uid in ("demo-user", "anon", "dev-user")
