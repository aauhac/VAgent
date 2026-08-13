"""v2.4 optional recording — UI copy / enum leak contracts (filesystem)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINI = ROOT / "miniapp" / "src"


def test_skip_all_copy_present():
    text = (MINI / "pages" / "DiagnosticRecordingIntro.tsx").read_text(encoding="utf-8")
    assert "추가 녹음 없이 결과 보기" in text
    assert "확인 범위" in text and "분석 신뢰도" in text
    assert "정밀분석 포기" not in text
    assert "간이 분석" not in text


def test_skip_confirmation_copy_present():
    text = (MINI / "pages" / "DiagnosticRecordingIntro.tsx").read_text(encoding="utf-8")
    assert "추가 녹음 없이 계속할까요?" in text
    assert "추가 녹음 없이 계속" in text
    assert "성능이 크게 저하" not in text
    assert "정확도가 낮습니다" not in text


def test_per_task_skip_present():
    text = (MINI / "pages" / "DiagnosticTask.tsx").read_text(encoding="utf-8")
    assert "이 과제 건너뛰기" in text
    assert "남은 과제 없이 결과 보기" in text or "남은 과제를 건너뛰고" in text


def test_concern_only_title_in_report():
    text = (MINI / "pages" / "PremiumReport.tsx").read_text(encoding="utf-8")
    assert "고민 중심 분석" in text
    assert "CONCERN_ONLY" in text  # mode key for branching OK
    # Must not render enum as visible Korean-free token alone without translation path
    assert "고민 중심 분석" in text


def test_partial_precision_notice():
    text = (MINI / "pages" / "PremiumReport.tsx").read_text(encoding="utf-8")
    assert "일부 추가 과제를 건너뛰어" in text


def test_internal_skip_enum_not_as_user_copy():
    """USER_SKIPPED / USER_CHOICE must not appear as user-visible string literals in flow pages."""
    for rel in (
        "pages/DiagnosticRecordingIntro.tsx",
        "pages/DiagnosticTask.tsx",
    ):
        text = (MINI / rel).read_text(encoding="utf-8")
        assert "USER_SKIPPED" not in text
        assert "USER_CHOICE" not in text
        assert "FULL_PRECISION" not in text
        assert "PARTIAL_PRECISION" not in text
        assert "CONCERN_ONLY" not in text

    report = (MINI / "pages" / "PremiumReport.tsx").read_text(encoding="utf-8")
    assert "USER_SKIPPED" not in report
    assert "USER_CHOICE" not in report
    # Mode keys used for branching must map to Korean titles/copy
    assert "고민 중심 분석" in report
