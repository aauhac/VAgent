"""Auth session revoke helpers. Never stores Toss access/refresh tokens."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from ..config import database_url
from .models import AuthSession, User
from .session import session_scope


def revoke_sessions_for_user_key(toss_user_key: str) -> int:
    """Revoke VAgent sessions for a Toss userKey. Does not delete analyses or payments."""
    key = str(toss_user_key or "").strip()
    if not key or not database_url():
        return 0
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        user = session.scalar(
            select(User).where(
                User.external_provider == "TOSS",
                User.external_subject == key,
            )
        )
        if user is not None:
            user.auth_revoked_at = now
        rows = list(
            session.scalars(
                select(AuthSession).where(
                    AuthSession.toss_user_key == key,
                    AuthSession.revoked_at.is_(None),
                )
            )
        )
        for row in rows:
            row.revoked_at = now
        return len(rows)


def clear_auth_revocation(toss_user_key: str) -> None:
    """Allow a new login after Toss reconnect."""
    key = str(toss_user_key or "").strip()
    if not key or not database_url():
        return
    with session_scope() as session:
        user = session.scalar(
            select(User).where(
                User.external_provider == "TOSS",
                User.external_subject == key,
            )
        )
        if user is not None:
            user.auth_revoked_at = None


def session_token_is_revoked(*, jti: str, toss_user_key: str, iat: int) -> bool:
    from ..config import is_production

    if not database_url():
        return False
    try:
        with session_scope() as session:
            if jti:
                row = session.scalar(select(AuthSession).where(AuthSession.jti == jti))
                if row is not None and row.revoked_at is not None:
                    return True
            user = session.scalar(
                select(User).where(
                    User.external_provider == "TOSS",
                    User.external_subject == str(toss_user_key),
                )
            )
            if user is not None and user.auth_revoked_at is not None:
                issued = datetime.fromtimestamp(int(iat), tz=timezone.utc)
                revoked_at = user.auth_revoked_at
                if revoked_at.tzinfo is None:
                    revoked_at = revoked_at.replace(tzinfo=timezone.utc)
                return issued <= revoked_at
            return False
    except Exception:
        return bool(is_production())
