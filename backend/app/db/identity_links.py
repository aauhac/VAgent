"""Canonical identity resolution over the anon-hash ↔ Toss userKey mapping.

Role split, deliberately:
  - the anonymous hash is the CANONICAL identity for ordinary data ownership
    (analyses, history, diagnostic sessions, entitlement lookup)
  - a verified Toss session/userKey remains the only proof accepted for payment and for
    granting new entitlements

Nothing here authenticates. A client-asserted hash resolves to a canonical identity only
through a link that a *verified* login already wrote.

Resolution never moves rows. Production already contains analyses that the old destructive
migration moved onto `(TOSS, userKey)` users, so a canonical identity is a SET of user rows
— the canonical hash user plus every user linked to the same userKey — and queries union
over that set.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import User, UserIdentityLink
from .users import get_or_create_user, get_user_by_identity

logger = logging.getLogger("vagent.identity.links")

PROVIDER_TOSS = "TOSS"
ANONYMOUS_PROVIDERS = ("TOSS_ANONYMOUS", "DEV")
MAX_SUBJECT_LEN = 255


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def find_link(
    session: Session, subject: str, provider: str | None = None
) -> UserIdentityLink | None:
    """The link a subject belongs to.

    `anon_subject` and `toss_user_key` are separate namespaces. When the caller knows the
    provider, only the matching column is searched, so a hash can never be mistaken for a
    userKey that happens to be the same string.
    """
    token = _clean(subject)
    if not token:
        return None
    side = (provider or "").strip().upper()
    if side == PROVIDER_TOSS:
        where = UserIdentityLink.toss_user_key == token
    elif side in ANONYMOUS_PROVIDERS:
        where = UserIdentityLink.anon_subject == token
    else:
        where = or_(
            UserIdentityLink.anon_subject == token,
            UserIdentityLink.toss_user_key == token,
        )
    return session.scalars(
        select(UserIdentityLink)
        .where(where)
        .order_by(UserIdentityLink.linked_at.asc())
        .limit(1)
    ).first()


def resolve_canonical_user(
    session: Session, subject: str, provider: str | None = None
) -> User | None:
    """The user row that owns this identity's data, or None if there is no link."""
    link = find_link(session, subject, provider)
    if link is None:
        return None
    return session.get(User, link.canonical_user_id)


def identity_group_ids(
    session: Session, subject: str, provider: str | None = None
) -> list[uuid.UUID]:
    """Every user row belonging to this identity.

    Merging rows across providers is justified ONLY by a UserIdentityLink — never by two
    subjects happening to be the same string. Each side of a link is then looked up with
    its own provider: `anon_subject` on the anonymous providers, `toss_user_key` on TOSS.

    With no link the group is just the caller's own row, so an anonymous user who never
    logged in behaves exactly as before.
    """
    token = _clean(subject)
    if not token:
        return []
    ids: list[uuid.UUID] = []

    def add(user: User | None) -> None:
        if user is not None and user.id not in ids:
            ids.append(user.id)

    link = find_link(session, token, provider)
    if link is not None:
        add(session.get(User, link.canonical_user_id))
        for row in session.scalars(
            select(UserIdentityLink).where(
                UserIdentityLink.toss_user_key == link.toss_user_key
            )
        ).all():
            add(session.get(User, row.canonical_user_id))
            for anon_provider in ANONYMOUS_PROVIDERS:
                add(get_user_by_identity(session, anon_provider, row.anon_subject))
        add(get_user_by_identity(session, PROVIDER_TOSS, link.toss_user_key))

    add(_own_row(session, token, provider))
    return ids


def _own_row(session: Session, subject: str, provider: str | None) -> User | None:
    """The caller's own row. Never merges providers.

    Without a stated provider this cannot disambiguate a colliding subject, so it probes
    the providers in a fixed order and returns at most ONE row — enough to scope the
    caller's own data, never enough to fold two identities together.
    """
    if provider:
        return get_user_by_identity(session, provider, subject)
    for candidate in (PROVIDER_TOSS,) + ANONYMOUS_PROVIDERS:
        row = get_user_by_identity(session, candidate, subject)
        if row is not None:
            return row
    return None


def canonical_subject(session: Session, subject: str, provider: str | None = None) -> str:
    """Stable identity string for comparing two subjects.

    Used where a subject was persisted as a plain string (diagnostic sessions) and must
    still match its owner after that owner logs in.
    """
    token = _clean(subject)
    if not token:
        return token
    user = resolve_canonical_user(session, token, provider)
    if user is not None:
        return str(user.external_subject)
    return token


def same_identity(session: Session, left: str | None, right: str | None) -> bool:
    a, b = _clean(left), _clean(right)
    if not a or not b:
        return False
    if a == b:
        return True
    return canonical_subject(session, a) == canonical_subject(session, b)


def link_identities(
    session: Session,
    *,
    anonymous_subject: str | None,
    toss_user_key: str,
) -> dict[str, object]:
    """Record hash ↔ userKey after a verified login. Idempotent; never moves data.

    Refuses to repoint an existing link: if this hash already belongs to another userKey,
    a second Toss account signing in on that device cannot capture the first account's
    canonical identity.
    """
    verified = _clean(toss_user_key)
    if not verified:
        raise ValueError("toss_user_key required")
    subject = _clean(anonymous_subject)
    result: dict[str, object] = {"linked": False, "reason": "NO_SUBJECT"}
    if not subject or len(subject) > MAX_SUBJECT_LEN:
        return result
    if subject == verified:
        # The client asserted the userKey as its own hash; that shortcuts nothing.
        result["reason"] = "SUBJECT_IS_USER_KEY"
        return result

    now = datetime.now(timezone.utc)
    existing = session.scalars(
        select(UserIdentityLink).where(UserIdentityLink.anon_subject == subject).limit(1)
    ).first()
    if existing is not None:
        if existing.toss_user_key != verified:
            # Never repoint. Counter only — no hash or userKey in logs.
            logger.warning("identity_link_conflict_refused")
            result["reason"] = "CONFLICT_REFUSED"
            return result
        existing.last_seen_at = now
        result.update(
            linked=True,
            reason="ALREADY_LINKED",
            canonical_user_id=str(existing.canonical_user_id),
        )
        return result

    # Reuse the canonical user already chosen for this userKey (N:1), else this hash user
    # becomes canonical.
    sibling = session.scalars(
        select(UserIdentityLink)
        .where(UserIdentityLink.toss_user_key == verified)
        .order_by(UserIdentityLink.linked_at.asc())
        .limit(1)
    ).first()
    if sibling is not None:
        canonical_id = sibling.canonical_user_id
    else:
        canonical = get_or_create_user(
            session, provider="TOSS_ANONYMOUS", subject=subject
        )
        canonical_id = canonical.id

    # The verified user row must exist so payment lookups resolve into this group.
    get_or_create_user(session, provider=PROVIDER_TOSS, subject=verified)

    session.add(
        UserIdentityLink(
            anon_subject=subject,
            toss_user_key=verified,
            canonical_user_id=canonical_id,
            linked_at=now,
            last_seen_at=now,
        )
    )
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError:
        # Concurrent login wrote the same link first; treat as already linked.
        logger.info("identity_link_race_resolved")
        result.update(linked=True, reason="ALREADY_LINKED")
        return result

    logger.info("identity_link_created new_canonical=%s", sibling is None)
    result.update(linked=True, reason="LINKED", canonical_user_id=str(canonical_id))
    return result
