"""User identity persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import User


def get_user_by_identity(session: Session, provider: str, subject: str) -> User | None:
    """Exact `(external_provider, external_subject)` lookup — the users unique key.

    The identity primitive for auth, payment and canonical resolution. The same subject
    string can legitimately exist under several providers (a Toss userKey and an anonymous
    hash are different namespaces), so anything that decides ownership must say which one
    it means. Two rows are the same person only when a UserIdentityLink says so.
    """
    key = (subject or "").strip()
    if not key:
        return None
    return session.scalar(
        select(User).where(
            User.external_provider == (provider or "").strip().upper(),
            User.external_subject == key,
        )
    )


def get_or_create_user(session: Session, *, provider: str, subject: str) -> User:
    provider = (provider or "DEV").strip().upper()
    subject = (subject or "").strip()
    if not subject:
        raise ValueError("external_subject required")
    existing = session.scalar(
        select(User).where(
            User.external_provider == provider,
            User.external_subject == subject,
        )
    )
    now = datetime.now(timezone.utc)
    if existing:
        existing.last_seen_at = now
        session.flush()
        return existing
    user = User(external_provider=provider, external_subject=subject, created_at=now, last_seen_at=now)
    session.add(user)
    session.flush()
    return user
