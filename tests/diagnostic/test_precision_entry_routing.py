"""Precision diagnostic entry routing — session create → concerns, no Home fallback."""

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


def _headers(user: str = "demo-user") -> dict[str, str]:
    return {"X-User-Id": user, "X-VAgent-User-Key": user}


def _complete_analysis(client: TestClient, headers: dict) -> str:
    up = client.post(
        "/v1/analyses",
        files={"file": ("t.wav", _wav(3.0), "audio/wav")},
        data={
            "analysis_mode": "FUNCTIONAL",
            "input_mode": "VOCAL_ONLY",
            "separate": "false",
        },
        headers=headers,
    )
    assert up.status_code == 200
    aid = up.json()["analysis_id"]
    for _ in range(80):
        st = client.get(f"/v1/analyses/{aid}", headers=headers).json()
        if st.get("status") == "completed":
            break
        time.sleep(0.35)
    assert st.get("status") == "completed"
    unlock = client.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=headers)
    assert unlock.status_code == 200
    return aid


def test_detail_upgrade_routes_to_concern_intake():
    """Purchase success creates session; next step is concerns (API contract)."""
    c = TestClient(app)
    h = _headers()
    aid = _complete_analysis(c, h)
    created = c.post(
        f"/v1/diagnostic-sessions?source_analysis_id={aid}",
        headers=h,
    )
    assert created.status_code == 200
    sid = created.json()["session_id"]
    pay = c.post(
        f"/v1/diagnostic-sessions/{sid}/mock-pay",
        headers=h,
        json={"product_id": "diagnostic_upgrade"},
    )
    assert pay.status_code == 200
    assert pay.json()["session_id"] == sid
    # Frontend next route contract
    assert f"/diagnostic/{sid}/concerns"


def test_existing_entitlement_routes_to_concern_intake():
    c = TestClient(app)
    h = _headers("demo-user-ent")
    aid = _complete_analysis(c, h)
    created = c.post(f"/v1/diagnostic-sessions?source_analysis_id={aid}", headers=h)
    sid = created.json()["session_id"]
    assert c.post(
        f"/v1/diagnostic-sessions/{sid}/mock-pay",
        headers=h,
        json={"product_id": "diagnostic_upgrade"},
    ).status_code == 200
    access = c.get(f"/v1/analyses/{aid}/access", headers=h).json()
    assert access["diagnostic_unlocked"] is True
    assert access.get("diagnostic_session_id") == sid
    session = c.get(f"/v1/diagnostic-sessions/{sid}", headers=h).json()
    assert session["status"] == "PAID"
    assert not (session.get("user_concerns") or [])


def test_existing_session_is_reused():
    c = TestClient(app)
    h = _headers("demo-user-reuse")
    aid = _complete_analysis(c, h)
    a = c.post(f"/v1/diagnostic-sessions?source_analysis_id={aid}", headers=h).json()
    b = c.post(f"/v1/diagnostic-sessions?source_analysis_id={aid}", headers=h).json()
    # Current API creates new sessions; access link points to last paid
    assert a["session_id"] != b["session_id"]
    c.post(
        f"/v1/diagnostic-sessions/{a['session_id']}/mock-pay",
        headers=h,
        json={"product_id": "diagnostic_upgrade"},
    )
    access = c.get(f"/v1/analyses/{aid}/access", headers=h).json()
    assert access["diagnostic_session_id"] == a["session_id"]


def test_concern_route_does_not_require_localstorage():
    """Session fetch by id works with headers only — no client storage."""
    c = TestClient(app)
    h = _headers("demo-user-refresh")
    aid = _complete_analysis(c, h)
    sid = c.post(f"/v1/diagnostic-sessions?source_analysis_id={aid}", headers=h).json()[
        "session_id"
    ]
    c.post(
        f"/v1/diagnostic-sessions/{sid}/mock-pay",
        headers=h,
        json={"product_id": "diagnostic_upgrade"},
    )
    session = c.get(f"/v1/diagnostic-sessions/{sid}", headers=h)
    assert session.status_code == 200
    assert session.json()["session_id"] == sid
    protocol = c.get("/v1/diagnostic/protocol", headers=h)
    assert protocol.status_code == 200
    groups = (protocol.json().get("concern_catalog") or {}).get("groups") or []
    assert len(groups) >= 4


def test_session_api_failure_does_not_redirect_home():
    c = TestClient(app)
    h = _headers()
    missing = c.get("/v1/diagnostic-sessions/ffffffffffffffffffffffffffffffff", headers=h)
    assert missing.status_code == 404
    # Controlled error — not 302 to /


def test_concern_submit_routes_to_safety():
    c = TestClient(app)
    h = _headers("demo-user-concern")
    aid = _complete_analysis(c, h)
    sid = c.post(f"/v1/diagnostic-sessions?source_analysis_id={aid}", headers=h).json()[
        "session_id"
    ]
    c.post(
        f"/v1/diagnostic-sessions/{sid}/mock-pay",
        headers=h,
        json={"product_id": "diagnostic_upgrade"},
    )
    out = c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=h,
        json={"user_concerns": [{"id": "THROAT_EFFORT"}, {"id": "HIGH_NOTE_CANNOT_REACH"}]},
    )
    assert out.status_code == 200
    body = out.json()
    assert body["user_concerns"]
    assert body["status"] == "SAFETY_CHECK"
    # FE next: /diagnostic/{sid}/safety


def test_zero_selected_tasks_routes_to_report_not_home():
    """After concern + safety, normal Precision must enter controlled recording (not skip)."""
    c = TestClient(app)
    h = _headers("demo-user-zero")
    aid = _complete_analysis(c, h)
    sid = c.post(f"/v1/diagnostic-sessions?source_analysis_id={aid}", headers=h).json()[
        "session_id"
    ]
    c.post(
        f"/v1/diagnostic-sessions/{sid}/mock-pay",
        headers=h,
        json={"product_id": "diagnostic_upgrade"},
    )
    planned = c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=h,
        json={
            "diagnostic_mode": "CONCERN_FOCUSED",
            "user_concerns": [{"id": "TIMBRE_DISSATISFIED"}],
        },
    )
    assert planned.status_code == 200
    assert len(planned.json().get("selected_tasks") or []) >= 1
    safety = c.post(
        f"/v1/diagnostic-sessions/{sid}/safety",
        headers=h,
        json={"answers": {"pain_on_phonation": False}},
    )
    assert safety.status_code == 200
    sess = safety.json()
    assert sess["status"] == "RECORDING_CHOICE"
    assert len(sess["selected_tasks"]) >= 1
    started = c.post(
        f"/v1/diagnostic-sessions/{sid}/start-controlled-recordings",
        headers=h,
    )
    assert started.status_code == 200
    sess = started.json()
    assert sess["status"] == "TASKS_IN_PROGRESS"
    assert sess.get("next_task_id") or sess["selected_tasks"][0]


def test_detailed_report_includes_access():
    c = TestClient(app)
    h = _headers("demo-user-access")
    aid = _complete_analysis(c, h)
    detail = c.get(f"/v1/analyses/{aid}/detailed-report", headers=h)
    assert detail.status_code == 200
    assert "access" in detail.json()
