"""
API routes for analysis jobs.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..schemas.analysis import AnalysisCreateResponse, AnalysisStatusResponse
from ..services.analysis_service import AnalysisService

router = APIRouter(prefix="/v1")
service = AnalysisService()


@router.post("/analyses", response_model=AnalysisCreateResponse)
async def create_analysis(
    file: UploadFile = File(...),
    separate: bool = Form(False),
    include_feedback: bool = Form(False),
) -> AnalysisCreateResponse:
    try:
        analysis_id = await service.enqueue_upload(
            file=file,
            separate=separate,
            include_feedback=include_feedback,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AnalysisCreateResponse(analysis_id=analysis_id, status="queued")


@router.get("/analyses/{analysis_id}", response_model=AnalysisStatusResponse)
def get_analysis(analysis_id: str) -> AnalysisStatusResponse:
    job = service.get_job(analysis_id)
    if job is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    return AnalysisStatusResponse(**job)


@router.delete("/analyses/{analysis_id}")
def delete_analysis(analysis_id: str) -> dict:
    ok = service.delete_job(analysis_id)
    if not ok:
        raise HTTPException(status_code=404, detail="analysis not found")
    return {"deleted": True, "analysis_id": analysis_id}
