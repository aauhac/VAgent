"""Anonymous to verified Toss user linking.

A free analysis is owned by (TOSS_ANONYMOUS | DEV, client-asserted hash). A purchase
runs as (TOSS, Toss-verified userKey). Without linking, the owner check in
payments.service._analysis_owned rejects the buyer's own analysis.

Security contract:
  - Only called AFTER Toss returns a verified userKey. Login failure links nothing.
  - The anonymous subject is a client-asserted IDENTIFIER, never treated as a userKey.
    It grants no authority it did not already grant: any request carrying that header
    already reads and writes that anonymous user's rows.
  - Data only ever moves anonymous -> verified. Rows already owned by a verified TOSS
    user are never moved, overwritten, or deleted.
  - Unique-constraint collisions keep the verified user's existing row and leave the
    anonymous row in place, so nothing is destroyed and nothing is duplicated.
  - Idempotent: a second login for the same pair finds nothing left to move.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Analysis,
    DiagnosticSession,
    Entitlement,
    PaymentIntent,
    PersonalVocalSnapshot,
    PurchaseOrder,
    RewardedAdClaim,
    RewardedAdDailySlot,
    SingerIdentityShadowEvent,
    User,
    UserVoiceProfile,
    VoiceProfileEnrollment,
)
from .users import get_or_create_user

logger = logging.getLogger("vagent.identity.link")

PROVIDER_TOSS = "TOSS"
# Providers a pre-login client can own rows under. TOSS is deliberately excluded.
ANONYMOUS_PROVIDERS = ("TOSS_ANONYMOUS", "DEV")

MAX_SUBJECT_LEN = 255

# Rewarded-ad daily cap; slot indices are 1..N (rewards.rewarded_detail._consume_daily_slot).
_DAILY_SLOT_MAX = 3


def _anonymous_users(session: Session, subject: str) -> list[User]:
    return list(
        session.scalars(
            select(User).where(
                User.external_provider.in_(ANONYMOUS_PROVIDERS),
                User.external_subject == subject,
            )
        )
    )


def _move_simple(session: Session, model, src_id: uuid.UUID, dst_id: uuid.UUID) -> int:
    rows = list(session.scalars(select(model).where(model.user_id == src_id)))
    for row in rows:
        row.user_id = dst_id
    return len(rows)


def _move_entitlements(session: Session, src_id: uuid.UUID, dst_id: uuid.UUID) -> tuple[int, int]:
    """Move entitlements the verified user does not already hold. Never duplicates."""
    taken = {
        (e.resource_type, e.resource_id, e.entitlement_type)
        for e in session.scalars(select(Entitlement).where(Entitlement.user_id == dst_id))
    }
    moved = skipped = 0
    for row in session.scalars(select(Entitlement).where(Entitlement.user_id == src_id)):
        key = (row.resource_type, row.resource_id, row.entitlement_type)
        if key in taken:
            skipped += 1
            continue
        row.user_id = dst_id
        taken.add(key)
        moved += 1
    return moved, skipped


def _move_voice_profile(session: Session, src_id: uuid.UUID, dst_id: uuid.UUID) -> int:
    """uq_user_voice_profiles_user: the verified user's own profile always wins."""
    if session.scalar(select(UserVoiceProfile).where(UserVoiceProfile.user_id == dst_id)):
        return 0
    return _move_simple(session, UserVoiceProfile, src_id, dst_id)


def _move_enrollments(session: Session, src_id: uuid.UUID, dst_id: uuid.UUID) -> int:
    """uq_voice_enrollment_user_sha: skip audio the verified user already enrolled."""
    taken = {
        e.audio_sha256
        for e in session.scalars(
            select(VoiceProfileEnrollment).where(VoiceProfileEnrollment.user_id == dst_id)
        )
    }
    moved = 0
    for row in session.scalars(
        select(VoiceProfileEnrollment).where(VoiceProfileEnrollment.user_id == src_id)
    ):
        if row.audio_sha256 in taken:
            continue
        row.user_id = dst_id
        taken.add(row.audio_sha256)
        moved += 1
    return moved


def _move_rewarded(session: Session, src: User, dst: User) -> tuple[int, int]:
    """Move rewarded-ad claims and the daily slots that cap them.

    Slots are re-indexed into the verified principal's free indices; anything beyond the
    daily cap is dropped, so merging can never hand back extra free unlocks.
    """
    src_pkey = f"{src.external_provider}:{src.external_subject}"
    dst_pkey = f"{dst.external_provider}:{dst.external_subject}"
    claims = 0
    for row in session.scalars(select(RewardedAdClaim).where(RewardedAdClaim.user_id == src.id)):
        row.user_id = dst.id
        row.principal_key = dst_pkey
        row.principal_provider = dst.external_provider
        row.principal_subject = dst.external_subject
        claims += 1

    slots = 0
    src_slots = list(
        session.scalars(
            select(RewardedAdDailySlot).where(RewardedAdDailySlot.principal_key == src_pkey)
        )
    )
    for row in src_slots:
        used = {
            s.slot_index
            for s in session.scalars(
                select(RewardedAdDailySlot).where(
                    RewardedAdDailySlot.principal_key == dst_pkey,
                    RewardedAdDailySlot.seoul_day == row.seoul_day,
                )
            )
        }
        free = next((i for i in range(1, _DAILY_SLOT_MAX + 1) if i not in used), None)
        if free is None:
            # Cap already saturated for that day: drop rather than grant a bonus slot.
            session.delete(row)
            session.flush()
            continue
        row.principal_key = dst_pkey
        row.slot_index = free
        session.flush()
        slots += 1
    return claims, slots


def link_anonymous_user_to_toss_user(
    session: Session,
    *,
    anonymous_subject: str | None,
    toss_user_key: str,
) -> dict[str, int]:
    """Migrate one anonymous identity's rows onto the verified Toss user.

    Runs inside the caller's transaction. Returns per-table move counts, never values.
    """
    verified_key = str(toss_user_key or "").strip()
    if not verified_key:
        raise ValueError("toss_user_key required")
    subject = str(anonymous_subject or "").strip()
    empty = {"analyses": 0, "entitlements": 0, "diagnostic_sessions": 0}
    if not subject or len(subject) > MAX_SUBJECT_LEN:
        return empty
    # A client asserting the verified key as its own anonymous hash shortcuts nothing.
    if subject == verified_key:
        return empty

    dst = get_or_create_user(session, provider=PROVIDER_TOSS, subject=verified_key)
    sources = _anonymous_users(session, subject)
    if not sources:
        return empty

    moved = {
        "analyses": 0,
        "entitlements": 0,
        "entitlements_skipped": 0,
        "diagnostic_sessions": 0,
        "payment_intents": 0,
        "purchase_orders": 0,
        "voice_profiles": 0,
        "voice_enrollments": 0,
        "vocal_snapshots": 0,
        "shadow_events": 0,
        "rewarded_claims": 0,
        "rewarded_slots": 0,
    }
    for src in sources:
        if src.id == dst.id:
            continue
        moved["analyses"] += _move_simple(session, Analysis, src.id, dst.id)
        ent_moved, ent_skipped = _move_entitlements(session, src.id, dst.id)
        moved["entitlements"] += ent_moved
        moved["entitlements_skipped"] += ent_skipped
        moved["diagnostic_sessions"] += _move_simple(session, DiagnosticSession, src.id, dst.id)
        moved["payment_intents"] += _move_simple(session, PaymentIntent, src.id, dst.id)
        moved["purchase_orders"] += _move_simple(session, PurchaseOrder, src.id, dst.id)
        moved["voice_profiles"] += _move_voice_profile(session, src.id, dst.id)
        moved["voice_enrollments"] += _move_enrollments(session, src.id, dst.id)
        moved["vocal_snapshots"] += _move_simple(session, PersonalVocalSnapshot, src.id, dst.id)
        moved["shadow_events"] += _move_simple(session, SingerIdentityShadowEvent, src.id, dst.id)
        claims, slots = _move_rewarded(session, src, dst)
        moved["rewarded_claims"] += claims
        moved["rewarded_slots"] += slots
        # AuthSession rows are bound to verified userKeys; an anonymous user never has one.
        src.last_seen_at = datetime.now(timezone.utc)

    session.flush()
    if any(value for key, value in moved.items() if key != "entitlements_skipped"):
        # Counts only. Never the anonymous hash or the userKey.
        logger.info(
            "identity_link analyses=%s entitlements=%s sessions=%s rewarded=%s",
            moved["analyses"],
            moved["entitlements"],
            moved["diagnostic_sessions"],
            moved["rewarded_claims"],
        )
    return moved
