"""Diagnostic report lifecycle — READY → ANALYZING → COMPLETED."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.diagnostic.service import DiagnosticSessionService


class _Ent:
    # `provider` names the identity namespace; this stub unlocks regardless.
    def has_session_unlock(self, user_id, session_id, *, provider=None):
        return True


def _svc(tmp_path: Path) -> DiagnosticSessionService:
    svc = DiagnosticSessionService(runtime_dir=tmp_path)
    svc.entitlements = _Ent()
    return svc


def test_analyzing_does_not_raise_user_visible_report_not_ready(tmp_path: Path):
    svc = _svc(tmp_path)
    sid = "a" * 32
    d = svc._dir(sid)
    d.mkdir(parents=True)
    session = {
        "session_id": sid,
        "user_id": "anon",
        "status": "ANALYZING",
    }
    (d / "session.json").write_text(json.dumps(session), encoding="utf-8")
    out = svc.get_report(sid, "anon")
    assert out.get("error") == "REPORT_GENERATING"
    assert out.get("status") == "ANALYZING"
    assert "report not ready" not in str(out).lower()


def test_ready_triggers_analysis(tmp_path: Path, monkeypatch):
    svc = _svc(tmp_path)
    sid = "b" * 32
    d = svc._dir(sid)
    d.mkdir(parents=True)
    session = {
        "session_id": sid,
        "user_id": "anon",
        "status": "READY_FOR_ANALYSIS",
        "task_results": [],
        "selected_tasks": [],
        "user_concerns": [],
    }
    (d / "session.json").write_text(json.dumps(session), encoding="utf-8")

    called = {"n": 0}

    def _fake_analyze(session_id, user_id="anon"):
        called["n"] += 1
        return {"ok": True, "session_id": session_id}

    monkeypatch.setattr(svc, "analyze", _fake_analyze)
    out = svc.get_report(sid, "anon")
    assert called["n"] == 1
    assert out.get("ok") is True


def test_completed_returns_report(tmp_path: Path):
    svc = _svc(tmp_path)
    sid = "c" * 32
    d = svc._dir(sid)
    d.mkdir(parents=True)
    session = {"session_id": sid, "user_id": "anon", "status": "COMPLETED"}
    (d / "session.json").write_text(json.dumps(session), encoding="utf-8")
    report = {
        "summary": {"headline": "ok"},
        "sections": {},
        "reliable_findings": [],
        "uncertain_findings": [],
    }
    (d / "premium_report.json").write_text(json.dumps(report), encoding="utf-8")
    out = svc.get_report(sid, "anon", include_scientific_debug=True)
    assert out.get("error") != "REPORT_GENERATING"
    assert out.get("summary", {}).get("headline") == "ok"
