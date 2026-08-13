"""API-level E2E: concern → safety → recording choice → start → next task."""

from __future__ import annotations

import io
import struct
import time
import wave

from fastapi.testclient import TestClient

from backend.app.main import app


def _wav(seconds: float = 2.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(struct.pack("<h", 1200) * int(44100 * seconds))
    return buf.getvalue()


def _headers(user: str) -> dict[str, str]:
    return {"X-User-Id": user, "X-VAgent-User-Key": user}


def _session(client: TestClient, user: str) -> str:
    h = _headers(user)
    up = client.post(
        "/v1/analyses",
        files={"file": ("t.wav", _wav(3.0), "audio/wav")},
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "VOCAL_ONLY", "separate": "false"},
        headers=h,
    )
    assert up.status_code == 200
    aid = up.json()["analysis_id"]
    for _ in range(80):
        st = client.get(f"/v1/analyses/{aid}", headers=h).json()
        if st.get("status") == "completed":
            break
        time.sleep(0.3)
    assert st.get("status") == "completed"
    client.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=h)
    sid = client.post(f"/v1/diagnostic-sessions?source_analysis_id={aid}", headers=h).json()[
        "session_id"
    ]
    pay = client.post(
        f"/v1/diagnostic-sessions/{sid}/mock-pay",
        headers=h,
        json={"product_id": "diagnostic_upgrade"},
    )
    assert pay.status_code == 200
    return sid


def test_e2e_api_safety_to_recording_task():
    c = TestClient(app)
    h = _headers("e2e-safety-rec")
    sid = _session(c, "e2e-safety-rec")
    concerns = c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=h,
        json={
            "diagnostic_mode": "CONCERN_FOCUSED",
            "user_concerns": [{"id": "THROAT_EFFORT"}],
        },
    )
    assert concerns.status_code == 200
    assert concerns.json()["status"] == "SAFETY_CHECK"

    safety = c.post(
        f"/v1/diagnostic-sessions/{sid}/safety",
        headers=h,
        json={"answers": {"pain_on_phonation": False}},
    )
    assert safety.status_code == 200
    body = safety.json()
    assert body["status"] == "RECORDING_CHOICE"
    assert len(body["selected_tasks"]) >= 1

    started = c.post(f"/v1/diagnostic-sessions/{sid}/start-controlled-recordings", headers=h)
    assert started.status_code == 200
    s2 = started.json()
    assert s2["status"] == "TASKS_IN_PROGRESS"
    assert s2.get("next_task_id")


def test_e2e_api_pain_to_safety_limited():
    c = TestClient(app)
    h = _headers("e2e-pain-limited")
    sid = _session(c, "e2e-pain-limited")
    c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=h,
        json={
            "diagnostic_mode": "CONCERN_FOCUSED",
            "user_concerns": [{"id": "HIGH_NOTE_TOO_EFFORTFUL"}],
        },
    )
    safety = c.post(
        f"/v1/diagnostic-sessions/{sid}/safety",
        headers=h,
        json={"answers": {"pain_on_phonation": True}},
    )
    assert safety.status_code == 200
    body = safety.json()
    assert body["status"] == "READY_FOR_ANALYSIS"
    assert body["selected_tasks"] == []
    assert body["diagnostic_status"] == "SAFETY_LIMITED"
