# -*- coding: utf-8 -*-
"""File-backed voice profile / snapshot / shadow store (works without DATABASE_URL)."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.app.config import get_runtime_dir

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def profile_status_for_count(n: int) -> str:
    if n <= 0:
        return "NOT_ENROLLED"
    if n == 1:
        return "INITIAL"
    if n <= 4:
        return "DEVELOPING"
    return "EXPANDED"


class VoiceProfileFileStore:
    """RUNTIME_DIR/voice_identity/*.json — no raw ECAPA vectors."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root or (get_runtime_dir() / "voice_identity"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.profiles_path = self.root / "profiles.json"
        self.enrollments_path = self.root / "enrollments.json"
        self.snapshots_path = self.root / "snapshots.json"
        self.shadow_path = self.root / "shadow_events.json"
        if not self.profiles_path.exists():
            self.profiles_path.write_text("{}", encoding="utf-8")
        if not self.enrollments_path.exists():
            self.enrollments_path.write_text("[]", encoding="utf-8")
        if not self.snapshots_path.exists():
            self.snapshots_path.write_text("[]", encoding="utf-8")
        if not self.shadow_path.exists():
            self.shadow_path.write_text("[]", encoding="utf-8")

    def _read_json(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_profile(self, external_subject: str) -> Optional[dict[str, Any]]:
        with _lock:
            data = self._read_json(self.profiles_path)
            row = data.get(external_subject)
            if not row or row.get("deleted_at"):
                return None
            return row

    def upsert_profile(self, external_subject: str, patch: dict[str, Any]) -> dict[str, Any]:
        with _lock:
            data = self._read_json(self.profiles_path)
            row = data.get(external_subject) or {
                "id": str(uuid.uuid4()),
                "external_subject": external_subject,
                "singer_id": "",
                "status": "ACTIVE",
                "profile_status": "NOT_ENROLLED",
                "recording_count": 0,
                "profile_version": 0,
                "strategy": "CENTROID",
                "compatibility_state": "COMPATIBLE",
                "created_at": _now(),
            }
            row.update(patch)
            row["updated_at"] = _now()
            data[external_subject] = row
            self._write_json(self.profiles_path, data)
            return row

    def soft_delete_profile(self, external_subject: str) -> bool:
        with _lock:
            data = self._read_json(self.profiles_path)
            row = data.get(external_subject)
            if not row:
                return False
            row["deleted_at"] = _now()
            row["status"] = "DELETED"
            row["recording_count"] = 0
            row["profile_version"] = 0
            row["profile_status"] = "NOT_ENROLLED"
            data[external_subject] = row
            enrolls = [
                e for e in self._read_json(self.enrollments_path) if e.get("external_subject") != external_subject
            ]
            self._write_json(self.enrollments_path, enrolls)
            self._write_json(self.profiles_path, data)
            return True

    def list_enrollments(self, external_subject: str) -> list[dict[str, Any]]:
        with _lock:
            return [e for e in self._read_json(self.enrollments_path) if e.get("external_subject") == external_subject]

    def has_sha(self, external_subject: str, sha256: str) -> bool:
        return any(e.get("audio_sha256") == sha256 for e in self.list_enrollments(external_subject))

    def add_enrollment(self, row: dict[str, Any]) -> dict[str, Any]:
        with _lock:
            enrolls = self._read_json(self.enrollments_path)
            row = {**row, "id": row.get("id") or str(uuid.uuid4()), "created_at": row.get("created_at") or _now()}
            enrolls.append(row)
            self._write_json(self.enrollments_path, enrolls)
            return row

    def add_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        with _lock:
            snaps = self._read_json(self.snapshots_path)
            row = {**row, "id": row.get("id") or str(uuid.uuid4()), "created_at": row.get("created_at") or _now()}
            snaps.append(row)
            self._write_json(self.snapshots_path, snaps)
            return row

    def list_snapshots(self, external_subject: str) -> list[dict[str, Any]]:
        with _lock:
            snaps = [s for s in self._read_json(self.snapshots_path) if s.get("external_subject") == external_subject]
            snaps.sort(key=lambda s: s.get("created_at") or "")
            return snaps

    def add_shadow_event(self, row: dict[str, Any]) -> dict[str, Any]:
        for k in list(row.keys()):
            if "embedding" in k.lower():
                raise ValueError("raw embeddings forbidden in shadow events")
        with _lock:
            events = self._read_json(self.shadow_path)
            row = {**row, "id": row.get("id") or str(uuid.uuid4()), "created_at": row.get("created_at") or _now()}
            events.append(row)
            self._write_json(self.shadow_path, events)
            return row


_store: Optional[VoiceProfileFileStore] = None


def get_voice_profile_store() -> VoiceProfileFileStore:
    global _store
    if _store is None:
        _store = VoiceProfileFileStore()
    return _store
