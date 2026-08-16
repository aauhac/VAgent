# -*- coding: utf-8 -*-
"""Progress Insight UX — count-based how-much, no fake %, brightness ≠ improvement."""

from __future__ import annotations

from backend.app.services.progress_insight import build_progress_insight


def _snap(axis: str, label: str, ver: str = "v1") -> dict:
    return {"canonical_json": {axis: label}, "analyzer_version": ver}


def test_no_baseline_soft_empty():
    out = build_progress_insight(
        current_canonical={"register_connection": "CONNECTED"},
        historical_snapshots=[],
    )
    assert out["insight_available"] is False
    assert out["status"] == "NO_BASELINE"
    assert out["improved"] == []


def test_register_goal_aligned_goes_to_improved():
    hist = [
        _snap("register_connection", "PARTIAL"),
        _snap("register_connection", "DISRUPTED"),
        _snap("register_connection", "PARTIAL"),
        _snap("register_connection", "PARTIAL"),
        _snap("register_connection", "DISRUPTED"),
    ]
    out = build_progress_insight(
        current_canonical={"register_connection": "CONNECTED"},
        historical_snapshots=hist,
        goal="REGISTER_CONNECTION",
    )
    assert out["insight_available"] is True
    assert len(out["improved"]) >= 1
    card = out["improved"][0]
    assert card["axis"] == "register_connection"
    assert card["kind"] == "IMPROVED"
    assert card["how_much"]["type"] == "COUNT_IN_WINDOW"
    assert "%" not in (card.get("detail") or "")
    assert "%" not in (card["how_much"].get("summary") or "")


def test_brightness_never_in_improved():
    hist = [_snap("brightness", "LOW"), _snap("brightness", "LOW"), _snap("brightness", "MID")]
    out = build_progress_insight(
        current_canonical={"brightness": "HIGH"},
        historical_snapshots=hist,
        goal="REGISTER_CONNECTION",
    )
    assert all(c["axis"] != "brightness" for c in out["improved"])
    bright = next((c for c in out["changed"] if c["axis"] == "brightness"), None)
    assert bright is not None
    assert bright["kind"] == "CHANGED"
    assert bright["why_improvement"] is None


def test_effort_change_not_improved():
    hist = [_snap("effort", "HIGH"), _snap("effort", "HIGH"), _snap("effort", "MODERATE")]
    out = build_progress_insight(
        current_canonical={"effort": "LOW"},
        historical_snapshots=hist,
    )
    assert all(c["axis"] != "effort" for c in out["improved"])


def test_maintained_when_matches_modal():
    hist = [
        _snap("effort", "MODERATE"),
        _snap("effort", "MODERATE"),
        _snap("effort", "MODERATE"),
    ]
    out = build_progress_insight(
        current_canonical={"effort": "MODERATE"},
        historical_snapshots=hist,
    )
    assert any(c["axis"] == "effort" and c["kind"] == "MAINTAINED" for c in out["maintained"])


def test_improved_capped_at_two():
    # Only register can improve with goal; ensure cap logic doesn't explode
    hist = [_snap("register_connection", "PARTIAL") for _ in range(5)]
    out = build_progress_insight(
        current_canonical={"register_connection": "CONNECTED", "brightness": "HIGH"},
        historical_snapshots=hist,
        goal="REGISTER_CONNECTION",
    )
    assert len(out["improved"]) <= 2


def test_count_based_how_much_not_percent():
    hist = [
        _snap("register_connection", "CONNECTED"),
        _snap("register_connection", "PARTIAL"),
        _snap("register_connection", "PARTIAL"),
        _snap("register_connection", "DISRUPTED"),
        _snap("register_connection", "PARTIAL"),
    ]
    out = build_progress_insight(
        current_canonical={"register_connection": "CONNECTED"},
        historical_snapshots=hist,
        goal="REGISTER_CONNECTION",
    )
    card = out["improved"][0]
    hm = card["how_much"]
    assert hm["recent_count"] == 1  # one CONNECTED in recent 5
    assert "회" in hm["summary"]
