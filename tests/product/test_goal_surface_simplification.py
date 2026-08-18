# -*- coding: utf-8 -*-
"""Goal surface simplification — Detail-owned goals; Home/Result/Progress goal-free UI."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINI = ROOT / "miniapp" / "src"


def _read(rel: str) -> str:
    return (MINI / rel).read_text(encoding="utf-8")


def test_home_does_not_render_current_goal():
    home = _read("pages/Home.tsx")
    assert "GoalProgressCard" not in home
    assert "home-goal-card" not in home
    assert "이번 목표" not in home
    assert "목표 정하기" not in home


def test_home_still_links_to_progress():
    home = _read("pages/Home.tsx")
    assert 'to="/progress"' in home
    assert "내 변화 보기" in home


def test_free_result_does_not_render_goal_card():
    result = _read("pages/Result.tsx")
    today = _read("components/progress/TodayPhonationSummary.tsx")
    assert "GoalProgressCard" not in result
    assert "GoalProgressCard" not in today
    assert "목표 정하기" not in result
    assert "목표 바꾸기" not in result


def test_free_result_still_passes_goal_internally_for_insight():
    result = _read("pages/Result.tsx")
    assert "getLocalActiveGoal" in result
    assert "postVocalProgressInsight" in result or "buildLocalProgressInsight" in result


def test_progress_has_no_goal_ui():
    page = _read("pages/ProgressInsight.tsx")
    assert "GoalProgressCard" not in page
    assert "아직 연습 목표가 없어요" not in page
    assert "목표 정하러 가기" not in page
    assert "현재 목표" not in page
    assert "이전 목표" not in page
    assert "progress-no-goal" not in page
    assert "좋아진 부분" in page
    assert "달라진 부분" in page


def test_progress_still_uses_hidden_goal_for_classification():
    page = _read("pages/ProgressInsight.tsx")
    assert "getLocalActiveGoal" in page
    assert "buildLocalProgressInsight" in page


def test_detail_is_diagnosis_only_without_goal_management():
    detail = _read("pages/SongDetailReport.tsx")
    assert "내 연습 목표" not in detail
    assert "GoalSelectorSheet" not in detail
    assert "목표 바꾸기" not in detail
    assert "SubPageHeader" not in detail
    assert "상세 리포트" in detail


def test_goal_hydration_distinguishes_loading_from_none():
    hyd = _read("lib/goalHydration.ts")
    assert "'loading'" in hyd
    assert "'none'" in hyd
    assert "'ready'" in hyd


def test_precision_production_ui_hides_training_goal_copy():
    prem = _read("pages/PremiumReport.tsx")
    # Training/prescription blocks may remain in source for debug; production path must not rely on them as primary.
    assert "정밀 발성 진단" in prem or "report_title" in prem
    assert 'section-title">이번 목표' not in prem


def test_progress_sheet_no_goal_mode():
    sheet = _read("components/progress/ProgressInsightSheet.tsx")
    assert "mode === 'goal'" not in sheet
    assert "목표 방향 결과" not in sheet


def test_goal_history_helpers_preserved():
    store = _read("lib/localGoalStore.ts")
    assert "listLocalGoalHistory" in store
    assert "setLocalActiveGoal" in store
    assert "REPLACED" in store
