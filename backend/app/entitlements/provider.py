"""
Entitlement providers — permanent unlock per resource.

resource_type: ANALYSIS | DIAGNOSTIC_SESSION
entitlement_type: SONG_DETAIL | DIAGNOSTIC
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


RESOURCE_ANALYSIS = "ANALYSIS"
RESOURCE_DIAGNOSTIC_SESSION = "DIAGNOSTIC_SESSION"

ENTITLEMENT_SONG_DETAIL = "SONG_DETAIL"
ENTITLEMENT_DIAGNOSTIC = "DIAGNOSTIC"


class EntitlementProvider(ABC):
    @abstractmethod
    def has_unlock(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        entitlement_type: str,
    ) -> bool: ...

    @abstractmethod
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
    ) -> dict[str, Any]: ...

    # Back-compat wrappers used by diagnostic service
    def has_session_unlock(self, user_id: str, session_id: str) -> bool:
        return self.has_unlock(
            user_id, RESOURCE_DIAGNOSTIC_SESSION, session_id, ENTITLEMENT_DIAGNOSTIC
        )

    def grant_session_unlock(self, user_id: str, session_id: str, entitlement_id: str) -> None:
        self.grant_unlock(
            user_id,
            RESOURCE_DIAGNOSTIC_SESSION,
            session_id,
            ENTITLEMENT_DIAGNOSTIC,
            entitlement_id,
            product_id="diagnostic_full",
        )

    def has_song_detail(self, user_id: str, analysis_id: str) -> bool:
        return self.has_unlock(
            user_id, RESOURCE_ANALYSIS, analysis_id, ENTITLEMENT_SONG_DETAIL
        )

    def grant_song_detail(
        self,
        user_id: str,
        analysis_id: str,
        entitlement_id: str,
        *,
        product_id: str = "song_detail",
    ) -> dict[str, Any]:
        return self.grant_unlock(
            user_id,
            RESOURCE_ANALYSIS,
            analysis_id,
            ENTITLEMENT_SONG_DETAIL,
            entitlement_id,
            product_id=product_id,
        )

    def analysis_access(self, user_id: str, analysis_id: str) -> dict[str, Any]:
        data = self._user_blob(user_id) if hasattr(self, "_user_blob") else {}
        analyses = (data.get("analyses") or {}) if isinstance(data, dict) else {}
        if not isinstance(analyses, dict):
            analyses = {}
        sessions = (data.get("sessions") or {}) if isinstance(data, dict) else {}
        if not isinstance(sessions, dict):
            sessions = {}
        analyses_rec = analyses.get(analysis_id)
        if not isinstance(analyses_rec, dict):
            analyses_rec = {}
        linked = analyses_rec.get("diagnostic_session_id")
        diagnostic_unlocked = False
        if linked and linked in sessions and isinstance(sessions.get(linked), dict):
            diagnostic_unlocked = True
        # also scan sessions for source link stored in meta
        if not diagnostic_unlocked:
            for sid, rec in sessions.items():
                if not isinstance(rec, dict):
                    continue
                meta = rec.get("meta") if isinstance(rec.get("meta"), dict) else {}
                if meta.get("source_analysis_id") == analysis_id:
                    diagnostic_unlocked = True
                    linked = sid
                    break
        return {
            "analysis_id": analysis_id,
            "song_detail_unlocked": self.has_song_detail(user_id, analysis_id),
            "diagnostic_unlocked": diagnostic_unlocked,
            "diagnostic_session_id": linked if diagnostic_unlocked else analyses_rec.get("diagnostic_session_id"),
        }


class MockEntitlementProvider(EntitlementProvider):
    """Dev/test only. Disabled when VAGENT_ENV=production for mock grant endpoints."""

    def __init__(self, store_path: Path) -> None:
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.exists():
            self.store_path.write_text("{}", encoding="utf-8")

    def _load(self) -> dict:
        try:
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        self.store_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _user_blob(self, user_id: str) -> dict[str, Any]:
        raw = self._load().get(user_id)
        if not raw:
            return {"sessions": {}, "analyses": {}}
        if not isinstance(raw, dict):
            return {"sessions": {}, "analyses": {}}
        if "sessions" in raw or "analyses" in raw:
            sessions = raw.get("sessions") or {}
            analyses = raw.get("analyses") or {}
            return {
                "sessions": dict(sessions) if isinstance(sessions, dict) else {},
                "analyses": dict(analyses) if isinstance(analyses, dict) else {},
            }
        # Legacy flat map: session_id → record
        return {"sessions": dict(raw), "analyses": {}}

    def _write_user(self, user_id: str, blob: dict[str, Any]) -> None:
        data = self._load()
        data[user_id] = blob
        self._save(data)

    def has_unlock(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        entitlement_type: str,
    ) -> bool:
        blob = self._user_blob(user_id)
        if resource_type == RESOURCE_DIAGNOSTIC_SESSION:
            rec = (blob.get("sessions") or {}).get(resource_id)
            return bool(rec)
        if resource_type == RESOURCE_ANALYSIS:
            rec = (blob.get("analyses") or {}).get(resource_id) or {}
            if not isinstance(rec, dict):
                return False
            if entitlement_type == ENTITLEMENT_SONG_DETAIL:
                return bool(rec.get(ENTITLEMENT_SONG_DETAIL) or rec.get("song_detail_unlocked"))
        return False

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
        blob = self._user_blob(user_id)
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "entitlement_id": entitlement_id,
            "entitlement_type": entitlement_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "permanent": True,
            "unlocked_at": now,
            "product_id": product_id,
            "meta": meta or {},
        }
        if resource_type == RESOURCE_DIAGNOSTIC_SESSION:
            # idempotent
            existing = (blob.get("sessions") or {}).get(resource_id)
            if existing:
                return existing
            blob.setdefault("sessions", {})[resource_id] = record
            src = (meta or {}).get("source_analysis_id")
            if src:
                a = blob.setdefault("analyses", {}).setdefault(src, {})
                a["diagnostic_session_id"] = resource_id
        elif resource_type == RESOURCE_ANALYSIS and entitlement_type == ENTITLEMENT_SONG_DETAIL:
            a = blob.setdefault("analyses", {}).setdefault(resource_id, {})
            if a.get(ENTITLEMENT_SONG_DETAIL):
                return a[ENTITLEMENT_SONG_DETAIL]
            a[ENTITLEMENT_SONG_DETAIL] = record
            a["song_detail_unlocked"] = True
        self._write_user(user_id, blob)
        return record

    def link_diagnostic_session(
        self, user_id: str, analysis_id: str, session_id: str
    ) -> None:
        blob = self._user_blob(user_id)
        a = blob.setdefault("analyses", {}).setdefault(analysis_id, {})
        a["diagnostic_session_id"] = session_id
        self._write_user(user_id, blob)


class TossIAPEntitlementProvider(EntitlementProvider):
    """Production stub — wire Apps in Toss IAP verification here."""

    def __init__(self, store_path: Path) -> None:
        self._fallback = MockEntitlementProvider(store_path)

    def has_unlock(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        entitlement_type: str,
    ) -> bool:
        return self._fallback.has_unlock(
            user_id, resource_type, resource_id, entitlement_type
        )

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
        # TODO: verify IAP receipt via Apps in Toss server API before grant
        return self._fallback.grant_unlock(
            user_id,
            resource_type,
            resource_id,
            entitlement_type,
            entitlement_id,
            product_id=product_id,
            meta=meta,
        )

    def _user_blob(self, user_id: str) -> dict[str, Any]:
        return self._fallback._user_blob(user_id)

    def link_diagnostic_session(
        self, user_id: str, analysis_id: str, session_id: str
    ) -> None:
        self._fallback.link_diagnostic_session(user_id, analysis_id, session_id)


def get_entitlement_provider(runtime_dir: Path | None = None) -> EntitlementProvider:
    from ..config import database_url, get_environment, get_runtime_dir

    # PostgreSQL is SoT whenever DATABASE_URL is configured
    if database_url():
        from ..db.entitlements_db import DatabaseEntitlementProvider

        return DatabaseEntitlementProvider(provider_name="DEV")

    env = get_environment()
    base = runtime_dir if runtime_dir is not None else get_runtime_dir()
    store = Path(base) / "entitlements.json"
    if env == "production":
        # Production without DATABASE_URL should fail at startup; keep Toss stub for safety
        return TossIAPEntitlementProvider(store)
    return MockEntitlementProvider(store)


def allow_dev_bypass() -> bool:
    env = (os.environ.get("VAGENT_ENV") or "development").lower()
    if env == "production":
        return False
    return (os.environ.get("ALLOW_MOCK_PREMIUM") or "true").lower() in ("1", "true", "yes")
