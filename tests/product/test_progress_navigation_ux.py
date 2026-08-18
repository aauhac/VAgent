# -*- coding: utf-8 -*-
"""Progress navigation UX — source policy (goal-free progress page)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINI = ROOT / "miniapp" / "src"


def _read(rel: str) -> str:
    return (MINI / rel).read_text(encoding="utf-8")


def test_progress_page_has_content_title_without_internal_header():
    page = _read("pages/ProgressInsight.tsx")
    assert "SubPageHeader" not in page
    assert "내 변화 보기" in page


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


def test_detail_uses_shared_header_without_goal_ui():
    detail = _read("pages/SongDetailReport.tsx")
    assert "GoalSelectorSheet" not in detail
    assert "goal-setting" not in detail
    assert "내 연습 목표" not in detail
    assert "SubPageHeader" not in detail


def test_detail_has_no_goal_change_cta():
    detail = _read("pages/SongDetailReport.tsx")
    assert "목표 바꾸기" not in detail


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


def test_detail_goal_apis_not_required_on_detail_page():
    detail = _read("pages/SongDetailReport.tsx")
    assert "putActiveVocalGoal" not in detail
    assert "setLocalActiveGoal" not in detail
    assert "SubPageHeader" not in detail


def test_progress_insight_sheet_still_opens():
    page = _read("pages/ProgressInsight.tsx")
    assert "ProgressInsightSheet" in page
    assert "setSheetCard" in page


def test_sub_page_header_not_in_production_css():
    css = (ROOT / "miniapp" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
    assert "sub-page-header" not in css
