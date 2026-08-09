"""
backend/app/main.py
-------------------
FastAPI entry for 노래 실력 진단받기 (vocalfb).
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from audio_analyzer.env_utils import load_dotenv_if_available

from .api.routes import router

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "vocalfb", "analysis_version": "2.0"}
