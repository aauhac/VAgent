"""A diagnostic session is a workspace, not a receipt.

Production bug: creating a DiagnosticSession — including one created before a purchase the
user then cancelled — made `diagnostic_unlocked` true across access, history, and the
Result CTA. The report body itself stayed entitlement-gated, so nothing leaked, but the UI
promised access that returned 402 on click.

The only unlock source is an ACTIVE DIAGNOSTIC entitlement, held either against the
analysis or against one of its sessions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.db.models import Analysis, Base, DiagnosticSession, Entitlement
from backend.app.db.session import reset_engine, session_scope
from backend.app.db.users import get_or_create_user

SUBJECT = "gate-user"
OTHER = "gate-other"


@pytest.fixture()
def gate_env(tmp_path, monkeypatch):
    db = tmp_path / "gate.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path / "runtime"))
    (tmp_path / "runtime").mkdir()
    reset_engine()
    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    from backend.app.api import routes as routes_mod
    from backend.app.diagnostic import DiagnosticSessionService
    from backend.app.jobs.runner import JobRunner
    from backend.app.main import app
    from backend.app.services.analysis_service import AnalysisService

    svc = AnalysisService()
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    routes_mod.service = svc
    routes_mod.diag = DiagnosticSessionService(svc.runtime_dir)
    client = TestClient(app, raise_server_exceptions=True)
    yield client
    reset_engine()
    get_runtime_dir.cache_clear()


def _user(subject: str):
    with session_scope() as session:
        return get_or_create_user(session, provider="DEV", subject=subject).id


def _analysis(user_id) -> str:
    aid = uuid.uuid4().hex
    with session_scope() as session:
        session.add(
            Analysis(
                id=aid,
                user_id=user_id,
                status="completed",
                created_at=datetime.now(timezone.utc),
            )
        )
    return aid


def _session(user_id, source: str | None, status: str = "CREATED") -> str:
    sid = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        session.add(
            DiagnosticSession(
                id=sid,
                user_id=user_id,
                source_analysis_id=source,
                status=status,
                created_at=now,
                updated_at=now,
                completed_at=now if status == "COMPLETED" else None,
            )
        )
    return sid


def _grant(user_id, *, resource_type: str, resource_id: str) -> None:
    with session_scope() as session:
        session.add(
            Entitlement(
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                entitlement_type="DIAGNOSTIC",
                status="ACTIVE",
                granted_at=datetime.now(timezone.utc),
            )
        )


def _access(subject: str, analysis_id: str) -> dict:
    from backend.app.entitlements import get_entitlement_provider
    from backend.app.api import routes as routes_mod

    return get_entitlement_provider(routes_mod.service.runtime_dir).analysis_access(
        subject, analysis_id
    )


def _history(client: TestClient, subject: str) -> dict:
    r = client.get("/v1/history", headers={"X-User-Id": subject})
    assert r.status_code == 200, r.text
    return r.json()


def _row(body: dict, analysis_id: str) -> dict:
    return next(i for i in body["items"] if i["analysis_id"] == analysis_id)


# --- the core rule -------------------------------------------------------------------


def test_session_without_entitlement_stays_locked(gate_env):
    """Scenario 2: session exists, entitlement absent."""
    uid = _user(SUBJECT)
    aid = _analysis(uid)
    _session(uid, aid)

    access = _access(SUBJECT, aid)
    assert access["diagnostic_unlocked"] is False
    assert access["diagnostic_session_id"] is None


def test_active_diagnostic_entitlement_unlocks(gate_env):
    """Scenario 3: entitlement present."""
    uid = _user(SUBJECT)
    aid = _analysis(uid)
    sid = _session(uid, aid)
    _grant(uid, resource_type="DIAGNOSTIC_SESSION", resource_id=sid)

    access = _access(SUBJECT, aid)
    assert access["diagnostic_unlocked"] is True
    assert access["diagnostic_session_id"] == sid


def test_analysis_level_entitlement_also_unlocks(gate_env):
    """diagnostic_full grants against the analysis before any session exists."""
    uid = _user(SUBJECT)
    aid = _analysis(uid)
    _grant(uid, resource_type="ANALYSIS", resource_id=aid)

    access = _access(SUBJECT, aid)
    assert access["diagnostic_unlocked"] is True
    # No session yet — the purchase flow creates it after the grant.
    assert access["diagnostic_session_id"] is None


def test_cancelled_purchase_leftover_session_does_not_unlock(gate_env):
    """Scenario 1: the exact production bug — abandoned session must stay locked."""
    uid = _user(SUBJECT)
    aid = _analysis(uid)
    _session(uid, aid, status="CREATED")

    access = _access(SUBJECT, aid)
    assert access["diagnostic_unlocked"] is False

    row = _row(_history(gate_env, SUBJECT), aid)
    assert row["diagnostic_unlocked"] is False
    assert row["diagnostic_sessions"] == []
    assert row["diagnostic_session_id"] is None


def test_revoked_entitlement_relocks(gate_env):
    uid = _user(SUBJECT)
    aid = _analysis(uid)
    sid = _session(uid, aid)
    _grant(uid, resource_type="DIAGNOSTIC_SESSION", resource_id=sid)
    with session_scope() as session:
        row = session.query(Entitlement).filter(Entitlement.resource_id == sid).one()
        row.status = "REVOKED"

    assert _access(SUBJECT, aid)["diagnostic_unlocked"] is False


# --- history ---------------------------------------------------------------------------


def test_history_hides_unpaid_sessions_but_keeps_the_analysis(gate_env):
    uid = _user(SUBJECT)
    aid = _analysis(uid)
    _session(uid, aid)

    body = _history(gate_env, SUBJECT)
    row = _row(body, aid)
    assert row["diagnostic_unlocked"] is False
    assert row["diagnostic_sessions"] == []
    # The free analysis itself must never disappear.
    assert row["analysis_id"] == aid


def test_history_shows_paid_sessions(gate_env):
    uid = _user(SUBJECT)
    aid = _analysis(uid)
    sid = _session(uid, aid, status="COMPLETED")
    _grant(uid, resource_type="DIAGNOSTIC_SESSION", resource_id=sid)

    row = _row(_history(gate_env, SUBJECT), aid)
    assert row["diagnostic_unlocked"] is True
    assert [s["session_id"] for s in row["diagnostic_sessions"]] == [sid]
    assert row["diagnostic_session_id"] == sid


def test_history_hides_unpaid_unlinked_sessions(gate_env):
    uid = _user(SUBJECT)
    _analysis(uid)
    orphan = _session(uid, None)

    body = _history(gate_env, SUBJECT)
    assert all(s["session_id"] != orphan for s in body["unlinked_diagnostics"])


def test_history_keeps_paid_unlinked_sessions(gate_env):
    uid = _user(SUBJECT)
    _analysis(uid)
    orphan = _session(uid, None, status="COMPLETED")
    _grant(uid, resource_type="DIAGNOSTIC_SESSION", resource_id=orphan)

    body = _history(gate_env, SUBJECT)
    assert any(s["session_id"] == orphan for s in body["unlinked_diagnostics"])


# --- isolation ---------------------------------------------------------------------------


def test_another_users_entitlement_does_not_unlock(gate_env):
    owner = _user(SUBJECT)
    stranger = _user(OTHER)
    aid = _analysis(owner)
    sid = _session(owner, aid)
    # The stranger paid for their own unrelated things; it must not carry over.
    _grant(stranger, resource_type="DIAGNOSTIC_SESSION", resource_id=sid)
    _grant(stranger, resource_type="ANALYSIS", resource_id=aid)

    assert _access(SUBJECT, aid)["diagnostic_unlocked"] is False
