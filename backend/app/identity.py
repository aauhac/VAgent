"""Backend identity resolution.

Client headers (X-User-Id / X-VAgent-User-Key) are IDENTIFIERS, not authentication proof.
TOSS_IDENTITY_TRUST_MODE cannot upgrade a forgeable header into a verified user.

Verified identity exists only after:
  appLogin authorizationCode → backend token exchange → login-me userKey → VAgent session.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from .config import is_production

USER_KEY_HEADER = "X-VAgent-User-Key"
USER_ID_HEADER = "X-User-Id"

TRUST_MODE_ENV = "TOSS_IDENTITY_TRUST_MODE"
TRUST_UNVERIFIED = "UNVERIFIED_CLIENT_SUBJECT"
TRUST_VERIFIED = "VERIFIED_TOSS_SUBJECT"


@dataclass(frozen=True)
class ResolvedIdentity:
    provider: str  # DEV | TOSS_ANONYMOUS | TOSS
    subject: str
    trust_mode: str
    authenticated: bool = False
    toss_user_key: str | None = None
    auth_method: str = "CLIENT_ASSERTED_HEADER"


def identity_trust_mode() -> str:
    """Configured env label. Does NOT mean the current request is verified."""
    raw = (os.environ.get(TRUST_MODE_ENV) or "").strip().upper()
    if raw in (TRUST_UNVERIFIED, TRUST_VERIFIED):
        return raw
    return TRUST_UNVERIFIED


def env_flag_cannot_verify_identity() -> bool:
    """True: setting VERIFIED_TOSS_SUBJECT does not authenticate headers."""
    return True


def _extract_bearer(request: Request | None) -> str | None:
    if request is None:
        return None
    header = request.headers.get("Authorization") or request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        return token or None
    cookie = request.cookies.get("vagent_session")
    return cookie or None


def resolve_verified_session(request: Request | None) -> ResolvedIdentity | None:
    token = _extract_bearer(request)
    if not token:
        return None
    from .payments.session_tokens import SessionTokenError, verify_session

    try:
        session = verify_session(token)
    except SessionTokenError:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "INVALID_SESSION",
                    "message": "로그인이 필요해요.",
                }
            },
        ) from None
    from .db.auth_sessions import session_token_is_revoked

    if session_token_is_revoked(
        jti=session.jti,
        toss_user_key=session.toss_user_key,
        iat=session.iat,
    ):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "INVALID_SESSION",
                    "message": "로그인이 필요해요.",
                }
            },
        )
    return ResolvedIdentity(
        provider="TOSS",
        subject=session.toss_user_key,
        trust_mode=TRUST_VERIFIED,
        authenticated=True,
        toss_user_key=session.toss_user_key,
        auth_method="VAGENT_SESSION",
    )


def resolve_identity_from_headers(
    *,
    x_user_id: str | None = None,
    x_vagent_user_key: str | None = None,
) -> ResolvedIdentity:
    """
    Resolve client-asserted subject.

    This is an IDENTIFIER, not an AUTHENTICATION PROOF.
    TOSS_IDENTITY_TRUST_MODE is ignored here — headers never become verified auth.
    Production must not fall back to demo-user.
    """
    subject = (x_vagent_user_key or x_user_id or "").strip()
    if not subject:
        if is_production():
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "code": "USER_IDENTITY_UNAVAILABLE",
                        "message": "사용자 식별에 실패했어요.",
                        "trust_mode": TRUST_UNVERIFIED,
                    }
                },
            )
        subject = "anon"

    if is_production() and subject == "demo-user":
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "DEMO_USER_FORBIDDEN",
                    "message": "production에서는 demo-user를 사용할 수 없어요.",
                    "trust_mode": TRUST_UNVERIFIED,
                }
            },
        )

    return ResolvedIdentity(
        provider="DEV" if not is_production() else "TOSS_ANONYMOUS",
        subject=subject,
        trust_mode=TRUST_UNVERIFIED,
        authenticated=False,
        toss_user_key=None,
        auth_method="CLIENT_ASSERTED_HEADER",
    )


def mask_subject(subject: str) -> str:
    s = subject or ""
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}…{s[-4:]}"


async def require_identity(
    request: Request,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias=USER_KEY_HEADER),
) -> ResolvedIdentity:
    session_ident = resolve_verified_session(request)
    if session_ident is not None:
        request.state.identity = session_ident
        return session_ident
    identity = resolve_identity_from_headers(
        x_user_id=x_user_id,
        x_vagent_user_key=x_vagent_user_key,
    )
    request.state.identity = identity
    return identity


async def require_authenticated_user(
    request: Request,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias=USER_KEY_HEADER),
) -> ResolvedIdentity:
    identity = await require_identity(request, x_user_id, x_vagent_user_key)
    if not identity.authenticated or not identity.toss_user_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "AUTH_REQUIRED",
                    "message": "로그인이 필요해요.",
                }
            },
        )
    return identity
