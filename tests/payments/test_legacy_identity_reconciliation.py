"""Legacy reconciliation for users the retired destructive migration already moved.

Their hash ↔ userKey pair was never recorded, so it is recovered from evidence:
runtime analysis_meta.json, and ANON completion-notification recipients. Read-only until
--apply; never moves, deletes, or duplicates rows.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.app.db.identity_linking import derive_legacy_links, reconcile_legacy_links
from backend.app.db.models import (
    Analysis,
    AnalysisCompletionNotification,
    Base,
    Entitlement,
    User,
    UserIdentityLink,
)
from backend.app.db.session import reset_engine, session_scope
from backend.app.db.users import get_or_create_user

USER_KEY = "443731104"
ANON_A = "anon-A-hash"
ANON_B = "anon-B-hash"


@pytest.fixture()
def legacy_env(tmp_path, monkeypatch):
    db = tmp_path / "legacy.sqlite"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    reset_engine()
    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    yield runtime
    reset_engine()
    get_runtime_dir.cache_clear()


def _migrated_analysis(runtime, *, original_subject: str | None, user_key: str = USER_KEY) -> str:
    """An analysis the old path moved onto the TOSS user."""
    aid = uuid.uuid4().hex
    with session_scope() as session:
        toss = get_or_create_user(session, provider="TOSS", subject=user_key)
        session.add(Analysis(id=aid, user_id=toss.id, status="completed"))
    if original_subject is not None:
        meta = runtime / aid
        meta.mkdir(parents=True, exist_ok=True)
        (meta / "analysis_meta.json").write_text(
            json.dumps({"analysis_id": aid, "user_id": original_subject}), encoding="utf-8"
        )
    return aid


def _anon_notification(analysis_id: str, subject: str) -> None:
    with session_scope() as session:
        session.add(
            AnalysisCompletionNotification(
                analysis_id=analysis_id,
                recipient_kind="ANON",
                recipient_key=subject,
                status="SENT",
                requested_at=datetime.now(timezone.utc),
                sent_at=datetime.now(timezone.utc),
            )
        )


def test_pairs_recovered_from_runtime_meta(legacy_env):
    runtime = legacy_env
    _migrated_analysis(runtime, original_subject=ANON_A)
    with session_scope() as session:
        pairs = derive_legacy_links(session, runtime)
    assert pairs == {ANON_A: USER_KEY}


def test_pairs_recovered_from_anon_notification(legacy_env):
    runtime = legacy_env
    aid = _migrated_analysis(runtime, original_subject=None)
    _anon_notification(aid, ANON_B)
    with session_scope() as session:
        pairs = derive_legacy_links(session, runtime)
    assert pairs == {ANON_B: USER_KEY}


def test_dry_run_writes_nothing(legacy_env):
    runtime = legacy_env
    _migrated_analysis(runtime, original_subject=ANON_A)
    with session_scope() as session:
        tally = reconcile_legacy_links(session, runtime, apply=False)
    assert tally["discovered"] == 1
    assert tally["to_create"] == 1
    assert tally["already_linked"] == 0
    with session_scope() as session:
        assert session.scalars(select(UserIdentityLink)).first() is None


def test_apply_creates_the_link_and_restores_history(legacy_env):
    runtime = legacy_env
    aid = _migrated_analysis(runtime, original_subject=ANON_A)
    with session_scope() as session:
        reconcile_legacy_links(session, runtime, apply=True)

    with session_scope() as session:
        keys = [
            (link.anon_subject, link.toss_user_key)
            for link in session.scalars(select(UserIdentityLink))
        ]
    assert keys == [(ANON_A, USER_KEY)]

    # The device's hash can now see the analysis the old migration took away.
    from backend.app.db.analysis_repo import list_analyses_for_subject

    ids = {row["analysis_id"] for row in list_analyses_for_subject(ANON_A)["items"]}
    assert aid in ids


def test_reconciliation_is_idempotent(legacy_env):
    runtime = legacy_env
    _migrated_analysis(runtime, original_subject=ANON_A)
    with session_scope() as session:
        reconcile_legacy_links(session, runtime, apply=True)
    with session_scope() as session:
        second = reconcile_legacy_links(session, runtime, apply=True)
    assert second["discovered"] == 1
    assert second["already_linked"] == 1
    assert second["to_create"] == 0
    assert second["applied_already_linked"] == 1
    with session_scope() as session:
        assert len(list(session.scalars(select(UserIdentityLink)))) == 1


def test_reconciliation_never_moves_or_deletes_rows(legacy_env):
    runtime = legacy_env
    aid = _migrated_analysis(runtime, original_subject=ANON_A)
    with session_scope() as session:
        toss = session.scalar(
            select(User).where(
                User.external_provider == "TOSS", User.external_subject == USER_KEY
            )
        )
        session.add(
            Entitlement(
                user_id=toss.id,
                resource_type="ANALYSIS",
                resource_id=aid,
                entitlement_type="SONG_DETAIL",
                status="ACTIVE",
            )
        )
        owner_before = toss.id

    with session_scope() as session:
        reconcile_legacy_links(session, runtime, apply=True)

    with session_scope() as session:
        row = session.get(Analysis, aid)
        assert row.user_id == owner_before  # ownership untouched
        ents = list(session.scalars(select(Entitlement).where(Entitlement.resource_id == aid)))
    assert len(ents) == 1  # purchase preserved, not duplicated


def test_no_evidence_yields_no_pairs(legacy_env):
    runtime = legacy_env
    _migrated_analysis(runtime, original_subject=None)
    with session_scope() as session:
        assert derive_legacy_links(session, runtime) == {}


def test_meta_naming_the_user_key_is_not_a_pair(legacy_env):
    """A meta already rewritten to the userKey carries no anonymous evidence."""
    runtime = legacy_env
    _migrated_analysis(runtime, original_subject=USER_KEY)
    with session_scope() as session:
        assert derive_legacy_links(session, runtime) == {}
