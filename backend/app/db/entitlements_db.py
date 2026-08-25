"""PostgreSQL-backed entitlement provider (production SoT when DATABASE_URL set)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select

from .models import Entitlement
from .purchases import grant_from_purchase
from .session import session_scope
from .users import get_or_create_user, get_user_by_identity
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

    IDENTITY_PROVIDERS = ("TOSS", "TOSS_ANONYMOUS", "DEV")

    def _resolve_user(self, session, user_id: str, provider: Optional[str] = None):
        """The caller's own row, chosen by exact (provider, subject).

        Never the ambiguous cross-provider lookup: a Toss userKey and an anonymous hash
        can be the same string yet different people. When the caller states its provider
        that namespace is used outright; otherwise each namespace is probed exactly, in a
        fixed order, and at most ONE row is returned — enough to scope the caller's own
        data, never enough to fold two identities together.
        """
        if provider:
            namespace = provider.strip().upper()
            existing = get_user_by_identity(session, namespace, user_id)
            if existing is not None:
                return existing
            return get_or_create_user(session, provider=namespace, subject=user_id)
        for namespace in self.IDENTITY_PROVIDERS:
            existing = get_user_by_identity(session, namespace, user_id)
            if existing is not None:
                return existing
        return get_or_create_user(session, provider=self.provider_name, subject=user_id)

    def _grant_target(self, session, user_id: str, provider: Optional[str] = None):
        """Where a NEW entitlement is written.

        Explicitly canonical so one person cannot end up holding the same entitlement
        twice — once on their anonymous row, once on their verified row. Reads still union
        the group, so grants written before a link existed stay visible.
        """
        from .identity_links import resolve_canonical_user

        existing = self._resolve_user(session, user_id, provider)
        canonical = resolve_canonical_user(
            session, user_id, provider or (str(existing.external_provider) if existing else None)
        )
        if canonical is not None:
            return canonical
        return existing

    def _group_ids(self, session, user_id: str, fallback, provider: Optional[str] = None) -> list:
        """User rows of one canonical identity.

        Reads must union them: an entitlement bought before a verified login sits on the
        anonymous user, one bought after sits on the canonical user, and the old
        destructive migration may have left either on the (TOSS, userKey) row.
        """
        from .identity_links import identity_group_ids

        namespace = provider or (str(fallback.external_provider) if fallback is not None else None)
        ids = identity_group_ids(session, user_id, namespace)
        if fallback is not None and fallback.id not in ids:
            ids.append(fallback.id)
        return ids

    def has_unlock(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        entitlement_type: str,
        *,
        provider: Optional[str] = None,
    ) -> bool:
        with session_scope() as session:
            user = self._resolve_user(session, user_id, provider)
            group = self._group_ids(session, user_id, user, provider)
            row = session.scalar(
                select(Entitlement).where(
                    Entitlement.user_id.in_(group),
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
        provider: Optional[str] = None,
    ) -> dict[str, Any]:
        with session_scope() as session:
            user = self._grant_target(session, user_id, provider)
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

    def analysis_access(
        self, user_id: str, analysis_id: str, *, provider: Optional[str] = None
    ) -> dict[str, Any]:
        song = self.has_song_detail(user_id, analysis_id, provider=provider)
        linked = None
        diagnostic_unlocked = False
        with session_scope() as session:
            user = self._resolve_user(session, user_id, provider)
            group = self._group_ids(session, user_id, user, provider)
            from .models import Analysis, DiagnosticSession

            row = session.get(Analysis, analysis_id)
            if row and isinstance(row.public_summary, dict):
                linked = row.public_summary.get("diagnostic_session_id")
            sessions = session.scalars(
                select(DiagnosticSession)
                .where(
                    DiagnosticSession.user_id.in_(group),
                    DiagnosticSession.source_analysis_id == analysis_id,
                )
                .order_by(DiagnosticSession.created_at.desc())
            ).all()
            # A session is a workspace, never a receipt. Creating one — or abandoning a
            # purchase that created one — must not unlock anything. An ACTIVE DIAGNOSTIC
            # entitlement is the only unlock source.
            entitled_session_ids = set()
            candidate_ids = {str(s.id) for s in sessions}
            if linked:
                candidate_ids.add(str(linked))
            if candidate_ids:
                entitled_session_ids = {
                    str(e.resource_id)
                    for e in session.scalars(
                        select(Entitlement).where(
                            Entitlement.user_id.in_(group),
                            Entitlement.resource_type == RESOURCE_DIAGNOSTIC_SESSION,
                            Entitlement.resource_id.in_(candidate_ids),
                            Entitlement.entitlement_type == ENTITLEMENT_DIAGNOSTIC,
                            Entitlement.status == "ACTIVE",
                        )
                    ).all()
                }
            analysis_entitled = (
                session.scalar(
                    select(Entitlement).where(
                        Entitlement.user_id.in_(group),
                        Entitlement.resource_type == RESOURCE_ANALYSIS,
                        Entitlement.resource_id == analysis_id,
                        Entitlement.entitlement_type == ENTITLEMENT_DIAGNOSTIC,
                        Entitlement.status == "ACTIVE",
                    )
                )
                is not None
            )
            diagnostic_unlocked = analysis_entitled or bool(entitled_session_ids)
            # Prefer a paid session; never point the client at an unpaid one.
            paid = [s for s in sessions if str(s.id) in entitled_session_ids]
            if paid:
                linked = paid[0].id
            elif linked and str(linked) not in entitled_session_ids and not analysis_entitled:
                linked = None
            elif analysis_entitled and sessions and not paid:
                linked = sessions[0].id or linked
        return {
            "analysis_id": analysis_id,
            "song_detail_unlocked": song,
            "diagnostic_unlocked": diagnostic_unlocked,
            "diagnostic_session_id": linked if diagnostic_unlocked else None,
        }
