"""Ensure Home / History / Record / Upload match production UX contracts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "miniapp" / "src"


def test_home_logo_and_trust_removed():
    home = (ROOT / "pages" / "Home.tsx").read_text(encoding="utf-8")
    assert "BrandMark" not in home
    assert "VAgent" not in home
    assert "노래만으로 부족한" not in home
    assert "의료 진단이 아닙니다" not in home
    assert "home-product-compare" not in home
    assert "보컬 리포트" not in home
    assert "고음·음색 심층 분석" not in home
    assert "개인화 발성 피드백" not in home
    assert "Head/Chest" not in home
    assert "FREE" not in home
    assert "DETAIL" not in home
    assert "PREMIUM" not in home
    assert "PRECISION" not in home
    assert "녹음 시작" in home
    assert "파일 선택" in home
    assert "이용약관" in home
    assert "무료 리포트" in home
    assert "상세 리포트" in home
    assert "보컬 진단" in home
    assert home.find("home-input") < home.find("home-depth")


def test_subpages_have_content_titles_without_internal_header():
    for name, title in (("Record.tsx", "노래를 불러주세요"), ("Upload.tsx", "파일로 분석하기"), ("History.tsx", "분석 기록")):
        text = (ROOT / "pages" / name).read_text(encoding="utf-8")
        assert "SubPageHeader" not in text
        assert title in text
        assert "← 홈" not in text
        assert "‹ 홈" not in text


def test_history_hides_raw_session_ids():
    text = (ROOT / "pages" / "History.tsx").read_text(encoding="utf-8")
    assert "세션 " not in text
    assert "slice(0, 10)" not in text
    assert "연결된 정밀 진단" not in text
    assert "서버에 없는 기록" not in text
    assert "로컬 목록" not in text
    assert "아직 분석 기록이 없어요" in text
    assert "loadUnlockedSessions" not in text
    assert "정밀 진단 없음" not in text
    assert "history-actions" in text
    assert "history-delete" in text
    assert "이 분석을 삭제할까요?" in text
    assert "이전 정밀 진단" in text
    assert "이전 기록 더 보기" in text
    assert "무료 결과상세" not in text.replace(" ", "")
