# -*- coding: utf-8 -*-
"""HTTP client for Singer Identity service — bounded timeout, fail-open friendly."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import httpx

from backend.app.config import (
    singer_identity_enabled,
    singer_identity_service_url,
    singer_identity_timeout_seconds,
)

logger = logging.getLogger(__name__)

# Never log full embedding vectors
_FORBIDDEN_LOG_KEYS = frozenset({"embedding", "embeddings", "centroid", "prototype_embedding"})


def _sanitize_for_log(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            k: ("<redacted>" if k.lower() in _FORBIDDEN_LOG_KEYS else _sanitize_for_log(v))
            for k, v in payload.items()
        }
    if isinstance(payload, list):
        return [_sanitize_for_log(x) for x in payload[:20]]
    return payload


class SingerIdentityUnavailable(Exception):
    """Service timeout / connection / HTTP error — callers must fail-open for analysis."""


class SingerIdentityClient:
    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (base_url or singer_identity_service_url()).rstrip("/")
        self.timeout = timeout if timeout is not None else singer_identity_timeout_seconds()

    def enabled(self) -> bool:
        return singer_identity_enabled()

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def health(self) -> dict[str, Any]:
        if not self.enabled():
            return {"status": "disabled"}
        try:
            with self._client() as c:
                r = c.get("/health")
                r.raise_for_status()
                return r.json()
        except Exception as e:
            raise SingerIdentityUnavailable(str(e)) from e

    def get_model_info(self) -> dict[str, Any]:
        try:
            with self._client() as c:
                r = c.get("/v1/model")
                r.raise_for_status()
                return r.json()
        except Exception as e:
            raise SingerIdentityUnavailable(str(e)) from e

    def create_subject(
        self,
        *,
        display_name: str = "내 음성 프로필",
        singer_id: Optional[str] = None,
        consented_enrollment: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "display_name": display_name,
            "consented_enrollment": consented_enrollment,
        }
        if singer_id:
            body["singer_id"] = singer_id
        try:
            with self._client() as c:
                r = c.post("/v1/singers", json=body)
                r.raise_for_status()
                return r.json()
        except Exception as e:
            raise SingerIdentityUnavailable(str(e)) from e

    def enroll_recording(self, singer_id: str, audio_path: Path) -> dict[str, Any]:
        try:
            with self._client() as c:
                with audio_path.open("rb") as f:
                    r = c.post(
                        f"/v1/singers/{singer_id}/enroll",
                        files=[("files", (audio_path.name, f, "application/octet-stream"))],
                    )
                r.raise_for_status()
                data = r.json()
                logger.info("singer enroll ok singer_id=%s payload=%s", singer_id, _sanitize_for_log(data))
                return data
        except Exception as e:
            raise SingerIdentityUnavailable(str(e)) from e

    def verify_recording(
        self,
        singer_id: str,
        audio_path: Path,
        *,
        include_shadow_k2: bool = False,
    ) -> dict[str, Any]:
        try:
            with self._client() as c:
                with audio_path.open("rb") as f:
                    data = {
                        "candidate_singer_id": singer_id,
                        "include_shadow_k2": "true" if include_shadow_k2 else "false",
                    }
                    r = c.post(
                        "/v1/verify",
                        data=data,
                        files={"file": (audio_path.name, f, "application/octet-stream")},
                    )
                r.raise_for_status()
                out = r.json()
                # strip any accidental embedding
                out.pop("embedding", None)
                return out
        except Exception as e:
            raise SingerIdentityUnavailable(str(e)) from e

    def get_profile(self, singer_id: str) -> dict[str, Any]:
        try:
            with self._client() as c:
                r = c.get(f"/v1/singers/{singer_id}")
                r.raise_for_status()
                out = r.json()
                if isinstance(out.get("profile"), dict):
                    out["profile"].pop("centroid", None)
                return out
        except Exception as e:
            raise SingerIdentityUnavailable(str(e)) from e

    def delete_profile(self, singer_id: str) -> dict[str, Any]:
        try:
            with self._client() as c:
                r = c.delete(f"/v1/singers/{singer_id}")
                r.raise_for_status()
                return r.json()
        except Exception as e:
            raise SingerIdentityUnavailable(str(e)) from e


def get_singer_identity_client() -> SingerIdentityClient:
    return SingerIdentityClient()
