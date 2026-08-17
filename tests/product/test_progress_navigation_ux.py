# -*- coding: utf-8 -*-
"""Progress navigation UX — source policy (goal-free progress page)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINI = ROOT / "miniapp" / "src"


def _read(rel: str) -> str:
    return (MINI / rel).read_text(encoding="utf-8")


def test_progress_header_has_back_left_and_home_right():
    header = _read("components/ui/SubPageHeader.tsx")
    page = _read("pages/ProgressInsight.tsx")
    assert "이전 화면으로 돌아가기" in header
    assert "홈으로 이동" in header
    assert 'title="내 변화"' in page
    assert "SubPageHeader" in page


def test_progress_back_resolution_prefers_return_to():
    nav = _read("lib/progressNavigation.ts")
    assert "isSafeInternalReturnTo" in nav
    assert "resolveProgressBackTarget" in nav
    assert "javascript:" in nav


def test_progress_rejects_external_return_to():
    nav = _read("lib/progressNavigation.ts")
    assert "startsWith('//')" in nav or 'startsWith("//")' in nav


def test_progress_has_no_goal_management_ui():
    page = _read("pages/ProgressInsight.tsx")
    assert "GoalSelectorSheet" not in page
    assert "GoalProgressCard" not in page
    assert "목표 바꾸기" not in page
    assert "목표 정하러 가기" not in page
    assert "현재 목표" not in page


def test_detail_still_allows_goal_setting():
    detail = _read("pages/SongDetailReport.tsx")
    assert "GoalSelectorSheet" in detail
    assert "goal-setting" in detail
    assert "GoalEmptyCta" in detail or "목표 정하기" in detail


def test_detail_still_allows_goal_change():
    detail = _read("pages/SongDetailReport.tsx")
    assert "목표 바꾸기" in detail


def test_progress_shows_change_groups():
    page = _read("pages/ProgressInsight.tsx")
    assert "progress-generic-changes" in page
    assert "좋아진 부분" in page
    assert "달라진 부분" in page


def test_result_progress_link_sets_return_to():
    today = _read("components/progress/TodayPhonationSummary.tsx")
    assert "progressLinkState" in today or "returnTo" in today


def test_home_progress_link_sets_return_to_home():
    home = _read("pages/Home.tsx")
    assert "progressLinkState" in home or "returnTo" in home
    assert 'to="/progress"' in home


def test_free_result_still_has_no_goal_selector():
    result = _read("pages/Result.tsx")
    assert "GoalSelectorSheet" not in result


def test_detail_goal_history_preserved():
    detail = _read("pages/SongDetailReport.tsx")
    assert "putActiveVocalGoal" in detail
    assert "setLocalActiveGoal" in detail


def test_progress_insight_sheet_still_opens():
    page = _read("pages/ProgressInsight.tsx")
    assert "ProgressInsightSheet" in page
    assert "setSheetCard" in page


def test_sub_page_header_grid_css():
    css = (ROOT / "miniapp" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
    assert "sub-page-header" in css
    assert "1fr auto 1fr" in css
    assert "min-height: 44px" in css
