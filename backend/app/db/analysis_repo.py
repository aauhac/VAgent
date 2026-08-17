"""Analysis row helpers — DB is production metadata SoT when DATABASE_URL is set."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import database_url, is_production
from .models import Analysis, DiagnosticSession, Entitlement, User
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
                (User.external_provider == "TOSS") & (User.external_subject == subject),
                (User.external_provider == "DEV") & (User.external_subject == subject),
                (User.external_provider == "TOSS_ANONYMOUS") & (User.external_subject == subject),
            )
        )
    )


def _persisted_source_id(row: DiagnosticSession) -> str | None:
    if row.source_analysis_id:
        return str(row.source_analysis_id)
    rationale = row.plan_rationale if isinstance(row.plan_rationale, dict) else {}
    ext = rationale.get("_session_ext") if isinstance(rationale.get("_session_ext"), dict) else {}
    raw = ext.get("persisted_source_analysis_id")
    return str(raw).strip() if raw else None


def _vocal_type_label(summary: dict[str, Any] | None) -> str | None:
    if not isinstance(summary, dict):
        return None
    raw = summary.get("vocal_type") or summary.get("vocal_type_teaser")
    if isinstance(raw, dict):
        name = raw.get("display_name")
        return str(name).strip() if name else None
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _serialize_diag_session(row: DiagnosticSession) -> dict[str, Any]:
    return {
        "session_id": row.id,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def _pick_primary_diagnostic(sessions: list[dict[str, Any]]) -> str | None:
    if not sessions:
        return None
    completed = [s for s in sessions if str(s.get("status") or "").upper() == "COMPLETED"]
    pool = completed or sessions
    pool = sorted(
        pool,
        key=lambda s: str(s.get("completed_at") or s.get("created_at") or ""),
        reverse=True,
    )
    return pool[0].get("session_id")


def list_analyses_for_subject(
    subject: str, *, limit: int = 20, offset: int = 0
) -> dict[str, Any]:
    """History rows from PostgreSQL — production SoT. Joins diagnostic_sessions.source_analysis_id."""
    require_db_for_prod_metadata()
    empty = {
        "items": [],
        "unlinked_diagnostics": [],
        "has_more": False,
        "offset": offset,
        "limit": limit,
        "total_analyses": 0,
    }
    if not db_enabled():
        return empty

    cap = max(1, min(limit, 200))
    skip = max(0, offset)

    with session_scope() as session:
        user = get_user_by_subject(session, subject)
        if not user:
            return empty

        owned = session.scalars(
            select(Analysis)
            .where(Analysis.user_id == user.id, Analysis.deleted_at.is_(None))
            .order_by(Analysis.created_at.desc())
        ).all()
        owned_ids = {row.id for row in owned}

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
        diag_entitled_analyses = {
            e.resource_id
            for e in session.scalars(
                select(Entitlement).where(
                    Entitlement.user_id == user.id,
                    Entitlement.resource_type == "ANALYSIS",
                    Entitlement.entitlement_type == "DIAGNOSTIC",
                    Entitlement.status == "ACTIVE",
                )
            ).all()
        }

        diag_rows = session.scalars(
            select(DiagnosticSession)
            .where(DiagnosticSession.user_id == user.id)
            .order_by(DiagnosticSession.created_at.desc())
        ).all()

        linked: dict[str, list[DiagnosticSession]] = {aid: [] for aid in owned_ids}
        unlinked: list[DiagnosticSession] = []
        seen_ids: set[str] = set()

        for drow in diag_rows:
            explicit = _persisted_source_id(drow)
            if drow.source_analysis_id is None and explicit and explicit in owned_ids:
                # Safe backfill: explicit persisted source, same user, unique analysis id.
                drow.source_analysis_id = explicit
                explicit = drow.source_analysis_id
            if explicit and explicit in owned_ids:
                linked.setdefault(explicit, []).append(drow)
                seen_ids.add(drow.id)
            elif explicit:
                source = session.get(Analysis, explicit)
                if source is not None and source.user_id != user.id:
                    # Cross-user: keep session unlinked; never attach to the other analysis.
                    unlinked.append(drow)
                else:
                    unlinked.append(drow)
            else:
                unlinked.append(drow)

        # public_summary.diagnostic_session_id is an explicit persisted pointer.
        for row in owned:
            summary = row.public_summary if isinstance(row.public_summary, dict) else {}
            pointer = summary.get("diagnostic_session_id")
            if not pointer:
                continue
            sid = str(pointer)
            if any(s.id == sid for s in linked.get(row.id, [])):
                continue
            pointed = session.get(DiagnosticSession, sid)
            if pointed is None or pointed.user_id != user.id:
                continue
            linked.setdefault(row.id, []).append(pointed)
            seen_ids.add(pointed.id)
            unlinked = [u for u in unlinked if u.id != pointed.id]

        page = owned[skip : skip + cap]
        out: list[dict[str, Any]] = []
        for row in page:
            summary = row.public_summary if isinstance(row.public_summary, dict) else {}
            sessions = [_serialize_diag_session(s) for s in linked.get(row.id, [])]
            primary = _pick_primary_diagnostic(sessions)
            status = row.status or "failed"
            if row.error_code == "INTERRUPTED_RESTART":
                status = "failed"
            out.append(
                {
                    "analysis_id": row.id,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "filename": row.original_filename,
                    "status": status,
                    "vocal_type": _vocal_type_label(summary),
                    "song_detail_unlocked": row.id in song_ids,
                    "diagnostic_unlocked": bool(sessions) or row.id in diag_entitled_analyses,
                    "diagnostic_session_id": primary,
                    "diagnostic_sessions": sessions,
                    "artifact_missing": bool(
                        status == "completed"
                        and not (row.result_storage_key or row.preview_storage_key)
                    ),
                    "error_code": row.error_code,
                }
            )

        unlinked_out = [
            _serialize_diag_session(s)
            for s in unlinked
            if s.id not in seen_ids
        ]
        return {
            "items": out,
            "unlinked_diagnostics": unlinked_out,
            "has_more": skip + cap < len(owned),
            "offset": skip,
            "limit": cap,
            "total_analyses": len(owned),
        }


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
