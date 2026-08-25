"""Analysis row helpers — DB is production metadata SoT when DATABASE_URL is set."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, or_, select, update
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
    audio_storage_key: str | None = None,
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
            if audio_storage_key is not None:
                row.audio_storage_key = audio_storage_key
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
    """LEGACY, AMBIGUOUS: first row with this subject under ANY known provider.

    The users unique key is (external_provider, external_subject), so the same string can
    name two different people — a Toss userKey and an anonymous hash live in separate
    namespaces. This helper cannot tell them apart and may return either row.

    Do NOT use in auth, payment, or canonical identity resolution. Use instead:
      - `users.get_user_by_identity(session, provider, subject)` for an exact lookup
      - `identity_links.resolve_canonical_user` / `identity_group_ids` / `same_identity`
        for canonical resolution, which merges rows only when a UserIdentityLink says so

    Kept for legacy call sites that hold a bare subject and only need a single row to
    scope their own data; it can never be the reason two identities are treated as one.
    """
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
    from audio_analyzer.coach_profile.public_presentation import public_vocal_type_label

    raw = summary.get("vocal_type") or summary.get("vocal_type_teaser") or summary.get("vocal_type_profile")
    if isinstance(raw, dict):
        return public_vocal_type_label(
            resolution_state=raw.get("resolution_state") or summary.get("vocal_type_resolution_state"),
            display_name=raw.get("display_name"),
            base_type=raw.get("base_type"),
            type_id=raw.get("type_id"),
            available=raw.get("available"),
        )
    if isinstance(raw, str) and raw.strip():
        return public_vocal_type_label(display_name=raw.strip())
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
    subject: str, *, limit: int = 20, offset: int = 0, provider: str | None = None
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
        from .identity_links import identity_group_ids

        # One canonical identity can span several user rows (canonical hash user, the
        # (TOSS, userKey) user the old migration parked data on, other linked hashes).
        # History unions them instead of moving anything.
        group = identity_group_ids(session, subject, provider)
        if not group:
            return empty

        owned = session.scalars(
            select(Analysis)
            .where(Analysis.user_id.in_(group), Analysis.deleted_at.is_(None))
            .order_by(Analysis.created_at.desc())
        ).all()
        owned_ids = {row.id for row in owned}

        song_ids = {
            e.resource_id
            for e in session.scalars(
                select(Entitlement).where(
                    Entitlement.user_id.in_(group),
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
                    Entitlement.user_id.in_(group),
                    Entitlement.resource_type == "ANALYSIS",
                    Entitlement.entitlement_type == "DIAGNOSTIC",
                    Entitlement.status == "ACTIVE",
                )
            ).all()
        }
        # Sessions the user actually paid for. An unpaid CREATED session is a workspace,
        # not a purchase, and never appears in history as an available product.
        diag_entitled_sessions = {
            e.resource_id
            for e in session.scalars(
                select(Entitlement).where(
                    Entitlement.user_id.in_(group),
                    Entitlement.resource_type == "DIAGNOSTIC_SESSION",
                    Entitlement.entitlement_type == "DIAGNOSTIC",
                    Entitlement.status == "ACTIVE",
                )
            ).all()
        }

        diag_rows = session.scalars(
            select(DiagnosticSession)
            .where(DiagnosticSession.user_id.in_(group))
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
                if source is not None and source.user_id not in group:
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
            if pointed is None or pointed.user_id not in group:
                continue
            linked.setdefault(row.id, []).append(pointed)
            seen_ids.add(pointed.id)
            unlinked = [u for u in unlinked if u.id != pointed.id]

        page = owned[skip : skip + cap]
        out: list[dict[str, Any]] = []
        for row in page:
            summary = row.public_summary if isinstance(row.public_summary, dict) else {}
            analysis_entitled = row.id in diag_entitled_analyses
            all_sessions = linked.get(row.id, [])
            # Show a session only when it is paid for, either directly or via an
            # analysis-level DIAGNOSTIC entitlement covering this analysis.
            visible_sessions = [
                s
                for s in all_sessions
                if analysis_entitled or str(s.id) in diag_entitled_sessions
            ]
            sessions = [_serialize_diag_session(s) for s in visible_sessions]
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
                    "diagnostic_unlocked": analysis_entitled or bool(sessions),
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
            if s.id not in seen_ids and str(s.id) in diag_entitled_sessions
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

    Compares canonical identities, so an analysis parked on the (TOSS, userKey) user by the
    old migration is still the caller's own once a verified login has linked them. A bare
    anonymous hash with no link resolves to itself and cannot reach a linked user's data.
    """
    if not db_enabled():
        return None
    owner = resolve_owner_subject(analysis_id)
    if owner is not None and owner != subject:
        with session_scope() as session:
            from .identity_links import same_identity

            if same_identity(session, owner, subject):
                return True
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


def _analysis_snapshot(row: Analysis | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "status": row.status,
        "stage": row.stage,
        "progress": row.progress,
        "analysis_mode": row.analysis_mode,
        "input_mode": row.input_mode,
        "separate": row.separate,
        "audio_storage_key": row.audio_storage_key,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "deleted_at": row.deleted_at,
        "worker_claim_token": row.worker_claim_token,
        "worker_lease_expires_at": row.worker_lease_expires_at,
        "worker_attempt_count": row.worker_attempt_count or 0,
    }


def get_analysis_snapshot(analysis_id: str) -> dict[str, Any] | None:
    if not db_enabled():
        return None
    with session_scope() as session:
        return _analysis_snapshot(session.get(Analysis, analysis_id))


def claim_analysis_job(
    analysis_id: str,
    *,
    claim_token: str,
    lease_seconds: int,
) -> dict[str, Any] | None:
    """Atomic claim: queued, or analyzing with an expired lease. One winner."""
    if not db_enabled():
        return None
    now = datetime.now(timezone.utc)
    lease = now + timedelta(seconds=max(1, int(lease_seconds)))
    stmt = (
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            Analysis.deleted_at.is_(None),
            or_(
                Analysis.status == "queued",
                and_(
                    Analysis.status == "analyzing",
                    or_(
                        Analysis.worker_lease_expires_at.is_(None),
                        Analysis.worker_lease_expires_at < now,
                    ),
                ),
            ),
        )
        .values(
            status="analyzing",
            stage="start",
            progress=1,
            worker_claim_token=claim_token,
            worker_lease_expires_at=lease,
            worker_attempt_count=Analysis.worker_attempt_count + 1,
            updated_at=now,
        )
    )
    with session_scope() as session:
        result = session.execute(stmt)
        if int(result.rowcount or 0) != 1:
            return None
        return _analysis_snapshot(session.get(Analysis, analysis_id))


def extend_worker_lease(
    analysis_id: str,
    *,
    claim_token: str,
    lease_seconds: int,
) -> bool:
    if not db_enabled():
        return False
    now = datetime.now(timezone.utc)
    lease = now + timedelta(seconds=max(1, int(lease_seconds)))
    stmt = (
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            Analysis.worker_claim_token == claim_token,
            Analysis.deleted_at.is_(None),
        )
        .values(worker_lease_expires_at=lease, updated_at=now)
    )
    with session_scope() as session:
        result = session.execute(stmt)
        return int(result.rowcount or 0) == 1


def release_claim_to_queued(analysis_id: str, *, claim_token: str) -> None:
    """Retryable failure: allow another receive/claim. Does not mark failed."""
    if not db_enabled():
        return
    now = datetime.now(timezone.utc)
    stmt = (
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            Analysis.worker_claim_token == claim_token,
            Analysis.status == "analyzing",
            Analysis.deleted_at.is_(None),
        )
        .values(
            status="queued",
            stage="queued",
            worker_claim_token=None,
            worker_lease_expires_at=None,
            updated_at=now,
        )
    )
    with session_scope() as session:
        session.execute(stmt)
