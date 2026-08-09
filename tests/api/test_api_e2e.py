"""Expanded FastAPI tests for VAgent v2 hardening."""

from __future__ import annotations

import io
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.api import routes as routes_mod
from backend.app.services.analysis_service import AnalysisService


@pytest.fixture()
def client(tmp_path, monkeypatch):
    svc = AnalysisService()
    svc.runtime_dir = tmp_path / "runtime"
    svc.runtime_dir.mkdir(parents=True, exist_ok=True)
    svc.max_upload_mb = 1.0
    from backend.app.jobs.runner import JobRunner

    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    monkeypatch.setattr(routes_mod, "service", svc)
    return TestClient(app), svc


def _wav_bytes(duration=3.5, amp=0.25, freq=220.0, sr=22050) -> bytes:
    t = np.arange(int(sr * duration)) / sr
    y = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    return buf.getvalue()


def _wait_done(client: TestClient, analysis_id: str, timeout=60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/v1/analyses/{analysis_id}")
        assert r.status_code == 200
        body = r.json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.3)
    raise AssertionError("timeout waiting for analysis")


def test_health(client):
    c, _ = client
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_post_valid_wav_and_poll(client):
    c, _ = client
    data = _wav_bytes()
    r = c.post(
        "/v1/analyses",
        files={"file": ("tone.wav", data, "audio/wav")},
        data={"include_feedback": "false"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    aid = r.json()["analysis_id"]
    body = _wait_done(c, aid)
    assert body["status"] == "completed"
    assert body["result"]["score"]["available"] is True
    blob = str(body["result"])
    assert "C:\\" not in blob
    assert "/runtime/" not in blob
    assert "analysis.wav" not in blob


def test_invalid_extension(client):
    c, _ = client
    r = c.post(
        "/v1/analyses",
        files={"file": ("x.txt", b"nope", "text/plain")},
    )
    assert r.status_code == 400


def test_oversized_upload(client):
    c, svc = client
    svc.max_upload_mb = 0.0001  # tiny
    big = b"0" * 2000
    r = c.post(
        "/v1/analyses",
        files={"file": ("big.wav", big, "audio/wav")},
    )
    assert r.status_code == 400


def test_unknown_id(client):
    c, _ = client
    r = c.get("/v1/analyses/" + ("a" * 32))
    assert r.status_code == 404


def test_delete_then_404_and_preview_404(client):
    c, _ = client
    data = _wav_bytes()
    r = c.post("/v1/analyses", files={"file": ("tone.wav", data, "audio/wav")})
    aid = r.json()["analysis_id"]
    body = _wait_done(c, aid)
    assert body["status"] == "completed"
    prev = c.get(f"/v1/analyses/{aid}/preview")
    assert prev.status_code == 200
    assert prev.headers["content-type"].startswith("audio/")
    d = c.delete(f"/v1/analyses/{aid}")
    assert d.status_code == 200
    assert c.get(f"/v1/analyses/{aid}").status_code == 404
    assert c.get(f"/v1/analyses/{aid}/preview").status_code == 404


def test_quality_fail_score_unavailable(client):
    c, _ = client
    # silence
    sr = 22050
    y = np.zeros(int(sr * 4), dtype=np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    r = c.post("/v1/analyses", files={"file": ("silent.wav", buf.getvalue(), "audio/wav")})
    aid = r.json()["analysis_id"]
    body = _wait_done(c, aid)
    assert body["status"] == "completed"
    assert body["result"]["quality"]["status"] == "fail"
    assert body["result"]["score"]["available"] is False


def test_llm_failure_keeps_analysis(client, monkeypatch):
    """Free song API ignores include_feedback; analysis must still complete."""
    c, _ = client

    def boom(*_a, **_k):
        raise RuntimeError("llm down")

    monkeypatch.setattr(
        "audio_analyzer.feedback.llm.generate_feedback",
        boom,
    )
    data = _wav_bytes()
    r = c.post(
        "/v1/analyses",
        files={"file": ("tone.wav", data, "audio/wav")},
        data={"include_feedback": "true"},
    )
    aid = r.json()["analysis_id"]
    body = _wait_done(c, aid)
    assert body["status"] == "completed"
    assert body["analysis_status"] == "completed"
    # Free path: LLM feedback not required / not exposed as premium narrative
    assert body["feedback_status"] in ("skipped", "failed", None)
    assert body["result"]["score"]["available"] is True
    assert body["result"]["tier"] == "free"
    assert "physiology_assessments" not in body["result"]
