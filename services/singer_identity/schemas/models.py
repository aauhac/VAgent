# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    encoder_name: str
    model_version: str
    embedding_dim: int
    preprocessing_version: str


class SegmentEmbedding(BaseModel):
    start_sec: float
    end_sec: float
    quality: float
    embedding: list[float]


class AudioEmbeddingResult(BaseModel):
    audio_id: str = ""
    embedding_dim: int
    segment_count: int
    used_segment_count: int
    quality: Literal["GOOD", "FAIR", "POOR", "FAILED"] = "FAIR"
    model_version: str
    encoder_name: str
    preprocessing_version: str
    embedding: Optional[list[float]] = None  # omitted in public API responses
    sha256: str = ""
    filename: str = ""


class SingerCreate(BaseModel):
    display_name: str
    consented_enrollment: bool = False
    singer_id: Optional[str] = None


class EnrollResponse(BaseModel):
    singer_id: str
    display_name: str
    recording_count: int
    profile_quality: str
    model_version: str
    within_similarity: dict[str, Any] = Field(default_factory=dict)


class VerifyRequest(BaseModel):
    candidate_singer_id: str
    # audio provided as multipart in API; for JSON tests we allow embedding override
    audio_id: Optional[str] = None


class VerifyResponse(BaseModel):
    match: bool
    singer_id: str
    similarity: float
    decision: Literal["MATCH", "NON_MATCH", "UNCERTAIN"]
    threshold: float
    model_version: str
    strategy: str = "CENTROID"
    # Shadow-only experimental fields — never drive production UX
    shadow_k2_similarity: Optional[float] = None
    shadow_k2_decision: Optional[Literal["MATCH", "NON_MATCH", "UNCERTAIN"]] = None
    shadow_strategy: Optional[str] = None
    shadow_does_not_affect_production_decision: bool = True


class IdentifyCandidate(BaseModel):
    singer_id: str
    display_name: str
    similarity: float


class IdentifyResponse(BaseModel):
    decision: Literal["MATCH", "UNKNOWN", "UNCERTAIN"]
    top_match: Optional[IdentifyCandidate] = None
    candidates: list[IdentifyCandidate] = Field(default_factory=list)
    margin: Optional[float] = None
    model_version: str


class SingerVocalProfileContract(BaseModel):
    """Future contract only — not computed in v1."""

    singer_id: str
    note: str = "Historical VAgent canonical distributions live here in a future release."
    effort_distribution: dict[str, float] = Field(default_factory=dict)
    register_connection_distribution: dict[str, float] = Field(default_factory=dict)
    brightness_distribution: dict[str, float] = Field(default_factory=dict)
    presence_distribution: dict[str, float] = Field(default_factory=dict)


class SingerIdentityProfileContract(BaseModel):
    singer_id: str
    centroid: Optional[list[float]] = None
    recording_count: int = 0
    within_singer_similarity: dict[str, float] = Field(default_factory=dict)
    prototypes: dict[str, list[float]] = Field(default_factory=dict)
