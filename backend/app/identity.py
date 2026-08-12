"""Backend identity resolution — client-asserted identifier boundary."""

from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from .config import is_production

USER_KEY_HEADER = "X-VAgent-User-Key"
USER_ID_HEADER = "X-User-Id"

# Production gate: header is NOT a verified auth proof unless Toss server verification lands.
TRUST_MODE_ENV = "TOSS_IDENTITY_TRUST_MODE"
TRUST_UNVERIFIED = "UNVERIFIED_CLIENT_SUBJECT"
TRUST_VERIFIED = "VERIFIED_TOSS_SUBJECT"


@dataclass(frozen=True)
class ResolvedIdentity:
    provider: str  # DEV | TOSS_ANONYMOUS
    subject: str
    trust_mode: str


def identity_trust_mode() -> str:
    raw = (os.environ.get(TRUST_MODE_ENV) or "").strip().upper()
    if raw in (TRUST_UNVERIFIED, TRUST_VERIFIED):
        return raw
    # Default: never claim verified auth from a forgeable header
    return TRUST_UNVERIFIED


def resolve_identity_from_headers(
    *,
    x_user_id: str | None = None,
    x_vagent_user_key: str | None = None,
) -> ResolvedIdentity:
    """
    Resolve client-asserted subject.

    This is an IDENTIFIER, not an AUTHENTICATION PROOF.
    Production must not fall back to demo-user.
    """
    trust = identity_trust_mode()
    subject = (x_vagent_user_key or x_user_id or "").strip()
    if not subject:
        if is_production():
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "code": "USER_IDENTITY_UNAVAILABLE",
                        "message": "사용자 식별에 실패했어요.",
                        "trust_mode": trust,
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
                    "trust_mode": trust,
                }
            },
        )

    provider = "TOSS_ANONYMOUS" if trust == TRUST_VERIFIED else "DEV"
    # Heuristic: if client sent via VAgent key in prod unverified mode, still DEV provider label
    if not is_production():
        provider = "DEV"
    return ResolvedIdentity(provider=provider, subject=subject, trust_mode=trust)


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
    identity = resolve_identity_from_headers(
        x_user_id=x_user_id,
        x_vagent_user_key=x_vagent_user_key,
    )
    request.state.identity = identity
    return identity
