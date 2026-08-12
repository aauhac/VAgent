"""Pydantic schemas."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


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
    analysis_mode: Optional[str] = None
    input_mode: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("progress", mode="before")
    @classmethod
    def _coerce_progress(cls, value: Any) -> Any:
        if value is None:
            return None
        try:
            ivalue = int(float(value))
        except (TypeError, ValueError):
            return None
        return max(0, min(100, ivalue))

