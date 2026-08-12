"""ORM models — production source of truth for metadata / entitlements."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
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

    analyses: Mapped[list["Analysis"]] = relationship(back_populates="user")


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

    user: Mapped[User] = relationship(back_populates="analyses")


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

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType, ForeignKey("users.id"), nullable=False, index=True)
    toss_order_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATED")
    status_determined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
