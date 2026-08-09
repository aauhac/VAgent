"""Pydantic schemas."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class AnalysisCreateResponse(BaseModel):
    analysis_id: str
    status: str = "queued"


class AnalysisStatusResponse(BaseModel):
    analysis_id: str
    status: str
    stage: Optional[str] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    analysis_status: Optional[str] = None
    feedback_status: Optional[str] = None
