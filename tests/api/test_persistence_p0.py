"""P0 persistence reliability tests — reproduce and lock 500 fixes."""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from backend.app.api import routes as routes_mod
from backend.app.config import get_runtime_dir, project_root
from backend.app.entitlements.provider import MockEntitlementProvider
from backend.app.jobs.runner import JobRunner
from backend.app.main import app
from backend.app.services.analysis_service import AnalysisService
from backend.app.services.history_service import write_analysis_meta


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("VAGENT_ENV", "development")
    # File-backed history tests must not hit a developer Postgres SoT
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_runtime_dir.cache_clear()

    svc = AnalysisService()
    assert svc.runtime_dir.resolve() == runtime.resolve()
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    monkeypatch.setattr(routes_mod, "service", svc)
    from backend.app.diagnostic import DiagnosticSessionService

    monkeypatch.setattr(routes_mod, "diag", DiagnosticSessionService(svc.runtime_dir))
    client = TestClient(app, raise_server_exceptions=True)
    yield client, svc, runtime
    get_runtime_dir.cache_clear()


def _wav_bytes(duration=0.5, amp=0.2, freq=220.0, sr=16000) -> bytes:
    t = np.arange(int(sr * duration)) / sr
    y = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    return buf.getvalue()


def test_runtime_dir_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_DIR", "runtime")
    get_runtime_dir.cache_clear()
    monkeypatch.chdir(tmp_path)
    resolved = get_runtime_dir()
    assert resolved == (project_root() / "runtime").resolve()
    get_runtime_dir.cache_clear()


def test_post_valid_wav_not_500(isolated):
    client, _, _ = isolated
    r = client.post(
        "/v1/analyses",
        files={"file": ("tone.wav", _wav_bytes(), "audio/wav")},
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "VOCAL_ONLY", "separate": "false"},
        headers={"X-User-Id": "demo-user", "X-VAgent-User-Key": "demo-user"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "queued"
    assert r.headers.get("x-request-id")


def test_post_vocal_only_queued(isolated):
    client, _, _ = isolated
    r = client.post(
        "/v1/analyses",
        files={"file": ("tone.wav", _wav_bytes(), "audio/wav")},
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "VOCAL_ONLY", "separate": "false"},
        headers={"X-User-Id": "demo-user"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


def test_post_mixed_queued(isolated):
    client, _, _ = isolated
    r = client.post(
        "/v1/analyses",
        files={"file": ("tone.wav", _wav_bytes(), "audio/wav")},
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "MIXED", "separate": "true"},
        headers={"X-User-Id": "demo-user"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


def test_access_existing_200(isolated):
    client, svc, runtime = isolated
    aid = "a" * 32
    d = runtime / aid
    d.mkdir()
    (d / "job_status.json").write_text(
        json.dumps({"analysis_id": aid, "status": "completed", "progress": 100, "result": {}}),
        encoding="utf-8",
    )
    write_analysis_meta(aid, user_id="demo-user", runtime_dir=runtime)
    r = client.get(f"/v1/analyses/{aid}/access", headers={"X-User-Id": "demo-user"})
    assert r.status_code == 200
    assert r.json()["analysis_id"] == aid


def test_access_missing_404(isolated):
    client, _, _ = isolated
    r = client.get(f"/v1/analyses/{'b'*32}/access", headers={"X-User-Id": "demo-user"})
    assert r.status_code == 404


def test_access_malformed_404(isolated):
    client, _, _ = isolated
    r = client.get("/v1/analyses/not-valid/access", headers={"X-User-Id": "demo-user"})
    assert r.status_code == 404


def test_empty_entitlements_access_200(isolated):
    client, _, runtime = isolated
    (runtime / "entitlements.json").write_text("{}", encoding="utf-8")
    aid = "c" * 32
    d = runtime / aid
    d.mkdir()
    (d / "job_status.json").write_text(
        json.dumps({"analysis_id": aid, "status": "completed", "progress": 100}),
        encoding="utf-8",
    )
    write_analysis_meta(aid, user_id="demo-user", runtime_dir=runtime)
    r = client.get(f"/v1/analyses/{aid}/access", headers={"X-User-Id": "demo-user"})
    assert r.status_code == 200


def test_corrupt_entitlement_store_not_raw_500(isolated):
    client, _, runtime = isolated
    (runtime / "entitlements.json").write_text(
        json.dumps({"demo-user": {"sessions": {"x": "legacy-string"}, "analyses": {}}}),
        encoding="utf-8",
    )
    aid = "d" * 32
    d = runtime / aid
    d.mkdir()
    (d / "job_status.json").write_text(
        json.dumps({"analysis_id": aid, "status": "completed", "progress": 100}),
        encoding="utf-8",
    )
    write_analysis_meta(aid, user_id="demo-user", runtime_dir=runtime)
    r = client.get(f"/v1/analyses/{aid}/access", headers={"X-User-Id": "demo-user"})
    assert r.status_code == 200
    assert r.json()["song_detail_unlocked"] is False


def test_restart_disk_recovery_empty_memory(isolated):
    _, svc, runtime = isolated
    aid = "e" * 32
    d = runtime / aid
    d.mkdir()
    payload = {
        "analysis_id": aid,
        "status": "completed",
        "stage": "done",
        "progress": 100,
        "result": {"score": {"available": True}},
    }
    (d / "job_status.json").write_text(json.dumps(payload), encoding="utf-8")
    # Fresh runner = empty memory
    runner = JobRunner(runtime, max_workers=1)
    assert not runner._jobs
    got = runner.get(aid)
    assert got is not None
    assert got["status"] == "completed"
    assert got["result"]["score"]["available"] is True


def test_corrupt_job_status_not_500(isolated):
    client, _, runtime = isolated
    aid = "f" * 32
    d = runtime / aid
    d.mkdir()
    (d / "job_status.json").write_text("NOT-JSON{{{", encoding="utf-8")
    write_analysis_meta(aid, user_id="demo-user", runtime_dir=runtime)
    r = client.get(f"/v1/analyses/{aid}", headers={"X-User-Id": "demo-user"})
    assert r.status_code == 200
    assert r.json()["status"] == "failed"


def test_interrupted_analyzing_becomes_failed_on_disk_load(isolated):
    _, _, runtime = isolated
    aid = "1" * 32
    d = runtime / aid
    d.mkdir()
    (d / "job_status.json").write_text(
        json.dumps({"analysis_id": aid, "status": "analyzing", "progress": 40}),
        encoding="utf-8",
    )
    runner = JobRunner(runtime)
    got = runner.get(aid)
    assert got["status"] == "failed"
    assert got["error"] == "INTERRUPTED_RESTART"


def test_ownership_other_user_404(isolated):
    client, _, runtime = isolated
    aid = "2" * 32
    d = runtime / aid
    d.mkdir()
    (d / "job_status.json").write_text(
        json.dumps({"analysis_id": aid, "status": "completed", "progress": 100}),
        encoding="utf-8",
    )
    write_analysis_meta(aid, user_id="alice", runtime_dir=runtime)
    r = client.get(f"/v1/analyses/{aid}/access", headers={"X-User-Id": "bob"})
    assert r.status_code == 404


def test_history_includes_access_summary(isolated):
    client, _, runtime = isolated
    aid = "3" * 32
    d = runtime / aid
    d.mkdir()
    (d / "job_status.json").write_text(
        json.dumps({"analysis_id": aid, "status": "completed", "progress": 100}),
        encoding="utf-8",
    )
    write_analysis_meta(aid, user_id="demo-user", filename="x.wav", runtime_dir=runtime)
    r = client.get("/v1/history", headers={"X-User-Id": "demo-user"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["analysis_id"] == aid for i in items)
    row = next(i for i in items if i["analysis_id"] == aid)
    assert "song_detail_unlocked" in row


def test_provider_analysis_access_legacy_string_session():
    # Unit lock for the original AttributeError root cause
    import tempfile

    td = Path(tempfile.mkdtemp())
    store = td / "entitlements.json"
    store.write_text(
        json.dumps({"u": {"sessions": {"s1": "legacy"}, "analyses": {}}}),
        encoding="utf-8",
    )
    p = MockEntitlementProvider(store)
    out = p.analysis_access("u", "a" * 32)
    assert out["song_detail_unlocked"] is False
