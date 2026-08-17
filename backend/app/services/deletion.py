"""Owner-verified analysis content deletion (files + linked diagnostics).

Payment/purchase rows are not deleted here.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..diagnostic.service import validate_session_id
from ..jobs.runner import validate_analysis_id

logger = logging.getLogger("vagent.deletion")


@dataclass
class DeleteResult:
    ok: bool
    analysis_id: str
    linked_diagnostic_ids: list[str] = field(default_factory=list)
    files_removed: bool = False
    db_updated: bool = False
    error: str | None = None


def _safe_under_root(root: Path, candidate: Path) -> Path | None:
    try:
        root_r = root.resolve()
        resolved = candidate.resolve()
        resolved.relative_to(root_r)
    except (OSError, ValueError):
        return None
    return resolved


def _rmtree_contained(root: Path, target: Path) -> None:
    safe = _safe_under_root(root, target)
    if safe is None:
        raise ValueError("path_outside_runtime")
    if safe == root.resolve():
        raise ValueError("refusing_runtime_root")
    if not safe.exists():
        return
    shutil.rmtree(safe)


def _explicit_source_id(data: dict[str, Any]) -> str | None:
    raw = data.get("source_analysis_id")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    persisted = data.get("persisted_source_analysis_id")
    if persisted is not None and str(persisted).strip():
        return str(persisted).strip()
    rationale = data.get("plan_rationale") if isinstance(data.get("plan_rationale"), dict) else {}
    ext = rationale.get("_session_ext") if isinstance(rationale.get("_session_ext"), dict) else {}
    nested = ext.get("persisted_source_analysis_id")
    if nested is not None and str(nested).strip():
        return str(nested).strip()
    return None


def linked_diagnostic_ids_from_disk(runtime_dir: Path, analysis_id: str) -> set[str]:
    found: set[str] = set()
    root = runtime_dir / "diagnostic_sessions"
    if not root.is_dir():
        return found
    for child in root.iterdir():
        if not child.is_dir() or not validate_session_id(child.name):
            continue
        session_json = child / "session.json"
        if not session_json.is_file():
            continue
        try:
            data = json.loads(session_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            continue
        if not isinstance(data, dict):
            continue
        src = _explicit_source_id(data)
        if src == analysis_id:
            found.add(child.name)
    return found


def linked_diagnostic_ids_from_db(analysis_id: str) -> set[str]:
    from ..config import database_url

    if not database_url():
        return set()
    from sqlalchemy import select

    from ..db.models import DiagnosticSession
    from ..db.session import session_scope

    found: set[str] = set()
    with session_scope() as session:
        rows = session.scalars(select(DiagnosticSession)).all()
        for row in rows:
            src = str(row.source_analysis_id).strip() if row.source_analysis_id else ""
            if not src:
                rationale = row.plan_rationale if isinstance(row.plan_rationale, dict) else {}
                ext = rationale.get("_session_ext") if isinstance(rationale.get("_session_ext"), dict) else {}
                raw = ext.get("persisted_source_analysis_id")
                src = str(raw).strip() if raw else ""
            if src == analysis_id:
                found.add(str(row.id))
    return found


def _purge_diagnostic_db_rows(session_ids: list[str]) -> None:
    from ..config import database_url

    if not database_url() or not session_ids:
        return
    from sqlalchemy import delete as sa_delete

    from ..db.models import DiagnosticSession, DiagnosticTaskAttempt
    from ..db.session import session_scope

    with session_scope() as session:
        session.execute(
            sa_delete(DiagnosticTaskAttempt).where(DiagnosticTaskAttempt.session_id.in_(session_ids))
        )
        session.execute(sa_delete(DiagnosticSession).where(DiagnosticSession.id.in_(session_ids)))


def _soft_delete_analysis_row(analysis_id: str) -> bool:
    from ..config import database_url

    if not database_url():
        return False
    from datetime import datetime, timezone

    from ..db.models import Analysis
    from ..db.session import session_scope

    now = datetime.now(timezone.utc)
    with session_scope() as session:
        row = session.get(Analysis, analysis_id)
        if not row:
            return False
        row.deleted_at = now
        row.audio_deleted_at = now
        row.status = "deleted"
        row.public_summary = None
        row.preview_storage_key = None
        row.audio_storage_key = None
        row.result_storage_key = None
        row.updated_at = now
        return True


def delete_analysis_content(runtime_dir: Path, analysis_id: str) -> DeleteResult:
    """Remove analysis artifacts + explicitly linked diagnostics. Not payment records."""
    if not validate_analysis_id(analysis_id):
        return DeleteResult(ok=False, analysis_id=analysis_id, error="invalid_id")

    root = Path(runtime_dir)
    linked = linked_diagnostic_ids_from_disk(root, analysis_id) | linked_diagnostic_ids_from_db(analysis_id)
    linked_list = sorted(linked)

    analysis_dir = root / analysis_id
    try:
        if _safe_under_root(root, analysis_dir) is None:
            return DeleteResult(ok=False, analysis_id=analysis_id, error="path_outside_runtime")
        _rmtree_contained(root, analysis_dir)
        for sid in linked_list:
            if not validate_session_id(sid):
                continue
            _rmtree_contained(root, root / "diagnostic_sessions" / sid)
    except ValueError as exc:
        logger.info("analysis_delete_path_blocked analysis_id=%s reason=%s", analysis_id, type(exc).__name__)
        return DeleteResult(ok=False, analysis_id=analysis_id, error="path_outside_runtime")
    except OSError as exc:
        logger.info("analysis_delete_fs_failed analysis_id=%s type=%s", analysis_id, type(exc).__name__)
        return DeleteResult(
            ok=False,
            analysis_id=analysis_id,
            linked_diagnostic_ids=linked_list,
            error="filesystem_delete_failed",
        )

    if analysis_dir.exists():
        return DeleteResult(
            ok=False,
            analysis_id=analysis_id,
            linked_diagnostic_ids=linked_list,
            error="filesystem_delete_incomplete",
        )

    try:
        _purge_diagnostic_db_rows(linked_list)
        _soft_delete_analysis_row(analysis_id)
    except Exception:
        logger.exception("analysis_delete_db_failed analysis_id=%s", analysis_id)
        return DeleteResult(
            ok=False,
            analysis_id=analysis_id,
            linked_diagnostic_ids=linked_list,
            files_removed=True,
            error="db_delete_incomplete",
        )

    logger.info(
        "analysis_deleted analysis_id=%s linked_diagnostics=%s",
        analysis_id,
        len(linked_list),
    )
    return DeleteResult(
        ok=True,
        analysis_id=analysis_id,
        linked_diagnostic_ids=linked_list,
        files_removed=True,
        db_updated=True,
    )
