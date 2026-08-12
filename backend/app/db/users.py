"""User identity persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import User


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
