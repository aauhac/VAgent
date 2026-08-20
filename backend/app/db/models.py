"""ORM models — production source of truth for metadata / entitlements."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# JSONB on Postgres; portable JSON elsewhere (tests)
JSONType = JSON().with_variant(JSONB(), "postgresql")
UUIDType = UUID(as_uuid=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("external_provider", "external_subject", name="uq_users_external"),)

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    external_provider: Mapped[str] = mapped_column(String(32), nullable=False)  # TOSS_ANONYMOUS | DEV
    external_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    auth_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    analyses: Mapped[list["Analysis"]] = relationship(back_populates="user")
    payment_intents: Mapped[list["PaymentIntent"]] = relationship(back_populates="user")
    auth_sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user")


class AnalysisCompletionNotification(Base):
    """Opt-in to send an analysis-complete smart message. Recipient key is never logged."""

    __tablename__ = "analysis_completion_notifications"

    analysis_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("analyses.id"), primary_key=True
    )
    recipient_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # ANON | TOSS_USER
    recipient_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="REQUESTED")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    analysis: Mapped["Analysis"] = relationship(back_populates="completion_notification")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analysis_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    separate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    audio_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_summary: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audio_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    worker_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    user: Mapped[User] = relationship(back_populates="analyses")
    completion_notification: Mapped["AnalysisCompletionNotification | None"] = relationship(
        back_populates="analysis", uselist=False
    )


class UserVoiceProfile(Base):
    """Maps VAgent user → opaque Singer Identity subject (no raw embeddings)."""

    __tablename__ = "user_voice_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_voice_profiles_user"),)

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("users.id"), nullable=False, index=True)
    external_subject: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    singer_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    profile_status: Mapped[str] = mapped_column(String(32), nullable=False, default="INITIAL")
    recording_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False, default="CENTROID")
    encoder_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    encoder_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compatibility_state: Mapped[str] = mapped_column(String(32), nullable=False, default="COMPATIBLE")
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VoiceProfileEnrollment(Base):
    __tablename__ = "voice_profile_enrollments"
    __table_args__ = (
        UniqueConstraint("user_id", "audio_sha256", name="uq_voice_enrollment_user_sha"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("users.id"), nullable=False, index=True)
    singer_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    recording_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audio_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_source: Mapped[str] = mapped_column(String(64), nullable=False, default="USER_EXPLICIT")
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    label_source: Mapped[str] = mapped_column(String(64), nullable=False, default="USER_ENROLLED")
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PersonalVocalSnapshot(Base):
    """Canonical HOW snapshot — separate from ECAPA WHO profile."""

    __tablename__ = "personal_vocal_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("users.id"), nullable=False, index=True)
    singer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    recording_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    diagnostic_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analyzer_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    canonical_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    goal_json: Mapped[dict | list | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SingerIdentityShadowEvent(Base):
    """CENTROID production vs K2 shadow — scores/decisions only, no raw embeddings."""

    __tablename__ = "singer_identity_shadow_events"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("users.id"), nullable=False, index=True)
    singer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recording_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    centroid_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    k2_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    k2_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    disagreement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DiagnosticSession(Base):
    __tablename__ = "diagnostic_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("users.id"), nullable=False, index=True)
    source_analysis_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("analyses.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATED")
    planner_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    protocol_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selected_tasks: Mapped[dict | list | None] = mapped_column(JSONType, nullable=True)
    unresolved_dimensions: Mapped[dict | list | None] = mapped_column(JSONType, nullable=True)
    diagnostic_offer: Mapped[dict | list | None] = mapped_column(JSONType, nullable=True)
    tasks_state: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    task_results: Mapped[dict | list | None] = mapped_column(JSONType, nullable=True)
    safety_answers: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    safety_flags: Mapped[dict | list | None] = mapped_column(JSONType, nullable=True)
    user_concerns: Mapped[dict | list | None] = mapped_column(JSONType, nullable=True)
    plan_rationale: Mapped[dict | list | None] = mapped_column(JSONType, nullable=True)
    final_diagnostic_profile: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    current_task_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entitlement_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiagnosticTaskAttempt(Base):
    __tablename__ = "diagnostic_task_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("diagnostic_sessions.id"), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    audio_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dimension_evidence: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Entitlement(Base):
    __tablename__ = "entitlements"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "resource_type",
            "resource_id",
            "entitlement_type",
            name="uq_entitlement_resource",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("users.id"), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entitlement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("purchase_orders.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("provider", "provider_order_id", name="uq_purchase_orders_provider_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("users.id"), nullable=False, index=True)
    toss_order_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="TOSS")
    provider_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    provider_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATED")
    status_determined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class PaymentIntent(Base):
    """Pre-purchase intent bound to verified user + product + resource. TTL: INTENT_TTL_SECONDS."""

    __tablename__ = "payment_intents"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("users.id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sku: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    toss_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped[User] = relationship(back_populates="payment_intents")


class AuthSession(Base):
    """VAgent session after server-side Toss token exchange. Never stores Toss tokens."""

    __tablename__ = "auth_sessions"
    __table_args__ = (UniqueConstraint("jti", name="uq_auth_sessions_jti"),)

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("users.id"), nullable=False, index=True)
    jti: Mapped[str] = mapped_column(String(64), nullable=False)
    toss_user_key: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped[User] = relationship(back_populates="auth_sessions")


class RewardedAdClaim(Base):
    """Pending/claimed rewarded-ad unlock for one analysis SONG_DETAIL."""

    __tablename__ = "rewarded_ad_claims"
    __table_args__ = (
        UniqueConstraint("claim_token_hash", name="uq_rewarded_ad_claim_token"),
        UniqueConstraint(
            "claimed_analysis_id",
            name="uq_rewarded_ad_claimed_analysis",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[str] = mapped_column(String(64), ForeignKey("analyses.id"), nullable=False, index=True)
    principal_key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    principal_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    principal_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, ForeignKey("users.id"), nullable=True, index=True)
    reward_type: Mapped[str] = mapped_column(String(32), nullable=False, default="SONG_DETAIL")
    claim_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    seoul_day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    # Set only when status=claimed so unique(claimed_analysis_id) allows multiple pendings.
    claimed_analysis_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entitlement_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, ForeignKey("entitlements.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RewardedAdDailySlot(Base):
    """One row per successful daily unlock slot (1..3). Unique insert enforces the cap."""

    __tablename__ = "rewarded_ad_daily_slots"
    __table_args__ = (
        UniqueConstraint("principal_key", "seoul_day", "slot_index", name="uq_rewarded_ad_daily_slot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    principal_key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    seoul_day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, ForeignKey("rewarded_ad_claims.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
