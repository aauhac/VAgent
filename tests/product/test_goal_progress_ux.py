# -*- coding: utf-8 -*-
"""Goal-aware progress UX — count evidence, no fake %, goal lifecycle."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.goal_catalog import list_user_goal_catalog, normalize_goal_payload
from backend.app.services.goal_progress import (
    brightness_without_style_goal_is_improvement,
    build_goal_progress,
    contact_is_generic_improvement,
    evaluate_goal_evidence,
    identity_similarity_used_in_goal_progress,
    lower_effort_always_goal_aligned,
    source_balance_is_generic_improvement,
)
from backend.app.services.goal_store import UserGoalFileStore
from backend.app.services.progress_insight import build_progress_insight


def _snap(reg: str, *, ver: str = "v1", created: str = "2026-08-01T00:00:00+00:00", **extra):
    return {
        "canonical_json": {"register_connection": reg, **{k: v for k, v in extra.items() if k != "qid"}},
        "analyzer_version": ver,
        "created_at": created,
        "analysis_quality": "pass",
        **{k: v for k, v in extra.items() if k in ("goal_id_at_analysis", "goal_focus_at_analysis", "analysis_id")},
    }


def test_no_goal_hides_goal_progress():
    out = build_goal_progress(goal=None, historical_snapshots=[_snap("CONNECTED")])
    assert out["status"] == "NO_GOAL"


def test_register_goal_counts_connected_as_goal_aligned():
    goal = normalize_goal_payload("REGISTER_CONNECTION")
    hist = [
        _snap("PARTIAL"),
        _snap("DISRUPTED"),
        _snap("PARTIAL"),
        _snap("CONNECTED"),
        _snap("PARTIAL"),
    ]
    out = build_goal_progress(
        goal=goal,
        historical_snapshots=hist,
        current_canonical={"register_connection": "CONNECTED"},
    )
    assert out["window"]["goal_aligned_count"] == 1
    assert out["uses_fake_percent"] is False


def test_register_goal_does_not_assign_fake_numeric_score():
    ev = evaluate_goal_evidence(
        {"focus": "REGISTER_CONNECTION"},
        {"register_connection": "CONNECTED"},
    )
    assert "score" not in ev
    assert "percent" not in ev
    assert ev.get("uses_fake_percent") is not True


def test_unknown_register_excluded_from_evaluable_count():
    goal = normalize_goal_payload("REGISTER_CONNECTION")
    hist = [
        _snap("CONNECTED"),
        _snap("UNRESOLVED"),
        _snap("PARTIAL"),
        _snap("UNKNOWN"),
        _snap("CONNECTED"),
    ]
    # Force unresolved into canonical
    hist[1]["canonical_json"]["register_connection"] = "UNRESOLVED"
    hist[3]["canonical_json"]["register_connection"] = "UNKNOWN"
    out = build_goal_progress(goal=goal, historical_snapshots=hist)
    assert out["window"]["evaluable_count"] == 3
    assert out["window"]["goal_aligned_count"] == 2
    assert "INSUFFICIENT_EVIDENCE" in out["sequence"]


def test_brightness_without_explicit_style_goal_not_improvement():
    assert brightness_without_style_goal_is_improvement("LOW", "HIGH") is False
    ev = evaluate_goal_evidence({"focus": "BRIGHTNESS"}, {"brightness": "HIGH"})
    assert ev["direction"] == "NEUTRAL"


def test_source_balance_not_generic_improvement():
    assert source_balance_is_generic_improvement("A", "B") is False


def test_contact_not_generic_improvement():
    assert contact_is_generic_improvement("LIGHT", "FIRM") is False
    ev = evaluate_goal_evidence({"focus": "CONTACT"}, {"contact": "FIRM"})
    assert ev["direction"] == "NEUTRAL"


def test_brightness_target_can_be_goal_aligned_without_being_generic_quality_improvement():
    goal = {
        "focus": "BRIGHTNESS",
        "kind": "STYLE",
        "target": "HIGHER",
        "wording": "STYLE_DIRECTION",
        "label": "더 밝고 선명한 음색",
    }
    ev = evaluate_goal_evidence(goal, {"brightness": "HIGH"})
    assert ev["direction"] == "GOAL_ALIGNED"
    assert ev["called_generic_improvement"] is False
    out = build_goal_progress(
        goal=goal,
        historical_snapshots=[
            {"canonical_json": {"brightness": "LOW"}, "analyzer_version": "v1", "created_at": "2026-08-01T00:00:00+00:00"},
            {"canonical_json": {"brightness": "LOW"}, "analyzer_version": "v1", "created_at": "2026-08-02T00:00:00+00:00"},
            {"canonical_json": {"brightness": "MID"}, "analyzer_version": "v1", "created_at": "2026-08-03T00:00:00+00:00"},
            {"canonical_json": {"brightness": "HIGH"}, "analyzer_version": "v1", "created_at": "2026-08-04T00:00:00+00:00"},
        ],
    )
    assert "음색" in (out.get("summary") or "") or out["window"]["goal_aligned_count"] >= 1
    assert "발성이 좋아" not in (out.get("summary") or "")


def test_lower_effort_not_always_goal_aligned():
    assert lower_effort_always_goal_aligned() is False
    ev = evaluate_goal_evidence({"focus": "EFFORT", "kind": "OTHER", "target": None}, {"effort": "LOW"})
    # Without EFFORT_REDUCE kind / LOWER target → neutral
    assert ev["direction"] in ("NEUTRAL", "INSUFFICIENT_EVIDENCE", "GOAL_ALIGNED")
    # Explicit: without reduce intent from normalize, EFFORT defaults to EFFORT_REDUCE in catalog
    # Test raw focus without kind
    raw = evaluate_goal_evidence({"focus": "EFFORT", "kind": "OTHER", "axis": "effort"}, {"effort": "LOW"})
    assert raw["direction"] == "NEUTRAL"


def test_reduce_excessive_effort_goal_can_interpret_reliable_change():
    goal = {"focus": "EFFORT", "kind": "EFFORT_REDUCE", "target": "LOWER", "axis": "effort"}
    assert evaluate_goal_evidence(goal, {"effort": "LOW"})["direction"] == "GOAL_ALIGNED"
    assert evaluate_goal_evidence(goal, {"effort": "HIGH"})["direction"] == "NOT_GOAL_ALIGNED"


def test_recent_window_count_correct():
    goal = normalize_goal_payload("REGISTER_CONNECTION")
    hist = [_snap("CONNECTED" if i % 2 == 0 else "PARTIAL", created=f"2026-08-0{i+1}T00:00:00+00:00") for i in range(5)]
    out = build_goal_progress(goal=goal, historical_snapshots=hist, recent_n=5)
    assert out["window"]["size"] == 5
    assert out["window"]["goal_aligned_count"] == 3


def test_previous_window_count_correct():
    goal = normalize_goal_payload("REGISTER_CONNECTION")
    hist = []
    for i, lab in enumerate(["PARTIAL", "PARTIAL", "PARTIAL", "PARTIAL", "CONNECTED", "PARTIAL", "CONNECTED", "PARTIAL", "CONNECTED", "CONNECTED"]):
        hist.append(_snap(lab, created=f"2026-08-{i+1:02d}T00:00:00+00:00"))
    out = build_goal_progress(goal=goal, historical_snapshots=hist, recent_n=5)
    assert out["previous_window"] is not None
    assert out["previous_window"]["goal_aligned_count"] == 1
    assert out["window"]["goal_aligned_count"] == 3
    assert out["status"] == "IMPROVING"


def test_current_recording_not_double_counted():
    goal = normalize_goal_payload("REGISTER_CONNECTION")
    hist = [_snap("PARTIAL") for _ in range(5)]
    out = build_goal_progress(
        goal=goal,
        historical_snapshots=hist,
        current_canonical={"register_connection": "CONNECTED"},
        include_current_in_recent=False,
    )
    assert out["window"]["goal_aligned_count"] == 0
    assert out["current_evidence"]["direction"] == "GOAL_ALIGNED"


def test_new_goal_does_not_mix_previous_goal_progress(tmp_path: Path):
    store = UserGoalFileStore(tmp_path)
    g1 = store.set_goal("u", focus="REGISTER_CONNECTION", label="성구")
    snaps = [
        {**_snap("CONNECTED", created="2026-08-01T00:00:00+00:00"), "goal_id_at_analysis": g1["id"]},
        {**_snap("CONNECTED", created="2026-08-02T00:00:00+00:00"), "goal_id_at_analysis": g1["id"]},
    ]
    g2 = store.set_goal("u", focus="EFFORT", label="힘", target="LOWER")
    snaps.append(
        {
            "canonical_json": {"effort": "LOW"},
            "analyzer_version": "v1",
            "created_at": "2026-08-21T00:00:00+00:00",
            "goal_id_at_analysis": g2["id"],
            "analysis_quality": "pass",
        }
    )
    out = build_goal_progress(goal=g2, historical_snapshots=snaps, recent_n=5)
    # Only effort snap under new goal
    assert out["window"]["recording_count"] == 1
    assert out["window"]["goal_aligned_count"] == 1


def test_previous_goal_history_preserved(tmp_path: Path):
    store = UserGoalFileStore(tmp_path)
    store.set_goal("u", focus="REGISTER_CONNECTION")
    store.set_goal("u", focus="EFFORT")
    hist = store.list_goals("u")
    assert len(hist) == 2
    assert hist[0]["status"] == "REPLACED"
    assert hist[1]["status"] == "ACTIVE"
    assert store.get_active("u")["goal_focus"] == "EFFORT"


def test_incompatible_history_excluded_or_flagged():
    goal = normalize_goal_payload("REGISTER_CONNECTION")
    hist = [
        _snap("PARTIAL", ver="v8"),
        _snap("PARTIAL", ver="v8"),
        _snap("CONNECTED", ver="v10"),
        _snap("CONNECTED", ver="v10"),
        _snap("CONNECTED", ver="v10"),
    ]
    out = build_goal_progress(goal=goal, historical_snapshots=hist)
    assert out.get("mixed_analyzer_versions") is True


def test_sequence_supports_aligned_not_aligned_insufficient():
    goal = normalize_goal_payload("REGISTER_CONNECTION")
    hist = [
        _snap("CONNECTED"),
        _snap("PARTIAL"),
        {"canonical_json": {"register_connection": "UNRESOLVED"}, "analyzer_version": "v1", "created_at": "2026-08-03T00:00:00+00:00"},
    ]
    out = build_goal_progress(goal=goal, historical_snapshots=hist)
    assert set(out["sequence"]) <= {
        "GOAL_ALIGNED",
        "NOT_GOAL_ALIGNED",
        "NEUTRAL",
        "INSUFFICIENT_EVIDENCE",
    }


def test_identity_similarity_not_used_in_goal_progress():
    assert identity_similarity_used_in_goal_progress() is False
    out = build_goal_progress(
        goal=normalize_goal_payload("REGISTER_CONNECTION"),
        historical_snapshots=[_snap("CONNECTED")],
    )
    assert out["uses_identity_similarity"] is False


def test_existing_progress_insight_without_goal_still_works():
    out = build_progress_insight(
        current_canonical={"effort": "LOW", "brightness": "HIGH"},
        historical_snapshots=[
            {"canonical_json": {"effort": "MODERATE", "brightness": "LOW"}, "analyzer_version": "v1"},
        ],
        goal=None,
    )
    assert out["insight_available"] is True
    assert (out.get("goal_progress") or {}).get("status") in (None, "NO_GOAL") or out["goal_progress"]["status"] == "NO_GOAL"


def test_catalog_reuses_coaching_focus():
    opts = list_user_goal_catalog()
    focuses = {o["focus"] for o in opts}
    assert "REGISTER_CONNECTION" in focuses
    assert "SAFETY" not in focuses


def test_result_goal_card_uses_count_not_percent():
    goal = normalize_goal_payload("REGISTER_CONNECTION")
    out = build_goal_progress(
        goal=goal,
        historical_snapshots=[_snap("CONNECTED"), _snap("PARTIAL"), _snap("CONNECTED")],
    )
    blob = str(out)
    assert "%" not in (out.get("summary") or "")
    assert "72" not in (out.get("summary") or "")
    assert out["window"]["goal_aligned_count"] >= 1
    assert "percent" not in blob.lower() or out["uses_fake_percent"] is False


def test_maintaining_not_hundred_percent_complete():
    goal = normalize_goal_payload("REGISTER_CONNECTION")
    hist = [_snap("CONNECTED") for _ in range(5)]
    out = build_goal_progress(goal=goal, historical_snapshots=hist)
    assert out["status"] in ("MAINTAINING", "STARTING", "STABLE")
    assert "100" not in (out.get("summary") or "")
    assert "완료" not in (out.get("summary") or "")
