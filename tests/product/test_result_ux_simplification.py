# -*- coding: utf-8 -*-
"""Result UX simplification — Korean copy, history counts, no raw enums."""

from __future__ import annotations

from backend.app.services.progress_insight import (
    _change_copy,
    _how_much_summary,
    build_progress_insight,
)


def test_how_much_one_history_does_not_say_recent_five():
    s = _how_much_summary(1, 1, 5)
    assert "최근 5회" not in s
    assert "이전" in s


def test_how_much_three_history_says_recent_three():
    s = _how_much_summary(3, 2, 5)
    assert "최근 3회" in s
    assert "최근 5회" not in s


def test_how_much_five_plus_uses_recent_five():
    s = _how_much_summary(5, 3, 5)
    assert "최근 5회" in s


def test_changed_copy_contains_no_i_ga_placeholder():
    for axis in ("effort", "contact", "brightness", "source_balance", "register_connection"):
        text = _change_copy(axis, "HIGH", "LOW")
        assert "이(가)" not in text


def test_effort_changed_copy_is_natural_korean():
    text = _change_copy("effort", "MODERATE", "LOW")
    assert "힘을 덜 쓰는" in text
    assert "effort" not in text.lower()


def test_contact_changed_copy_is_natural_korean():
    text = _change_copy("contact", "FIRM", "MID")
    assert "접촉감" in text
    assert "이(가)" not in text
    assert "FIRM" not in text


def test_source_balance_has_korean_user_label():
    out = build_progress_insight(
        current_canonical={"source_balance": "CHEST_LEANING"},
        historical_snapshots=[
            {"canonical_json": {"source_balance": "BALANCED"}, "analyzer_version": "v1"},
        ],
    )
    card = (out.get("changed") or [None])[0]
    assert card is not None
    assert "소스 밸런스" not in card["detail"]
    assert "흉성" in card["detail"] or "음향 성향" in card["detail"]
    assert "이(가)" not in card["detail"]


def test_one_history_how_much_in_insight():
    out = build_progress_insight(
        current_canonical={"register_connection": "CONNECTED"},
        historical_snapshots=[
            {"canonical_json": {"register_connection": "PARTIAL"}, "analyzer_version": "v1"},
        ],
        goal="REGISTER_CONNECTION",
    )
    cards = out["improved"] + out["changed"] + out["maintained"]
    for c in cards:
        hm = c.get("how_much") or {}
        assert "최근 5회" not in (hm.get("summary") or "")
        assert hm.get("actual_count") == 1 or hm.get("window") == 1


def test_existing_progress_insight_without_goal_still_works():
    out = build_progress_insight(
        current_canonical={"effort": "LOW"},
        historical_snapshots=[
            {"canonical_json": {"effort": "HIGH"}, "analyzer_version": "v1"},
        ],
    )
    assert out["insight_available"] is True
    assert "이(가)" not in str(out.get("changed"))
