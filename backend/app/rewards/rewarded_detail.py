"""Rewarded-ad unlock for SONG_DETAIL — session + claim + Asia/Seoul daily limit.

Apps in Toss does not expose AdMob SSV callbacks in the web SDK.
Reward is gated by a one-time server session token created before show,
and claimed only after the client reports the official userEarnedReward event.
Client-asserted "watched=true" alone is never enough without a valid session.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.analysis_repo import get_user_by_subject
from ..db.models import Entitlement, RewardedAdClaim, RewardedAdDailySlot
from ..db.session import database_url, session_scope
from ..db.users import get_or_create_user
from ..entitlements import get_entitlement_provider
from ..entitlements.provider import (
    ENTITLEMENT_SONG_DETAIL,
    RESOURCE_ANALYSIS,
)
from ..identity import ResolvedIdentity

logger = logging.getLogger("vagent.rewarded_ad")

DAILY_LIMIT = 3
REWARD_TYPE_SONG_DETAIL = "SONG_DETAIL"
SESSION_TTL_SECONDS = 15 * 60
SEOUL = ZoneInfo("Asia/Seoul")
STATUS_PENDING = "pending"
STATUS_CLAIMED = "claimed"
STATUS_EXPIRED = "expired"
PRODUCT_SONG_DETAIL = "song_detail"


class RewardedAdError(Exception):
    def __init__(self, code: str, *, http_status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.http_status = http_status


def seoul_day(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(SEOUL).date().isoformat()


def principal_key(identity: ResolvedIdentity) -> str:
    provider = (identity.provider or "DEV").strip().upper()
    subject = (identity.subject or "").strip()
    if not subject:
        raise RewardedAdError("IDENTITY_REQUIRED", http_status=401)
    return f"{provider}:{subject}"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _status_payload(
    *,
    used_today: int,
    already_unlocked: bool,
    can_use: bool | None = None,
) -> dict[str, Any]:
    used = max(0, min(DAILY_LIMIT, int(used_today)))
    remaining = max(0, DAILY_LIMIT - used)
    if can_use is None:
        can_use = (not already_unlocked) and remaining > 0
    return {
        "daily_limit": DAILY_LIMIT,
        "used_today": used,
        "remaining_today": remaining,
        "already_unlocked": bool(already_unlocked),
        "can_use_rewarded_ad": bool(can_use),
        "reward_type": REWARD_TYPE_SONG_DETAIL,
    }


def _used_today_db(session: Session, pkey: str, day: str) -> int:
    from sqlalchemy import func

    return int(
        session.scalar(
            select(func.count())
            .select_from(RewardedAdDailySlot)
            .where(
                RewardedAdDailySlot.principal_key == pkey,
                RewardedAdDailySlot.seoul_day == day,
            )
        )
        or 0
    )


def _already_claimed_analysis(session: Session, analysis_id: str) -> RewardedAdClaim | None:
    return session.scalar(
        select(RewardedAdClaim).where(
            RewardedAdClaim.claimed_analysis_id == analysis_id,
            RewardedAdClaim.status == STATUS_CLAIMED,
            RewardedAdClaim.reward_type == REWARD_TYPE_SONG_DETAIL,
        )
    )


def _resolve_user(session: Session, identity: ResolvedIdentity):
    existing = get_user_by_subject(session, identity.subject)
    if existing is not None:
        return existing
    provider = (identity.provider or "DEV").strip().upper()
    return get_or_create_user(session, provider=provider, subject=identity.subject)


def _grant_song_detail_db(
    session: Session,
    *,
    user_id: uuid.UUID,
    analysis_id: str,
) -> Entitlement:
    existing = session.scalar(
        select(Entitlement).where(
            Entitlement.user_id == user_id,
            Entitlement.resource_type == RESOURCE_ANALYSIS,
            Entitlement.resource_id == analysis_id,
            Entitlement.entitlement_type == ENTITLEMENT_SONG_DETAIL,
            Entitlement.status == "ACTIVE",
        )
    )
    if existing is not None:
        return existing
    ent = Entitlement(
        user_id=user_id,
        resource_type=RESOURCE_ANALYSIS,
        resource_id=analysis_id,
        entitlement_type=ENTITLEMENT_SONG_DETAIL,
        product_id=PRODUCT_SONG_DETAIL,
        purchase_order_id=None,
        status="ACTIVE",
        granted_at=datetime.now(timezone.utc),
    )
    session.add(ent)
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(Entitlement).where(
                Entitlement.user_id == user_id,
                Entitlement.resource_type == RESOURCE_ANALYSIS,
                Entitlement.resource_id == analysis_id,
                Entitlement.entitlement_type == ENTITLEMENT_SONG_DETAIL,
                Entitlement.status == "ACTIVE",
            )
        )
        if existing is None:
            raise
        return existing
    return ent


def _consume_daily_slot(session: Session, pkey: str, day: str, claim_id: uuid.UUID) -> int:
    """Reserve next daily slot via unique insert (safe under concurrent SQLite/Postgres)."""
    now = datetime.now(timezone.utc)
    for slot_index in range(1, DAILY_LIMIT + 1):
        try:
            with session.begin_nested():
                session.add(
                    RewardedAdDailySlot(
                        principal_key=pkey,
                        seoul_day=day,
                        slot_index=slot_index,
                        claim_id=claim_id,
                        created_at=now,
                    )
                )
                session.flush()
            return slot_index
        except IntegrityError:
            continue
    raise RewardedAdError("DAILY_LIMIT_REACHED", http_status=429)


# --- file fallback (no DATABASE_URL) -------------------------------------------------

def _file_store(runtime_dir: Path) -> Path:
    path = runtime_dir / "rewarded_ad_claims.json"
    if not path.exists():
        path.write_text('{"sessions":{},"daily":{},"claimed_analyses":{}}', encoding="utf-8")
    return path


def _load_file(runtime_dir: Path) -> dict[str, Any]:
    import json

    try:
        data = json.loads(_file_store(runtime_dir).read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("sessions", {})
    data.setdefault("daily", {})
    data.setdefault("claimed_analyses", {})
    return data


def _save_file(runtime_dir: Path, data: dict[str, Any]) -> None:
    import json

    _file_store(runtime_dir).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def rewarded_ad_status(
    analysis_id: str,
    identity: ResolvedIdentity,
    *,
    already_unlocked: bool,
    runtime_dir: Path | None = None,
) -> dict[str, Any]:
    pkey = principal_key(identity)
    day = seoul_day()
    if database_url():
        with session_scope() as session:
            used = _used_today_db(session, pkey, day)
            claimed = _already_claimed_analysis(session, analysis_id) is not None
            unlocked = already_unlocked or claimed
            return _status_payload(used_today=used, already_unlocked=unlocked)
    from ..config import get_runtime_dir

    base = runtime_dir or get_runtime_dir()
    data = _load_file(base)
    used = int((data.get("daily") or {}).get(f"{pkey}:{day}") or 0)
    claimed = analysis_id in (data.get("claimed_analyses") or {})
    unlocked = already_unlocked or claimed
    return _status_payload(used_today=used, already_unlocked=unlocked)


def create_rewarded_session(
    analysis_id: str,
    identity: ResolvedIdentity,
    *,
    already_unlocked: bool,
    runtime_dir: Path | None = None,
) -> dict[str, Any]:
    status = rewarded_ad_status(
        analysis_id,
        identity,
        already_unlocked=already_unlocked,
        runtime_dir=runtime_dir,
    )
    if status["already_unlocked"]:
        raise RewardedAdError("ALREADY_UNLOCKED", http_status=409)
    if status["remaining_today"] <= 0:
        logger.info("[REWARDED_AD] daily_limit_reached")
        raise RewardedAdError("DAILY_LIMIT_REACHED", http_status=429)

    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=SESSION_TTL_SECONDS)
    day = seoul_day(now)
    pkey = principal_key(identity)

    if database_url():
        with session_scope() as session:
            if _already_claimed_analysis(session, analysis_id) is not None:
                raise RewardedAdError("ALREADY_UNLOCKED", http_status=409)
            user = _resolve_user(session, identity)
            claim = RewardedAdClaim(
                analysis_id=analysis_id,
                principal_key=pkey,
                principal_provider=(identity.provider or "DEV").strip().upper(),
                principal_subject=identity.subject,
                user_id=user.id,
                reward_type=REWARD_TYPE_SONG_DETAIL,
                claim_token_hash=token_hash,
                status=STATUS_PENDING,
                seoul_day=day,
                created_at=now,
                expires_at=expires,
            )
            session.add(claim)
            session.flush()
            logger.info("[REWARDED_AD] session_created")
            return {
                **status,
                "session_token": token,
                "expires_at": expires.isoformat(),
                "reward_type": REWARD_TYPE_SONG_DETAIL,
            }

    from ..config import get_runtime_dir

    base = runtime_dir or get_runtime_dir()
    data = _load_file(base)
    if analysis_id in (data.get("claimed_analyses") or {}):
        raise RewardedAdError("ALREADY_UNLOCKED", http_status=409)
    data["sessions"][token_hash] = {
        "analysis_id": analysis_id,
        "principal_key": pkey,
        "status": STATUS_PENDING,
        "seoul_day": day,
        "expires_at": expires.isoformat(),
        "created_at": now.isoformat(),
    }
    _save_file(base, data)
    logger.info("[REWARDED_AD] session_created")
    return {
        **status,
        "session_token": token,
        "expires_at": expires.isoformat(),
        "reward_type": REWARD_TYPE_SONG_DETAIL,
    }


def claim_rewarded_song_detail(
    analysis_id: str,
    identity: ResolvedIdentity,
    *,
    session_token: str,
    runtime_dir: Path | None = None,
) -> dict[str, Any]:
    token = (session_token or "").strip()
    if not token:
        raise RewardedAdError("SESSION_TOKEN_REQUIRED", http_status=400)
    token_hash = _hash_token(token)
    pkey = principal_key(identity)
    now = datetime.now(timezone.utc)
    day = seoul_day(now)

    if database_url():
        with session_scope() as session:
            claim = session.scalar(
                select(RewardedAdClaim)
                .where(RewardedAdClaim.claim_token_hash == token_hash)
                .with_for_update()
            )
            if claim is None:
                raise RewardedAdError("SESSION_NOT_FOUND", http_status=404)
            if claim.analysis_id != analysis_id:
                raise RewardedAdError("SESSION_MISMATCH", http_status=400)
            if claim.principal_key != pkey:
                raise RewardedAdError("SESSION_MISMATCH", http_status=403)
            if claim.reward_type != REWARD_TYPE_SONG_DETAIL:
                raise RewardedAdError("INVALID_REWARD_TYPE", http_status=400)

            if claim.status == STATUS_CLAIMED:
                logger.info("[REWARDED_AD] claim_duplicate")
                used = _used_today_db(session, pkey, day)
                return {
                    **_status_payload(used_today=used, already_unlocked=True),
                    "unlocked": True,
                    "duplicate": True,
                    "entitlement_type": ENTITLEMENT_SONG_DETAIL,
                }

            expires = claim.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < now or claim.status == STATUS_EXPIRED:
                claim.status = STATUS_EXPIRED
                session.flush()
                raise RewardedAdError("SESSION_EXPIRED", http_status=410)

            existing_claim = _already_claimed_analysis(session, analysis_id)
            if existing_claim is not None and existing_claim.id != claim.id:
                raise RewardedAdError("ALREADY_UNLOCKED", http_status=409)

            user = _resolve_user(session, identity)
            # Reserve daily slot before entitlement so concurrent claims cannot exceed 3.
            try:
                used = _consume_daily_slot(session, pkey, day, claim.id)
            except RewardedAdError:
                logger.info("[REWARDED_AD] daily_limit_reached")
                raise

            ent = _grant_song_detail_db(session, user_id=user.id, analysis_id=analysis_id)
            claim.status = STATUS_CLAIMED
            claim.claimed_analysis_id = analysis_id
            claim.entitlement_id = ent.id
            claim.rewarded_at = now
            claim.user_id = user.id
            try:
                with session.begin_nested():
                    session.flush()
            except IntegrityError as exc:
                # Lost race on claimed_analysis_id — treat as already unlocked.
                logger.info("[REWARDED_AD] claim_duplicate")
                raise RewardedAdError("ALREADY_UNLOCKED", http_status=409) from exc

            logger.info("[REWARDED_AD] claim_success")
            return {
                **_status_payload(used_today=used, already_unlocked=True),
                "unlocked": True,
                "duplicate": False,
                "entitlement_type": ENTITLEMENT_SONG_DETAIL,
                "entitlement_id": str(ent.id),
            }

    from ..config import get_runtime_dir

    base = runtime_dir or get_runtime_dir()
    data = _load_file(base)
    sessions = data.setdefault("sessions", {})
    rec = sessions.get(token_hash)
    if not isinstance(rec, dict):
        raise RewardedAdError("SESSION_NOT_FOUND", http_status=404)
    if rec.get("analysis_id") != analysis_id or rec.get("principal_key") != pkey:
        raise RewardedAdError("SESSION_MISMATCH", http_status=403)
    if rec.get("status") == STATUS_CLAIMED:
        logger.info("[REWARDED_AD] claim_duplicate")
        used = int((data.get("daily") or {}).get(f"{pkey}:{day}") or 0)
        return {
            **_status_payload(used_today=used, already_unlocked=True),
            "unlocked": True,
            "duplicate": True,
            "entitlement_type": ENTITLEMENT_SONG_DETAIL,
        }
    exp_raw = str(rec.get("expires_at") or "")
    try:
        expires = datetime.fromisoformat(exp_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RewardedAdError("SESSION_EXPIRED", http_status=410) from exc
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        rec["status"] = STATUS_EXPIRED
        _save_file(base, data)
        raise RewardedAdError("SESSION_EXPIRED", http_status=410)

    claimed = data.setdefault("claimed_analyses", {})
    if analysis_id in claimed:
        raise RewardedAdError("ALREADY_UNLOCKED", http_status=409)

    daily = data.setdefault("daily", {})
    daily_key = f"{pkey}:{day}"
    used = int(daily.get(daily_key) or 0)
    if used >= DAILY_LIMIT:
        logger.info("[REWARDED_AD] daily_limit_reached")
        raise RewardedAdError("DAILY_LIMIT_REACHED", http_status=429)

    ents = get_entitlement_provider(base)
    if not ents.has_song_detail(identity.subject, analysis_id):
        ents.grant_song_detail(
            identity.subject,
            analysis_id,
            f"rewarded_{uuid.uuid4().hex[:12]}",
            product_id=PRODUCT_SONG_DETAIL,
        )
    used += 1
    daily[daily_key] = used
    rec["status"] = STATUS_CLAIMED
    claimed[analysis_id] = {
        "principal_key": pkey,
        "rewarded_at": now.isoformat(),
        "seoul_day": day,
    }
    _save_file(base, data)
    logger.info("[REWARDED_AD] claim_success")
    return {
        **_status_payload(used_today=used, already_unlocked=True),
        "unlocked": True,
        "duplicate": False,
        "entitlement_type": ENTITLEMENT_SONG_DETAIL,
    }


def seoul_day_from_date(d: date) -> str:
    return d.isoformat()
