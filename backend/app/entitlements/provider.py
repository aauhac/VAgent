"""
Entitlement providers — permanent unlock per diagnostic session.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class EntitlementProvider(ABC):
    @abstractmethod
    def has_session_unlock(self, user_id: str, session_id: str) -> bool: ...

    @abstractmethod
    def grant_session_unlock(self, user_id: str, session_id: str, entitlement_id: str) -> None: ...


class MockEntitlementProvider(EntitlementProvider):
    """Dev/test only. Disabled when VAGENT_ENV=production."""

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

    def has_session_unlock(self, user_id: str, session_id: str) -> bool:
        data = self._load()
        return bool((data.get(user_id) or {}).get(session_id))

    def grant_session_unlock(self, user_id: str, session_id: str, entitlement_id: str) -> None:
        data = self._load()
        data.setdefault(user_id, {})[session_id] = {
            "entitlement_id": entitlement_id,
            "permanent": True,
        }
        self._save(data)


class TossIAPEntitlementProvider(EntitlementProvider):
    """Production stub — wire Apps in Toss IAP verification here."""

    def __init__(self, store_path: Path) -> None:
        # Persist verified unlocks server-side (permanent per session)
        self._fallback = MockEntitlementProvider(store_path)

    def has_session_unlock(self, user_id: str, session_id: str) -> bool:
        return self._fallback.has_session_unlock(user_id, session_id)

    def grant_session_unlock(self, user_id: str, session_id: str, entitlement_id: str) -> None:
        # TODO: verify IAP receipt via Apps in Toss server API before grant
        self._fallback.grant_session_unlock(user_id, session_id, entitlement_id)


def get_entitlement_provider(runtime_dir: Path) -> EntitlementProvider:
    env = (os.environ.get("VAGENT_ENV") or "development").lower()
    store = runtime_dir / "entitlements.json"
    if env == "production":
        return TossIAPEntitlementProvider(store)
    return MockEntitlementProvider(store)


def allow_dev_bypass() -> bool:
    env = (os.environ.get("VAGENT_ENV") or "development").lower()
    if env == "production":
        return False
    return (os.environ.get("ALLOW_MOCK_PREMIUM") or "true").lower() in ("1", "true", "yes")
