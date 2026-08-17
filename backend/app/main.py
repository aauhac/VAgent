"""
backend/app/main.py
-------------------
FastAPI entry for 노래 실력 진단받기 (vocalfb).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from audio_analyzer.env_utils import load_dotenv_if_available

from .api.auth_routes import router as auth_router
from .api.legal_routes import router as legal_router
from .api.payment_routes import router as payment_router
from .api.routes import router
from .api.voice_profile_routes import router as voice_profile_router
from .config import (
    artifact_storage_mode,
    database_url,
    get_runtime_dir,
    is_production,
    log_startup_banner,
    runtime_writable,
)
from .http_config import cors_origins, public_backend_base_url, validate_production_http_config
from .middleware.request_context import RequestContextMiddleware
from .payments.settings import backend_replicas, payments_enabled, toss_login_enabled
from .payments.startup import validate_login_production_config, validate_payment_production_config

load_dotenv_if_available()


def _build_app() -> FastAPI:
    kwargs: dict = {
        "title": "Vocal Skill Test API",
        "description": "노래 실력 진단받기 — VAgent v2",
        "version": "2.0.0",
    }
    if is_production():
        kwargs.update(docs_url=None, redoc_url=None, openapi_url=None)
    return FastAPI(**kwargs)


app = _build_app()

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-User-Id", "X-VAgent-User-Key", "X-Request-Id", "X-VAgent-Debug"],
    expose_headers=["X-Request-Id"],
)

app.include_router(legal_router)
app.include_router(router)
app.include_router(auth_router)
app.include_router(payment_router)
app.include_router(voice_profile_router)


@app.on_event("startup")
def _on_startup() -> None:
    log_startup_banner()
    runtime_ok = runtime_writable()
    get_runtime_dir()
    db_url = database_url()
    db_ok = False
    if db_url:
        try:
            from .db.session import database_reachable

            db_ok = database_reachable()
        except Exception:
            db_ok = False
    if not is_production():
        print(
            f"[VAgent startup] runtime_writable={runtime_ok} database_reachable={db_ok if db_url else 'n/a'}",
            flush=True,
        )
    if is_production():
        if not runtime_ok:
            raise RuntimeError("runtime directory is not writable")
        if not db_url:
            raise RuntimeError("DATABASE_URL is required in production")
        if not db_ok:
            raise RuntimeError("database is not reachable")
        http_blockers = validate_production_http_config()
        if http_blockers:
            raise RuntimeError("production http config not ready: " + ",".join(http_blockers))
        if payments_enabled():
            blockers = validate_payment_production_config()
            if blockers:
                raise RuntimeError("production payments not ready: " + ",".join(blockers))
        elif toss_login_enabled():
            blockers = validate_login_production_config()
            if blockers:
                raise RuntimeError("production login not ready: " + ",".join(blockers))
        if artifact_storage_mode() == "LOCAL_PERSISTENT" and backend_replicas() != 1:
            raise RuntimeError("LOCAL_PERSISTENT artifact store requires BACKEND_REPLICAS=1")


@app.get("/health")
def health() -> dict:
    """Liveness — process is up. Does not probe PostgreSQL or Toss."""
    return {
        "status": "ok",
        "service": "vocalfb",
        "backend": "ok",
    }


@app.get("/ready")
def ready():
    """Readiness — fail closed when production dependencies are down."""
    runtime_ok = runtime_writable()
    db = database_url()
    if db or is_production():
        try:
            from .db.session import database_reachable

            db_ok = bool(db) and database_reachable()
        except Exception:
            db_ok = False
    else:
        db_ok = True
    payment_blockers = []
    payment_state = "off"
    if payments_enabled():
        payment_blockers = validate_payment_production_config() if is_production() else []
        payment_state = "ok" if not payment_blockers else "degraded"
    login_state = "off"
    if toss_login_enabled():
        login_blockers = validate_login_production_config() if is_production() else []
        login_state = "ok" if not login_blockers else "degraded"
    ok = runtime_ok and db_ok
    body = {
        "ready": ok,
        "backend": "ok",
        "database": "ok" if db_ok else ("missing" if not db else "error"),
        "runtime": "ok" if runtime_ok else "not_writable",
        "payments": payment_state,
        "login": login_state,
        "public_backend_base": "configured" if public_backend_base_url() else "unset",
        "multi_instance_safe": False,
    }
    if not ok:
        return JSONResponse(status_code=503, content=body)
    return body
