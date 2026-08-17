# -*- coding: utf-8 -*-
"""Precision report readability v2 — presentation-only source policy checks."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINI = ROOT / "miniapp" / "src"


def _read(rel: str) -> str:
    return (MINI / rel).read_text(encoding="utf-8")


def test_progress_subtitle_does_not_say_fake_score():
    page = _read("pages/ProgressInsight.tsx")
    assert "가짜 점수" not in page


def test_progress_subtitle_explains_record_comparison():
    page = _read("pages/ProgressInsight.tsx")
    assert "이전보다 뭐가 달라졌을까요" in page
    assert "비교" in page or "최근 기록" in page


def test_precision_distinct_feature_has_no_decorative_01():
    page = _read("pages/PremiumReport.tsx")
    assert "padStart(2" not in page
    assert "확인된 핵심 특징" in page
    assert "가장 뚜렷한 특징" not in page


def test_precision_distinct_feature_does_not_concat_tone():
    page = _read("pages/PremiumReport.tsx")
    assert "diag-tone" not in page
    assert "finding.tone" not in page


def test_supporting_section_uses_user_facing_title():
    page = _read("pages/PremiumReport.tsx")
    assert "참고로 확인된 변화" in page
    assert "추가로 관찰된 특징" not in page


def test_uncertain_section_title_is_confirm_not_decided_wording():
    page = _read("pages/PremiumReport.tsx")
    assert "이번에 확정하지 않은 부분" in page
    assert "추가 확인이 필요한 항목" not in page


def test_analysis_scope_does_not_say_song_analysis_used():
    page = _read("pages/PremiumReport.tsx")
    helper = _read("lib/precisionPresentation.ts")
    assert "노래 분석 사용함" not in page
    assert "이번 진단에 사용한 녹음" in helper
    assert "presentAnalysisScope" in page


def test_analysis_method_limit_accordion_removed():
    page = _read("pages/PremiumReport.tsx")
    more = _read("components/report/MoreDetails.tsx")
    assert "분석 방법과 한계" not in page
    assert "분석 방법과 한계" not in more
    assert "precision-disclaimer" in page


def test_precision_presentation_helpers_exist():
    helper = _read("lib/precisionPresentation.ts")
    assert "presentSupportingObservation" in helper
    assert "buildUncertainUserCopy" in helper
    assert "presentAnalysisScope" in helper
    assert "buildCompactReportDisclaimer" in helper
    assert "점수화하지" in helper


def test_supporting_backend_payload_unchanged_in_analyzer():
    """Scientific generation still emits research observations — UI filters only."""
    report = (ROOT / "audio_analyzer" / "physiology" / "report.py").read_text(encoding="utf-8")
    assert "점수화하지는 않았어요" in report
    assert "supporting_observations" in report


def test_safety_warning_still_prominent_in_premium():
    page = _read("pages/PremiumReport.tsx")
    assert "safetyNote" in page
    assert 'className="warn"' in page
