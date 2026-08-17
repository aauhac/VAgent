"""PostgreSQL-backed entitlement provider (production SoT when DATABASE_URL set)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select

from .models import Entitlement
from .purchases import grant_from_purchase
from .session import session_scope
from .users import get_or_create_user
from ..entitlements.provider import (
    ENTITLEMENT_DIAGNOSTIC,
    ENTITLEMENT_SONG_DETAIL,
    EntitlementProvider,
    RESOURCE_ANALYSIS,
    RESOURCE_DIAGNOSTIC_SESSION,
)


class DatabaseEntitlementProvider(EntitlementProvider):
    def __init__(self, *, provider_name: str = "DEV") -> None:
        self.provider_name = provider_name

    def _resolve_user(self, session, user_id: str):
        from .analysis_repo import get_user_by_subject

        existing = get_user_by_subject(session, user_id)
        if existing is not None:
            return existing
        return get_or_create_user(session, provider=self.provider_name, subject=user_id)

    def has_unlock(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        entitlement_type: str,
    ) -> bool:
        with session_scope() as session:
            user = self._resolve_user(session, user_id)
            row = session.scalar(
                select(Entitlement).where(
                    Entitlement.user_id == user.id,
                    Entitlement.resource_type == resource_type,
                    Entitlement.resource_id == resource_id,
                    Entitlement.entitlement_type == entitlement_type,
                    Entitlement.status == "ACTIVE",
                )
            )
            return row is not None

    def grant_unlock(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        entitlement_type: str,
        entitlement_id: str,
        *,
        product_id: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        with session_scope() as session:
            user = self._resolve_user(session, user_id)
            # Idempotent via unique constraint + grant_from_purchase when order id present
            order_key = (meta or {}).get("toss_order_id") or entitlement_id
            order, ent, _created = grant_from_purchase(
                session,
                user_id=user.id,
                toss_order_id=str(order_key),
                product_id=product_id or entitlement_type.lower(),
                resource_type=resource_type,
                resource_id=resource_id,
                entitlement_type=entitlement_type,
                sku=product_id,
            )
            src = (meta or {}).get("source_analysis_id")
            if src and resource_type == RESOURCE_DIAGNOSTIC_SESSION:
                from .analysis_repo import set_analysis_diagnostic_link

                # deferred after commit — call outside
                self._pending_link = (str(src), resource_id)
            else:
                self._pending_link = None
            result = {
                "entitlement_id": str(ent.id),
                "entitlement_type": entitlement_type,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "permanent": True,
                "unlocked_at": (ent.granted_at or datetime.now(timezone.utc)).isoformat(),
                "product_id": product_id,
                "purchase_order_id": str(order.id),
                "meta": meta or {},
            }
        pending = getattr(self, "_pending_link", None)
        if pending:
            from .analysis_repo import set_analysis_diagnostic_link

            set_analysis_diagnostic_link(pending[0], pending[1])
            self._pending_link = None
        return result

    def link_diagnostic_session(self, user_id: str, analysis_id: str, session_id: str) -> None:
        from .analysis_repo import set_analysis_diagnostic_link

        set_analysis_diagnostic_link(analysis_id, session_id)

    def analysis_access(self, user_id: str, analysis_id: str) -> dict[str, Any]:
        song = self.has_song_detail(user_id, analysis_id)
        linked = None
        diagnostic_unlocked = False
        with session_scope() as session:
            user = self._resolve_user(session, user_id)
            from .models import Analysis, DiagnosticSession

            row = session.get(Analysis, analysis_id)
            if row and isinstance(row.public_summary, dict):
                linked = row.public_summary.get("diagnostic_session_id")
            sessions = session.scalars(
                select(DiagnosticSession)
                .where(
                    DiagnosticSession.user_id == user.id,
                    DiagnosticSession.source_analysis_id == analysis_id,
                )
                .order_by(DiagnosticSession.created_at.desc())
            ).all()
            if sessions:
                linked = sessions[0].id or linked
                diagnostic_unlocked = True
            if linked and not diagnostic_unlocked:
                diagnostic_unlocked = (
                    session.scalar(
                        select(Entitlement).where(
                            Entitlement.user_id == user.id,
                            Entitlement.resource_type == RESOURCE_DIAGNOSTIC_SESSION,
                            Entitlement.resource_id == str(linked),
                            Entitlement.entitlement_type == ENTITLEMENT_DIAGNOSTIC,
                            Entitlement.status == "ACTIVE",
                        )
                    )
                    is not None
                )
            if not diagnostic_unlocked:
                diagnostic_unlocked = (
                    session.scalar(
                        select(Entitlement).where(
                            Entitlement.user_id == user.id,
                            Entitlement.resource_type == RESOURCE_ANALYSIS,
                            Entitlement.resource_id == analysis_id,
                            Entitlement.entitlement_type == ENTITLEMENT_DIAGNOSTIC,
                            Entitlement.status == "ACTIVE",
                        )
                    )
                    is not None
                )
        return {
            "analysis_id": analysis_id,
            "song_detail_unlocked": song,
            "diagnostic_unlocked": diagnostic_unlocked,
            "diagnostic_session_id": linked if diagnostic_unlocked else linked,
        }
