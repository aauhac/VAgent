"""Short-lived signed VAgent session tokens. Toss Access/Refresh tokens never enter this payload."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass

from .settings import SESSION_TTL_SECONDS, session_signing_secret


class SessionTokenError(Exception):
    pass


@dataclass(frozen=True)
class VAgentSession:
    jti: str
    subject: str
    toss_user_key: str
    provider: str
    iat: int
    exp: int


def _secret() -> bytes:
    raw = session_signing_secret()
    if not raw:
        # Dev-only fallback — production startup must require VAGENT_SESSION_SECRET
        raw = os.environ.get("VAGENT_SESSION_SECRET") or "dev-only-unverified-session-secret"
    return raw.encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    pad = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + pad)


def issue_session(*, toss_user_key: str, ttl_seconds: int = SESSION_TTL_SECONDS) -> tuple[str, VAgentSession]:
    now = int(time.time())
    payload = VAgentSession(
        jti=uuid.uuid4().hex,
        subject=str(toss_user_key),
        toss_user_key=str(toss_user_key),
        provider="TOSS",
        iat=now,
        exp=now + int(ttl_seconds),
    )
    body = json.dumps(
        {
            "jti": payload.jti,
            "sub": payload.subject,
            "toss_user_key": payload.toss_user_key,
            "provider": payload.provider,
            "iat": payload.iat,
            "exp": payload.exp,
            "v": 1,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    sig = hmac.new(_secret(), body, hashlib.sha256).digest()
    token = f"v1.{_b64url(body)}.{_b64url(sig)}"
    return token, payload


def verify_session(token: str) -> VAgentSession:
    raw = (token or "").strip()
    if not raw.startswith("v1."):
        raise SessionTokenError("malformed")
    parts = raw.split(".")
    if len(parts) != 3:
        raise SessionTokenError("malformed")
    try:
        body = _b64url_decode(parts[1])
        sig = _b64url_decode(parts[2])
    except Exception as exc:
        raise SessionTokenError("malformed") from exc
    expected = hmac.new(_secret(), body, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise SessionTokenError("invalid_signature")
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise SessionTokenError("malformed") from exc
    exp = int(data.get("exp") or 0)
    if exp < int(time.time()):
        raise SessionTokenError("expired")
    key = str(data.get("toss_user_key") or data.get("sub") or "").strip()
    if not key:
        raise SessionTokenError("missing_subject")
    return VAgentSession(
        jti=str(data.get("jti") or ""),
        subject=key,
        toss_user_key=key,
        provider=str(data.get("provider") or "TOSS"),
        iat=int(data.get("iat") or 0),
        exp=exp,
    )
