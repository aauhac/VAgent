"""
API routes for analysis jobs + diagnostic sessions.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from audio_analyzer.diagnostic import SAFETY_QUESTIONS, TASKS

from ..diagnostic import DiagnosticSessionService, validate_session_id
from ..jobs.runner import validate_analysis_id
from ..schemas.analysis import AnalysisCreateResponse, AnalysisStatusResponse
from ..services.analysis_service import AnalysisService

router = APIRouter(prefix="/v1")
service = AnalysisService()
diag = DiagnosticSessionService(Path(os.environ.get("RUNTIME_DIR", "runtime")))


def _user_id(x_user_id: str | None) -> str:
    return (x_user_id or "anon").strip() or "anon"


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
            include_feedback=False,  # free path: no premium LLM dump
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AnalysisCreateResponse(analysis_id=analysis_id, status="queued")


@router.get("/analyses/{analysis_id}", response_model=AnalysisStatusResponse)
def get_analysis(analysis_id: str) -> AnalysisStatusResponse:
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    job = service.get_job(analysis_id)
    if job is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    # FREE endpoint: strip premium / deep-debug keys if present (never CSS-gate them)
    result = job.get("result")
    if isinstance(result, dict):
        for banned in (
            "physiology_assessments",
            "diagnostic_metrics",
            "coaching_recommendations",
            "premium_report",
            "timeline",
            "optional_analysis",
            "issues",
            "metrics_detail",
            "phonation",
            "evidence",
        ):
            result.pop(banned, None)
        job["result"] = result
    return AnalysisStatusResponse(**job)


@router.get("/analyses/{analysis_id}/preview")
def get_preview_audio(analysis_id: str):
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    path = service.preview_path(analysis_id)
    if path is None:
        raise HTTPException(status_code=404, detail="preview audio not found")
    return FileResponse(
        path,
        media_type="audio/wav",
        filename=f"{analysis_id}_preview.wav",
    )


@router.get("/analyses/{analysis_id}/audio")
def get_audio_alias(analysis_id: str):
    return get_preview_audio(analysis_id)


@router.delete("/analyses/{analysis_id}")
def delete_analysis(analysis_id: str) -> dict:
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    ok = service.delete_job(analysis_id)
    if not ok:
        raise HTTPException(status_code=404, detail="analysis not found")
    return {"deleted": True, "analysis_id": analysis_id}


# ── Diagnostic sessions ───────────────────────────────────────────────────


@router.get("/diagnostic/protocol")
def diagnostic_protocol() -> dict:
    return diag.protocol()


@router.post("/diagnostic-sessions")
def create_diagnostic_session(
    source_analysis_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict:
    try:
        return diag.create(
            user_id=_user_id(x_user_id),
            source_analysis_id=source_analysis_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/diagnostic-sessions/{session_id}/mock-pay")
def mock_pay_session(
    session_id: str,
    x_user_id: str | None = Header(default=None),
) -> dict:
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    try:
        return diag.mock_pay(session_id, user_id=_user_id(x_user_id))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found") from None


@router.post("/diagnostic-sessions/{session_id}/safety")
def submit_safety(
    session_id: str,
    payload: dict,
    x_user_id: str | None = Header(default=None),
) -> dict:
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    answers = payload.get("answers") or {}
    try:
        return diag.submit_safety(session_id, answers, user_id=_user_id(x_user_id))
    except PermissionError:
        raise HTTPException(status_code=402, detail="REPORT_LOCKED") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/diagnostic-sessions/{session_id}/tasks/{task_id}")
async def upload_task(
    session_id: str,
    task_id: str,
    file: UploadFile = File(...),
    x_user_id: str | None = Header(default=None),
) -> dict:
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    data = await file.read()
    try:
        return diag.upload_task(
            session_id,
            task_id,
            data,
            file.filename or "task.wav",
            user_id=_user_id(x_user_id),
        )
    except PermissionError:
        raise HTTPException(status_code=402, detail="REPORT_LOCKED") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/diagnostic-sessions/{session_id}/analyze")
def analyze_session(
    session_id: str,
    x_user_id: str | None = Header(default=None),
) -> dict:
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    try:
        return diag.analyze(session_id, user_id=_user_id(x_user_id))
    except PermissionError:
        raise HTTPException(status_code=402, detail="REPORT_LOCKED") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/diagnostic-sessions/{session_id}")
def get_session(
    session_id: str,
    x_user_id: str | None = Header(default=None),
) -> dict:
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    session = diag.get_session(session_id, user_id=_user_id(x_user_id))
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.get("/diagnostic-sessions/{session_id}/report")
def get_report(
    session_id: str,
    x_user_id: str | None = Header(default=None),
    x_vagent_debug: str | None = Header(default=None),
) -> dict:
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    debug = (x_vagent_debug or "").lower() in ("1", "true", "yes") or (
        (os.environ.get("PHYSIOLOGY_DEBUG") or "").lower() in ("1", "true", "yes")
    )
    try:
        report = diag.get_report(
            session_id,
            user_id=_user_id(x_user_id),
            include_scientific_debug=debug,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found") from None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="report not ready") from None
    if report.get("error") == "REPORT_LOCKED":
        raise HTTPException(status_code=402, detail="REPORT_LOCKED")
    return report
