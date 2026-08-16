"""
backend/app/main.py
-------------------
FastAPI entry for 노래 실력 진단받기 (vocalfb).
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from audio_analyzer.env_utils import load_dotenv_if_available

from .api.routes import router
from .api.voice_profile_routes import router as voice_profile_router
from .config import (
    artifact_storage_mode,
    database_url,
    get_environment,
    get_runtime_dir,
    identity_trust_mode,
    is_production,
    log_startup_banner,
    runtime_writable,
    singer_identity_enabled,
)
from .middleware.request_context import RequestContextMiddleware

load_dotenv_if_available()


def _cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["http://localhost:5173"]


app = FastAPI(
    title="Vocal Skill Test API",
    description="노래 실력 진단받기 — VAgent v2",
    version="2.0.0",
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)

app.include_router(router)
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


@app.get("/health")
def health() -> dict:
    runtime = get_runtime_dir()
    db = database_url()
    db_status = "missing"
    if db:
        try:
            from .db.session import database_reachable

            db_status = "ok" if database_reachable() else "error"
        except Exception:
            db_status = "error"
    payload = {
        "status": "ok" if (runtime_writable() and db_status in ("ok", "missing")) else "degraded",
        "service": "vocalfb",
        "analysis_version": "2.0",
        "backend": "ok",
        "database": db_status,
        "runtime": "ok" if runtime_writable() else "not_writable",
        "artifact_store": "ok" if runtime_writable() else "not_writable",
        "environment": get_environment(),
        "identity_trust_mode": identity_trust_mode(),
        "artifact_storage_mode": artifact_storage_mode(),
    }
    if not is_production():
        payload["debug"] = {
            "runtime_dir": str(runtime),
            "multi_instance_safe": False,
            "singer_identity_enabled": singer_identity_enabled(),
        }
    return payload


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
    ok = runtime_ok and db_ok
    body = {
        "ready": ok,
        "backend": "ok",
        "database": "ok" if db_ok else ("missing" if not db else "error"),
        "runtime": "ok" if runtime_ok else "not_writable",
    }
    if not ok:
        return JSONResponse(status_code=503, content=body)
    return body
