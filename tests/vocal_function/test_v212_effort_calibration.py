"""v2.12 — absolute effort calibration + report consistency."""

from __future__ import annotations

from audio_analyzer.vocal_function.derived.effort_assessment import (
    SEVERITY_LABELS_KO,
    build_effort_assessment,
    check_effort_report_consistency,
    finding_copy_for_effort,
)


def _effort_dim(
    *,
    status="OCCASIONAL",
    peak=0.55,
    mean=0.08,
    hits=1,
    core=2,
    support=1,
    persistent=1,
    conf="medium",
    prevalence="rare",
):
    return {
        "dimension_id": "vocal_effort_strain",
        "status": status,
        "confidence_label": conf,
        "prevalence": prevalence,
        "continuum_0_to_1": peak,
        "profile": {
            "effort_score": peak,
            "mean_segment_effort_score": mean,
            "hit_segments": hits,
            "core_family_count": core,
            "support_family_count": support,
            "persistent_segments": persistent,
            "recovery_cost": persistent,
        },
    }


def test_general_excess_effort_not_displayed_as_neutral():
    a = build_effort_assessment(
        _effort_dim(),
        episodes=[{"type": "GENERAL_EFFORT", "episode_id": "e1"}],
        valid_segment_count=10,
    )
    assert a["global_severity"] in ("MILD", "MODERATE", "HIGH")
    assert a["label"] != "보통"
    assert "편안" not in a["label"] or a["global_severity"] != "LOW"
    copy = finding_copy_for_effort(a, "GENERAL_EXCESS_EFFORT")
    assert "보통" not in copy["title"]


def test_repeated_effort_maps_to_non_neutral_severity():
    a = build_effort_assessment(
        _effort_dim(status="REPEATED", hits=5, peak=0.7, core=2, persistent=2, prevalence="repeated"),
        episodes=[{"type": "GENERAL_EFFORT"} for _ in range(3)],
        valid_segment_count=10,
    )
    assert a["global_severity"] in ("MODERATE", "HIGH")
    assert a["label"] == SEVERITY_LABELS_KO[a["global_severity"]]


def test_firm_easy_remains_low_effort():
    a = build_effort_assessment(
        _effort_dim(status="LOW", peak=0.08, mean=0.08, hits=0, core=0, support=0, persistent=0),
        episodes=[],
        valid_segment_count=10,
    )
    assert a["global_severity"] == "LOW"
    assert a["label"] == "편안한 편"


def test_loud_only_does_not_raise_effort_severity():
    # Detector status LOW with static loud profile fields — assessment stays LOW
    dim = _effort_dim(status="LOW", peak=0.1, hits=0, core=0, support=0, persistent=0)
    dim["profile"]["static_loud_segments"] = 8
    dim["profile"]["loudness_level"] = "LOUD"
    a = build_effort_assessment(dim, valid_segment_count=10)
    assert a["global_severity"] == "LOW"


def test_roughness_only_does_not_raise_effort():
    a = build_effort_assessment(
        _effort_dim(status="LOW", hits=0, core=0, peak=0.05),
        episodes=[{"type": "ROUGHNESS", "episode_id": "r1"}],
        valid_segment_count=10,
    )
    assert a["global_severity"] == "LOW"


def test_breathiness_only_does_not_raise_effort():
    a = build_effort_assessment(
        _effort_dim(status="LOW", hits=0, core=0, peak=0.02),
        episodes=[{"type": "AIR_LEAKAGE", "episode_id": "a1"}],
        valid_segment_count=10,
    )
    assert a["global_severity"] == "LOW"


def test_global_low_highnote_high_is_allowed():
    a = build_effort_assessment(
        _effort_dim(status="LOW", hits=0, core=0, peak=0.05),
        high_note_profile={
            "available": True,
            "axes": {
                "high_note_effort_cost": {"status": "INCREASED", "continuum": 0.7},
            },
        },
        valid_segment_count=10,
    )
    assert a["global_severity"] == "LOW"
    assert a["high_note_severity"] == "HIGH"
    assert a["context_note"]
    assert "고음" in a["context_note"]


def test_repeated_global_effort_low_profile_is_inconsistent():
    a = {
        "global_severity": "LOW",
        "severity": "LOW",
        "label": "보통",
        "localized_episode_count": 2,
        "high_note_severity": None,
    }
    issues = check_effort_report_consistency(
        assessment=a,
        coaching_decision={
            "primary_bottleneck": {
                "id": "GENERAL_EXCESS_EFFORT",
                "confidence": "medium",
                "supporting_episode_ids": ["e1", "e2"],
            }
        },
    )
    assert any(i["id"] == "general_excess_effort_vs_neutral_profile" for i in issues)


def test_effort_profile_and_main_finding_share_assessment():
    dim = _effort_dim()
    a = build_effort_assessment(
        dim,
        episodes=[{"type": "GENERAL_EFFORT", "episode_id": "e1"}],
        valid_segment_count=10,
    )
    dim["effort_assessment"] = a
    copy = finding_copy_for_effort(a, "GENERAL_EXCESS_EFFORT")
    # Same assessment drives both label and finding direction
    assert a["label"] == SEVERITY_LABELS_KO[a["global_severity"]]
    if a["global_severity"] in ("MODERATE", "HIGH"):
        assert "힘" in copy["title"]
        assert "보통" not in copy["title"]


def test_support_only_cannot_create_moderate_or_high():
    a = build_effort_assessment(
        _effort_dim(status="MODERATE", hits=3, core=0, support=2, peak=0.7, persistent=2),
        valid_segment_count=10,
    )
    assert a["global_severity"] in ("LOW", "MILD")


def test_confidence_100_percent_not_rendered_in_production_sources():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "miniapp" / "src"
    pat = re.compile(r"신뢰도\s*\$\{[^}]*\}%|신뢰도\s*100%")
    offenders = []
    for p in list(root.rglob("*.ts")) + list(root.rglob("*.tsx")):
        text = p.read_text(encoding="utf-8")
        if pat.search(text):
            offenders.append(str(p.relative_to(root)))
    assert offenders == [], f"production confidence % still present: {offenders}"


def test_effort_보통_label_removed_from_effort_axis_mapping():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "miniapp"
        / "src"
        / "lib"
        / "reportPresentation.ts"
    ).read_text(encoding="utf-8")
    # Effort branch must not map OCCASIONAL → 보통
    assert "kind === 'effort'" in text
    assert "힘이 들어가는 편" in text
    assert "formatAnalysisConfidence" in text
    # Isolate effort block
    idx = text.find("if (kind === 'effort')")
    block = text[idx : idx + 500]
    assert "return '보통'" not in block


def test_pressed_copy_not_anatomical():
    from audio_analyzer.vocal_quality import config as vq_cfg

    assert "압착" not in vq_cfg.DIMENSION_DISPLAY["pressed_like"]
    assert "단단" in vq_cfg.DIMENSION_DISPLAY["pressed_like"]


def test_mokjabi_like_packet_is_at_least_moderate():
    """Matches audited 목잡이 packet: OCCASIONAL + peak~0.55 + core2 + persistent."""
    a = build_effort_assessment(
        _effort_dim(status="OCCASIONAL", peak=0.552, hits=1, core=2, support=1, persistent=1),
        episodes=[{"type": "GENERAL_EFFORT", "start_sec": 4.5, "end_sec": 7.5}],
        valid_segment_count=10,
    )
    assert a["global_severity"] in ("MODERATE", "HIGH")
    assert a["label"] == "힘이 들어가는 편" or a["global_severity"] == "HIGH"
