"""Adaptive Precision Diagnostic planner + fusion (protocol v1.1)."""

from __future__ import annotations

from audio_analyzer.diagnostic.fusion import (
    build_final_diagnostic_profile,
    fuse_song_and_task_evidence,
)
from audio_analyzer.diagnostic.planner import (
    build_uncertainty_profile,
    select_diagnostic_tasks,
)
from audio_analyzer.diagnostic.task_registry import (
    normalize_recommended_task,
)


def _row(dim, *, suf="INSUFFICIENT", conf="low", finding="UNDETERMINED", req_s=0, req_t=2):
    return {
        "dimension_id": dim,
        "measurement_sufficiency": suf,
        "confidence_label": conf,
        "finding": finding,
        "required_satisfied": req_s,
        "required_total": req_t,
        "criteria": [],
        "coaching_eligibility": "NEEDS_MEASUREMENT" if suf == "INSUFFICIENT" else "ELIGIBLE",
    }


def test_contact_only_one_sustain():
    matrix = [
        _row("glottal_contact_profile"),
        _row("air_leakage_breathiness", suf="SUFFICIENT", conf="high", finding="NOT_PROMINENT", req_s=2),
        _row("vocal_effort_strain", suf="SUFFICIENT", conf="high", finding="NOT_PROMINENT", req_s=2),
        _row("register_configuration", suf="SUFFICIENT", conf="high", finding="NOT_PROMINENT", req_s=2),
        _row("phonation_regularity", suf="SUFFICIENT", conf="high", finding="NOT_PROMINENT", req_s=2),
    ]
    profile = build_uncertainty_profile(criteria_matrix=matrix)
    plan = select_diagnostic_tasks(profile)
    assert plan["unresolved_dimensions"] == ["contact"]
    assert plan["selected_tasks"] == ["sustain_a"]
    assert "siren" not in plan["selected_tasks"]
    assert "dynamic_swell" not in plan["selected_tasks"]


def test_register_only_siren():
    matrix = [
        _row("register_configuration"),
        _row("glottal_contact_profile", suf="SUFFICIENT", conf="high", finding="NOT_PROMINENT", req_s=2),
    ]
    plan = select_diagnostic_tasks(build_uncertainty_profile(criteria_matrix=matrix))
    assert plan["selected_tasks"] == ["siren"]


def test_effort_only_dynamic_swell():
    matrix = [
        _row("vocal_effort_strain"),
        _row("glottal_contact_profile", suf="SUFFICIENT", conf="high", finding="NOT_PROMINENT", req_s=2),
    ]
    plan = select_diagnostic_tasks(build_uncertainty_profile(criteria_matrix=matrix))
    assert plan["selected_tasks"] == ["dynamic_swell"]


def test_contact_breathiness_stability_one_sustain():
    matrix = [
        _row("glottal_contact_profile"),
        _row("air_leakage_breathiness"),
        _row("phonation_regularity"),
    ]
    plan = select_diagnostic_tasks(build_uncertainty_profile(criteria_matrix=matrix))
    assert "sustain_a" in plan["selected_tasks"]
    assert len(plan["selected_tasks"]) == 1


def test_contact_register_effort_minimal_set():
    matrix = [
        _row("glottal_contact_profile"),
        _row("register_configuration"),
        _row("vocal_effort_strain"),
        _row("air_leakage_breathiness"),
        _row("phonation_regularity"),
    ]
    plan = select_diagnostic_tasks(build_uncertainty_profile(criteria_matrix=matrix))
    assert set(plan["selected_tasks"]) == {"sustain_a", "siren", "dynamic_swell"}


def test_all_resolved_zero_tasks():
    matrix = [
        _row(d, suf="SUFFICIENT", conf="high", finding="NOT_PROMINENT", req_s=2)
        for d in (
            "glottal_contact_profile",
            "air_leakage_breathiness",
            "vocal_effort_strain",
            "register_configuration",
            "phonation_regularity",
            "resonance_formant_strategy",
            "onset_offset_coordination",
            "respiratory_phonatory_coordination",
        )
    ]
    plan = select_diagnostic_tasks(build_uncertainty_profile(criteria_matrix=matrix))
    assert plan["selected_tasks"] == []
    assert plan["unresolved_dimensions"] == []


def test_unsupported_recommended_task_not_rendered():
    n = normalize_recommended_task("five_tone")
    assert n["supported"] is True
    assert n["task_id"] == "siren"
    n2 = normalize_recommended_task("re_record_with_headphones")
    assert n2["supported"] is False


def test_planner_deterministic():
    matrix = [
        _row("glottal_contact_profile"),
        _row("register_configuration"),
        _row("vocal_effort_strain"),
    ]
    a = select_diagnostic_tasks(build_uncertainty_profile(criteria_matrix=matrix))
    b = select_diagnostic_tasks(build_uncertainty_profile(criteria_matrix=matrix))
    assert a["selected_tasks"] == b["selected_tasks"]


def test_fusion_confirms_increases_confidence():
    song = {
        "dimensions": {
            "glottal_contact_profile": {
                "status": "light",
                "summary": "light",
                "confidence_label": "low",
            }
        }
    }
    tasks = [
        {
            "task_id": "sustain_a",
            "mechanisms": [
                {
                    "mechanism_id": "phonation_contact_pattern",
                    "status": "firm-mid",
                    "summary": "firm",
                    "confidence_label": "high",
                }
            ],
        }
    ]
    fused = fuse_song_and_task_evidence(
        song_profile=song,
        task_results=tasks,
        unresolved_before=["contact"],
        selected_tasks=["sustain_a"],
    )
    assert "contact" in fused["resolved_dimensions"]
    assert fused["resolved_dimensions"]["contact"]["final_confidence"] > 0.5
    assert fused["fusion_rules"]["blind_average"] is False


def test_fusion_contextual_difference():
    song = {
        "dimensions": {
            "glottal_contact_profile": {
                "status": "light",
                "summary": "light",
                "confidence_label": "medium",
            }
        }
    }
    tasks = [
        {
            "task_id": "sustain_a",
            "mechanisms": [
                {
                    "mechanism_id": "phonation_contact_pattern",
                    "status": "firm",
                    "summary": "firm",
                    "confidence_label": "high",
                }
            ],
        }
    ]
    fused = fuse_song_and_task_evidence(
        song_profile=song,
        task_results=tasks,
        unresolved_before=["contact"],
        selected_tasks=["sustain_a"],
    )
    # May resolve with contextual note when statuses differ
    assert fused["song_profile"]["contact"]["status"] == "light"
    assert fused["baseline_profile"]["contact"]["status"] == "firm"


def test_invalid_task_no_confidence_boost():
    song = {
        "dimensions": {
            "glottal_contact_profile": {
                "status": "light",
                "confidence_label": "low",
            }
        }
    }
    tasks = [
        {
            "task_id": "sustain_a",
            "quality": {"status": "fail"},
            "invalid": True,
            "mechanisms": [
                {
                    "mechanism_id": "phonation_contact_pattern",
                    "status": "firm",
                    "confidence_label": "high",
                }
            ],
        }
    ]
    fused = fuse_song_and_task_evidence(
        song_profile=song,
        task_results=tasks,
        unresolved_before=["contact"],
        selected_tasks=["sustain_a"],
    )
    assert "contact" in fused["remaining_uncertainties"]
    assert fused["resolved_dimensions"].get("contact") is None or not fused[
        "resolved_dimensions"
    ].get("contact", {}).get("resolved")


def test_final_profile_no_blind_average():
    profile = build_final_diagnostic_profile(
        song_profile={
            "dimensions": {
                "glottal_contact_profile": {
                    "status": "0.3",
                    "confidence_label": "low",
                }
            }
        },
        task_results=[
            {
                "task_id": "sustain_a",
                "mechanisms": [
                    {
                        "mechanism_id": "phonation_contact_pattern",
                        "status": "0.7",
                        "confidence_label": "high",
                    }
                ],
            }
        ],
        plan={"unresolved_dimensions": ["contact"], "selected_tasks": ["sustain_a"]},
    )
    assert profile["fusion_rules"]["blind_average"] is False
    # Must not invent 0.5 average status
    final = profile["resolved_dimensions"]["contact"]["final_status"]
    assert final in ("0.7", "0.3")
