"""QA v4 runtime integration: vite default port, stale report policy, fresh QA."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from audio_analyzer.diagnostic.concern_resolver import evaluate_concern
from audio_analyzer.diagnostic.concerns import build_personalized_qa
from audio_analyzer.diagnostic.report_versions import (
    GOAL_VERSION,
    QA_GUIDANCE_VERSION,
    REPORT_LOGIC_VERSION,
)
from audio_analyzer.diagnostic.song_evidence import get_canonical_snapshot

MISSING = (
    "충분히 비교되지 않았어요",
    "하나로 좁히기 어려워요",
    "알기 어려워요",
    "확인하기 어려워요",
    "추가 확인이 필요해요",
)


def _song(
    *,
    effort="LOW",
    contact="FIRM",
    register="PARTIAL",
    presence=0.72,
    breath="LOW",
    brightness=None,
    stability="STABLE",
    high_note_available=False,
):
    cont = {"FIRM": 0.72, "LIGHT": 0.28, "MID": 0.5}.get(contact, 0.5)
    axes = {"airiness": {"continuum": 0.25}}
    if presence is not None:
        axes["presence"] = {"continuum": presence}
    if brightness is not None:
        axes["brightness"] = {"continuum": brightness}
    return {
        "vocal_function_profile": {
            "effort_assessment": {"severity": effort},
            "dimensions": {
                "vocal_effort_strain": {"status": effort},
                "glottal_contact_profile": {
                    "status": "OBSERVED",
                    "continuum_0_to_1": cont,
                    "status_label": "단단" if contact == "FIRM" else "중간",
                },
                "air_leakage_breathiness": {"status": breath},
                "phonation_regularity": {"status": stability},
            },
            "vocal_type_profile": {
                "register_strategy": {"status": register},
                "canonical_register": {"status": register},
            },
            "timbre_profile": {"available": True, "axes": axes},
            "high_note_function_profile": {
                "available": bool(high_note_available),
                "reason": None,
                "summary": None,
                "axes": {},
            },
        }
    }


def _skip():
    return {
        "task_profiles": {},
        "controlled_contrasts": {},
        "user_skipped_tasks": ["siren", "high_note_sustain_a"],
        "task_evidence": {"user_skipped_tasks": ["siren", "high_note_sustain_a"]},
    }


def test_vite_default_proxy_is_8000():
    text = Path("miniapp/vite.config.ts").read_text(encoding="utf-8")
    assert "VITE_API_PROXY_TARGET" in text
    assert "http://127.0.0.1:8000" in text
    assert "'http://127.0.0.1:8001'" not in text
    assert '"http://127.0.0.1:8001"' not in text
    e2e = Path("miniapp/scripts/e2e_qa_v4_runtime_browser.mjs").read_text(encoding="utf-8")
    assert "VAGENT_E2E_API" in e2e
    assert "vite.config.ts" in e2e
    assert "Do not edit miniapp/vite.config.ts" in e2e


def test_nasal_with_partial_register_returns_actionable_guidance():
    ev = evaluate_concern(
        "VOICE_TOO_NASAL_PERCEPT",
        song_profile=_song(register="PARTIAL", presence=0.72),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "직접 확정할 음향 지표는 제한적이에요" not in ans
    assert "비교해보기" not in ans
    assert "모음" in (ev.get("what_to_change") or ans)
    assert ev.get("what_to_change")
    assert ev.get("prescription")
    assert (ev.get("action") or {}).get("short_instruction")
    assert ev.get("success_cues")
    assert ev.get("comparison_protocol", {}).get("A")
    assert "콧구멍이" not in ans
    assert "비강" not in ans or "확정하지" in ans
    ks = str(ev.get("knowledge_support") or "")
    if ks:
        assert ks not in ans


def test_thin_low_breath_high_presence_partial_register_uses_register_action():
    ev = evaluate_concern(
        "VOICE_TOO_THIN",
        song_profile=_song(breath="LOW", presence=0.72, register="PARTIAL"),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "숨이 많이 새" in ans or "두드러지지" in ans or "막는 방향은 우선" in ans
    assert "비교해보기" not in ans
    assert (ev.get("comparison") or {}).get("B") or ev.get("prescription")
    assert ev.get("primary_focus") == "REGISTER_CONNECTION"
    assert ev.get("what_to_change")
    assert "얇지 않아요" not in ans
    assert "뚜렷한 음향 특징이 강하지 않아요" not in ans


def test_high_timbre_change_partial_register_uses_register_connection():
    ev = evaluate_concern(
        "TIMBRE_CHANGES_HIGH",
        song_profile=_song(register="PARTIAL", high_note_available=False),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "하나로 좁히기" not in ans
    assert "한 원인으로 단정" not in ans
    assert "음역" in ans
    assert "비교해보기" not in ans
    assert (ev.get("comparison") or {}).get("B") or ev.get("prescription")
    assert "\n\n→ " in ans
    assert ev.get("primary_focus") == "REGISTER_CONNECTION"
    pid = (ev.get("action") or {}).get("practice_id") or (ev.get("practice") or {}).get("practice_id")
    assert pid == "REGISTER_GLIDE_LIGHT"


def test_knowledge_support_not_appended_to_public_answer():
    ev = evaluate_concern(
        "TIMBRE_CHANGES_HIGH",
        song_profile=_song(register="PARTIAL"),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    ks = str(ev.get("knowledge_support") or "")
    assert ks
    assert "음역 전환이 급격할 때는" not in ans or ans.count("고음을 더") <= 1
    assert ks not in ans
    assert ev.get("knowledge_support_internal") is True


def test_convergent_register_focus_promotes_global_goal_over_style():
    from audio_analyzer.diagnostic.concerns import build_personalized_qa
    from audio_analyzer.diagnostic.goal_planner import plan_coaching_goal

    concerns = [
        {"id": "VOICE_TOO_NASAL_PERCEPT"},
        {"id": "VOICE_TOO_THIN"},
        {"id": "TIMBRE_CHANGES_HIGH"},
    ]
    qa = build_personalized_qa(
        user_concerns=concerns,
        song_profile=_song(),
        fused_profile=_skip(),
        timbre_goal={"id": "INTENSE_DISTINCT", "label": "강렬하고 개성 있게"},
    )
    goal = plan_coaching_goal(
        user_concerns=concerns,
        timbre_goal={"id": "INTENSE_DISTINCT", "label": "강렬하고 개성 있게"},
        concern_evaluations=qa.get("concern_evaluations") or [],
        song_profile=_song(),
    )
    assert goal.get("primary_focus") == "REGISTER_CONNECTION"
    assert goal.get("mode") != "STYLE"
    assert "음역" in (goal.get("goal_title") or "")


def test_nasal_does_not_claim_measured_nasality():
    ev = evaluate_concern(
        "VOICE_TOO_NASAL_PERCEPT",
        song_profile=_song(),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "콧소리로 측정" not in ans
    assert "비음이 확인" not in ans
    assert "후두" not in ans


def test_thin_does_not_claim_high_breathiness_when_breathiness_low():
    ev = evaluate_concern(
        "VOICE_TOO_THIN",
        song_profile=_song(breath="LOW", presence=0.72, register="PARTIAL"),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "숨 섞임이 큰 편" not in ans
    assert "숨이 많이 새" in ans or "두드러지지" in ans


def test_high_timbre_does_not_claim_direct_high_note_measurement_when_unavailable():
    ev = evaluate_concern(
        "TIMBRE_CHANGES_HIGH",
        song_profile=_song(register="PARTIAL", high_note_available=False),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "고음 자체를 직접 비교" not in ans
    assert "음역이 올라가는 과정" in ans or "음역이 올라갈 때" in ans or "중음에서 위쪽" in ans


def test_related_available_evidence_prevents_terminal_unknown_answer():
    qa = build_personalized_qa(
        user_concerns=[
            {"id": "VOICE_TOO_NASAL_PERCEPT"},
            {"id": "VOICE_TOO_THIN"},
            {"id": "TIMBRE_CHANGES_HIGH"},
        ],
        song_profile=_song(),
        fused_profile=_skip(),
        timbre_goal={"id": "INTENSE_DISTINCT"},
    )
    blob = " ".join(q.get("answer") or "" for q in qa["questions"])
    for phrase in MISSING:
        assert phrase not in blob, phrase
    for q in qa["questions"]:
        assert q.get("what_to_change")
        assert (q.get("action") or {}).get("short_instruction")
        assert q.get("success_cues")


def test_report_contains_qa_guidance_version_constant():
    assert QA_GUIDANCE_VERSION == "precision-qa-coaching-ux-v9"
    assert REPORT_LOGIC_VERSION == "precision-report-v10"
    assert GOAL_VERSION == "precision-goal-v1.2"


def test_canonical_fixture_matches_sample():
    snap = get_canonical_snapshot(_song())
    assert str((snap.get("effort") or {}).get("level") or "").upper() == "LOW"
    assert str((snap.get("contact") or {}).get("status") or "").upper() == "FIRM"
    assert str((snap.get("breathiness") or {}).get("level") or "").upper() == "LOW"
    assert str((snap.get("register") or {}).get("status") or "").upper() == "PARTIAL"
    assert float((snap.get("timbre") or {}).get("presence")) >= 0.58
    assert not (snap.get("high_note") or {}).get("available")


from backend.app.main import app
from backend.app.api import routes as routes_mod
from backend.app.diagnostic.service import DiagnosticSessionService
from backend.app.services.analysis_service import AnalysisService
from backend.app.jobs.runner import JobRunner


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
    return TestClient(app), diag, runtime


def _seed_song_analysis(runtime: Path, user_id: str = "demo-user") -> str:
    """Write canonical VF without re-running the audio analyzer."""
    aid = uuid.uuid4().hex
    d = runtime / aid
    d.mkdir(parents=True, exist_ok=True)
    payload = _song()
    (d / "analysis.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (d / "analysis_meta.json").write_text(
        json.dumps({"user_id": user_id, "status": "completed"}, ensure_ascii=False),
        encoding="utf-8",
    )
    return aid


def _complete_session(c, headers, concerns, timbre="INTENSE_DISTINCT", *, runtime: Path | None = None):
    params = {}
    if runtime is not None:
        aid = _seed_song_analysis(runtime, headers.get("X-User-Id") or "demo-user")
        params["source_analysis_id"] = aid
    sid = c.post("/v1/diagnostic-sessions", headers=headers, params=params).json()["session_id"]
    assert c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=headers).status_code == 200
    body = {
        "diagnostic_mode": "CONCERN_FOCUSED",
        "user_concerns": [{"id": x} for x in concerns],
        "timbre_goal": {"id": timbre},
    }
    assert c.post(f"/v1/diagnostic-sessions/{sid}/concerns", headers=headers, json=body).status_code == 200
    assert (
        c.post(
            f"/v1/diagnostic-sessions/{sid}/safety",
            headers=headers,
            json={"answers": {"pain_on_phonation": False}},
        ).status_code
        == 200
    )
    skip = c.post(
        f"/v1/diagnostic-sessions/{sid}/skip-controlled-recordings",
        headers=headers,
        json={"remaining_only": True},
    )
    assert skip.status_code == 200, skip.text
    analyzed = c.post(f"/v1/diagnostic-sessions/{sid}/analyze", headers=headers)
    assert analyzed.status_code == 200, analyzed.text
    return sid


def test_report_contains_qa_guidance_version(client):
    c, _, runtime = client
    headers = {"X-User-Id": "demo-user"}
    sid = _complete_session(
        c,
        headers,
        ["VOICE_TOO_NASAL_PERCEPT", "VOICE_TOO_THIN", "TIMBRE_CHANGES_HIGH"],
        runtime=runtime,
    )
    rep = c.get(f"/v1/diagnostic-sessions/{sid}/report", headers=headers).json()
    assert rep.get("qa_guidance_version") == QA_GUIDANCE_VERSION
    assert rep.get("report_logic_version") == REPORT_LOGIC_VERSION
    assert rep.get("goal_version") == GOAL_VERSION
    proto = c.get("/v1/diagnostic/protocol").json()
    assert proto.get("qa_guidance_version") == QA_GUIDANCE_VERSION


def test_dev_regenerate_report_uses_current_qa_logic(client):
    c, _, runtime = client
    headers = {"X-User-Id": "demo-user"}
    sid = _complete_session(
        c, headers, ["VOICE_TOO_NASAL_PERCEPT", "TIMBRE_CHANGES_HIGH"], runtime=runtime
    )
    path = runtime / "diagnostic_sessions" / sid / "premium_report.json"
    old = json.loads(path.read_text(encoding="utf-8"))
    old["qa_guidance_version"] = "precision-qa-legacy"
    old["personalized_qa"] = {
        "questions": [
            {
                "concern_id": "TIMBRE_CHANGES_HIGH",
                "question": "왜 고음에서 음색이 갑자기 달라질까요?",
                "answer": "이번 노래만으로 음색 관련 원인을 하나로 좁히기는 어려워요.",
            }
        ]
    }
    path.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    stale = c.get(f"/v1/diagnostic-sessions/{sid}/report", headers=headers).json()
    assert stale.get("qa_guidance_version") == "precision-qa-legacy"
    assert "좁히기는 어려워요" in json.dumps(stale, ensure_ascii=False)
    regen = c.post(f"/v1/diagnostic-sessions/{sid}/regenerate-report", headers=headers)
    assert regen.status_code == 200, regen.text
    fresh = regen.json()
    assert fresh.get("qa_guidance_version") == QA_GUIDANCE_VERSION
    blob = json.dumps(fresh.get("personalized_qa") or {}, ensure_ascii=False)
    assert "하나로 좁히기는 어려워요" not in blob


def test_dev_regenerate_preserves_task_results(client):
    c, diag, runtime = client
    headers = {"X-User-Id": "demo-user"}
    sid = _complete_session(c, headers, ["VOICE_TOO_THIN"], runtime=runtime)
    before = diag._load(sid)
    assert before is not None
    marker = [{"task_id": "siren", "skipped": True, "note": "preserve-me"}]
    before["task_results"] = marker
    diag._save(before)
    assert c.post(f"/v1/diagnostic-sessions/{sid}/regenerate-report", headers=headers).status_code == 200
    after = diag._load(sid)
    assert after is not None
    assert after.get("task_results") == marker


def test_dev_regenerate_preserves_concerns(client):
    c, diag, runtime = client
    headers = {"X-User-Id": "demo-user"}
    ids = ["VOICE_TOO_NASAL_PERCEPT", "VOICE_TOO_THIN", "TIMBRE_CHANGES_HIGH"]
    sid = _complete_session(c, headers, ids, runtime=runtime)
    assert c.post(f"/v1/diagnostic-sessions/{sid}/regenerate-report", headers=headers).status_code == 200
    sess = diag._load(sid)
    assert [x.get("id") for x in (sess.get("user_concerns") or [])] == ids
    rep = c.get(f"/v1/diagnostic-sessions/{sid}/report", headers=headers).json()
    assert [q["concern_id"] for q in (rep.get("personalized_qa") or {}).get("questions") or []] == ids


def test_dev_regenerate_preserves_timbre_goal(client):
    c, diag, runtime = client
    headers = {"X-User-Id": "demo-user"}
    sid = _complete_session(
        c, headers, ["VOICE_TOO_THIN"], timbre="INTENSE_DISTINCT", runtime=runtime
    )
    assert c.post(f"/v1/diagnostic-sessions/{sid}/regenerate-report", headers=headers).status_code == 200
    sess = diag._load(sid)
    assert (sess.get("timbre_goal") or {}).get("id") == "INTENSE_DISTINCT"
    rep = c.get(f"/v1/diagnostic-sessions/{sid}/report", headers=headers).json()
    assert (rep.get("timbre_goal") or {}).get("id") == "INTENSE_DISTINCT"


def test_dev_regenerate_preserves_entitlement(client):
    c, diag, runtime = client
    headers = {"X-User-Id": "demo-user"}
    sid = _complete_session(c, headers, ["VOICE_TOO_THIN"], runtime=runtime)
    assert diag.entitlements.has_session_unlock("demo-user", sid)
    assert c.post(f"/v1/diagnostic-sessions/{sid}/regenerate-report", headers=headers).status_code == 200
    assert diag.entitlements.has_session_unlock("demo-user", sid)
    locked = c.get(f"/v1/diagnostic-sessions/{sid}/report", headers={"X-User-Id": "other-user"})
    assert locked.status_code in (402, 404)


def test_completed_report_is_not_auto_regenerated_in_production(client, monkeypatch):
    c, _, runtime = client
    headers = {"X-User-Id": "qa-runtime-user"}
    sid = _complete_session(c, headers, ["TIMBRE_CHANGES_HIGH"], runtime=runtime)
    path = runtime / "diagnostic_sessions" / sid / "premium_report.json"
    old = json.loads(path.read_text(encoding="utf-8"))
    old["qa_guidance_version"] = "precision-qa-legacy"
    old["personalized_qa"] = {
        "questions": [{"concern_id": "TIMBRE_CHANGES_HIGH", "answer": "이번 노래만으로 하나로 좁히기는 어려워요."}]
    }
    path.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("VAGENT_ENV", "production")
    got = c.get(f"/v1/diagnostic-sessions/{sid}/report", headers=headers).json()
    assert got.get("qa_guidance_version") == "precision-qa-legacy"
    analyzed = c.post(f"/v1/diagnostic-sessions/{sid}/analyze", headers=headers)
    assert analyzed.status_code == 200
    assert analyzed.json().get("qa_guidance_version") == "precision-qa-legacy"
    regen = c.post(f"/v1/diagnostic-sessions/{sid}/regenerate-report", headers=headers)
    assert regen.status_code == 403
    still = json.loads(path.read_text(encoding="utf-8"))
    assert still.get("qa_guidance_version") == "precision-qa-legacy"

    path = runtime / "diagnostic_sessions" / sid / "premium_report.json"
    old = json.loads(path.read_text(encoding="utf-8"))
    old["qa_guidance_version"] = "precision-qa-legacy"
    old["personalized_qa"] = {
        "questions": [{"concern_id": "TIMBRE_CHANGES_HIGH", "answer": "이번 노래만으로 하나로 좁히기는 어려워요."}]
    }
    path.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("VAGENT_ENV", "production")
    got = c.get(f"/v1/diagnostic-sessions/{sid}/report", headers=headers).json()
    assert got.get("qa_guidance_version") == "precision-qa-legacy"
    analyzed = c.post(f"/v1/diagnostic-sessions/{sid}/analyze", headers=headers)
    assert analyzed.status_code == 200
    assert analyzed.json().get("qa_guidance_version") == "precision-qa-legacy"
    regen = c.post(f"/v1/diagnostic-sessions/{sid}/regenerate-report", headers=headers)
    assert regen.status_code == 403
    still = json.loads(path.read_text(encoding="utf-8"))
    assert still.get("qa_guidance_version") == "precision-qa-legacy"
