"""Analysis-complete notification opt-in and best-effort send."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import get_runtime_dir, is_production
from ..db.session import session_scope
from ..identity import ResolvedIdentity
from ..payments.toss_clients import TossApiError, get_messenger_client

logger = logging.getLogger("vagent.notifications")

KIND_ANON = "ANON"
KIND_TOSS_USER = "TOSS_USER"
STATUS_REQUESTED = "REQUESTED"
STATUS_SENT = "SENT"
STATUS_FAILED = "FAILED"

_LOCK = threading.Lock()


def analysis_complete_template_set_code() -> str:
    return (os.environ.get("TOSS_ANALYSIS_COMPLETE_TEMPLATE_SET_CODE") or "").strip()


def messenger_recipient_headers(kind: str, key: str) -> dict[str, str]:
    token = (key or "").strip()
    if not token:
        raise ValueError("RECIPIENT_KEY_MISSING")
    if kind == KIND_ANON:
        return {"x-anon-key": token}
    if kind == KIND_TOSS_USER:
        return {"x-user-key": token}
    raise ValueError("INVALID_RECIPIENT_KIND")


def recipient_from_identity(identity: ResolvedIdentity) -> tuple[str, str]:
    if identity.authenticated and identity.toss_user_key:
        return KIND_TOSS_USER, str(identity.toss_user_key)
    return KIND_ANON, str(identity.subject)


def _file_path(analysis_id: str, runtime_dir: Path | None = None) -> Path:
    base = runtime_dir or get_runtime_dir()
    return base / analysis_id / "completion_notification.json"


def _db_enabled() -> bool:
    from ..db.analysis_repo import db_enabled

    return db_enabled()


def _public_record(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "analysis_id": rec.get("analysis_id"),
        "recipient_kind": rec.get("recipient_kind"),
        "status": rec.get("status"),
        "requested_at": rec.get("requested_at"),
        "sent_at": rec.get("sent_at"),
    }


def _load_file(analysis_id: str, runtime_dir: Path | None = None) -> dict[str, Any] | None:
    path = _file_path(analysis_id, runtime_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _save_file(rec: dict[str, Any], runtime_dir: Path | None = None) -> None:
    path = _file_path(str(rec["analysis_id"]), runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _load_db(analysis_id: str) -> dict[str, Any] | None:
    if not _db_enabled():
        return None
    from ..db.models import AnalysisCompletionNotification

    with session_scope() as session:
        row = session.get(AnalysisCompletionNotification, analysis_id)
        if not row:
            return None
        return {
            "analysis_id": row.analysis_id,
            "recipient_kind": row.recipient_kind,
            "recipient_key": row.recipient_key,
            "status": row.status,
            "requested_at": row.requested_at.isoformat() if row.requested_at else None,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            "last_error_code": row.last_error_code,
        }


def _save_db(rec: dict[str, Any]) -> bool:
    if not _db_enabled():
        return False
    from ..db.models import Analysis, AnalysisCompletionNotification

    with session_scope() as session:
        if session.get(Analysis, rec["analysis_id"]) is None:
            return False
        row = session.get(AnalysisCompletionNotification, rec["analysis_id"])
        sent_at = rec.get("sent_at")
        sent_dt = None
        if sent_at:
            try:
                sent_dt = datetime.fromisoformat(str(sent_at).replace("Z", "+00:00"))
            except ValueError:
                sent_dt = datetime.now(timezone.utc)
        requested = rec.get("requested_at")
        try:
            requested_dt = (
                datetime.fromisoformat(str(requested).replace("Z", "+00:00"))
                if requested
                else datetime.now(timezone.utc)
            )
        except ValueError:
            requested_dt = datetime.now(timezone.utc)
        if row is None:
            session.add(
                AnalysisCompletionNotification(
                    analysis_id=rec["analysis_id"],
                    recipient_kind=rec["recipient_kind"],
                    recipient_key=rec["recipient_key"],
                    status=rec["status"],
                    requested_at=requested_dt,
                    sent_at=sent_dt,
                    last_error_code=rec.get("last_error_code"),
                )
            )
        else:
            if row.status == STATUS_SENT:
                return True
            row.recipient_kind = rec["recipient_kind"]
            row.recipient_key = rec["recipient_key"]
            row.status = rec["status"]
            row.sent_at = sent_dt
            row.last_error_code = rec.get("last_error_code")
        return True


def load_record(analysis_id: str, runtime_dir: Path | None = None) -> dict[str, Any] | None:
    rec = _load_db(analysis_id)
    if rec is not None:
        return rec
    return _load_file(analysis_id, runtime_dir)


def save_record(rec: dict[str, Any], runtime_dir: Path | None = None) -> None:
    if not _save_db(rec):
        _save_file(rec, runtime_dir)


def analysis_is_completed(analysis_id: str, runtime_dir: Path | None = None) -> bool:
    if _db_enabled():
        from ..db.models import Analysis

        try:
            with session_scope() as session:
                row = session.get(Analysis, analysis_id)
                if row and str(row.status or "").lower() == "completed":
                    return True
        except Exception:
            if is_production():
                raise
    base = runtime_dir or get_runtime_dir()
    job_path = base / analysis_id / "job_status.json"
    if job_path.exists():
        try:
            data = json.loads(job_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and str(data.get("status") or "").lower() == "completed":
                return True
        except (OSError, json.JSONDecodeError):
            pass
    return (base / analysis_id / "public_result.json").exists()


def opt_in_completion_notification(
    analysis_id: str,
    identity: ResolvedIdentity,
    runtime_dir: Path | None = None,
) -> dict[str, Any]:
    kind, key = recipient_from_identity(identity)
    now = datetime.now(timezone.utc).isoformat()
    with _LOCK:
        existing = load_record(analysis_id, runtime_dir)
        if existing and existing.get("status") == STATUS_SENT:
            return _public_record(existing)
        rec = existing or {}
        if rec.get("status") != STATUS_REQUESTED:
            rec = {
                "analysis_id": analysis_id,
                "recipient_kind": kind,
                "recipient_key": key,
                "status": STATUS_REQUESTED,
                "requested_at": rec.get("requested_at") or now,
                "sent_at": None,
                "last_error_code": None,
            }
        else:
            rec.setdefault("analysis_id", analysis_id)
            rec.setdefault("recipient_kind", kind)
            rec.setdefault("recipient_key", key)
        save_record(rec, runtime_dir)
    send_if_requested(analysis_id, runtime_dir=runtime_dir)
    latest = load_record(analysis_id, runtime_dir) or rec
    return _public_record(latest)


def send_if_requested(analysis_id: str, runtime_dir: Path | None = None) -> None:
    """Best-effort. Never raises to callers that complete analysis."""
    try:
        _send_if_requested_locked(analysis_id, runtime_dir)
    except Exception:
        logger.warning("[NOTIFICATION] send_failed analysis=%s", analysis_id[:8])


def _send_if_requested_locked(analysis_id: str, runtime_dir: Path | None = None) -> None:
    template = analysis_complete_template_set_code()
    if not template:
        logger.info("[NOTIFICATION] disabled template_missing")
        return
    with _LOCK:
        rec = load_record(analysis_id, runtime_dir)
        if not rec or rec.get("status") == STATUS_SENT:
            return
        if rec.get("status") not in (STATUS_REQUESTED, STATUS_FAILED):
            return
        if not analysis_is_completed(analysis_id, runtime_dir):
            return
        headers = messenger_recipient_headers(str(rec["recipient_kind"]), str(rec["recipient_key"]))
        try:
            result_type = get_messenger_client().send_message(
                template_set_code=template,
                headers=headers,
            )
            if result_type != "SUCCESS":
                rec["status"] = STATUS_FAILED
                rec["last_error_code"] = str(result_type)
            else:
                rec["status"] = STATUS_SENT
                rec["sent_at"] = datetime.now(timezone.utc).isoformat()
                rec["last_error_code"] = None
        except TossApiError as exc:
            rec["status"] = STATUS_FAILED
            rec["last_error_code"] = str(exc.code or "TOSS_RESULT_FAIL")[:64]
        except Exception:
            rec["status"] = STATUS_FAILED
            rec["last_error_code"] = "SEND_ERROR"
        save_record(rec, runtime_dir)
