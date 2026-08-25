"""
API routes for analysis jobs + diagnostic sessions + song detail entitlements.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from audio_analyzer.song_detail import build_song_detailed_report

from ..config import get_runtime_dir, is_production
from ..diagnostic import DiagnosticSessionService, validate_session_id
from ..entitlements import allow_dev_bypass, get_entitlement_provider
from ..jobs.runner import validate_analysis_id
from ..products import product_catalog
from ..schemas.analysis import AnalysisCreateResponse, AnalysisStatusResponse
from ..services.analysis_service import AnalysisService, AnalysisSubmitError
from ..services.history_service import list_user_history
from ..services.ownership import can_access_analysis

router = APIRouter(prefix="/v1")
service = AnalysisService()
diag = DiagnosticSessionService(get_runtime_dir())


from ..identity import resolve_identity_from_headers, resolve_verified_session


def _ident(
    request: Request | None = None,
    x_user_id: str | None = None,
    x_vagent_user_key: str | None = None,
):
    if request is None:
        from ..middleware.request_context import current_request

        request = current_request()
    if request is not None:
        session_ident = resolve_verified_session(request)
        if session_ident is not None:
            return session_ident
    return resolve_identity_from_headers(
        x_user_id=x_user_id,
        x_vagent_user_key=x_vagent_user_key,
    )


def _user_id(
    x_user_id: str | None = None,
    x_vagent_user_key: str | None = None,
    request: Request | None = None,
) -> str:
    return _ident(request, x_user_id, x_vagent_user_key).subject


def _ents():
    # Prefer service/diag runtime so tests that monkeypatch services still work
    return get_entitlement_provider(service.runtime_dir)


def _require_analysis_owner(
    analysis_id: str,
    x_user_id: str | None = None,
    x_vagent_user_key: str | None = None,
    request: Request | None = None,
) -> str:
    uid = _user_id(x_user_id, x_vagent_user_key, request)
    if not can_access_analysis(uid, analysis_id, service.runtime_dir):
        raise HTTPException(status_code=404, detail="analysis not found")
    return uid


@router.get("/products")
def get_products(
    request: Request,
    analysis_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict:
    song_owned = False
    if analysis_id and validate_analysis_id(analysis_id):
        uid = _require_analysis_owner(analysis_id, x_user_id, x_vagent_user_key, request)
        song_owned = _ents().has_song_detail(uid, analysis_id)
    elif analysis_id:
        raise HTTPException(status_code=404, detail="analysis not found")
    return product_catalog(song_detail_owned=song_owned)


@router.post("/analyses", response_model=AnalysisCreateResponse)
async def create_analysis(
    request: Request,
    file: UploadFile = File(...),
    separate: bool = Form(False),
    include_feedback: bool = Form(False),
    analysis_mode: str = Form("QUICK"),
    input_mode: str = Form("AUTO"),
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
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
    ident = _ident(request, x_user_id, x_vagent_user_key)
    try:
        analysis_id = await service.enqueue_upload(
            file=file,
            separate=separate,
            include_feedback=False,
            analysis_mode=mode,
            input_mode=in_mode,
            user_id=ident.subject,
            user_provider=ident.provider,
        )
    except AnalysisSubmitError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AnalysisCreateResponse(analysis_id=analysis_id, status="queued")


@router.get("/history")
def get_history(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict:
    """Server-side analysis history with access summary (avoids N× /access)."""
    uid = _user_id(x_user_id, x_vagent_user_key, request)
    payload = list_user_history(
        uid, limit=limit, offset=offset, runtime_dir=service.runtime_dir
    )
    if isinstance(payload, list):
        return {"items": payload, "unlinked_diagnostics": [], "has_more": False}
    return payload


@router.get("/analyses/{analysis_id}", response_model=AnalysisStatusResponse)
def get_analysis(
    analysis_id: str,
    request: Request,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> AnalysisStatusResponse:
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    uid = _require_analysis_owner(analysis_id, x_user_id, x_vagent_user_key, request)
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
        try:
            access = _ents().analysis_access(uid, analysis_id)
        except Exception:
            access = {
                "song_detail_unlocked": False,
                "diagnostic_unlocked": False,
                "diagnostic_session_id": None,
            }
        result["access"] = {
            "song_detail_unlocked": access["song_detail_unlocked"],
            "diagnostic_unlocked": access["diagnostic_unlocked"],
            "diagnostic_session_id": access.get("diagnostic_session_id"),
        }
        try:
            from ..rewards import rewarded_ad_status

            result["access"]["rewarded_ad"] = rewarded_ad_status(
                analysis_id,
                _ident(request, x_user_id, x_vagent_user_key),
                already_unlocked=bool(access["song_detail_unlocked"]),
                runtime_dir=service.runtime_dir,
            )
        except Exception:
            result["access"]["rewarded_ad"] = {
                "daily_limit": 3,
                "used_today": 0,
                "remaining_today": 3,
                "already_unlocked": bool(access["song_detail_unlocked"]),
                "can_use_rewarded_ad": not bool(access["song_detail_unlocked"]),
                "reward_type": "SONG_DETAIL",
            }
        result["product_offers"] = product_catalog(
            song_detail_owned=access["song_detail_unlocked"]
        ).get("offers")
        job["result"] = result
    return AnalysisStatusResponse(**job)


@router.post("/analyses/{analysis_id}/completion-notification")
def request_completion_notification(
    analysis_id: str,
    request: Request,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict:
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    session_ident = _ident(request, x_user_id, x_vagent_user_key)
    header_ident = resolve_identity_from_headers(
        x_user_id=x_user_id,
        x_vagent_user_key=x_vagent_user_key,
    )
    runtime = service.runtime_dir
    if can_access_analysis(session_ident.subject, analysis_id, runtime):
        ident = session_ident
    elif can_access_analysis(header_ident.subject, analysis_id, runtime):
        ident = header_ident
    else:
        raise HTTPException(status_code=404, detail="analysis not found")
    from ..notifications.completion import opt_in_completion_notification

    return opt_in_completion_notification(analysis_id, ident, runtime_dir=runtime)


@router.get("/notifications/latest-result")
def latest_notification_result(
    request: Request,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict:
    """Which analysis the completion alert the user just tapped was about.

    Backs `intoss://vocalfb/notification-result`. Always 200: for a deep-link landing,
    "nothing to open" is a normal state the client falls back from, not an error.

    The response carries an analysis id and a timestamp only — never a recipient key,
    anonymous hash, Toss userKey, or internal user id.
    """
    from ..notifications.deep_link import resolve_latest_sent_analysis_for_identity

    session_ident = _ident(request, x_user_id, x_vagent_user_key)
    header_ident = resolve_identity_from_headers(
        x_user_id=x_user_id,
        x_vagent_user_key=x_vagent_user_key,
    )
    idents = [session_ident]
    if (header_ident.provider, header_ident.subject) != (
        session_ident.provider,
        session_ident.subject,
    ):
        idents.append(header_ident)

    found = resolve_latest_sent_analysis_for_identity(idents, runtime_dir=service.runtime_dir)
    if not found or not validate_analysis_id(str(found.get("analysis_id") or "")):
        return {"found": False, "analysis_id": None, "sent_at": None}
    return {
        "found": True,
        "analysis_id": found["analysis_id"],
        "sent_at": found.get("sent_at"),
    }


@router.get("/analyses/{analysis_id}/access")
def get_analysis_access(
    analysis_id: str,
    request: Request,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict:
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    uid = _require_analysis_owner(analysis_id, x_user_id, x_vagent_user_key, request)
    if service.get_job(analysis_id) is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    try:
        access = _ents().analysis_access(uid, analysis_id)
        catalog = product_catalog(song_detail_owned=bool(access.get("song_detail_unlocked")))
    except Exception:
        # Corrupt entitlement store must not become a raw 500
        access = {
            "analysis_id": analysis_id,
            "song_detail_unlocked": False,
            "diagnostic_unlocked": False,
            "diagnostic_session_id": None,
        }
        catalog = product_catalog(song_detail_owned=False)
    payload = {
        **access,
        "offers": catalog["offers"],
        "products": catalog["products"],
    }
    try:
        from ..rewards import rewarded_ad_status

        ident = _ident(request, x_user_id, x_vagent_user_key)
        payload["rewarded_ad"] = rewarded_ad_status(
            analysis_id,
            ident,
            already_unlocked=bool(access.get("song_detail_unlocked")),
            runtime_dir=service.runtime_dir,
        )
    except Exception:
        payload["rewarded_ad"] = {
            "daily_limit": 3,
            "used_today": 0,
            "remaining_today": 3,
            "already_unlocked": bool(access.get("song_detail_unlocked")),
            "can_use_rewarded_ad": not bool(access.get("song_detail_unlocked")),
            "reward_type": "SONG_DETAIL",
        }
    return payload


@router.get("/analyses/{analysis_id}/rewarded-ad")
def get_rewarded_ad_status(
    analysis_id: str,
    request: Request,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict:
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    uid = _require_analysis_owner(analysis_id, x_user_id, x_vagent_user_key, request)
    unlocked = _ents().has_song_detail(uid, analysis_id)
    from ..rewards import RewardedAdError, rewarded_ad_status

    try:
        return rewarded_ad_status(
            analysis_id,
            _ident(request, x_user_id, x_vagent_user_key),
            already_unlocked=unlocked,
            runtime_dir=service.runtime_dir,
        )
    except RewardedAdError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.code) from exc


@router.post("/analyses/{analysis_id}/rewarded-ad/session")
def create_rewarded_ad_session(
    analysis_id: str,
    request: Request,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict:
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    uid = _require_analysis_owner(analysis_id, x_user_id, x_vagent_user_key, request)
    if service.get_job(analysis_id) is None and service.load_full_analysis(analysis_id) is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    unlocked = _ents().has_song_detail(uid, analysis_id)
    from ..rewards import RewardedAdError, create_rewarded_session

    try:
        return create_rewarded_session(
            analysis_id,
            _ident(request, x_user_id, x_vagent_user_key),
            already_unlocked=unlocked,
            runtime_dir=service.runtime_dir,
        )
    except RewardedAdError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.code) from exc


@router.post("/analyses/{analysis_id}/rewarded-ad/claim")
def claim_rewarded_ad(
    analysis_id: str,
    request: Request,
    body: dict | None = Body(default=None),
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict:
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    _require_analysis_owner(analysis_id, x_user_id, x_vagent_user_key, request)
    payload = body if isinstance(body, dict) else {}
    session_token = str(payload.get("session_token") or "").strip()
    from ..rewards import RewardedAdError, claim_rewarded_song_detail

    try:
        return claim_rewarded_song_detail(
            analysis_id,
            _ident(request, x_user_id, x_vagent_user_key),
            session_token=session_token,
            runtime_dir=service.runtime_dir,
        )
    except RewardedAdError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.code) from exc


@router.get("/analyses/{analysis_id}/detailed-report")
def get_detailed_report(
    analysis_id: str,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict:
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    uid = _require_analysis_owner(analysis_id, x_user_id, x_vagent_user_key)
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
    try:
        access = _ents().analysis_access(uid, analysis_id)
    except Exception:
        access = {
            "song_detail_unlocked": True,
            "diagnostic_unlocked": False,
            "diagnostic_session_id": None,
        }
    report["access"] = {
        "song_detail_unlocked": bool(access.get("song_detail_unlocked")),
        "diagnostic_unlocked": bool(access.get("diagnostic_unlocked")),
        "diagnostic_session_id": access.get("diagnostic_session_id"),
    }
    return report


def _forbid_mock() -> None:
    if is_production() or not allow_dev_bypass():
        raise HTTPException(status_code=403, detail="mock unlock disabled in production")


@router.post("/analyses/{analysis_id}/mock-unlock-detail")
def mock_unlock_song_detail(
    analysis_id: str,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict:
    _forbid_mock()
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    uid = _require_analysis_owner(analysis_id, x_user_id, x_vagent_user_key)
    if service.get_job(analysis_id) is None and service.load_full_analysis(analysis_id) is None:
        raise HTTPException(status_code=404, detail="analysis not found")
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
def get_preview_audio(
    analysis_id: str,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
):
    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    _require_analysis_owner(analysis_id, x_user_id, x_vagent_user_key)
    path = service.preview_path(analysis_id)
    if path is None:
        raise HTTPException(status_code=404, detail="preview audio not found")
    return FileResponse(
        path,
        media_type="audio/wav",
        filename=f"{analysis_id}_preview.wav",
    )


@router.get("/analyses/{analysis_id}/audio")
def get_audio_alias(
    analysis_id: str,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
):
    return get_preview_audio(analysis_id, x_user_id, x_vagent_user_key)


@router.delete("/analyses/{analysis_id}")
def delete_analysis(
    request: Request,
    analysis_id: str,
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict:
    from ..identity import resolve_verified_session

    if not validate_analysis_id(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    ident = resolve_verified_session(request)
    if ident is None or not ident.authenticated:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "AUTH_REQUIRED",
                    "message": "로그인이 필요해요.",
                }
            },
        )
    if not can_access_analysis(ident.subject, analysis_id, service.runtime_dir):
        raise HTTPException(status_code=404, detail="analysis not found")
    ok = service.delete_job(analysis_id)
    if not ok:
        raise HTTPException(status_code=500, detail="analysis delete failed")
    return {"deleted": True, "analysis_id": analysis_id}


# ── Diagnostic sessions ───────────────────────────────────────────────────


@router.get("/diagnostic/protocol")
def diagnostic_protocol() -> dict:
    return diag.protocol()


@router.post("/diagnostic-sessions")
def create_diagnostic_session(
    source_analysis_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None),
    x_vagent_user_key: str | None = Header(default=None, alias="X-VAgent-User-Key"),
) -> dict:
    try:
        return diag.create(
            user_id=_user_id(x_user_id, x_vagent_user_key),
            source_analysis_id=source_analysis_id,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail="analysis not found") from exc
        raise HTTPException(status_code=400, detail=msg) from exc


@router.post("/diagnostic-sessions/{session_id}/mock-pay")
def mock_pay_session(
    session_id: str,
    x_user_id: str | None = Header(default=None),
    payload: dict | None = Body(default=None),
) -> dict:
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    _forbid_mock()
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


@router.post("/diagnostic-sessions/{session_id}/concerns")
def submit_concerns(
    session_id: str,
    payload: dict,
    x_user_id: str | None = Header(default=None),
) -> dict:
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    raw = payload.get("user_concerns") or payload.get("concerns") or []
    mode = payload.get("diagnostic_mode")
    timbre_goal = payload.get("timbre_goal")
    try:
        return diag.submit_concerns(
            session_id,
            raw,
            user_id=_user_id(x_user_id),
            diagnostic_mode=mode,
            timbre_goal=timbre_goal,
        )
    except PermissionError:
        raise HTTPException(status_code=402, detail="REPORT_LOCKED") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@router.post("/diagnostic-sessions/{session_id}/ensure-plan")
def ensure_diagnostic_plan(
    session_id: str,
    x_user_id: str | None = Header(default=None),
) -> dict:
    """Recover empty NORMAL task plans without creating a new session."""
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    try:
        return diag.ensure_planned_tasks(session_id, user_id=_user_id(x_user_id))
    except PermissionError:
        raise HTTPException(status_code=402, detail="REPORT_LOCKED") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/diagnostic-sessions/{session_id}/tasks/{task_id}/skip")
def skip_diagnostic_task(
    session_id: str,
    task_id: str,
    payload: dict | None = None,
    x_user_id: str | None = Header(default=None),
) -> dict:
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    reason = (payload or {}).get("reason") or "USER_CHOICE"
    try:
        return diag.skip_task(
            session_id, task_id, user_id=_user_id(x_user_id), reason=reason
        )
    except PermissionError:
        raise HTTPException(status_code=402, detail="REPORT_LOCKED") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/diagnostic-sessions/{session_id}/start-controlled-recordings")
def start_controlled_recordings(
    session_id: str,
    x_user_id: str | None = Header(default=None),
) -> dict:
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    try:
        return diag.start_controlled_recordings(session_id, user_id=_user_id(x_user_id))
    except PermissionError:
        raise HTTPException(status_code=402, detail="REPORT_LOCKED") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/diagnostic-sessions/{session_id}/skip-controlled-recordings")
def skip_controlled_recordings(
    session_id: str,
    payload: dict | None = None,
    x_user_id: str | None = Header(default=None),
) -> dict:
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    remaining_only = True if payload is None else bool((payload or {}).get("remaining_only", True))
    try:
        return diag.skip_controlled_recordings(
            session_id,
            user_id=_user_id(x_user_id),
            remaining_only=remaining_only,
        )
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


@router.post("/diagnostic-sessions/{session_id}/regenerate-report")
def regenerate_report(
    session_id: str,
    x_user_id: str | None = Header(default=None),
) -> dict:
    """DEV only. Rebuild QA/goal presentation from stored evidence. Production → 403."""
    if is_production():
        raise HTTPException(status_code=403, detail="REGENERATE_DISABLED")
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    try:
        return diag.regenerate_report(session_id, user_id=_user_id(x_user_id))
    except PermissionError as exc:
        if str(exc) == "REGENERATE_DISABLED":
            raise HTTPException(status_code=403, detail="REGENERATE_DISABLED") from None
        raise HTTPException(status_code=402, detail="REPORT_LOCKED") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found") from None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="report not ready") from None
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
    if report.get("error") == "REPORT_GENERATING":
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=202, content=report)
    if report.get("error") == "REPORT_FAILED":
        raise HTTPException(status_code=409, detail=report.get("message") or "REPORT_FAILED")
    return report
