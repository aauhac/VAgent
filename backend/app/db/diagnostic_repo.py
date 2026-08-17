"""Diagnostic session/attempt persistence — PostgreSQL SoT when DATABASE_URL set."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select

from ..config import database_url, is_production
from .models import Analysis, DiagnosticSession, DiagnosticTaskAttempt, User
from .session import session_scope
from .users import get_or_create_user


def db_enabled() -> bool:
    return bool(database_url())


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def upsert_session_from_dict(session_dict: dict[str, Any], *, provider: str = "DEV") -> None:
    if not db_enabled():
        # Production without DATABASE_URL fails at startup; file-only path remains for
        # isolated unit tests that set VAGENT_ENV=production to exercise mock-pay gates.
        return

    subject = str(session_dict.get("user_id") or "anon")
    sid = session_dict["session_id"]
    with session_scope() as session:
        user = get_or_create_user(session, provider=provider, subject=subject)
        src = session_dict.get("source_analysis_id")
        explicit_src = str(src).strip() if src else None
        if explicit_src and not session.get(Analysis, explicit_src):
            # FK cannot point at a missing analysis row. Keep the explicit id
            # in plan_rationale so history can restore it later if the analysis appears.
            src = None
        else:
            src = explicit_src

        row = session.get(DiagnosticSession, sid)
        now = datetime.now(timezone.utc)
        rationale = dict(session_dict.get("plan_rationale") or {})
        prev_ext = {}
        if isinstance(rationale.get("_session_ext"), dict):
            prev_ext = dict(rationale.get("_session_ext") or {})
        if row and isinstance(row.plan_rationale, dict) and isinstance(row.plan_rationale.get("_session_ext"), dict):
            prev_ext = {**dict(row.plan_rationale.get("_session_ext") or {}), **prev_ext}
        persisted_src = explicit_src or prev_ext.get("persisted_source_analysis_id")
        rationale["_session_ext"] = {
            "diagnostic_mode": session_dict.get("diagnostic_mode"),
            "diagnostic_status": session_dict.get("diagnostic_status"),
            "core_tasks": session_dict.get("core_tasks"),
            "adaptive_tasks": session_dict.get("adaptive_tasks"),
            "planned_task_count": session_dict.get("planned_task_count"),
            "provisional_task_count": session_dict.get("provisional_task_count"),
            "safety_flag_pain": session_dict.get("safety_flag_pain"),
            "persisted_source_analysis_id": persisted_src,
        }
        payload = {
            "user_id": user.id,
            "source_analysis_id": src,
            "status": session_dict.get("status") or "CREATED",
            "planner_version": session_dict.get("planner_version"),
            "protocol_version": session_dict.get("protocol_version"),
            "report_version": (session_dict.get("final_diagnostic_profile") or {}).get("report_version")
            if isinstance(session_dict.get("final_diagnostic_profile"), dict)
            else session_dict.get("report_version"),
            "selected_tasks": session_dict.get("selected_tasks"),
            "unresolved_dimensions": session_dict.get("unresolved_dimensions"),
            "diagnostic_offer": session_dict.get("diagnostic_offer"),
            "tasks_state": session_dict.get("tasks"),
            "task_results": session_dict.get("task_results"),
            "safety_answers": session_dict.get("safety_answers"),
            "safety_flags": session_dict.get("safety_flags"),
            "user_concerns": session_dict.get("user_concerns"),
            "plan_rationale": rationale,
            "final_diagnostic_profile": session_dict.get("final_diagnostic_profile"),
            "current_task_index": session_dict.get("current_task_index"),
            "entitlement_id": session_dict.get("entitlement_id"),
            "product_id": session_dict.get("product_id"),
            "report_storage_key": session_dict.get("report_storage_key"),
            "error_message": session_dict.get("error"),
            "updated_at": now,
            "completed_at": _parse_dt(session_dict.get("completed_at")),
        }
        if row is None:
            row = DiagnosticSession(
                id=sid,
                created_at=_parse_dt(session_dict.get("created_at")) or now,
                **payload,
            )
            session.add(row)
        else:
            for k, v in payload.items():
                setattr(row, k, v)


def load_session_dict(session_id: str) -> Optional[dict[str, Any]]:
    if not db_enabled():
        return None
    with session_scope() as session:
        row = session.get(DiagnosticSession, session_id)
        if not row:
            return None
        user = session.get(User, row.user_id)
        subject = user.external_subject if user else "anon"
        attempts = session.scalars(
            select(DiagnosticTaskAttempt)
            .where(DiagnosticTaskAttempt.session_id == session_id)
            .order_by(DiagnosticTaskAttempt.attempt_number.asc())
        ).all()
        # Prefer tasks_state from row; enrich attempt audio keys if needed
        tasks = dict(row.tasks_state or {})
        rationale = dict(row.plan_rationale or {})
        ext = dict(rationale.get("_session_ext") or {})
        return {
            "session_id": row.id,
            "user_id": subject,
            "persisted_source_analysis_id": ext.get("persisted_source_analysis_id"),
            "source_analysis_id": row.source_analysis_id or ext.get("persisted_source_analysis_id"),
            "analysis_mode": "diagnostic",
            "protocol_version": row.protocol_version,
            "planner_version": row.planner_version,
            "status": row.status,
            "entitlement_id": row.entitlement_id,
            "product_id": row.product_id,
            "safety_flags": row.safety_flags or [],
            "safety_answers": row.safety_answers or {},
            "user_concerns": row.user_concerns or [],
            "diagnostic_mode": ext.get("diagnostic_mode"),
            "diagnostic_status": ext.get("diagnostic_status") or "NORMAL",
            "core_tasks": list(ext.get("core_tasks") or []),
            "adaptive_tasks": list(ext.get("adaptive_tasks") or []),
            "planned_task_count": ext.get("planned_task_count"),
            "provisional_task_count": ext.get("provisional_task_count"),
            "safety_flag_pain": bool(ext.get("safety_flag_pain")),
            "unresolved_dimensions": row.unresolved_dimensions or [],
            "selected_tasks": list(row.selected_tasks or []),
            "current_task_index": row.current_task_index or 0,
            "diagnostic_offer": row.diagnostic_offer,
            "plan_rationale": rationale,
            "tasks": tasks,
            "task_results": list(row.task_results or []),
            "final_diagnostic_profile": row.final_diagnostic_profile,
            "report_storage_key": row.report_storage_key,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "error": row.error_message,
            "_db_attempt_count": len(attempts),
        }


def insert_task_attempt(
    *,
    session_id: str,
    task_id: str,
    attempt_number: int,
    audio_storage_key: str | None,
    quality_status: str | None,
    passed: bool | None,
    dimension_evidence: dict | None = None,
) -> None:
    if not db_enabled():
        return
    with session_scope() as session:
        session.add(
            DiagnosticTaskAttempt(
                id=uuid4(),
                session_id=session_id,
                task_id=task_id,
                attempt_number=attempt_number,
                audio_storage_key=audio_storage_key,
                quality_status=quality_status,
                dimension_evidence=dimension_evidence,
                passed=passed,
                created_at=datetime.now(timezone.utc),
            )
        )
