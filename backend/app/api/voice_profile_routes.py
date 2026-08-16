# -*- coding: utf-8 -*-
"""Current-user voice profile & personal vocal progress APIs (feature-flagged)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.app.config import (
    get_runtime_dir,
    personal_vocal_baseline_enabled,
    singer_identity_enabled,
    singer_identity_enrollment_enabled,
)
from backend.app.identity import resolve_identity_from_headers
from backend.app.services.goal_catalog import (
    SOURCE_USER_SELECTED,
    list_user_goal_catalog,
    normalize_goal_payload,
)
from backend.app.services.goal_progress import build_goal_progress
from backend.app.services.goal_store import get_user_goal_store
from backend.app.services.personal_vocal_baseline import (
    compare_progress,
    extract_canonical,
)
from backend.app.services.progress_insight import build_progress_insight
from backend.app.services.voice_profile import get_voice_profile_service
from backend.app.services.voice_profile_store import get_voice_profile_store

router = APIRouter(prefix="/v1/me", tags=["voice-profile"])


def _subject(
    x_user_id: str | None = None,
    x_vagent_user_key: str | None = None,
) -> str:
    return resolve_identity_from_headers(
        x_user_id=x_user_id,
        x_vagent_user_key=x_vagent_user_key,
    ).subject


class EnrollBody(BaseModel):
    analysis_id: Optional[str] = None
    consent: bool = False
    consent_source: str = "USER_EXPLICIT"


class VerifyBody(BaseModel):
    analysis_id: Optional[str] = None


class SnapshotBody(BaseModel):
    analysis_id: Optional[str] = None
    canonical: dict[str, Any] = Field(default_factory=dict)
    analyzer_version: Optional[str] = None
    analysis_quality: Optional[str] = None
    goal: Optional[Any] = None
    goal_id_at_analysis: Optional[str] = None
    goal_focus_at_analysis: Optional[str] = None


class GoalSetBody(BaseModel):
    focus: str
    label: Optional[str] = None
    source: str = SOURCE_USER_SELECTED
    target: Optional[str] = None
    style_id: Optional[str] = None


class ProgressBody(BaseModel):
    current_canonical: dict[str, Any] = Field(default_factory=dict)
    goal: Optional[Any] = None
    recent_n: int = 5
    # If set, exclude this snapshot id / analysis_id from baseline
    exclude_analysis_id: Optional[str] = None


def _resolve_analysis_audio(analysis_id: str) -> Path:
    """Resolve audio from runtime analysis dir — no client path input."""
    root = get_runtime_dir() / analysis_id
    for name in ("input_converted.wav", "input.wav", "preview.wav"):
        p = root / name
        if p.exists():
            return p
    # common nested layout
    for p in root.rglob("input_converted.wav"):
        return p
    raise HTTPException(status_code=404, detail="ANALYSIS_AUDIO_NOT_FOUND")


@router.get("/voice-profile")
def get_voice_profile(
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict[str, Any]:
    subject = _subject(x_user_id, x_vagent_user_key)
    status = get_voice_profile_service().get_status(subject)
    # Hide opaque singer_id from casual clients unless enrolled ops need it — keep for same-user
    return status


@router.post("/voice-profile/enroll")
def enroll_voice_profile(
    body: EnrollBody,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict[str, Any]:
    if not singer_identity_enrollment_enabled():
        raise HTTPException(status_code=404, detail="FEATURE_DISABLED")
    if not body.consent:
        raise HTTPException(status_code=400, detail="CONSENT_REQUIRED")
    if not body.analysis_id:
        raise HTTPException(status_code=400, detail="ANALYSIS_ID_REQUIRED")
    subject = _subject(x_user_id, x_vagent_user_key)
    audio = _resolve_analysis_audio(body.analysis_id)
    result = get_voice_profile_service().enroll(
        subject,
        audio,
        consent=True,
        consent_source=body.consent_source,
        analysis_id=body.analysis_id,
        recording_id=body.analysis_id,
    )
    if result.get("status") == "SERVICE_UNAVAILABLE":
        raise HTTPException(status_code=503, detail="SERVICE_UNAVAILABLE")
    return result


@router.post("/voice-profile/verify")
def verify_voice_profile(
    body: VerifyBody,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict[str, Any]:
    if not singer_identity_enabled():
        raise HTTPException(status_code=404, detail="FEATURE_DISABLED")
    if not body.analysis_id:
        raise HTTPException(status_code=400, detail="ANALYSIS_ID_REQUIRED")
    subject = _subject(x_user_id, x_vagent_user_key)
    audio = _resolve_analysis_audio(body.analysis_id)
    return get_voice_profile_service().verify(subject, audio, analysis_id=body.analysis_id)


@router.delete("/voice-profile")
def delete_voice_profile(
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict[str, Any]:
    if not singer_identity_enabled():
        raise HTTPException(status_code=404, detail="FEATURE_DISABLED")
    subject = _subject(x_user_id, x_vagent_user_key)
    return get_voice_profile_service().delete(subject)


@router.post("/vocal-snapshots")
def create_vocal_snapshot(
    body: SnapshotBody,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict[str, Any]:
    if not personal_vocal_baseline_enabled():
        raise HTTPException(status_code=404, detail="FEATURE_DISABLED")
    subject = _subject(x_user_id, x_vagent_user_key)
    canonical = extract_canonical(body.canonical) if body.canonical else {}
    if not canonical:
        raise HTTPException(status_code=400, detail="CANONICAL_REQUIRED")
    profile = get_voice_profile_store().get_profile(subject)
    active = get_user_goal_store().get_active(subject)
    goal_id = body.goal_id_at_analysis or (active or {}).get("id")
    goal_focus = body.goal_focus_at_analysis or (active or {}).get("goal_focus")
    # Historical mutation forbidden: stamp current active goal only; never rewrite older snaps
    row = get_voice_profile_store().add_snapshot(
        {
            "external_subject": subject,
            "singer_id": (profile or {}).get("singer_id"),
            "analysis_id": body.analysis_id,
            "recording_id": body.analysis_id,
            "analyzer_version": body.analyzer_version,
            "analysis_quality": body.analysis_quality,
            "canonical_json": canonical,
            "goal_json": body.goal or active,
            "goal_id_at_analysis": goal_id,
            "goal_focus_at_analysis": goal_focus,
        }
    )
    # never return embeddings
    return {
        "status": "CREATED",
        "snapshot_id": row["id"],
        "analyzer_version": body.analyzer_version,
        "goal_id_at_analysis": goal_id,
    }


@router.get("/vocal-progress")
def get_vocal_progress(
    recent_n: int = 5,
    goal: str | None = None,
    exclude_analysis_id: str | None = None,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict[str, Any]:
    if not personal_vocal_baseline_enabled():
        raise HTTPException(status_code=404, detail="FEATURE_DISABLED")
    subject = _subject(x_user_id, x_vagent_user_key)
    snaps = get_voice_profile_store().list_snapshots(subject)
    if not snaps:
        return {"status": "NO_BASELINE", "history_count": 0}
    current = snaps[-1]
    if exclude_analysis_id:
        historical = [s for s in snaps if s.get("analysis_id") != exclude_analysis_id]
        current_candidates = [s for s in snaps if s.get("analysis_id") == exclude_analysis_id]
        current = current_candidates[-1] if current_candidates else current
    else:
        historical = snaps[:-1]
    current_can = current.get("canonical_json") or {}
    result = compare_progress(
        current_canonical=current_can,
        historical_snapshots=historical,
        goal=goal,
        recent_n=recent_n,
    )
    return result


@router.post("/vocal-progress")
def post_vocal_progress(
    body: ProgressBody,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict[str, Any]:
    if not personal_vocal_baseline_enabled():
        raise HTTPException(status_code=404, detail="FEATURE_DISABLED")
    subject = _subject(x_user_id, x_vagent_user_key)
    snaps = get_voice_profile_store().list_snapshots(subject)
    historical = snaps
    if body.exclude_analysis_id:
        historical = [s for s in snaps if s.get("analysis_id") != body.exclude_analysis_id]
    current = extract_canonical(body.current_canonical) or body.current_canonical
    return compare_progress(
        current_canonical=current,
        historical_snapshots=historical,
        goal=body.goal,
        recent_n=body.recent_n,
    )


class InsightBody(BaseModel):
    current_canonical: dict[str, Any] = Field(default_factory=dict)
    goal: Optional[Any] = None
    recent_n: int = 5
    exclude_analysis_id: Optional[str] = None
    today_highlights: Optional[list[dict[str, str]]] = None


@router.post("/vocal-progress/insight")
def post_vocal_progress_insight(
    body: InsightBody,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict[str, Any]:
    """
    Progress Insight cards for the Result loop.
    Soft-empty when baseline disabled or history missing — never 500.
    """
    subject = _subject(x_user_id, x_vagent_user_key)
    current = extract_canonical(body.current_canonical) or body.current_canonical
    active = get_user_goal_store().get_active(subject)
    goal = body.goal or active

    if not personal_vocal_baseline_enabled():
        gp = build_goal_progress(
            goal=goal,
            historical_snapshots=[],
            current_canonical=current or {},
            recent_n=body.recent_n,
        )
        out = build_progress_insight(
            current_canonical=current or {},
            historical_snapshots=[],
            goal=goal,
            recent_n=body.recent_n,
            today_highlights=body.today_highlights,
            goal_progress=gp,
        )
        out["status"] = "FEATURE_DISABLED"
        out["insight_available"] = False
        return out

    snaps = get_voice_profile_store().list_snapshots(subject)
    historical = snaps
    if body.exclude_analysis_id:
        historical = [s for s in snaps if s.get("analysis_id") != body.exclude_analysis_id]
    gp = build_goal_progress(
        goal=goal,
        historical_snapshots=historical,
        current_canonical=current or {},
        recent_n=body.recent_n,
    )
    return build_progress_insight(
        current_canonical=current or {},
        historical_snapshots=historical,
        goal=goal,
        recent_n=body.recent_n,
        today_highlights=body.today_highlights,
        goal_progress=gp,
    )


@router.get("/vocal-progress/insight")
def get_vocal_progress_insight(
    recent_n: int = 5,
    goal: str | None = None,
    exclude_analysis_id: str | None = None,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict[str, Any]:
    subject = _subject(x_user_id, x_vagent_user_key)
    active = get_user_goal_store().get_active(subject)
    resolved_goal = normalize_goal_payload(goal) if goal else active

    if not personal_vocal_baseline_enabled():
        gp = build_goal_progress(goal=resolved_goal, historical_snapshots=[], recent_n=recent_n)
        return {
            "status": "FEATURE_DISABLED",
            "insight_available": False,
            "today": [],
            "improved": [],
            "changed": [],
            "maintained": [],
            "goal_progress": gp,
        }

    snaps = get_voice_profile_store().list_snapshots(subject)
    if not snaps:
        gp = build_goal_progress(goal=resolved_goal, historical_snapshots=[], recent_n=recent_n)
        return build_progress_insight(
            current_canonical={},
            historical_snapshots=[],
            goal=resolved_goal,
            recent_n=recent_n,
            goal_progress=gp,
        )
    current = snaps[-1]
    if exclude_analysis_id:
        historical = [s for s in snaps if s.get("analysis_id") != exclude_analysis_id]
        current_candidates = [s for s in snaps if s.get("analysis_id") == exclude_analysis_id]
        current = current_candidates[-1] if current_candidates else current
    else:
        historical = snaps[:-1]
    current_can = current.get("canonical_json") or {}
    gp = build_goal_progress(
        goal=resolved_goal,
        historical_snapshots=historical,
        current_canonical=current_can,
        recent_n=recent_n,
    )
    return build_progress_insight(
        current_canonical=current_can,
        historical_snapshots=historical,
        goal=resolved_goal,
        recent_n=recent_n,
        goal_progress=gp,
    )


@router.get("/vocal-goals/catalog")
def get_vocal_goal_catalog() -> dict[str, Any]:
    return {"options": list_user_goal_catalog(), "uses_existing_coaching_focus": True}


@router.get("/vocal-goals")
def get_vocal_goals(
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict[str, Any]:
    subject = _subject(x_user_id, x_vagent_user_key)
    store = get_user_goal_store()
    active = store.get_active(subject)
    history = [g for g in store.list_goals(subject) if g.get("status") != "ACTIVE"]
    return {"active": active, "history": history}


@router.put("/vocal-goals/active")
def put_active_vocal_goal(
    body: GoalSetBody,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict[str, Any]:
    subject = _subject(x_user_id, x_vagent_user_key)
    row = get_user_goal_store().set_goal(
        subject,
        focus=body.focus,
        label=body.label,
        source=body.source or SOURCE_USER_SELECTED,
        target=body.target,
        style_id=body.style_id,
    )
    return {"status": "ACTIVE", "goal": row, "previous_goals_preserved": True}


@router.post("/vocal-goals/active/complete")
def complete_active_vocal_goal(
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict[str, Any]:
    subject = _subject(x_user_id, x_vagent_user_key)
    row = get_user_goal_store().complete_active(subject)
    return {"status": "COMPLETED" if row else "NO_GOAL", "goal": row}


@router.get("/vocal-progress/goal")
def get_vocal_goal_progress(
    recent_n: int = 5,
    exclude_analysis_id: str | None = None,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict[str, Any]:
    """Single-source Goal Progress payload (Home + Result share this)."""
    subject = _subject(x_user_id, x_vagent_user_key)
    active = get_user_goal_store().get_active(subject)
    if not active:
        return {"status": "NO_GOAL", "uses_fake_percent": False, "uses_identity_similarity": False}
    snaps = get_voice_profile_store().list_snapshots(subject) if personal_vocal_baseline_enabled() else []
    historical = snaps
    if exclude_analysis_id:
        historical = [s for s in snaps if s.get("analysis_id") != exclude_analysis_id]
    else:
        historical = snaps[:-1] if snaps else []
    current_can = (snaps[-1].get("canonical_json") if snaps else {}) or {}
    return build_goal_progress(
        goal=active,
        historical_snapshots=historical,
        current_canonical=current_can,
        recent_n=recent_n,
    )


class GoalProgressBody(BaseModel):
    current_canonical: dict[str, Any] = Field(default_factory=dict)
    historical: list[dict[str, Any]] = Field(default_factory=list)
    recent_n: int = 5
    goal: Optional[Any] = None


@router.post("/vocal-progress/goal")
def post_vocal_goal_progress(
    body: GoalProgressBody,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict[str, Any]:
    """Client can POST local history when baseline flag is off."""
    subject = _subject(x_user_id, x_vagent_user_key)
    active = get_user_goal_store().get_active(subject)
    goal = body.goal or active
    hist = body.historical
    if not hist and personal_vocal_baseline_enabled():
        hist = get_voice_profile_store().list_snapshots(subject)
    return build_goal_progress(
        goal=goal,
        historical_snapshots=hist,
        current_canonical=extract_canonical(body.current_canonical) or body.current_canonical,
        recent_n=body.recent_n,
    )
