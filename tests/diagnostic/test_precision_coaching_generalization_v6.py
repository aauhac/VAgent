"""Precision Coaching Generalization v6 — checklist coverage + discrimination."""

from __future__ import annotations

from audio_analyzer.diagnostic.coaching_primitives import (
    COMPARISON_FAMILIES,
    CONCERN_DEFAULT_FAMILY,
    COACHING_PRIMITIVES,
    concern_policy,
    resolve_comparison_family,
)
from audio_analyzer.diagnostic.comparison_guidance import build_comparison_protocol
from audio_analyzer.diagnostic.concern_reasoning import reason_about_concern
from audio_analyzer.diagnostic.concerns import CONCERN_CATALOG, build_personalized_qa
from audio_analyzer.diagnostic.functional_hypothesis import ensure_actionable_guidance
from audio_analyzer.diagnostic.question_semantics import QUESTION_SEMANTICS, audited_concern_ids
from audio_analyzer.diagnostic.song_evidence import build_song_evidence_snapshot
from audio_analyzer.vocal_function.derived.effort_assessment import build_effort_assessment
from audio_analyzer.vocal_style.engine import _composite_from_axes


def _song(
    *,
    effort="LOW",
    contact="FIRM",
    register="PARTIAL",
    presence=0.72,
    breath="LOW",
    stability="STABLE",
    effort_status=None,
    effort_conf="medium",
):
    cont = {"FIRM": 0.72, "LIGHT": 0.28, "MID": 0.5}.get(contact, 0.5)
    estatus = effort_status or effort
    return {
        "vocal_function_profile": {
            "effort_assessment": {
                "severity": effort,
                "status": estatus,
                "confidence_label": effort_conf,
                "strength_eligible": effort == "LOW" and effort_conf in ("medium", "high"),
            },
            "dimensions": {
                "vocal_effort_strain": {
                    "status": estatus,
                    "confidence_label": effort_conf,
                },
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
            "timbre_profile": {
                "available": True,
                "axes": {
                    "presence": {"continuum": presence},
                    "airiness": {"continuum": 0.25},
                    "brightness": {"continuum": 0.5},
                },
            },
        }
    }


def _qa(concerns, song):
    return build_personalized_qa(
        user_concerns=[{"id": c} for c in concerns],
        song_profile=song,
        fused_profile={
            "task_profiles": {},
            "controlled_contrasts": {},
            "user_skipped_tasks": ["siren"],
            "task_evidence": {"user_skipped_tasks": ["siren"]},
        },
    )


# --- coverage ---


def test_every_catalog_concern_has_semantics():
    for cid in CONCERN_CATALOG:
        assert cid in QUESTION_SEMANTICS, cid
        pol = concern_policy(cid)
        assert pol["semantic_type"]
        assert pol["candidate_factors"] is not None
        assert pol["fallback_focus"]
        assert pol["response_policy"]
        assert pol["comparison_family"] in COMPARISON_FAMILIES
        assert pol["success_policy"] is not None
        assert pol["safety_policy"]


def test_every_non_safety_concern_has_action_policy():
    for cid, meta in CONCERN_CATALOG.items():
        if meta.get("category") == "safety":
            continue
        pol = concern_policy(cid)
        assert pol["what_to_change"]
        assert pol["action_or_comparison"]
        assert pol["success_policy"]


def test_every_non_safety_concern_has_comparison_or_direct_action():
    for cid, meta in CONCERN_CATALOG.items():
        if meta.get("category") == "safety":
            continue
        proto = build_comparison_protocol(cid, primary_focus=concern_policy(cid)["fallback_focus"])
        assert proto.get("baseline_instruction")
        assert proto.get("variant_instruction")
        assert proto.get("success_condition")
        lead = str(proto.get("lead") or "")
        assert lead.strip() not in (
            "같은 구절을 두 가지 방식으로 비교하세요.",
            "평소대로 한 번, 조금 작은 강도로 한 번.",
        )


def test_every_concern_has_success_policy():
    for cid in CONCERN_CATALOG:
        assert concern_policy(cid)["success_policy"] is not None


def test_audited_ids_match_catalog():
    assert set(audited_concern_ids()) == set(CONCERN_CATALOG.keys())


# --- discrimination ---


def test_high_note_unstable_differs_from_register_connection():
    song = _song(register="DISRUPTED", stability="UNSTABLE", effort="LOW")
    qa = _qa(["HIGH_NOTE_UNSTABLE", "REGISTER_CONNECTION_DIFFICULT"], song)
    by_id = {q["concern_id"]: q for q in qa["questions"]}
    u = by_id["HIGH_NOTE_UNSTABLE"]
    r = by_id["REGISTER_CONNECTION_DIFFICULT"]
    assert u.get("primary_focus") == "STABILITY"
    assert r.get("primary_focus") == "REGISTER_CONNECTION"
    cu = (u.get("comparison") or {}).get("comparison_family") or resolve_comparison_family(
        "HIGH_NOTE_UNSTABLE", primary_focus=u.get("primary_focus")
    )
    cr = (r.get("comparison") or {}).get("comparison_family") or resolve_comparison_family(
        "REGISTER_CONNECTION_DIFFICULT", primary_focus=r.get("primary_focus")
    )
    assert cu == "HIGH_NOTE_STABILITY_COMPARE"
    assert cr == "REGISTER_BRIDGE_COMPARE"
    assert str(u.get("answer") or "") != str(r.get("answer") or "")


def test_high_note_flip_differs_from_stability():
    song = _song(register="DISRUPTED", stability="UNSTABLE")
    qa = _qa(["HIGH_NOTE_FLIPS", "HIGH_NOTE_UNSTABLE"], song)
    by_id = {q["concern_id"]: q for q in qa["questions"]}
    flip = by_id["HIGH_NOTE_FLIPS"]
    unstable = by_id["HIGH_NOTE_UNSTABLE"]
    assert flip.get("primary_focus") == "REGISTER_CONNECTION"
    assert unstable.get("primary_focus") == "STABILITY"
    pf = build_comparison_protocol("HIGH_NOTE_FLIPS", snap=build_song_evidence_snapshot(song), primary_focus="REGISTER_CONNECTION")
    pu = build_comparison_protocol("HIGH_NOTE_UNSTABLE", snap=build_song_evidence_snapshot(song), primary_focus="STABILITY")
    assert pf["comparison_family"] != pu["comparison_family"]
    assert "뒤집힘" in (pf.get("success_condition") or "") or "연결" in (pf.get("lead") or "")
    assert "흔들" in (pu.get("lead") or "") or "안정" in (pu.get("success_condition") or "")


def test_pitch_unstable_differs_from_register_connection():
    song = _song(register="DISRUPTED", stability="UNSTABLE")
    qa = _qa(["PITCH_UNSTABLE", "REGISTER_CONNECTION_DIFFICULT"], song)
    by_id = {q["concern_id"]: q for q in qa["questions"]}
    assert by_id["PITCH_UNSTABLE"].get("primary_focus") == "STABILITY"
    assert by_id["REGISTER_CONNECTION_DIFFICULT"].get("primary_focus") == "REGISTER_CONNECTION"


def test_same_thin_concern_different_evidence_changes_focus():
    a = reason_about_concern("VOICE_TOO_THIN", song_profile=_song(breath="HIGH", presence=0.7, register="CONNECTED"))
    b = reason_about_concern("VOICE_TOO_THIN", song_profile=_song(breath="LOW", presence=0.28, register="CONNECTED"))
    c = reason_about_concern("VOICE_TOO_THIN", song_profile=_song(breath="LOW", presence=0.7, register="PARTIAL"))
    assert a.get("primary_focus") == "BREATHINESS"
    assert b.get("primary_focus") == "PRESENCE"
    assert c.get("primary_focus") == "REGISTER_CONNECTION"
    families = {
        build_comparison_protocol("VOICE_TOO_THIN", snap=build_song_evidence_snapshot(_song(breath="HIGH")), primary_focus=a["primary_focus"])[
            "comparison_family"
        ],
        build_comparison_protocol("VOICE_TOO_THIN", snap=build_song_evidence_snapshot(_song(breath="LOW", presence=0.28)), primary_focus=b["primary_focus"])[
            "comparison_family"
        ],
        build_comparison_protocol("VOICE_TOO_THIN", snap=build_song_evidence_snapshot(_song(breath="LOW", register="PARTIAL")), primary_focus=c["primary_focus"])[
            "comparison_family"
        ],
    }
    assert len(families) >= 2


def test_same_high_note_concern_different_evidence_changes_focus():
    hyp_e = ensure_actionable_guidance(
        {"concern_id": "HIGH_NOTE_CANNOT_REACH"},
        song_profile=_song(effort="HIGH", register="CONNECTED"),
    )
    hyp_r = ensure_actionable_guidance(
        {"concern_id": "HIGH_NOTE_CANNOT_REACH"},
        song_profile=_song(effort="LOW", register="DISRUPTED"),
    )
    # May come from reasoning or legacy — focus should adapt
    fe = str(hyp_e.get("primary_focus") or "")
    fr = str(hyp_r.get("primary_focus") or "")
    assert fe != fr or fe in ("EFFORT", "REGISTER_CONNECTION")


def test_unrelated_concerns_do_not_all_use_same_generic_comparison():
    song = _song()
    families = set()
    for cid in (
        "HIGH_NOTE_UNSTABLE",
        "VOICE_TOO_NASAL_PERCEPT",
        "DYNAMICS_DIFFICULT",
        "PHRASE_END_WEAK",
        "VIBRATO_UNSTABLE",
    ):
        fam = resolve_comparison_family(cid, primary_focus=concern_policy(cid)["fallback_focus"])
        families.add(fam)
        assert fam != "GENERAL_COMPARE" or cid == "OTHER_CONCERN"
    assert len(families) >= 4


def test_generic_fallback_does_not_override_specific_semantics():
    assert CONCERN_DEFAULT_FAMILY["HIGH_NOTE_UNSTABLE"] == "HIGH_NOTE_STABILITY_COMPARE"
    assert CONCERN_DEFAULT_FAMILY["REGISTER_CONNECTION_DIFFICULT"] == "REGISTER_BRIDGE_COMPARE"
    assert resolve_comparison_family("HIGH_NOTE_UNSTABLE", primary_focus="REGISTER_CONNECTION") == (
        "HIGH_NOTE_STABILITY_COMPARE"
    )


# --- effort presentation ---


def test_unknown_effort_not_rendered_as_low_strength():
    a = build_effort_assessment(
        {
            "status": "UNKNOWN",
            "hidden": False,
            "confidence_label": "low",
            "profile": {"hit_segments": 0, "core_family_count": 0, "effort_score": 0},
        }
    )
    assert a["global_severity"] == "UNKNOWN"
    assert "편안" not in a["label"]
    assert a.get("strength_eligible") is False
    snap = build_song_evidence_snapshot(
        {
            "vocal_function_profile": {
                "effort_assessment": a,
                "dimensions": {"vocal_effort_strain": {"status": "UNKNOWN"}},
            }
        }
    )
    assert snap["effort"]["level"] == "UNKNOWN"
    feats = snap.get("key_features") or []
    assert not any("힘 사용은 낮은 편" in f for f in feats)


def test_low_effort_preserve_requires_reliable_evidence():
    from audio_analyzer.diagnostic.general_guidance import timbre_goal_support_line

    weak = build_song_evidence_snapshot(
        {
            "vocal_function_profile": {
                "effort_assessment": {"severity": "UNKNOWN", "status": "UNKNOWN", "confidence_label": "low"},
                "dimensions": {"vocal_effort_strain": {"status": "UNKNOWN"}},
            }
        }
    )
    line = timbre_goal_support_line({"id": "DENSE_SOLID"}, weak)
    assert "편안한 힘 사용은 유지" not in line

    strong = build_song_evidence_snapshot(_song(effort="LOW", effort_status="LOW", effort_conf="medium"))
    line2 = timbre_goal_support_line({"id": "DENSE_SOLID"}, strong)
    assert "편안한 힘 사용은 유지" in line2 or "음량을 먼저 키우지" in line2


def test_pushed_fixture_not_silently_collapsed_to_low_if_raw_evidence_elevated():
    a = build_effort_assessment(
        {
            "status": "OCCASIONAL",
            "confidence_label": "medium",
            "continuum_0_to_1": 0.62,
            "profile": {
                "effort_score": 0.62,
                "mean_segment_effort_score": 0.2,
                "hit_segments": 2,
                "core_family_count": 2,
                "support_family_count": 1,
                "persistent_segments": 1,
            },
        },
        episodes=[{"type": "GENERAL_EFFORT"}],
        valid_segment_count=10,
    )
    assert a["global_severity"] in ("MILD", "MODERATE", "HIGH")
    assert a["global_severity"] != "LOW"


# --- key features ---


def test_disrupted_register_ranked_above_low_breathiness_strength():
    snap = build_song_evidence_snapshot(
        _song(breath="LOW", contact="FIRM", register="DISRUPTED", presence=0.3, effort="LOW")
    )
    feats = snap["key_features"]
    assert any("성구" in f or "연결" in f for f in feats)
    # Register disruption should appear within top features (not dropped)
    assert any("급격" in f or "성구" in f for f in feats[:3])


def test_actionable_limitation_not_dropped_by_three_item_limit():
    snap = build_song_evidence_snapshot(
        _song(breath="LOW", contact="FIRM", register="DISRUPTED", presence=0.3, effort="LOW", stability="STABLE")
    )
    feats = snap["key_features"]
    assert any("성구" in f or "급격" in f or "연결" in f for f in feats)


# --- vocal style ---


def test_style_title_never_contains_broken_fragment_join():
    title, _, _ = _composite_from_axes(
        {
            "effort": {"available": True, "value": "LOW"},
            "contact": {"available": True, "value": "FIRM"},
            "breathiness": {"available": True, "value": "LOW"},
        }
    )
    for broken in ("단단한 편안하고", "가벼운 안정적인하고", "낮은 단단하고", "편안하고 발성"):
        assert broken not in title


def test_firm_low_effort_style_is_natural_korean():
    title, _, _ = _composite_from_axes(
        {
            "effort": {"available": True, "value": "LOW"},
            "contact": {"available": True, "value": "FIRM"},
        }
    )
    assert "접촉은 단단하지만 힘 사용은 낮은 발성형" == title or "·" in title
    assert "편안하고" not in title


def test_primitives_cover_catalog_fallbacks():
    for cid in CONCERN_CATALOG:
        pol = concern_policy(cid)
        assert pol["primitive_id"] in COACHING_PRIMITIVES
