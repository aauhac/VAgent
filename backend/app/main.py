"""
backend/app/main.py
-------------------
FastAPI entry for 노래 실력 진단받기 (vocalfb).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router

app = FastAPI(
    title="Vocal Skill Test API",
    description="노래 실력 진단받기 — VAgent v2",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "vocalfb", "analysis_version": "2.0"}
