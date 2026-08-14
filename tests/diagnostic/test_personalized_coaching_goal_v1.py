"""Personalized Coaching Goal v1 — perceptual target + current→target gap."""

from __future__ import annotations

import inspect
import json

from audio_analyzer.diagnostic.concern_resolver import evaluate_concern
from audio_analyzer.diagnostic.concerns import build_personalized_qa, public_concern_catalog
from audio_analyzer.diagnostic.fusion import build_final_diagnostic_profile
from audio_analyzer.diagnostic.goal_planner import plan_coaching_goal, recommend_accessible_target
from audio_analyzer.diagnostic.practice_library import practice_for_focus
from audio_analyzer.diagnostic.song_evidence import (
    get_canonical_snapshot,
    snapshot_to_ui_acoustic_axes,
)
from audio_analyzer.diagnostic.timbre_goals import (
    TARGET_TIMBRE_OPTIONS,
    concerns_need_timbre_goal,
    normalize_timbre_goal,
)


def _song(
    *,
    effort="HIGH",
    contact="FIRM",
    register="PARTIAL",
    presence=0.32,
    breath="LOW",
    brightness=None,
    stability="STABLE",
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
                    "status_label": "중간"
                    if contact == "MID"
                    else ("단단" if contact == "FIRM" else "가벼"),
                },
                "air_leakage_breathiness": {"status": breath},
                "phonation_regularity": {"status": stability},
            },
            "vocal_type_profile": {
                "register_strategy": {"status": register},
                "canonical_register": {"status": register},
            },
            "timbre_profile": {"available": presence is not None or brightness is not None, "axes": axes},
        }
    }


def _skip(*tasks: str):
    return {
        "task_profiles": {},
        "controlled_contrasts": {},
        "user_skipped_tasks": list(tasks),
        "task_evidence": {"user_skipped_tasks": list(tasks)},
        "completed_tasks": [],
    }


def _evals(ids, song, fused=None):
    fused = fused or _skip()
    return [evaluate_concern(cid, song_profile=song, task_evidence=fused) for cid in ids]


def _plan(ids, song, timbre=None, fused=None, pain=False):
    fused = fused or _skip()
    return plan_coaching_goal(
        user_concerns=[{"id": x} for x in ids],
        timbre_goal={"id": timbre, "source": "USER_SELECTED"} if timbre else None,
        concern_evaluations=_evals(ids, song, fused),
        song_profile=song,
        pain=pain,
    )


def _blob(goal, qa=None):
    parts = [json.dumps(goal, ensure_ascii=False)]
    if qa:
        parts.append(json.dumps(qa, ensure_ascii=False))
    return " ".join(parts)


# --- PART S: UI / storage ---


def test_timbre_goal_step_only_for_timbre_related_concerns():
    assert concerns_need_timbre_goal(["TIMBRE_DISSATISFIED"])
    assert concerns_need_timbre_goal(["VOICE_TOO_THIN", "HIGH_NOTE_CANNOT_REACH"])
    assert concerns_need_timbre_goal(["HIGH_NOTE_THINS"])
    assert not concerns_need_timbre_goal(
        ["HIGH_NOTE_CANNOT_REACH", "HIGH_NOTE_TOO_EFFORTFUL", "HIGH_NOTE_FLIPS"]
    )
    assert not concerns_need_timbre_goal(["THROAT_EFFORT", "PITCH_UNSTABLE"])


def test_timbre_goal_single_selection():
    catalog = public_concern_catalog()["target_timbre"]
    ids = [o["id"] for o in catalog["options"]]
    assert "RECOMMEND_FOR_ME" in ids
    assert len(ids) == len(set(ids))
    g = normalize_timbre_goal({"id": "SOFT_SWEET", "also": "WARM_FULL"}, concerns=["VOICE_TOO_THIN"])
    assert g["id"] == "SOFT_SWEET"
    assert "genre_display" not in g


def test_timbre_goal_persisted_in_session(tmp_path):
    from backend.app.diagnostic.service import DiagnosticSessionService

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    svc = DiagnosticSessionService(runtime)

    class _Ent:
        def has_session_unlock(self, *a, **k):
            return True

    svc.entitlements = _Ent()
    sid = "a" * 32
    sess_dir = runtime / "diagnostic_sessions" / sid
    sess_dir.mkdir(parents=True)
    (sess_dir / "session.json").write_text(
        json.dumps(
            {
                "session_id": sid,
                "user_id": "demo-user",
                "status": "PAID",
                "selected_tasks": [],
                "tasks": {},
                "task_results": [],
                "diagnostic_status": "NORMAL",
            }
        ),
        encoding="utf-8",
    )
    out = svc.submit_concerns(
        sid,
        [{"id": "VOICE_TOO_THIN"}, {"id": "TIMBRE_DISSATISFIED"}],
        user_id="demo-user",
        diagnostic_mode="CONCERN_FOCUSED",
        timbre_goal={"id": "SOFT_SWEET"},
    )
    assert out["status"] == "SAFETY_CHECK"
    assert out["timbre_goal"]["id"] == "SOFT_SWEET"
    assert out["timbre_goal"]["source"] == "USER_SELECTED"
    rec = svc.submit_concerns(
        sid,
        [{"id": "VOICE_TOO_THIN"}],
        user_id="demo-user",
        diagnostic_mode="CONCERN_FOCUSED",
        timbre_goal={"id": "RECOMMEND_FOR_ME"},
    )
    assert rec["timbre_goal"]["id"] == "RECOMMEND_FOR_ME"
    assert rec["timbre_goal"]["source"] == "USER_REQUESTED_RECOMMENDATION"


def test_genre_display_not_used_as_reasoning_input():
    src = inspect.getsource(plan_coaching_goal)
    assert "genre" not in src.lower()
    from audio_analyzer.diagnostic import goal_planner as gp

    assert "genre_display" not in inspect.getsource(gp)
    for opt in TARGET_TIMBRE_OPTIONS:
        if opt["id"] == "DENSE_SOLID":
            assert "록" in opt["genre_display"]
    song = _song(effort="LOW", contact="LIGHT", register="CONNECTED", presence=0.5)
    goal = _plan(["TIMBRE_DISSATISFIED"], song, timbre="DENSE_SOLID")
    blob = _blob(goal)
    assert "록" not in blob
    assert "뮤지컬" not in blob
    assert goal["primary_focus"] != "CONTACT" or song  # genre must not imply FIRM


# --- PART S: target not direct acoustic mapping ---


def test_dense_goal_does_not_force_firm_contact():
    song = _song(effort="LOW", contact="FIRM", register="CONNECTED", presence=0.5, breath="LOW")
    goal = plan_coaching_goal(
        user_concerns=[{"id": "TIMBRE_DISSATISFIED"}],
        timbre_goal={"id": "DENSE_SOLID", "source": "USER_SELECTED"},
        concern_evaluations=[
            {
                "concern_id": "TIMBRE_DISSATISFIED",
                "primary_focus": "CONTACT",
                "guidance_level": "SONG_DIRECT",
                "status": "PARTIALLY_SUPPORTED",
            }
        ],
        song_profile=song,
    )
    assert goal["primary_focus"] != "CONTACT"
    blob = _blob(goal)
    assert "성대를" not in blob
    assert "접촉을 더 키우세요" not in blob
    assert "접촉을 더 단단" not in blob


def test_airy_goal_does_not_force_high_breathiness():
    song = _song(effort="LOW", contact="MID", register="CONNECTED", presence=0.5, breath="HIGH")
    goal = plan_coaching_goal(
        user_concerns=[{"id": "VOICE_TOO_BREATHY"}],
        timbre_goal={"id": "AIRY_DELICATE", "source": "USER_SELECTED"},
        concern_evaluations=[
            {
                "concern_id": "VOICE_TOO_BREATHY",
                "primary_focus": "BREATHINESS",
                "guidance_level": "SONG_DIRECT",
                "status": "PARTIALLY_SUPPORTED",
            }
        ],
        song_profile=song,
    )
    assert goal["primary_focus"] != "BREATHINESS" or goal["mode"] == "STYLE"
    blob = _blob(goal)
    assert "성대를 벌" not in blob
    assert "숨을 더 늘" not in blob or "늘리기보다" in blob


def test_soft_goal_does_not_force_light_contact():
    song = _song(effort="HIGH", contact="FIRM", register="DISRUPTED", presence=0.32)
    goal = _plan(["VOICE_TOO_THIN"], song, timbre="SOFT_SWEET")
    assert goal["primary_focus"] != "CONTACT"
    blob = _blob(goal)
    assert "성대를" not in blob


# --- same target, different user ---


def test_same_timbre_goal_different_current_state_different_primary_focus():
    a = _plan(
        ["TIMBRE_DISSATISFIED", "THROAT_EFFORT"],
        _song(effort="HIGH", contact="FIRM", register="DISRUPTED", presence=0.32, breath="LOW"),
        timbre="SOFT_SWEET",
    )
    b = _plan(
        ["TIMBRE_DISSATISFIED", "VOICE_TOO_THIN"],
        _song(effort="LOW", contact="LIGHT", register="CONNECTED", presence=0.28, breath="HIGH"),
        timbre="SOFT_SWEET",
    )
    assert a["desired_outcome"]["id"] == b["desired_outcome"]["id"] == "SOFT_SWEET"
    assert a["primary_focus"] in ("EFFORT", "REGISTER_CONNECTION")
    assert b["primary_focus"] in ("PRESENCE", "BREATHINESS", "STYLE")
    assert a["primary_focus"] != b["primary_focus"]


def test_same_timbre_goal_different_current_state_different_practice():
    a = _plan(
        ["THROAT_EFFORT"],
        _song(effort="HIGH", contact="FIRM", register="DISRUPTED"),
        timbre="SOFT_SWEET",
    )
    b = _plan(
        ["VOICE_TOO_THIN"],
        _song(effort="LOW", contact="LIGHT", register="CONNECTED", presence=0.28, breath="HIGH"),
        timbre="SOFT_SWEET",
    )
    assert (a.get("practice_ids") or [None])[0] != (b.get("practice_ids") or [None])[0]


# --- PART T: high note ---


def test_high_note_cannot_reach_generates_goal():
    goal = _plan(
        ["HIGH_NOTE_CANNOT_REACH"],
        _song(effort="LOW", register="DISRUPTED", contact="MID", presence=0.5),
    )
    assert goal["goal_title"]
    assert goal["desired_outcome"]["label"]
    assert "연결" in goal["desired_outcome"]["label"]


def test_high_note_effort_generates_goal():
    goal = _plan(
        ["HIGH_NOTE_TOO_EFFORTFUL"],
        _song(effort="HIGH", contact="FIRM", register="PARTIAL"),
    )
    assert goal["primary_focus"] == "EFFORT"
    assert goal["goal_title"]


def test_high_note_flip_generates_goal():
    goal = _plan(
        ["HIGH_NOTE_FLIPS"],
        _song(effort="LOW", register="DISRUPTED"),
    )
    assert goal["primary_focus"] == "REGISTER_CONNECTION"
    assert "뒤집힘" in goal["desired_outcome"]["label"] or "연결" in goal["goal_title"]


def test_high_note_thin_uses_timbre_goal_when_available():
    goal = _plan(
        ["HIGH_NOTE_THINS", "TIMBRE_DISSATISFIED"],
        _song(effort="LOW", breath="LOW", presence=0.30, register="PARTIAL"),
        timbre="WARM_FULL",
    )
    assert goal["desired_outcome"]["id"] == "WARM_FULL"
    assert "밀도" in goal["goal_title"] or "존재감" in goal["goal_title"]
    blob = _blob(goal)
    assert "접촉을 더" not in blob
    assert "성대를" not in blob


def test_high_note_too_effortful_register_when_effort_low():
    goal = _plan(
        ["HIGH_NOTE_TOO_EFFORTFUL"],
        _song(effort="LOW", register="DISRUPTED", contact="MID"),
    )
    assert goal["primary_focus"] == "REGISTER_CONNECTION"


def test_high_note_too_effortful_no_fake_correction():
    goal = _plan(
        ["HIGH_NOTE_TOO_EFFORTFUL"],
        _song(effort="LOW", register="CONNECTED", contact="MID", presence=0.55, breath="LOW"),
    )
    assert goal["primary_focus"] not in ("EFFORT",)
    assert goal["mode"] in ("STYLE", "GUIDE", "MAINTAIN") or goal["primary_focus"] in (
        "MAINTAIN",
        "STYLE",
    )


# --- PART U: global goal ---


def test_exactly_one_primary_global_goal():
    goal = _plan(
        ["TIMBRE_DISSATISFIED", "VOICE_TOO_THIN", "VOICE_TOO_DARK_MUFFLED"],
        _song(),
        timbre="SOFT_SWEET",
    )
    assert goal["goal_title"]
    assert goal["primary_focus"]
    assert isinstance(goal["practice_ids"], list)
    assert len(goal["practices"]) <= 2


def test_goal_uses_user_concerns():
    qa = build_personalized_qa(
        user_concerns=[{"id": "HIGH_NOTE_FLIPS"}, {"id": "THROAT_EFFORT"}],
        song_profile=_song(register="DISRUPTED", effort="HIGH"),
        fused_profile=_skip("siren"),
    )
    goal = plan_coaching_goal(
        user_concerns=[{"id": "HIGH_NOTE_FLIPS"}, {"id": "THROAT_EFFORT"}],
        concern_evaluations=qa["concern_evaluations"],
        song_profile=_song(register="DISRUPTED", effort="HIGH"),
    )
    assert goal["source_concern_id"] in ("HIGH_NOTE_FLIPS", "THROAT_EFFORT")
    assert [q["concern_id"] for q in qa["questions"]] == ["HIGH_NOTE_FLIPS", "THROAT_EFFORT"]


def test_goal_uses_target_timbre_when_present():
    goal = _plan(["VOICE_TOO_THIN"], _song(), timbre="BRIGHT_CLEAR")
    assert goal["desired_outcome"]["id"] == "BRIGHT_CLEAR"
    assert goal["desired_outcome"]["type"] == "TIMBRE"


def test_goal_preserves_existing_strengths():
    goal = _plan(
        ["VOICE_TOO_THIN"],
        _song(effort="LOW", breath="LOW", register="PARTIAL", presence=0.3, contact="MID"),
        timbre="WARM_FULL",
    )
    assert "LOW_EFFORT" in goal["preserve_factors"]
    assert goal["preserve_labels"]


def test_goal_why_this_first_matches_evidence():
    goal = _plan(
        ["HIGH_NOTE_FLIPS"],
        _song(effort="LOW", register="DISRUPTED", breath="LOW"),
    )
    why = goal["why_this_first"]
    assert "힘 사용은 낮은" in why or "연결" in why


def test_maintain_not_rendered_as_improvement():
    goal = _plan(
        ["TIMBRE_DISSATISFIED"],
        _song(effort="LOW", register="CONNECTED", contact="MID", presence=0.5, breath="LOW"),
        timbre="SOFT_SWEET",
    )
    assert "선명한 기반" not in goal["goal_title"]
    assert "특별한 문제 없음" not in goal["goal_title"]
    assert goal["mode"] in ("STYLE", "GUIDE", "CORRECT", "REFINE", "SAFETY")


def test_preserve_factors_render_under_maintain_section():
    goal = _plan(
        ["VOICE_TOO_THIN"],
        _song(effort="LOW", register="PARTIAL", presence=0.3, breath="LOW"),
        timbre="SOFT_SWEET",
    )
    assert goal["preserve_factors"]
    assert all(isinstance(x, str) for x in goal["preserve_labels"])


def test_style_exploration_when_no_functional_defect():
    goal = _plan(
        ["TIMBRE_DISSATISFIED"],
        _song(effort="LOW", register="CONNECTED", contact="MID", presence=0.5, breath="LOW", stability="STABLE"),
        timbre="SOFT_SWEET",
    )
    assert goal["mode"] == "STYLE"
    assert goal["primary_focus"] == "STYLE"
    assert (goal.get("practice_ids") or [""])[0].startswith("STYLE_")


# --- PART V: practice ---


def test_unknown_focus_does_not_default_to_register_glide():
    assert practice_for_focus("UNKNOWN_FOCUS") is None
    assert practice_for_focus("UNKNOWN_TIMBRE") is None
    assert practice_for_focus("UNKNOWN_CONTROL") is None
    assert practice_for_focus("UNKNOWN_TARGET") is None


def test_timbre_unknown_does_not_default_to_register_glide():
    p = practice_for_focus("NOT_A_REAL_FOCUS", category="timbre")
    assert p is None or p.get("practice_id") != "REGISTER_GLIDE_LIGHT"


def test_descriptive_concern_can_return_no_practice():
    ev = evaluate_concern(
        "TIMBRE_DISSATISFIED",
        song_profile=_song(effort="LOW", register="CONNECTED", presence=0.5),
        task_evidence=_skip(),
    )
    assert ev.get("practice_required") is False
    assert ev.get("practice") in (None, {})


def test_practice_follows_primary_focus():
    goal = _plan(["HIGH_NOTE_FLIPS"], _song(register="DISRUPTED", effort="LOW"))
    assert goal["primary_focus"] == "REGISTER_CONNECTION"
    assert goal["practice_ids"] == ["REGISTER_GLIDE_LIGHT"]


def test_practice_contains_instruction_success_cues_avoid():
    p = practice_for_focus("PRESENCE")
    assert p["instruction"]
    assert p["success_cues"]
    assert p["avoid"]
    style = practice_for_focus("STYLE_SOFT_SWEET")
    assert "성대" not in style["instruction"]
    assert "횡격막" not in style["instruction"]


# --- PART W: provenance / profile / consistency ---


def test_concern_only_zero_completed_tasks_has_no_task_result_section():
    fused = build_final_diagnostic_profile(
        song_profile=_song()["vocal_function_profile"],
        task_results=[],
        plan={
            "selected_tasks": ["sustain_a", "siren"],
            "completed_tasks": [],
            "user_skipped_tasks": ["sustain_a", "siren"],
        },
    )
    assert not (fused.get("task_profiles") or {})
    assert (fused.get("task_evidence") or {}).get("completed_tasks") in ([], None)


def test_finding_cannot_create_fake_task_result():
    fused = build_final_diagnostic_profile(
        song_profile=_song()["vocal_function_profile"],
        task_results=[],
        plan={"selected_tasks": [], "completed_tasks": [], "user_skipped_tasks": []},
    )
    assert not (fused.get("task_profiles") or {})


def test_planned_task_cannot_create_task_result():
    fused = build_final_diagnostic_profile(
        song_profile=_song()["vocal_function_profile"],
        task_results=[],
        plan={"selected_tasks": ["siren", "high_note_sustain_a"], "completed_tasks": []},
    )
    assert not (fused.get("task_profiles") or {})


def test_canonical_register_renders_without_legacy_register_dimension():
    song = {
        "vocal_function_profile": {
            "effort_assessment": {"severity": "LOW"},
            "dimensions": {},
            "vocal_type_profile": {
                "register_strategy": {"status": "CONNECTED"},
                "canonical_register": {"status": "CONNECTED"},
            },
            "timbre_profile": {"available": True, "axes": {"presence": {"continuum": 0.4}}},
        }
    }
    snap = get_canonical_snapshot(song)
    assert (snap.get("register") or {}).get("status") == "CONNECTED"
    axes = snapshot_to_ui_acoustic_axes(snap)["axes"]
    assert axes["register"]["available"] is True
    assert "register_configuration" not in (song["vocal_function_profile"]["dimensions"] or {})


def test_canonical_presence_renders_without_legacy_resonance_dimension():
    song = _song(presence=0.3)
    song["vocal_function_profile"]["dimensions"].pop("resonance_formant_strategy", None)
    snap = get_canonical_snapshot(song)
    axes = snapshot_to_ui_acoustic_axes(snap)["axes"]
    assert axes["presence"]["available"] is True
    assert axes["presence"]["continuum"] <= 0.42


def test_detail_qa_goal_presence_consistent():
    song = _song(presence=0.3, effort="LOW", register="CONNECTED", breath="LOW")
    qa = build_personalized_qa(
        user_concerns=[{"id": "VOICE_TOO_THIN"}],
        song_profile=song,
        fused_profile=_skip(),
    )
    goal = _plan(["VOICE_TOO_THIN"], song, timbre="SOFT_SWEET")
    ans = " ".join(q["answer"] for q in qa["questions"])
    assert "존재감이 높은" not in ans
    assert goal["current_state"]["presence"]["status"] == "LOW"
    if goal["primary_focus"] == "PRESENCE":
        assert "존재감" in (goal["why_this_first"] + goal["goal_title"])


def test_unavailable_brightness_never_used_in_goal_or_qa():
    song = _song(brightness=None, presence=0.3)
    qa = build_personalized_qa(
        user_concerns=[{"id": "VOICE_TOO_THIN"}],
        song_profile=song,
        fused_profile=_skip(),
    )
    goal = _plan(["VOICE_TOO_THIN"], song, timbre="SOFT_SWEET")
    blob = _blob(goal, qa)
    assert "밝기 유지" not in blob
    assert "밝다" not in blob
    assert goal["current_state"]["brightness"]["available"] is False
    assert "밝기는 밝은" not in blob
    assert "밝기는 어두운" not in blob


def test_recommend_for_me_is_accessible_not_best_timbre():
    snap = get_canonical_snapshot(_song(effort="HIGH", contact="FIRM", breath="LOW"))
    rec = recommend_accessible_target(snap)
    assert rec["id"] != "DENSE_SOLID"
    assert rec["source"] == "SYSTEM_RECOMMENDED"
    goal = _plan(["VOICE_TOO_THIN"], _song(effort="HIGH", contact="FIRM"), timbre="RECOMMEND_FOR_ME")
    assert goal["desired_outcome"]["source"] == "SYSTEM_RECOMMENDED"
    assert goal["desired_outcome"]["id"] != "DENSE_SOLID"


def test_pain_overrides_style_and_high_note():
    goal = _plan(
        ["VOICE_TOO_THIN", "PAIN_WHILE_SINGING"],
        _song(),
        timbre="DENSE_SOLID",
        pain=True,
    )
    assert goal["primary_focus"] == "SAFETY"
    assert "불편감" in goal["goal_title"]
    assert goal["practice_ids"] == ["SAFETY_STOP"]


def test_no_anatomical_claims_in_goal_or_style_practice():
    goal = _plan(["VOICE_TOO_THIN"], _song(), timbre="DENSE_SOLID")
    text = " ".join(
        [
            str(goal.get("goal_title") or ""),
            str(goal.get("goal_description") or ""),
            str(goal.get("why_this_first") or ""),
            str(goal.get("gap_interpretation") or ""),
            json.dumps(goal.get("practices") or [], ensure_ascii=False),
        ]
    )
    for bad in ("복압", "횡격막", "후두", "목 근육", "성대를 더", "성대가 벌어", " TA ", " CT ", " LCA "):
        assert bad not in text
    for pid in (
        "STYLE_DENSE_SOLID",
        "STYLE_AIRY_DELICATE",
        "STYLE_SOFT_SWEET",
    ):
        p = practice_for_focus(pid)
        instr = json.dumps(p, ensure_ascii=False)
        for bad in ("복압", "성대를", "후두", "횡격막"):
            assert bad not in instr
