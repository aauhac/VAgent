"""Entitlement and rewarded-ad paths pick the user row by exact (provider, subject).

A Toss userKey and an anonymous hash are separate namespaces that can hold the same
string. Before this, both paths resolved a bare subject cross-provider, so a collision
could read or grant against the wrong person. Sharing is now possible only through a
UserIdentityLink written by a verified login.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from backend.app.db.entitlements_db import DatabaseEntitlementProvider
from backend.app.db.identity_links import link_identities
from backend.app.db.models import Base, Entitlement, RewardedAdDailySlot, User
from backend.app.db.session import reset_engine, session_scope
from backend.app.db.users import get_or_create_user
from backend.app.identity import ResolvedIdentity

# One string used as BOTH a Toss userKey and an anonymous hash.
COLLIDING = "443731104"
REAL_HASH = "anon-real-hash"
ANALYSIS = "analysis-under-test"
DAY = "2026-08-25"


@pytest.fixture()
def db_env(tmp_path, monkeypatch):
    db = tmp_path / "exactness.sqlite"
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
    yield DatabaseEntitlementProvider(provider_name="DEV")
    reset_engine()
    get_runtime_dir.cache_clear()


def _collision() -> tuple[uuid.UUID, uuid.UUID]:
    with session_scope() as session:
        toss = get_or_create_user(session, provider="TOSS", subject=COLLIDING)
        anon = get_or_create_user(session, provider="TOSS_ANONYMOUS", subject=COLLIDING)
        return toss.id, anon.id


def _identity(provider: str, subject: str) -> ResolvedIdentity:
    verified = provider == "TOSS"
    return ResolvedIdentity(
        provider=provider,
        subject=subject,
        trust_mode="VERIFIED_TOSS_SUBJECT" if verified else "UNVERIFIED_CLIENT_SUBJECT",
        authenticated=verified,
        toss_user_key=subject if verified else None,
    )


def _entitlement_owners(resource_id: str) -> set[uuid.UUID]:
    with session_scope() as session:
        return {
            e.user_id
            for e in session.scalars(
                select(Entitlement).where(Entitlement.resource_id == resource_id)
            )
        }


# 1 + 2 — entitlement lookup and grant use the requested provider row


def test_grant_lands_on_the_requested_provider_row(db_env):
    toss_id, anon_id = _collision()
    db_env.grant_song_detail(
        COLLIDING, ANALYSIS, "ent-anon", provider="TOSS_ANONYMOUS"
    )
    assert _entitlement_owners(ANALYSIS) == {anon_id}
    assert toss_id not in _entitlement_owners(ANALYSIS)


def test_lookup_uses_the_requested_provider_row(db_env):
    _collision()
    db_env.grant_song_detail(COLLIDING, ANALYSIS, "ent-anon", provider="TOSS_ANONYMOUS")

    assert db_env.has_song_detail(COLLIDING, ANALYSIS, provider="TOSS_ANONYMOUS") is True
    assert db_env.has_song_detail(COLLIDING, ANALYSIS, provider="TOSS") is False


def test_analysis_access_respects_the_requested_provider(db_env):
    _collision()
    db_env.grant_song_detail(COLLIDING, ANALYSIS, "ent-anon", provider="TOSS_ANONYMOUS")

    anon_view = db_env.analysis_access(COLLIDING, ANALYSIS, provider="TOSS_ANONYMOUS")
    toss_view = db_env.analysis_access(COLLIDING, ANALYSIS, provider="TOSS")
    assert anon_view["song_detail_unlocked"] is True
    assert toss_view["song_detail_unlocked"] is False


# 3 — rewarded claims attach to the requested identity's row


def test_rewarded_user_resolution_uses_the_requested_provider(db_env):
    from backend.app.rewards.rewarded_detail import _resolve_user

    toss_id, anon_id = _collision()
    with session_scope() as session:
        assert _resolve_user(session, _identity("TOSS", COLLIDING)).id == toss_id
        assert _resolve_user(session, _identity("TOSS_ANONYMOUS", COLLIDING)).id == anon_id


def test_rewarded_principal_is_namespaced(db_env):
    from backend.app.rewards.rewarded_detail import principal_key

    _collision()
    assert principal_key(_identity("TOSS", COLLIDING)) == f"TOSS:{COLLIDING}"
    assert (
        principal_key(_identity("TOSS_ANONYMOUS", COLLIDING))
        == f"TOSS_ANONYMOUS:{COLLIDING}"
    )


# 4 — no link, no sharing


def test_no_link_means_no_entitlement_sharing(db_env):
    _collision()
    db_env.grant_song_detail(COLLIDING, ANALYSIS, "ent-anon", provider="TOSS_ANONYMOUS")
    # The verified namesake bought nothing and must see nothing.
    assert db_env.has_song_detail(COLLIDING, ANALYSIS, provider="TOSS") is False


def test_no_link_means_no_reward_sharing(db_env):
    from backend.app.rewards.rewarded_detail import _used_today_db, principal_keys

    _collision()
    with session_scope() as session:
        session.add(
            RewardedAdDailySlot(
                principal_key=f"TOSS_ANONYMOUS:{COLLIDING}", seoul_day=DAY, slot_index=1
            )
        )

    verified = _identity("TOSS", COLLIDING)
    keys = principal_keys(verified)
    assert f"TOSS_ANONYMOUS:{COLLIDING}" not in keys
    with session_scope() as session:
        used = _used_today_db(session, keys[0], DAY, keys)
    assert used == 0  # the namesake's usage is not this person's usage


# 5 — only after a link is state shared


def test_link_enables_entitlement_sharing(db_env):
    _collision()
    with session_scope() as session:
        get_or_create_user(session, provider="TOSS_ANONYMOUS", subject=REAL_HASH)
    db_env.grant_song_detail(REAL_HASH, ANALYSIS, "ent-hash", provider="TOSS_ANONYMOUS")

    assert db_env.has_song_detail(COLLIDING, ANALYSIS, provider="TOSS") is False
    with session_scope() as session:
        link_identities(session, anonymous_subject=REAL_HASH, toss_user_key=COLLIDING)
    assert db_env.has_song_detail(COLLIDING, ANALYSIS, provider="TOSS") is True


def test_grant_after_link_does_not_duplicate(db_env):
    _collision()
    with session_scope() as session:
        real = get_or_create_user(session, provider="TOSS_ANONYMOUS", subject=REAL_HASH)
        real_id = real.id
    db_env.grant_song_detail(REAL_HASH, ANALYSIS, "ent-hash", provider="TOSS_ANONYMOUS")
    with session_scope() as session:
        link_identities(session, anonymous_subject=REAL_HASH, toss_user_key=COLLIDING)

    # Buying again as the verified identity resolves to the same canonical row.
    db_env.grant_song_detail(COLLIDING, ANALYSIS, "ent-hash", provider="TOSS")
    assert _entitlement_owners(ANALYSIS) == {real_id}


# 6 + 7 — the daily rewarded cap survives login and cannot be reset by a collision


def test_daily_limit_is_summed_across_login(db_env):
    from backend.app.rewards.rewarded_detail import _used_today_db, principal_keys

    with session_scope() as session:
        get_or_create_user(session, provider="TOSS_ANONYMOUS", subject=REAL_HASH)
        get_or_create_user(session, provider="TOSS", subject=COLLIDING)
        session.add(
            RewardedAdDailySlot(
                principal_key=f"TOSS_ANONYMOUS:{REAL_HASH}", seoul_day=DAY, slot_index=1
            )
        )
        session.add(
            RewardedAdDailySlot(
                principal_key=f"TOSS_ANONYMOUS:{REAL_HASH}", seoul_day=DAY, slot_index=2
            )
        )
    with session_scope() as session:
        link_identities(session, anonymous_subject=REAL_HASH, toss_user_key=COLLIDING)

    verified = _identity("TOSS", COLLIDING)
    keys = principal_keys(verified)
    with session_scope() as session:
        used = _used_today_db(session, keys[0], DAY, keys)
    assert used == 2  # two of three consumed before login still count


def test_collision_cannot_reset_the_daily_limit(db_env):
    from backend.app.rewards.rewarded_detail import _used_today_db, principal_keys

    _collision()
    with session_scope() as session:
        get_or_create_user(session, provider="TOSS_ANONYMOUS", subject=REAL_HASH)
        for slot in (1, 2, 3):
            session.add(
                RewardedAdDailySlot(
                    principal_key=f"TOSS_ANONYMOUS:{REAL_HASH}",
                    seoul_day=DAY,
                    slot_index=slot,
                )
            )
    with session_scope() as session:
        link_identities(session, anonymous_subject=REAL_HASH, toss_user_key=COLLIDING)

    verified = _identity("TOSS", COLLIDING)
    keys = principal_keys(verified)
    # The unrelated (TOSS_ANONYMOUS, COLLIDING) namesake is not in this identity...
    assert f"TOSS_ANONYMOUS:{COLLIDING}" not in keys
    with session_scope() as session:
        used = _used_today_db(session, keys[0], DAY, keys)
    assert used == 3  # ...and the cap stays exhausted


def test_entitlement_group_excludes_the_namesake(db_env):
    toss_id, anon_id = _collision()
    with session_scope() as session:
        namesake = session.get(User, anon_id)
        group = db_env._group_ids(session, COLLIDING, namesake, "TOSS_ANONYMOUS")
    assert anon_id in group
    assert toss_id not in group
