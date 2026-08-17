"""Toss login → server token exchange → VAgent session. Toss tokens never returned."""

from datetime import datetime, timezone
import base64
import hmac
import logging
import os

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db.auth_sessions import revoke_sessions_for_user_key
from ..db.models import AuthSession
from ..db.session import session_scope
from ..db.users import get_or_create_user
from ..payments.errors import PaymentError, http_payment_error
from ..payments.rate_limit import allow as rate_allow
from ..payments.session_tokens import issue_session
from ..payments.settings import SESSION_TTL_SECONDS
from ..payments.toss_clients import TossApiError, get_login_client
from ..identity import resolve_verified_session

logger = logging.getLogger("vagent.auth")

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class TossLoginBody(BaseModel):
    authorization_code: str = Field(min_length=8, max_length=2048)
    referrer: str = Field(default="DEFAULT", max_length=32)


def _client_key(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"auth:{ip}"


@router.post("/toss/login")
def toss_login(body: TossLoginBody, request: Request) -> dict:
    if not rate_allow(_client_key(request), max_hits=20):
        raise http_payment_error("RATE_LIMITED", "잠시 후 다시 시도해주세요.", 429)
    referrer = (body.referrer or "DEFAULT").strip().upper()
    if referrer not in ("DEFAULT", "SANDBOX"):
        referrer = "DEFAULT"
    client = get_login_client()
    try:
        tokens = client.exchange_code(body.authorization_code, referrer)
        access = tokens.get("accessToken")
        if not access:
            raise PaymentError("AUTH_FAILED", "로그인을 완료하지 못했어요.", 401)
        me = client.login_me(str(access))
    except TossApiError as exc:
        logger.info("toss_login_failed code=%s", exc.code)
        status = 503 if exc.retryable else 401
        raise http_payment_error("AUTH_FAILED", "로그인을 완료하지 못했어요.", status) from exc
    except PaymentError as exc:
        raise exc.as_http() from exc
    finally:
        # Toss tokens must not leak via locals in logs; drop references.
        tokens = None  # noqa: F841
        access = None  # noqa: F841

    user_key = me.get("userKey")
    if user_key is None or str(user_key).strip() == "":
        raise http_payment_error("AUTH_FAILED", "로그인을 완료하지 못했어요.", 401)
    toss_user_key = str(user_key)
    vagent_token, payload = issue_session(toss_user_key=toss_user_key)
    try:
        with session_scope() as session:
            user = get_or_create_user(session, provider="TOSS", subject=toss_user_key)
            user.auth_revoked_at = None
            session.add(
                AuthSession(
                    user_id=user.id,
                    jti=payload.jti,
                    toss_user_key=toss_user_key,
                    expires_at=datetime.fromtimestamp(payload.exp, tz=timezone.utc),
                )
            )
    except Exception:
        # Session row is best-effort when DATABASE_URL is set; token still authenticates.
        from ..config import database_url

        if database_url():
            logger.exception("auth_session_persist_failed")
    return {
        "authenticated": True,
        "session_token": vagent_token,
        "token_type": "Bearer",
        "expires_in": SESSION_TTL_SECONDS,
        "provider": "TOSS",
    }


@router.get("/me")
def auth_me(request: Request) -> dict:
    ident = resolve_verified_session(request)
    if ident is None or not ident.authenticated:
        raise http_payment_error("AUTH_REQUIRED", "로그인이 필요해요.", 401)
    return {
        "authenticated": True,
        "provider": ident.provider,
        "auth_method": ident.auth_method,
    }


_DISCONNECT_REFERRERS = frozenset({"UNLINK", "WITHDRAWAL_TERMS", "WITHDRAWAL_TOSS"})


class TossDisconnectBody(BaseModel):
    userKey: str | int
    referrer: str


def _require_disconnect_basic(request: Request) -> None:
    expected_user = (os.environ.get("TOSS_DISCONNECT_BASIC_USER") or "").strip()
    expected_pass = (os.environ.get("TOSS_DISCONNECT_BASIC_PASSWORD") or "").strip()
    if not expected_user or not expected_pass:
        raise HTTPException(status_code=503, detail="disconnect callback is not configured")
    header = request.headers.get("Authorization") or ""
    if not header.lower().startswith("basic "):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1].strip()).decode("utf-8")
        given_user, given_pass = decoded.split(":", 1)
    except Exception as exc:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"}) from exc
    if not (
        hmac.compare_digest(given_user, expected_user)
        and hmac.compare_digest(given_pass, expected_pass)
    ):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})


def _handle_toss_disconnect(user_key: str | int | None, referrer: str | None) -> JSONResponse:
    key = str(user_key or "").strip()
    ref = str(referrer or "").strip().upper()
    if not key or ref not in _DISCONNECT_REFERRERS:
        raise HTTPException(status_code=400, detail="invalid disconnect payload")
    # Session revoke only. Does not delete analyses, audio, or payment records.
    # WITHDRAWAL_TOSS is Toss-account deletion, not this service's 회원탈퇴.
    n = revoke_sessions_for_user_key(key)
    logger.info("toss_disconnect referrer=%s sessions_revoked=%s", ref, n)
    return JSONResponse({"ok": True})


@router.post("/toss/disconnect")
def toss_disconnect_post(request: Request, body: TossDisconnectBody) -> JSONResponse:
    """Official Apps in Toss login disconnect callback (POST JSON)."""
    _require_disconnect_basic(request)
    return _handle_toss_disconnect(body.userKey, body.referrer)


@router.get("/toss/disconnect")
def toss_disconnect_get(
    request: Request,
    userKey: str | None = Query(default=None),
    referrer: str | None = Query(default=None),
) -> JSONResponse:
    """Official Apps in Toss login disconnect callback (GET query)."""
    _require_disconnect_basic(request)
    return _handle_toss_disconnect(userKey, referrer)

