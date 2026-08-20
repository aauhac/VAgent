"""Ensure Home / History / Record / Upload match production UX contracts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "miniapp" / "src"


def test_home_logo_and_trust_removed():
    home = (ROOT / "pages" / "Home.tsx").read_text(encoding="utf-8")
    assert "BrandMark" not in home
    assert "VAgent" not in home
    assert "의료 진단이 아닙니다" not in home
    assert "home-product-compare" not in home
    assert "녹음 시작" in home
    assert "파일 선택" in home
    assert 'h1 className="home-hero-title"' in home or "home-hero-title" in home
    assert "노래 실력 진단받기" in home
    assert "내 목소리는 지금 어떻게 쓰이고 있을까?" in home
    assert "노래나 음성을 분석해 발성 타입과 특징을 보여드려요." in home
    assert "평소 부르듯 자연스럽게 불러보는 걸 추천해요." in home
    assert "목소리가 잘 들리는 구간을 올리는 걸 추천해요." in home
    assert "15~60초" not in home
    assert "30~60초" not in home
    assert "한 구절이면 충분" not in home
    assert "내 발성 타입과 주요 특징을 확인해보세요." in home
    assert "특징이 나타난 실제 구간과 상세 발성 프로필을 확인해보세요." in home
    assert "추가 녹음으로 다시 측정하고 목표 발성에 맞춘 피드백을 받아보세요." in home
    assert "무료 리포트" in home
    assert "상세 리포트" in home
    assert "보컬 진단" in home
    assert "서비스 정보" in home
    assert 'to="/service-info"' in home
    assert 'to="/legal/terms"' not in home
    assert 'to="/legal/privacy"' not in home
    assert home.find("home-input") < home.find("home-depth")


def test_service_info_page_has_business_and_legal_links():
    page = (ROOT / "pages" / "ServiceInfo.tsx").read_text(encoding="utf-8")
    app = (ROOT / "App.tsx").read_text(encoding="utf-8")
    assert 'path="/service-info"' in app
    assert "프랙토컬" in page
    assert "강민혁" in page
    assert "453-09-03373" in page
    assert "사업장 주소" in page
    assert "대학로3길 45" in page
    assert "010-9873-6677" in page
    assert "uhaki04@gmail.com" in page
    assert 'to="/legal/terms"' in page
    assert 'to="/legal/privacy"' in page
    assert "거주지" not in page
    assert "자택" not in page


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
