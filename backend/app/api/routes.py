"""
API routes for analysis jobs + diagnostic sessions + song detail entitlements.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from audio_analyzer.song_detail import build_song_detailed_report

from ..diagnostic import DiagnosticSessionService, validate_session_id
from ..entitlements import allow_dev_bypass, get_entitlement_provider
from ..jobs.runner import validate_analysis_id
from ..products import product_catalog
from ..schemas.analysis import AnalysisCreateResponse, AnalysisStatusResponse
from ..services.analysis_service import AnalysisService

router = APIRouter(prefix="/v1")
service = AnalysisService()
diag = DiagnosticSessionService(Path(os.environ.get("RUNTIME_DIR", "runtime")))


def _user_id(x_user_id: str | None) -> str:
    return (x_user_id or "anon").strip() or "anon"


def _ents():
    # Prefer service/diag runtime so tests that monkeypatch services still work
    return get_entitlement_provider(service.runtime_dir)


@router.get("/products")
def get_products(
    analysis_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict:
    song_owned = False
    if analysis_id and validate_analysis_id(analysis_id):
        song_owned = _ents().has_song_detail(_user_id(x_user_id), analysis_id)
    return product_catalog(song_detail_owned=song_owned)


@router.post("/analyses", response_model=AnalysisCreateResponse)
async def create_analysis(
    file: UploadFile = File(...),
    separate: bool = Form(False),
    include_feedback: bool = Form(False),
    analysis_mode: str = Form("QUICK"),
    input_mode: str = Form("AUTO"),
) -> AnalysisCreateResponse:
    """
    analysis_mode: QUICK | FUNCTIONAL | DIAGNOSTIC  (depth)
    input_mode: AUTO | MIXED | VOCAL_ONLY  (independent of depth)
    """
    mode = (analysis_mode or "QUICK").upper()
    if mode not in ("QUICK", "FUNCTIONAL", "DIAGNOSTIC"):
        mode = "QUICK"
    in_mode = (input_mode or "AUTO").upper()
    if in_mode not in ("AUTO", "MIXED", "VOCAL_ONLY"):
        in_mode = "AUTO"
    # Backend policy: FUNCTIONAL + AUTO/MIXED forces separate; VOCAL_ONLY skips
    if mode == "FUNCTIONAL":
        separate = in_mode != "VOCAL_ONLY"
    try:
        analysis_id = await service.enqueue_upload(
            file=file,
            separate=separate,
            include_feedback=False,
            analysis_mode=mode,
            input_mode=in_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AnalysisCreateResponse(analysis_id=analysis_id, status="queued")


@router.get("/analyses/{analysis_id}", response_model=AnalysisStatusResponse)
def get_analysis(
    analysis_id: str,
    x_user_id: str | None = Header(default=None),
) -> AnalysisStatusResponse:
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
            "areas_detail",
            "strengths",
            "priority_issues",
            "training_plan",
            "vibrato",
            "focus_segments",
            "segment_scores",
            "why_this_score",
            "overall_assessment",
            "submetrics",
            "vocal_quality_profile",
            "vocal_function_profile",
            "scientific_debug",
        ):
            result.pop(banned, None)
        # Nested premium evidence must not leak via score.areas
        score = result.get("score")
        if isinstance(score, dict):
            areas = score.get("areas")
            if isinstance(areas, list):
                score["areas"] = [
                    {
                        "area_id": a.get("area_id"),
                        "display_name": a.get("display_name"),
                        "score": a.get("score"),
                        "status": a.get("status"),
                        "status_label": a.get("status_label"),
                        "confidence": a.get("confidence"),
                    }
                    for a in areas
                    if isinstance(a, dict)
                ]
            for nested_banned in (
                "segment_scores",
                "submetrics",
                "focus_segments",
                "why_this_score",
                "temporal",
            ):
                score.pop(nested_banned, None)
        # Attach access flags (no detailed content)
        access = _ents().analysis_access(_user_id(x_user_id), analysis_id)
        result["access"] = {
            "song_detail_unlocked": access["song_detail_unlocked"],
            "diagnostic_unlocked": access["diagnostic_unlocked"],
            "diagnostic_session_id": access.get("diagnostic_session_id"),
        }
        result["product_offers"] = product_catalog(
            song_detail_owned=access["song_detail_unlocked"]
        ).get("offers")
        job["result"] = result
    return AnalysisStatusResponse(**job)


@router.get("/analyses/{analysis_id}/access")
def get_analysis_access(
    analysis_id: str,
    x_user_id: str | None = Header(default=None),
) -> dict:
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    if service.get_job(analysis_id) is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    access = _ents().analysis_access(_user_id(x_user_id), analysis_id)
    catalog = product_catalog(song_detail_owned=access["song_detail_unlocked"])
    return {
        **access,
        "offers": catalog["offers"],
        "products": catalog["products"],
    }


@router.get("/analyses/{analysis_id}/detailed-report")
def get_detailed_report(
    analysis_id: str,
    x_user_id: str | None = Header(default=None),
) -> dict:
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    uid = _user_id(x_user_id)
    if not _ents().has_song_detail(uid, analysis_id):
        raise HTTPException(status_code=402, detail="SONG_DETAIL_LOCKED")
    full = service.load_full_analysis(analysis_id)
    if full is None:
        raise HTTPException(status_code=404, detail="analysis not ready")
    report = build_song_detailed_report(full, analysis_id=analysis_id)
    for banned in (
        "physiology_assessments",
        "reliable_findings",
        "uncertain_findings",
        "scientific_debug",
        "coaching_recommendations",
    ):
        report.pop(banned, None)
    return report


@router.post("/analyses/{analysis_id}/mock-unlock-detail")
def mock_unlock_song_detail(
    analysis_id: str,
    x_user_id: str | None = Header(default=None),
) -> dict:
    if not allow_dev_bypass():
        raise HTTPException(status_code=403, detail="mock unlock disabled in production")
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    if service.get_job(analysis_id) is None and service.load_full_analysis(analysis_id) is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    uid = _user_id(x_user_id)
    ents = _ents()
    if not ents.has_song_detail(uid, analysis_id):
        ents.grant_song_detail(
            uid,
            analysis_id,
            f"mock_detail_{uuid.uuid4().hex[:12]}",
            product_id="song_detail",
        )
    return {
        "unlocked": True,
        "analysis_id": analysis_id,
        "entitlement_type": "SONG_DETAIL",
        "permanent": True,
        "redirect": f"/result/{analysis_id}/detail",
    }


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
    payload: dict | None = Body(default=None),
) -> dict:
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    body = payload or {}
    product_id = body.get("product_id") if isinstance(body, dict) else None
    try:
        return diag.mock_pay(
            session_id,
            user_id=_user_id(x_user_id),
            product_id=product_id,
        )
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
