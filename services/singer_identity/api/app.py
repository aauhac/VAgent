# -*- coding: utf-8 -*-
"""FastAPI Singer Identity service — independent of VAgent diagnostic."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from services.singer_identity.config import DEFAULT_RUNTIME, MODEL_VERSION
from services.singer_identity.enrollment.service import enroll_audio_files
from services.singer_identity.identification.service import identify_embedding
from services.singer_identity.inference.encoder import get_default_encoder
from services.singer_identity.registry.store import SingerRegistry
from services.singer_identity.schemas.models import SingerCreate
from services.singer_identity.verification.service import verify_embedding

app = FastAPI(title="VAgent Singer Identity Engine", version="1.0.0")
_encoder = None
_registry: Optional[SingerRegistry] = None


def get_encoder():
    global _encoder
    if _encoder is None:
        _encoder = get_default_encoder()
    return _encoder


def get_registry() -> SingerRegistry:
    global _registry
    if _registry is None:
        _registry = SingerRegistry(DEFAULT_RUNTIME)
    return _registry


@app.get("/health")
def health():
    return {"status": "ok", "service": "singer-identity", "vagent_diagnostic": False}


@app.get("/v1/model")
def model_info():
    enc = get_encoder()
    return enc.model_info().model_dump()


@app.post("/v1/embed")
async def embed(file: UploadFile = File(...), expose_embedding: bool = False):
    """Internal/developer endpoint — raw embedding not for public frontend."""
    enc = get_encoder()
    data = await file.read()
    sha = hashlib.sha256(data).hexdigest()
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename or "x.wav").suffix, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        result = enc.encode_path(path, audio_id=sha[:12], sha256=sha, include_embedding=expose_embedding)
        payload = result.model_dump()
        if not expose_embedding:
            payload.pop("embedding", None)
        return payload
    finally:
        Path(path).unlink(missing_ok=True)


@app.post("/v1/singers")
def create_singer(body: SingerCreate):
    reg = get_registry()
    try:
        meta = reg.create_singer(
            body.display_name,
            consented_enrollment=body.consented_enrollment,
            singer_id=body.singer_id,
            model_version=MODEL_VERSION,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return meta


@app.get("/v1/singers")
def list_singers():
    return {"singers": get_registry().list_singers()}


@app.get("/v1/singers/{singer_id}")
def get_singer(singer_id: str):
    reg = get_registry()
    meta = reg.get_singer(singer_id)
    if not meta:
        raise HTTPException(404, "singer not found")
    profile = reg.get_profile(singer_id) or {}
    # never return raw centroid embedding in public get
    profile_public = {k: v for k, v in profile.items() if k != "centroid"}
    return {"singer": meta, "profile": profile_public}


@app.delete("/v1/singers/{singer_id}")
def delete_singer(singer_id: str):
    ok = get_registry().delete_singer(singer_id)
    if not ok:
        raise HTTPException(404, "singer not found")
    return {"deleted": True, "singer_id": singer_id}


@app.post("/v1/singers/{singer_id}/enroll")
async def enroll(singer_id: str, files: list[UploadFile] = File(...)):
    reg = get_registry()
    if not reg.get_singer(singer_id):
        raise HTTPException(404, "singer not found")
    enc = get_encoder()
    paths = []
    try:
        for f in files:
            data = await f.read()
            suffix = Path(f.filename or "x.wav").suffix
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            tmp.write(data)
            tmp.close()
            paths.append(tmp.name)
        result = enroll_audio_files(reg, enc, singer_id, paths)
        return result
    finally:
        for p in paths:
            Path(p).unlink(missing_ok=True)


@app.post("/v1/verify")
async def verify(
    candidate_singer_id: str = Form(...),
    file: UploadFile = File(...),
    include_shadow_k2: str = Form("false"),
):
    enc = get_encoder()
    data = await file.read()
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename or "x.wav").suffix, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        result = enc.encode_path(path, include_embedding=True)
        if not result.embedding:
            raise HTTPException(422, "embedding failed")
        shadow = str(include_shadow_k2).lower() in ("1", "true", "yes", "on")
        out = verify_embedding(
            get_registry(),
            np.asarray(result.embedding, dtype=np.float32),
            candidate_singer_id,
            model_version=enc.model_version,
            include_shadow_k2=shadow,
        )
        payload = out.model_dump()
        payload.pop("embedding", None)
        return payload
    finally:
        Path(path).unlink(missing_ok=True)


@app.post("/v1/identify")
async def identify(file: UploadFile = File(...)):
    enc = get_encoder()
    data = await file.read()
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename or "x.wav").suffix, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        result = enc.encode_path(path, include_embedding=True)
        if not result.embedding:
            raise HTTPException(422, "embedding failed")
        return identify_embedding(
            get_registry(),
            np.asarray(result.embedding, dtype=np.float32),
            model_version=enc.model_version,
        )
    finally:
        Path(path).unlink(missing_ok=True)


def create_app() -> FastAPI:
    return app
