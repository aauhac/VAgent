"""Analysis row helpers — DB is production metadata SoT when DATABASE_URL is set."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import database_url, is_production
from .models import Analysis, Entitlement, User
from .session import session_scope


def db_enabled() -> bool:
    return bool(database_url())


def require_db_for_prod_metadata() -> None:
    if is_production() and not db_enabled():
        raise RuntimeError("DATABASE_URL required for production metadata")


def update_analysis_status(
    analysis_id: str,
    *,
    status: str,
    stage: str | None = None,
    progress: int | None = None,
    error_message: str | None = None,
    error_code: str | None = None,
    public_summary: dict | None = None,
    preview_storage_key: str | None = None,
    result_storage_key: str | None = None,
) -> None:
    if not db_enabled():
        return
    try:
        with session_scope() as session:
            row = session.get(Analysis, analysis_id)
            if not row or row.deleted_at is not None:
                return
            row.status = status
            if stage is not None:
                row.stage = stage
            if progress is not None:
                row.progress = progress
            if error_message is not None:
                row.error_message = error_message
            if error_code is not None:
                row.error_code = error_code
            if public_summary is not None:
                # merge
                merged = dict(row.public_summary or {})
                merged.update(public_summary)
                row.public_summary = merged
            if preview_storage_key is not None:
                row.preview_storage_key = preview_storage_key
            if result_storage_key is not None:
                row.result_storage_key = result_storage_key
            row.updated_at = datetime.now(timezone.utc)
            if status == "completed":
                row.completed_at = row.completed_at or datetime.now(timezone.utc)
            if status == "failed":
                if error_code:
                    row.error_code = error_code
                elif error_message and "INTERRUPTED" in str(error_message):
                    row.error_code = "INTERRUPTED_RESTART"
    except Exception:
        if is_production():
            raise


def soft_delete_analysis(analysis_id: str) -> bool:
    if not db_enabled():
        return False
    with session_scope() as session:
        row = session.get(Analysis, analysis_id)
        if not row:
            return False
        row.deleted_at = datetime.now(timezone.utc)
        row.status = "deleted"
        row.updated_at = datetime.now(timezone.utc)
        return True


def get_user_by_subject(session: Session, subject: str) -> Optional[User]:
    return session.scalar(
        select(User).where(
            or_(
                (User.external_provider == "DEV") & (User.external_subject == subject),
                (User.external_provider == "TOSS_ANONYMOUS") & (User.external_subject == subject),
            )
        )
    )


def list_analyses_for_subject(subject: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """History rows from PostgreSQL — production SoT."""
    require_db_for_prod_metadata()
    if not db_enabled():
        return []

    with session_scope() as session:
        user = get_user_by_subject(session, subject)
        if not user:
            return []

        rows = session.scalars(
            select(Analysis)
            .where(Analysis.user_id == user.id, Analysis.deleted_at.is_(None))
            .order_by(Analysis.created_at.desc())
            .limit(max(1, min(limit, 200)))
        ).all()

        song_ids = {
            e.resource_id
            for e in session.scalars(
                select(Entitlement).where(
                    Entitlement.user_id == user.id,
                    Entitlement.resource_type == "ANALYSIS",
                    Entitlement.entitlement_type == "SONG_DETAIL",
                    Entitlement.status == "ACTIVE",
                )
            ).all()
        }
        diag_by_analysis: dict[str, str] = {}
        for e in session.scalars(
            select(Entitlement).where(
                Entitlement.user_id == user.id,
                Entitlement.resource_type == "DIAGNOSTIC_SESSION",
                Entitlement.entitlement_type == "DIAGNOSTIC",
                Entitlement.status == "ACTIVE",
            )
        ).all():
            # source analysis may be encoded in product_id field unused — check public_summary on analyses
            pass

        out: list[dict[str, Any]] = []
        for row in rows:
            summary = row.public_summary if isinstance(row.public_summary, dict) else {}
            diag_sid = summary.get("diagnostic_session_id")
            if diag_sid:
                diag_by_analysis[row.id] = str(diag_sid)

            vt = None
            raw_vt = summary.get("vocal_type") or summary.get("vocal_type_teaser")
            if isinstance(raw_vt, dict):
                vt = raw_vt.get("display_name")
            elif isinstance(raw_vt, str):
                vt = raw_vt

            status = row.status or "failed"
            if row.error_code == "INTERRUPTED_RESTART":
                status = "failed"

            out.append(
                {
                    "analysis_id": row.id,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "filename": row.original_filename,
                    "status": status,
                    "vocal_type": vt,
                    "song_detail_unlocked": row.id in song_ids,
                    "diagnostic_unlocked": bool(diag_sid),
                    "diagnostic_session_id": diag_sid,
                    "artifact_missing": bool(
                        status == "completed" and not (row.result_storage_key or row.preview_storage_key)
                    ),
                    "error_code": row.error_code,
                }
            )
        return out


def set_analysis_diagnostic_link(analysis_id: str, session_id: str) -> None:
    if not db_enabled():
        return
    with session_scope() as session:
        row = session.get(Analysis, analysis_id)
        if not row:
            return
        summary = dict(row.public_summary or {})
        summary["diagnostic_session_id"] = session_id
        row.public_summary = summary
        row.updated_at = datetime.now(timezone.utc)


def resolve_owner_subject(analysis_id: str) -> Optional[str]:
    if not db_enabled():
        return None
    with session_scope() as session:
        row = session.get(Analysis, analysis_id)
        if not row or row.deleted_at is not None:
            return None
        user = session.get(User, row.user_id)
        return user.external_subject if user else None


def analysis_owned_by(analysis_id: str, subject: str) -> Optional[bool]:
    """
    Returns True/False if DB has ownership info, None if DB disabled / row missing.
    """
    if not db_enabled():
        return None
    owner = resolve_owner_subject(analysis_id)
    if owner is None:
        # Row may not exist yet (legacy) — signal unknown
        with session_scope() as session:
            row = session.get(Analysis, analysis_id)
            if row is None:
                return None
            if row.deleted_at is not None:
                return False
        return False
    return owner == subject
