"""Song Detail vs Diagnostic entitlement split tests."""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.api import routes as routes_mod
from backend.app.diagnostic.service import DiagnosticSessionService
from backend.app.services.analysis_service import AnalysisService
from backend.app.jobs.runner import JobRunner
from backend.app.products import product_catalog
from backend.app.entitlements import allow_dev_bypass


@pytest.fixture()
def client(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    svc = AnalysisService()
    svc.runtime_dir = runtime
    svc.max_upload_mb = 2.0
    svc.runner = JobRunner(runtime, max_workers=1)
    diag = DiagnosticSessionService(runtime)
    monkeypatch.setattr(routes_mod, "service", svc)
    monkeypatch.setattr(routes_mod, "diag", diag)
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("ALLOW_MOCK_PREMIUM", "true")
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    return TestClient(app), svc, diag, runtime


def _wav(duration=3.0, freq=220.0, sr=22050) -> bytes:
    t = np.arange(int(sr * duration)) / sr
    y = (0.28 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    return buf.getvalue()


def _wait_done(c: TestClient, analysis_id: str, timeout=60.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        job = c.get(f"/v1/analyses/{analysis_id}", headers={"X-User-Id": "u1"}).json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.2)
    raise TimeoutError(analysis_id)


def test_free_detailed_report_402(client):
    c, _, _, _ = client
    headers = {"X-User-Id": "u1"}
    aid = c.post(
        "/v1/analyses",
        files={"file": ("t.wav", _wav(), "audio/wav")},
        data={"separate": "false", "include_feedback": "false"},
        headers=headers,
    ).json()["analysis_id"]
    _wait_done(c, aid)
    locked = c.get(f"/v1/analyses/{aid}/detailed-report", headers=headers)
    assert locked.status_code == 402
    assert locked.json()["detail"] == "SONG_DETAIL_LOCKED"


def test_mock_song_detail_unlock_and_report(client):
    c, _, _, _ = client
    headers = {"X-User-Id": "u1"}
    aid = c.post(
        "/v1/analyses",
        files={"file": ("t.wav", _wav(), "audio/wav")},
        data={"separate": "false"},
        headers=headers,
    ).json()["analysis_id"]
    _wait_done(c, aid)
    unlock = c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=headers)
    assert unlock.status_code == 200
    assert unlock.json()["redirect"].endswith("/detail")
    # idempotent
    assert c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=headers).status_code == 200
    report = c.get(f"/v1/analyses/{aid}/detailed-report", headers=headers)
    assert report.status_code == 200
    body = report.json()
    assert body["report_kind"] == "song_detail"
    assert "areas" in body
    assert "physiology_assessments" not in body
    assert "reliable_findings" not in body
    assert "scientific_debug" not in body
    blob = json.dumps(body, ensure_ascii=False)
    # Raw GIF / cepstral metrics must stay out of Song Detail public JSON
    assert "cepstral_prominence" not in blob
    assert "estimated_naq" not in blob
    assert "scientific_debug" not in blob
    # Physiology premium payloads still banned
    assert "phonation_contact_pattern" not in blob
    assert "physiology_assessments" not in blob


def test_song_detail_does_not_grant_diagnostic(client):
    c, _, diag, _ = client
    headers = {"X-User-Id": "u1"}
    aid = c.post(
        "/v1/analyses",
        files={"file": ("t.wav", _wav(), "audio/wav")},
        headers=headers,
    ).json()["analysis_id"]
    _wait_done(c, aid)
    c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=headers)
    sid = c.post(
        "/v1/diagnostic-sessions",
        headers=headers,
        params={"source_analysis_id": aid},
    ).json()["session_id"]
    # no diagnostic unlock yet
    locked = c.get(f"/v1/diagnostic-sessions/{sid}/report", headers=headers)
    assert locked.status_code == 402
    safety = c.post(
        f"/v1/diagnostic-sessions/{sid}/safety",
        headers=headers,
        json={"answers": {}},
    )
    assert safety.status_code == 402


def test_diagnostic_full_includes_song_detail(client):
    c, _, _, _ = client
    headers = {"X-User-Id": "u1"}
    aid = c.post(
        "/v1/analyses",
        files={"file": ("t.wav", _wav(), "audio/wav")},
        headers=headers,
    ).json()["analysis_id"]
    _wait_done(c, aid)
    sid = c.post(
        "/v1/diagnostic-sessions",
        headers=headers,
        params={"source_analysis_id": aid},
    ).json()["session_id"]
    pay = c.post(
        f"/v1/diagnostic-sessions/{sid}/mock-pay",
        headers=headers,
        json={"product_id": "diagnostic_full"},
    )
    assert pay.status_code == 200
    # Song detail unlocked as bundle
    detail = c.get(f"/v1/analyses/{aid}/detailed-report", headers=headers)
    assert detail.status_code == 200
    access = c.get(f"/v1/analyses/{aid}/access", headers=headers).json()
    assert access["song_detail_unlocked"] is True
    assert access["diagnostic_unlocked"] is True
    # Safety allowed
    assert (
        c.post(
            f"/v1/diagnostic-sessions/{sid}/safety",
            headers=headers,
            json={"answers": {"pain_on_phonation": False}},
        ).status_code
        == 200
    )


def test_analysis_a_unlock_not_b(client):
    c, _, _, _ = client
    headers = {"X-User-Id": "u1"}
    a1 = c.post(
        "/v1/analyses", files={"file": ("a.wav", _wav(), "audio/wav")}, headers=headers
    ).json()["analysis_id"]
    a2 = c.post(
        "/v1/analyses", files={"file": ("b.wav", _wav(), "audio/wav")}, headers=headers
    ).json()["analysis_id"]
    _wait_done(c, a1)
    _wait_done(c, a2)
    c.post(f"/v1/analyses/{a1}/mock-unlock-detail", headers=headers)
    assert c.get(f"/v1/analyses/{a1}/detailed-report", headers=headers).status_code == 200
    assert c.get(f"/v1/analyses/{a2}/detailed-report", headers=headers).status_code == 402


def test_diagnostic_upgrade_keeps_song_detail(client):
    c, _, _, _ = client
    headers = {"X-User-Id": "u1"}
    aid = c.post(
        "/v1/analyses", files={"file": ("t.wav", _wav(), "audio/wav")}, headers=headers
    ).json()["analysis_id"]
    _wait_done(c, aid)
    c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=headers)
    offers = c.get(f"/v1/products?analysis_id={aid}", headers=headers).json()
    assert offers["offers"]["diagnostic"] == "diagnostic_upgrade"
    sid = c.post(
        "/v1/diagnostic-sessions",
        headers=headers,
        params={"source_analysis_id": aid},
    ).json()["session_id"]
    c.post(
        f"/v1/diagnostic-sessions/{sid}/mock-pay",
        headers=headers,
        json={"product_id": "diagnostic_upgrade"},
    )
    assert c.get(f"/v1/analyses/{aid}/detailed-report", headers=headers).status_code == 200
    assert offers["products"]["diagnostic_upgrade"]["mock_amount_krw"] == 2000


def test_free_api_no_detail_leak(client):
    c, _, _, _ = client
    headers = {"X-User-Id": "u1"}
    aid = c.post(
        "/v1/analyses", files={"file": ("t.wav", _wav(), "audio/wav")}, headers=headers
    ).json()["analysis_id"]
    job = _wait_done(c, aid)
    result = job["result"] or {}
    assert "timeline" not in result
    assert "optional_analysis" not in result
    assert "physiology_assessments" not in result
    assert "focus_segments" not in result
    assert "overall_assessment" not in result
    assert result.get("tier") == "free"
    for a in (result.get("score") or {}).get("areas") or []:
        assert "submetrics" not in a
        assert "segment_scores" not in a
        assert "why_this_score" not in a
        assert "focus_segments" not in a
    blob = str(result)
    assert "segment_scores" not in blob
    assert "why_this_score" not in blob


def test_mock_disabled_in_production(client, monkeypatch):
    c, _, _, _ = client
    monkeypatch.setenv("VAGENT_ENV", "production")
    headers = {"X-User-Id": "u1"}
    aid = c.post(
        "/v1/analyses", files={"file": ("t.wav", _wav(), "audio/wav")}, headers=headers
    ).json()["analysis_id"]
    _wait_done(c, aid)
    assert c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=headers).status_code == 403
    sid = c.post("/v1/diagnostic-sessions", headers=headers).json()["session_id"]
    assert c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=headers).status_code == 403


def test_product_catalog_mock_amounts():
    cat = product_catalog(song_detail_owned=False)
    assert cat["products"]["song_detail"]["mock_amount_krw"] == 1000
    assert cat["products"]["diagnostic_full"]["mock_amount_krw"] == 3000
    assert cat["products"]["diagnostic_upgrade"]["mock_amount_krw"] == 2000
    assert cat["offers"]["diagnostic"] == "diagnostic_full"
    cat2 = product_catalog(song_detail_owned=True)
    assert cat2["offers"]["diagnostic"] == "diagnostic_upgrade"
    assert cat2["offers"]["song_detail"] is None


def test_song_detail_builder_no_physiology():
    from audio_analyzer.song_detail import build_song_detailed_report

    fake = {
        "score": {
            "available": True,
            "overall": 72,
            "label": "좋은 편",
            "areas": [
                {
                    "area_id": "stability",
                    "display_name": "발성 안정성",
                    "score": 70,
                    "status": "good",
                    "confidence": 0.7,
                }
            ],
            "strengths": [],
            "priority_issues": [],
        },
        "quality": {"status": "pass"},
        "timeline": [{"start_sec": 1.0, "end_sec": 2.0, "user_message": "흔들림"}],
        "optional_analysis": {"vibrato": {"available": False}},
        "analysis_notes": [],
        "audio": {},
    }
    report = build_song_detailed_report(fake, analysis_id="abc")
    assert report["report_kind"] == "song_detail"
    assert "physiology_assessments" not in report
    assert "reliable_findings" not in report
    assert report["areas"][0]["area_id"] == "stability"
