# -*- coding: utf-8 -*-
"""Current-user voice profile: explicit enrollment, CENTROID verify, fail-open side signal."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any, Optional

from backend.app.config import (
    personal_vocal_baseline_enabled,
    singer_identity_enabled,
    singer_identity_enrollment_enabled,
    singer_identity_shadow_k2_enabled,
)
from backend.app.services.singer_identity_client import (
    SingerIdentityClient,
    SingerIdentityUnavailable,
    get_singer_identity_client,
)
from backend.app.services.voice_profile_store import (
    VoiceProfileFileStore,
    get_voice_profile_store,
    profile_status_for_count,
)

PRODUCTION_STRATEGY = "CENTROID"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class VoiceProfileService:
    def __init__(
        self,
        store: Optional[VoiceProfileFileStore] = None,
        client: Optional[SingerIdentityClient] = None,
    ):
        self.store = store or get_voice_profile_store()
        self.client = client or get_singer_identity_client()

    def get_status(self, external_subject: str) -> dict[str, Any]:
        enabled = singer_identity_enabled()
        if not enabled:
            return {
                "enabled": False,
                "enrollment_enabled": False,
                "enrolled": False,
                "profile_status": "NOT_ENROLLED",
                "recording_count": 0,
                "strategy": PRODUCTION_STRATEGY,
                "production_feature": "OFF",
            }
        row = self.store.get_profile(external_subject)
        if not row:
            return {
                "enabled": True,
                "enrollment_enabled": singer_identity_enrollment_enabled(),
                "enrolled": False,
                "profile_status": "NOT_ENROLLED",
                "recording_count": 0,
                "strategy": PRODUCTION_STRATEGY,
                "model_version": None,
                "profile_version": 0,
            }
        return {
            "enabled": True,
            "enrollment_enabled": singer_identity_enrollment_enabled(),
            "enrolled": True,
            "profile_status": row.get("profile_status") or profile_status_for_count(int(row.get("recording_count") or 0)),
            "recording_count": int(row.get("recording_count") or 0),
            "strategy": row.get("strategy") or PRODUCTION_STRATEGY,
            "model_version": row.get("encoder_version"),
            "profile_version": int(row.get("profile_version") or 0),
            "compatibility_state": row.get("compatibility_state") or "COMPATIBLE",
            # no singer_id in public status optional — keep for same-user ops internal use via enroll
            "singer_id": row.get("singer_id"),
        }

    def enroll(
        self,
        external_subject: str,
        audio_path: Path,
        *,
        consent: bool,
        consent_source: str = "USER_EXPLICIT",
        analysis_id: Optional[str] = None,
        recording_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if not singer_identity_enrollment_enabled():
            return {"status": "FEATURE_DISABLED", "error": "SINGER_IDENTITY_ENROLLMENT_ENABLED=false"}
        if not consent:
            return {"status": "CONSENT_REQUIRED", "error": "explicit consent required"}
        if not audio_path.exists():
            return {"status": "AUDIO_NOT_FOUND", "error": "audio path missing"}

        sha = _sha256_file(audio_path)
        if self.store.has_sha(external_subject, sha):
            row = self.store.get_profile(external_subject)
            return {
                "status": "DUPLICATE_SHA",
                "recording_count": int((row or {}).get("recording_count") or 0),
                "profile_status": (row or {}).get("profile_status") or "NOT_ENROLLED",
                "profile_version": int((row or {}).get("profile_version") or 0),
            }

        try:
            model = self.client.get_model_info()
        except SingerIdentityUnavailable as e:
            return {"status": "SERVICE_UNAVAILABLE", "error": str(e)}

        row = self.store.get_profile(external_subject)
        singer_id = (row or {}).get("singer_id")
        try:
            if not singer_id:
                singer_id = f"singer_{uuid.uuid4().hex[:16]}"
                self.client.create_subject(
                    display_name="내 음성 프로필",
                    singer_id=singer_id,
                    consented_enrollment=True,
                )
            self.client.enroll_recording(singer_id, audio_path)
        except SingerIdentityUnavailable as e:
            return {"status": "SERVICE_UNAVAILABLE", "error": str(e)}

        count = int((row or {}).get("recording_count") or 0) + 1
        version = int((row or {}).get("profile_version") or 0) + 1
        status = profile_status_for_count(count)
        encoder_version = model.get("model_version") or model.get("version")
        # incompatible embedding versions must not be mixed
        prev_ver = (row or {}).get("encoder_version")
        compat = "COMPATIBLE"
        if prev_ver and encoder_version and prev_ver != encoder_version:
            compat = "NEEDS_REENROLLMENT"

        self.store.upsert_profile(
            external_subject,
            {
                "singer_id": singer_id,
                "recording_count": count,
                "profile_version": version,
                "profile_status": status,
                "strategy": PRODUCTION_STRATEGY,
                "encoder_name": model.get("encoder_name") or model.get("name") or "ECAPA-TDNN",
                "encoder_version": encoder_version,
                "embedding_dim": model.get("embedding_dim") or model.get("dim"),
                "compatibility_state": compat,
                "consented_at": (row or {}).get("consented_at"),
                "deleted_at": None,
                "status": "ACTIVE",
            },
        )
        if not (row or {}).get("consented_at"):
            from datetime import datetime, timezone

            self.store.upsert_profile(
                external_subject,
                {"consented_at": datetime.now(timezone.utc).isoformat()},
            )

        self.store.add_enrollment(
            {
                "external_subject": external_subject,
                "singer_id": singer_id,
                "recording_id": recording_id,
                "analysis_id": analysis_id,
                "audio_sha256": sha,
                "consent_source": consent_source,
                "label_source": "USER_ENROLLED",
                "model_version": encoder_version,
                "profile_version": version,
            }
        )
        return {
            "status": "ENROLLED",
            "recording_count": count,
            "profile_status": status,
            "profile_version": version,
            "strategy": PRODUCTION_STRATEGY,
            "compatibility_state": compat,
        }

    def verify(
        self,
        external_subject: str,
        audio_path: Path,
        *,
        analysis_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Current-user verification only — never global cross-user identify."""
        if not singer_identity_enabled():
            return {"decision": "DISABLED", "strategy": PRODUCTION_STRATEGY}
        row = self.store.get_profile(external_subject)
        if not row or not row.get("singer_id"):
            return {"decision": "NO_PROFILE", "strategy": PRODUCTION_STRATEGY}
        if row.get("compatibility_state") == "NEEDS_REENROLLMENT":
            return {
                "decision": "UNAVAILABLE",
                "reason": "NEEDS_REENROLLMENT",
                "strategy": PRODUCTION_STRATEGY,
                "compatibility_state": "NEEDS_REENROLLMENT",
            }
        shadow = singer_identity_shadow_k2_enabled()
        try:
            result = self.client.verify_recording(
                row["singer_id"],
                audio_path,
                include_shadow_k2=shadow,
            )
        except SingerIdentityUnavailable as e:
            return {
                "decision": "UNAVAILABLE",
                "error": str(e),
                "strategy": PRODUCTION_STRATEGY,
            }

        # Production decision always CENTROID fields from service
        decision = result.get("decision") or "UNCERTAIN"
        similarity = float(result.get("similarity") or 0.0)
        out = {
            "decision": decision,
            "similarity": similarity,
            "confidence": result.get("confidence"),
            "strategy": PRODUCTION_STRATEGY,
            "model_version": result.get("model_version"),
            "profile_version": int(row.get("profile_version") or 0),
            "production_strategy": PRODUCTION_STRATEGY,
            "production_score": similarity,
            "production_decision": decision,
        }
        # Shadow K2 — must not change production decision
        if shadow:
            k2_score = result.get("shadow_k2_similarity")
            k2_decision = result.get("shadow_k2_decision")
            if k2_score is not None:
                disagreement = str(k2_decision) != str(decision)
                out.update(
                    {
                        "shadow_strategy": "K2",
                        "shadow_score": float(k2_score),
                        "shadow_decision": k2_decision,
                        "disagreement": disagreement,
                    }
                )
                self.store.add_shadow_event(
                    {
                        "external_subject": external_subject,
                        "singer_id": row["singer_id"],
                        "profile_version": int(row.get("profile_version") or 0),
                        "analysis_id": analysis_id,
                        "centroid_score": similarity,
                        "centroid_decision": decision,
                        "k2_score": float(k2_score),
                        "k2_decision": k2_decision,
                        "disagreement": disagreement,
                        "model_version": result.get("model_version"),
                    }
                )
        # Ensure K2 never overrides
        out["decision"] = out["production_decision"]
        out["strategy"] = PRODUCTION_STRATEGY
        return out

    def delete(self, external_subject: str) -> dict[str, Any]:
        row = self.store.get_profile(external_subject)
        singer_id = (row or {}).get("singer_id")
        service_deleted = False
        if singer_id and singer_identity_enabled():
            try:
                self.client.delete_profile(singer_id)
                service_deleted = True
            except SingerIdentityUnavailable:
                # still remove local mapping
                service_deleted = False
        mapping_deleted = self.store.soft_delete_profile(external_subject)
        return {
            "deleted": mapping_deleted,
            "singer_embeddings_deleted": service_deleted,
            "vagent_mapping_deleted": mapping_deleted,
            "unrelated_history_deleted": False,
            "note": "Voice profile delete ≠ delete all vocal analysis history",
        }

    def maybe_verify_after_analysis(
        self,
        external_subject: str,
        audio_path: Optional[Path],
        *,
        analysis_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Fail-open optional side signal — never raises into analysis pipeline."""
        try:
            if not singer_identity_enabled() or audio_path is None or not Path(audio_path).exists():
                return {"decision": "DISABLED" if not singer_identity_enabled() else "SKIPPED"}
            return self.verify(external_subject, Path(audio_path), analysis_id=analysis_id)
        except Exception as e:
            return {"decision": "UNAVAILABLE", "error": str(e), "strategy": PRODUCTION_STRATEGY}

    def identity_context_block(self, verify_result: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not singer_identity_enabled():
            return None
        vr = verify_result or {}
        decision = vr.get("decision") or "NO_PROFILE"
        comparison_available = (
            personal_vocal_baseline_enabled()
            and decision == "MATCH"
        )
        return {
            "enabled": True,
            "status": decision,
            "profile_status": vr.get("profile_status"),
            "comparison_available": comparison_available,
            "strategy": PRODUCTION_STRATEGY,
        }


def get_voice_profile_service() -> VoiceProfileService:
    return VoiceProfileService()
