"""Provider is part of identity. A shared subject string is not a shared person.

`users` is unique on (external_provider, external_subject), so the same string can name a
Toss userKey and an anonymous hash at the same time. Those are different namespaces and
different people. The only thing that may merge them is a UserIdentityLink written by a
verified login.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from backend.app.db.identity_links import (
    identity_group_ids,
    link_identities,
    resolve_canonical_user,
    same_identity,
)
from backend.app.db.models import Analysis, Base, User
from backend.app.db.session import reset_engine, session_scope
from backend.app.db.users import get_or_create_user, get_user_by_identity
from backend.app.payments import rate_limit
from backend.app.payments.toss_clients import set_login_client

# One string, deliberately used as BOTH a Toss userKey and an anonymous hash.
COLLIDING = "443731104"
OTHER_HASH = "anon-real-hash"


@pytest.fixture()
def db_env(tmp_path, monkeypatch):
    db = tmp_path / "provider.sqlite"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("VAGENT_SESSION_SECRET", "test-session-secret-not-for-prod")
    monkeypatch.setenv("PAYMENTS_ENABLED", "true")
    monkeypatch.setenv("TOSS_LOGIN_ENABLED", "true")
    monkeypatch.setenv("IAP_SONG_DETAIL_SKU", "sku.song.detail.test")
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    rate_limit.reset()
    reset_engine()
    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    yield
    set_login_client(None)
    reset_engine()
    get_runtime_dir.cache_clear()


def _both_rows() -> tuple[uuid.UUID, uuid.UUID]:
    """(TOSS, COLLIDING) and (TOSS_ANONYMOUS, COLLIDING) — two distinct people."""
    with session_scope() as session:
        toss = get_or_create_user(session, provider="TOSS", subject=COLLIDING)
        anon = get_or_create_user(session, provider="TOSS_ANONYMOUS", subject=COLLIDING)
        return toss.id, anon.id


# 1 + 2 — the same subject under two providers, each fetched exactly


def test_same_subject_can_exist_under_two_providers(db_env):
    toss_id, anon_id = _both_rows()
    assert toss_id != anon_id


def test_exact_lookup_returns_the_row_it_was_asked_for(db_env):
    toss_id, anon_id = _both_rows()
    with session_scope() as session:
        assert get_user_by_identity(session, "TOSS", COLLIDING).id == toss_id
        assert get_user_by_identity(session, "TOSS_ANONYMOUS", COLLIDING).id == anon_id
        assert get_user_by_identity(session, "DEV", COLLIDING) is None


# 3 — without a link they stay separate identities


def test_without_a_link_they_are_different_identities(db_env):
    toss_id, anon_id = _both_rows()
    with session_scope() as session:
        assert identity_group_ids(session, COLLIDING, "TOSS") == [toss_id]
        assert identity_group_ids(session, COLLIDING, "TOSS_ANONYMOUS") == [anon_id]
        assert resolve_canonical_user(session, COLLIDING, "TOSS") is None
        assert resolve_canonical_user(session, COLLIDING, "TOSS_ANONYMOUS") is None


def test_history_does_not_leak_across_a_colliding_subject(db_env):
    """The ownership consequence: one person's analysis stays theirs."""
    from backend.app.db.analysis_repo import list_analyses_for_subject

    toss_id, anon_id = _both_rows()
    toss_aid, anon_aid = uuid.uuid4().hex, uuid.uuid4().hex
    with session_scope() as session:
        session.add(Analysis(id=toss_aid, user_id=toss_id, status="completed"))
        session.add(Analysis(id=anon_aid, user_id=anon_id, status="completed"))

    toss_view = {r["analysis_id"] for r in list_analyses_for_subject(COLLIDING, provider="TOSS")["items"]}
    anon_view = {
        r["analysis_id"]
        for r in list_analyses_for_subject(COLLIDING, provider="TOSS_ANONYMOUS")["items"]
    }
    assert toss_view == {toss_aid}
    assert anon_view == {anon_aid}


# 4 — only a link merges them


def test_only_a_link_merges_two_providers(db_env):
    toss_id, _anon_id = _both_rows()
    with session_scope() as session:
        real_anon = get_or_create_user(
            session, provider="TOSS_ANONYMOUS", subject=OTHER_HASH
        )
        real_anon_id = real_anon.id
        assert identity_group_ids(session, OTHER_HASH, "TOSS_ANONYMOUS") == [real_anon_id]

    with session_scope() as session:
        result = link_identities(
            session, anonymous_subject=OTHER_HASH, toss_user_key=COLLIDING
        )
        assert result["linked"] is True

    with session_scope() as session:
        group = identity_group_ids(session, OTHER_HASH, "TOSS_ANONYMOUS")
        assert real_anon_id in group
        assert toss_id in group  # merged, and only because the link says so
        assert same_identity(session, OTHER_HASH, COLLIDING) is True


def test_link_does_not_pull_in_the_colliding_anonymous_row(db_env):
    """Linking hash→userKey must not also absorb (TOSS_ANONYMOUS, <that userKey>)."""
    _toss_id, anon_collide_id = _both_rows()
    with session_scope() as session:
        get_or_create_user(session, provider="TOSS_ANONYMOUS", subject=OTHER_HASH)
    with session_scope() as session:
        link_identities(session, anonymous_subject=OTHER_HASH, toss_user_key=COLLIDING)

    with session_scope() as session:
        group = identity_group_ids(session, OTHER_HASH, "TOSS_ANONYMOUS")
    assert anon_collide_id not in group


# 5 — payment uses the verified TOSS side only


def test_payment_resolves_the_toss_side_of_a_colliding_subject(db_env):
    from backend.app.payments.service import resolve_toss_user

    toss_id, anon_id = _both_rows()
    with session_scope() as session:
        resolved = resolve_toss_user(session, COLLIDING)
        assert resolved.id == toss_id
        assert resolved.id != anon_id
        assert resolved.external_provider == "TOSS"


def test_payment_follows_the_link_to_the_canonical_user(db_env):
    from backend.app.payments.service import resolve_toss_user

    with session_scope() as session:
        get_or_create_user(session, provider="TOSS_ANONYMOUS", subject=OTHER_HASH)
    with session_scope() as session:
        link_identities(session, anonymous_subject=OTHER_HASH, toss_user_key=COLLIDING)

    with session_scope() as session:
        resolved = resolve_toss_user(session, COLLIDING)
        assert resolved.external_provider == "TOSS_ANONYMOUS"
        assert resolved.external_subject == OTHER_HASH


# 6 — an accidental collision never passes an ownership check


def test_colliding_subject_cannot_pass_ownership(db_env):
    from backend.app.db.analysis_repo import analysis_owned_by

    toss_id, anon_id = _both_rows()
    aid = uuid.uuid4().hex
    with session_scope() as session:
        session.add(Analysis(id=aid, user_id=toss_id, status="completed"))

    # Same string, but resolve_owner_subject returns the TOSS row's subject, and without a
    # link the anonymous namesake is a different person.
    with session_scope() as session:
        assert same_identity(session, COLLIDING, COLLIDING) is True  # identical strings
        anon_row = session.get(User, anon_id)
        assert anon_row.external_provider == "TOSS_ANONYMOUS"

    # The payment-side ownership gate is what production actually uses.
    from backend.app.payments.service import _analysis_owned, PaymentError

    with session_scope() as session:
        namesake = session.get(User, anon_id)
        with pytest.raises(PaymentError) as exc:
            _analysis_owned(session, namesake, aid)
        assert exc.value.code == "RESOURCE_NOT_FOUND"
        # The real owner still passes.
        owner = session.get(User, toss_id)
        assert _analysis_owned(session, owner, aid).id == aid


def test_entitlement_group_is_not_widened_by_a_collision(db_env):
    from backend.app.db.entitlements_db import DatabaseEntitlementProvider
    from backend.app.db.models import Entitlement

    toss_id, anon_id = _both_rows()
    aid = uuid.uuid4().hex
    with session_scope() as session:
        session.add(
            Entitlement(
                user_id=toss_id,
                resource_type="ANALYSIS",
                resource_id=aid,
                entitlement_type="SONG_DETAIL",
                status="ACTIVE",
            )
        )

    provider = DatabaseEntitlementProvider(provider_name="TOSS_ANONYMOUS")
    with session_scope() as session:
        namesake = session.get(User, anon_id)
        group = provider._group_ids(session, COLLIDING, namesake)
        assert toss_id not in group
        assert anon_id in group


def test_link_table_rows_are_scoped_by_column(db_env):
    """A hash is searched on anon_subject; a userKey on toss_user_key. Never swapped."""
    from backend.app.db.identity_links import find_link
    from backend.app.db.models import UserIdentityLink

    with session_scope() as session:
        get_or_create_user(session, provider="TOSS_ANONYMOUS", subject=OTHER_HASH)
    with session_scope() as session:
        link_identities(session, anonymous_subject=OTHER_HASH, toss_user_key=COLLIDING)

    with session_scope() as session:
        # COLLIDING is a userKey: found on the TOSS side, absent on the anonymous side.
        assert find_link(session, COLLIDING, "TOSS") is not None
        assert find_link(session, COLLIDING, "TOSS_ANONYMOUS") is None
        # OTHER_HASH is a hash: the mirror image.
        assert find_link(session, OTHER_HASH, "TOSS_ANONYMOUS") is not None
        assert find_link(session, OTHER_HASH, "TOSS") is None
        assert len(list(session.scalars(select(UserIdentityLink)))) == 1
