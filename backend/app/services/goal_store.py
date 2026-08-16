# -*- coding: utf-8 -*-
"""File-backed user vocal goals — history preserved on change (no delete)."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.app.config import get_runtime_dir
from backend.app.services.goal_catalog import (
    SOURCE_USER_SELECTED,
    normalize_goal_payload,
)

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UserGoalFileStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root or (get_runtime_dir() / "voice_identity"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "user_vocal_goals.json"
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def _read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_goals(self, external_subject: str) -> list[dict[str, Any]]:
        with _lock:
            data = self._read()
            rows = list(data.get(external_subject) or [])
            rows.sort(key=lambda g: g.get("started_at") or g.get("created_at") or "")
            return rows

    def get_active(self, external_subject: str) -> Optional[dict[str, Any]]:
        for g in reversed(self.list_goals(external_subject)):
            if g.get("status") == "ACTIVE":
                return g
        return None

    def set_goal(
        self,
        external_subject: str,
        *,
        focus: str,
        label: Optional[str] = None,
        source: str = SOURCE_USER_SELECTED,
        target: Optional[str] = None,
        style_id: Optional[str] = None,
        axis: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> dict[str, Any]:
        payload = normalize_goal_payload(
            {
                "focus": focus,
                "label": label,
                "source": source,
                "target": target,
                "style_id": style_id,
                "axis": axis,
                "kind": kind,
            }
        )
        if not payload:
            raise ValueError("INVALID_GOAL")
        with _lock:
            data = self._read()
            rows = list(data.get(external_subject) or [])
            now = _now()
            for g in rows:
                if g.get("status") == "ACTIVE":
                    g["status"] = "REPLACED"
                    g["ended_at"] = now
                    g["updated_at"] = now
            row = {
                "id": str(uuid.uuid4()),
                "external_subject": external_subject,
                "goal_type": payload.get("kind") or "FUNCTIONAL",
                "goal_focus": payload["focus"],
                "goal_label": payload.get("label") or focus,
                "source": source or SOURCE_USER_SELECTED,
                "status": "ACTIVE",
                "axis": payload.get("axis"),
                "target": payload.get("target"),
                "style_id": payload.get("style_id"),
                "kind": payload.get("kind"),
                "wording": payload.get("wording"),
                "started_at": now,
                "ended_at": None,
                "created_at": now,
                "updated_at": now,
            }
            rows.append(row)
            data[external_subject] = rows
            self._write(data)
            return row

    def complete_active(self, external_subject: str) -> Optional[dict[str, Any]]:
        with _lock:
            data = self._read()
            rows = list(data.get(external_subject) or [])
            now = _now()
            active = None
            for g in rows:
                if g.get("status") == "ACTIVE":
                    g["status"] = "COMPLETED"
                    g["ended_at"] = now
                    g["updated_at"] = now
                    active = g
            data[external_subject] = rows
            self._write(data)
            return active

    def pause_active(self, external_subject: str) -> Optional[dict[str, Any]]:
        with _lock:
            data = self._read()
            rows = list(data.get(external_subject) or [])
            now = _now()
            active = None
            for g in rows:
                if g.get("status") == "ACTIVE":
                    g["status"] = "PAUSED"
                    g["ended_at"] = now
                    g["updated_at"] = now
                    active = g
            data[external_subject] = rows
            self._write(data)
            return active


_goal_store: Optional[UserGoalFileStore] = None


def get_user_goal_store() -> UserGoalFileStore:
    global _goal_store
    if _goal_store is None:
        _goal_store = UserGoalFileStore()
    return _goal_store
