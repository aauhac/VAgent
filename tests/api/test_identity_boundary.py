"""Identity trust boundary tests."""

from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.api import routes as routes_mod
from backend.app.config import get_runtime_dir
from backend.app.diagnostic import DiagnosticSessionService
from backend.app.identity import resolve_identity_from_headers
from backend.app.jobs.runner import JobRunner
from backend.app.main import app
from backend.app.services.analysis_service import AnalysisService


def _wav_bytes(duration=0.4, amp=0.2, freq=220.0, sr=16000) -> bytes:
    t = np.arange(int(sr * duration)) / sr
    y = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    return buf.getvalue()


@pytest.fixture()
def analysis_client(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("VAGENT_ENV", "development")
    get_runtime_dir.cache_clear()
    svc = AnalysisService()
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    monkeypatch.setattr(routes_mod, "service", svc)
    monkeypatch.setattr(routes_mod, "diag", DiagnosticSessionService(svc.runtime_dir))
    client = TestClient(app, raise_server_exceptions=True)
    yield client
    get_runtime_dir.cache_clear()


def test_dev_identity_allowed_in_dev(monkeypatch):
    monkeypatch.setenv("VAGENT_ENV", "development")
    ident = resolve_identity_from_headers(x_user_id="demo-user")
    assert ident.subject == "demo-user"
    assert ident.trust_mode == "UNVERIFIED_CLIENT_SUBJECT"


def test_demo_user_forbidden_in_prod(monkeypatch):
    monkeypatch.setenv("VAGENT_ENV", "production")
    with pytest.raises(HTTPException) as ei:
        resolve_identity_from_headers(x_user_id="demo-user")
    assert ei.value.status_code == 401


def test_identity_missing_prod_rejected(monkeypatch):
    monkeypatch.setenv("VAGENT_ENV", "production")
    with pytest.raises(HTTPException) as ei:
        resolve_identity_from_headers(x_user_id=None, x_vagent_user_key=None)
    assert ei.value.status_code == 401


def test_client_asserted_header_is_not_verified_auth(monkeypatch):
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("TOSS_IDENTITY_TRUST_MODE", "UNVERIFIED_CLIENT_SUBJECT")
    ident = resolve_identity_from_headers(x_vagent_user_key="victim-user")
    assert ident.subject == "victim-user"
    assert ident.trust_mode == "UNVERIFIED_CLIENT_SUBJECT"


def test_create_analysis_with_canonical_user_header(analysis_client):
    """POST /analyses must accept X-VAgent-User-Key alone (canonical FE header)."""
    r = analysis_client.post(
        "/v1/analyses",
        files={"file": ("tone.wav", _wav_bytes(), "audio/wav")},
        data={
            "analysis_mode": "FUNCTIONAL",
            "input_mode": "VOCAL_ONLY",
            "separate": "false",
            "include_feedback": "false",
        },
        headers={"X-VAgent-User-Key": "header-only-user"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "queued"


def test_create_analysis_missing_identity_dev(analysis_client, monkeypatch):
    monkeypatch.setenv("VAGENT_ENV", "development")
    r = analysis_client.post(
        "/v1/analyses",
        files={"file": ("tone.wav", _wav_bytes(), "audio/wav")},
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "VOCAL_ONLY", "separate": "false"},
    )
    # Dev may fall back to anon — must not 500
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "queued"
