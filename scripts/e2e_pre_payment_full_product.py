"""
Pre-payment full product API E2E journey.

Fresh user → analyze → free locked → mock Detail unlock → goal →
second analysis → progress → mock Precision → partial tasks → report →
service recreate (restart simulation) → entitlements/session/goal intact.

No real payment. Uses TestClient + shared runtime_dir.
"""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "qa_output" / "prepayment_v1"
USER = "prepay_e2e_user"
HEADERS = {"X-User-Id": USER}


def _wav(duration: float = 3.5, freq: float = 220.0, sr: int = 22050) -> bytes:
    t = np.arange(int(sr * duration)) / sr
    y = (0.28 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    return buf.getvalue()


def _wait(c: TestClient, aid: str, timeout: float = 90.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        body = c.get(f"/v1/analyses/{aid}", headers=HEADERS).json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.2)
    raise TimeoutError(aid)


def _bind_runtime(runtime: Path, monkeypatch_env: dict):
    import os

    for k, v in monkeypatch_env.items():
        os.environ[k] = v

    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()

    from backend.app.api import routes as routes_mod
    from backend.app.diagnostic.service import DiagnosticSessionService
    from backend.app.jobs.runner import JobRunner
    from backend.app.main import app
    from backend.app.services.analysis_service import AnalysisService
    from backend.app.services import goal_store as goal_store_mod

    # Reset goal store singleton to this runtime
    goal_store_mod._goal_store = None

    svc = AnalysisService()
    svc.runtime_dir = runtime
    svc.runner = JobRunner(runtime, max_workers=1)
    diag = DiagnosticSessionService(runtime)
    routes_mod.service = svc
    routes_mod.diag = diag
    return TestClient(app), svc, diag


def main() -> int:
    import os
    import tempfile

    results: dict = {"steps": [], "ok": True, "errors": []}

    def step(name: str, ok: bool, detail: str = ""):
        results["steps"].append({"name": name, "ok": ok, "detail": detail})
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            results["ok"] = False
            results["errors"].append({"name": name, "detail": detail})

    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="vagent_prepay_"))
    runtime = tmp / "runtime"
    runtime.mkdir()

    env = {
        "VAGENT_ENV": "development",
        "ALLOW_MOCK_PREMIUM": "true",
        "RUNTIME_DIR": str(runtime),
    }
    # Ensure no DATABASE_URL so file entitlements are used
    os.environ.pop("DATABASE_URL", None)

    c, svc, diag = _bind_runtime(runtime, env)

    # —— 1. Free analysis ——
    r = c.post(
        "/v1/analyses",
        files={"file": ("a1.wav", _wav(), "audio/wav")},
        data={"separate": "false", "include_feedback": "false"},
        headers=HEADERS,
    )
    step("create_analysis", r.status_code == 200, r.text[:200])
    if r.status_code != 200:
        _write(results)
        return 1
    aid = r.json()["analysis_id"]
    job = _wait(c, aid)
    step("analysis_complete", job["status"] == "completed", job["status"])

    access = c.get(f"/v1/analyses/{aid}/access", headers=HEADERS).json()
    step(
        "free_detail_locked",
        access.get("song_detail_unlocked") is False
        and access.get("diagnostic_unlocked") is False,
        str(access),
    )

    locked = c.get(f"/v1/analyses/{aid}/detailed-report", headers=HEADERS)
    step(
        "direct_detail_url_blocked",
        locked.status_code == 402 and locked.json().get("detail") == "SONG_DETAIL_LOCKED",
        f"{locked.status_code} {locked.text[:120]}",
    )

    # —— 2. Mock Detail unlock ——
    u1 = c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=HEADERS)
    u2 = c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=HEADERS)
    step("detail_mock_unlock", u1.status_code == 200, u1.text[:120])
    step("detail_unlock_idempotent", u2.status_code == 200)

    detail = c.get(f"/v1/analyses/{aid}/detailed-report", headers=HEADERS)
    step("detail_report_after_unlock", detail.status_code == 200, f"keys={list((detail.json() or {}).keys())[:8]}")

    access2 = c.get(f"/v1/analyses/{aid}/access", headers=HEADERS).json()
    step(
        "detail_only_not_precision",
        access2.get("song_detail_unlocked") is True
        and access2.get("diagnostic_unlocked") is False,
        str(access2),
    )

    # —— 3. Goal ——
    put = c.put(
        "/v1/me/vocal-goals/active",
        headers=HEADERS,
        json={
            "focus": "REGISTER_CONNECTION",
            "label": "고음 구간을 더 안정적으로 연결하기",
            "source": "USER_SELECTED",
        },
    )
    step("goal_set", put.status_code == 200, put.text[:160])
    goals = c.get("/v1/me/vocal-goals", headers=HEADERS)
    active = (goals.json() or {}).get("active") if goals.status_code == 200 else None
    step("goal_get_active", bool(active and (active.get("goal_focus") or active.get("focus"))), str(active)[:160])

    # —— 4. Second analysis + progress ——
    r2 = c.post(
        "/v1/analyses",
        files={"file": ("a2.wav", _wav(duration=3.8, freq=246.0), "audio/wav")},
        data={"separate": "false"},
        headers=HEADERS,
    )
    aid2 = r2.json()["analysis_id"]
    job2 = _wait(c, aid2)
    step("second_analysis", job2["status"] == "completed")

    # Free result access still has no goal fields required — check insight accepts goal
    insight = c.post(
        "/v1/me/vocal-progress/insight",
        headers=HEADERS,
        json={
            "current_canonical": {"register_connection": "CONNECTED"},
            "goal": {
                "focus": "REGISTER_CONNECTION",
                "label": "고음 구간을 더 안정적으로 연결하기",
                "source": "USER_SELECTED",
            },
            "recent_n": 5,
            "historical_snapshots": [
                {"canonical_json": {"register_connection": "PARTIAL"}},
                {"canonical_json": {"register_connection": "PARTIAL"}},
                {"canonical_json": {"register_connection": "DISRUPTED"}},
            ],
        },
    )
    step("progress_insight_goal_aware", insight.status_code in (200, 404), f"{insight.status_code}")

    # —— 5. Precision: still locked for report until mock-pay ——
    sid_r = c.post(
        "/v1/diagnostic-sessions",
        headers=HEADERS,
        params={"source_analysis_id": aid2},
    )
    step("diagnostic_session_create", sid_r.status_code == 200, sid_r.text[:120])
    sid = sid_r.json()["session_id"]

    rep_locked = c.get(f"/v1/diagnostic-sessions/{sid}/report", headers=HEADERS)
    step(
        "precision_report_locked_before_pay",
        rep_locked.status_code == 402,
        f"{rep_locked.status_code}",
    )

    pay = c.post(
        f"/v1/diagnostic-sessions/{sid}/mock-pay",
        headers=HEADERS,
        json={"product_id": "diagnostic_upgrade"},
    )
    pay2 = c.post(
        f"/v1/diagnostic-sessions/{sid}/mock-pay",
        headers=HEADERS,
        json={"product_id": "diagnostic_upgrade"},
    )
    step("precision_mock_pay", pay.status_code == 200, pay.text[:120])
    step("precision_pay_idempotent", pay2.status_code == 200)

    # concerns + safety + one task + skip rest
    planned = c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=HEADERS,
        json={"diagnostic_mode": "GENERAL_DISCOVERY", "user_concerns": []},
    )
    step("concerns_general_discovery", planned.status_code == 200)
    assert (
        c.post(
            f"/v1/diagnostic-sessions/{sid}/safety",
            headers=HEADERS,
            json={"answers": {"pain_on_phonation": False}},
        ).status_code
        == 200
    )
    start = c.post(f"/v1/diagnostic-sessions/{sid}/start-controlled-recordings", headers=HEADERS)
    step("start_controlled_recordings", start.status_code == 200)

    session = c.get(f"/v1/diagnostic-sessions/{sid}", headers=HEADERS).json()
    selected = list(session.get("selected_tasks") or [])
    step("has_selected_tasks", len(selected) >= 1, str(selected))

    if selected:
        first = selected[0]
        up = c.post(
            f"/v1/diagnostic-sessions/{sid}/tasks/{first}",
            headers=HEADERS,
            files={"file": ("t.wav", _wav(4.0), "audio/wav")},
        )
        step("upload_one_task", up.status_code == 200, up.text[:160])

    skip = c.post(
        f"/v1/diagnostic-sessions/{sid}/skip-controlled-recordings",
        headers=HEADERS,
        json={"remaining_only": True},
    )
    step("skip_remaining_tasks", skip.status_code == 200, skip.text[:160])

    report = c.post(f"/v1/diagnostic-sessions/{sid}/analyze", headers=HEADERS)
    step("precision_analyze", report.status_code == 200, f"status={report.status_code}")
    if report.status_code == 200:
        body = report.json()
        step(
            "precision_report_has_sections",
            bool(body.get("sections") or body.get("reliable_findings") is not None),
            str(list(body.keys())[:12]),
        )

    get_rep = c.get(f"/v1/diagnostic-sessions/{sid}/report", headers=HEADERS)
    step("precision_report_get", get_rep.status_code == 200)

    # —— 6. Restart simulation: new service instances, same runtime ——
    c2, svc2, diag2 = _bind_runtime(runtime, env)

    access_r = c2.get(f"/v1/analyses/{aid}/access", headers=HEADERS).json()
    step(
        "restart_detail_entitlement",
        access_r.get("song_detail_unlocked") is True,
        str(access_r),
    )
    detail_r = c2.get(f"/v1/analyses/{aid}/detailed-report", headers=HEADERS)
    step("restart_detail_report", detail_r.status_code == 200)

    goals_r = c2.get("/v1/me/vocal-goals", headers=HEADERS)
    active_r = (goals_r.json() or {}).get("active") if goals_r.status_code == 200 else None
    step(
        "restart_goal",
        bool(active_r and (active_r.get("goal_focus") or active_r.get("focus"))),
        str(active_r)[:160],
    )

    sess_r = c2.get(f"/v1/diagnostic-sessions/{sid}", headers=HEADERS)
    step("restart_diagnostic_session", sess_r.status_code == 200, f"{sess_r.status_code}")

    rep_r = c2.get(f"/v1/diagnostic-sessions/{sid}/report", headers=HEADERS)
    step("restart_diagnostic_report", rep_r.status_code == 200, f"{rep_r.status_code}")

    # —— 7. Frontend spoof cannot unlock (backend remains source of truth) ——
    # Other analysis without unlock
    r3 = c2.post(
        "/v1/analyses",
        files={"file": ("a3.wav", _wav(), "audio/wav")},
        headers=HEADERS,
    )
    aid3 = r3.json()["analysis_id"]
    _wait(c2, aid3)
    spoof = c2.get(f"/v1/analyses/{aid3}/detailed-report", headers=HEADERS)
    step(
        "backend_blocks_unpaid_detail",
        spoof.status_code == 402,
        f"{spoof.status_code}",
    )

    _write(results)
    print("\nE2E summary:", "PASS" if results["ok"] else "FAIL")
    print(f"Artifacts → {OUT}")
    return 0 if results["ok"] else 1


def _write(results: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "e2e_api_journey.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
