"""Public legal pages: unauthenticated 200, no secrets, no release blockers."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)

ROOT = Path(__file__).resolve().parents[2]
LEGAL_DIR = ROOT / "docs" / "legal"
MINI_LEGAL = ROOT / "miniapp" / "src" / "legal"

PUBLIC_FILES = (
    "TERMS_OF_SERVICE.ko.md",
    "PRIVACY_POLICY.ko.md",
    "PRIVACY_COLLECTION_CONSENT.ko.md",
)

BANNED_SECRETS = [
    "BEGIN PRIVATE",
    "BEGIN RSA",
    "VAGENT_SESSION_SECRET",
    "TOSS_MTLS",
    "DATABASE_URL=postgres",
    "accessToken",
    "refreshToken",
    "authorizationCode",
]

RELEASE_BLOCKERS = [
    "[TODO:",
    "TODO_BEFORE_PRODUCTION",
    "POLICY_DECISION_REQUIRED",
    "PRODUCTION_HOSTING_DECISION_REQUIRED",
    "LEGAL_REVIEW_REQUIRED",
    "draft-2",
    "<PRODUCTION_DOMAIN>",
    "{PUBLIC_BACKEND_BASE_URL}",
]

DRAFT_PHRASES = [
    "정식 시행된 약관이 아닙니다",
    "정식 공개 방침으로 시행하지 않습니다",
    "초안(draft-2)",
    "작성한 **초안**",
]


def _joined_docs() -> str:
    return "".join((LEGAL_DIR / n).read_text(encoding="utf-8") for n in PUBLIC_FILES)


def test_legal_routes_ok_without_auth():
    for path in ("/legal/terms", "/legal/privacy", "/legal/privacy-consent"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "text/html" in r.headers.get("content-type", "")
        assert "<h1" in r.text
        body = r.text
        for token in BANNED_SECRETS:
            assert token not in body, token
        for token in RELEASE_BLOCKERS:
            assert token not in body, f"{path} still has {token}"
        for phrase in DRAFT_PHRASES:
            assert phrase not in body, phrase


def test_legal_markdown_has_no_secrets_or_env_names():
    text = _joined_docs()
    for token in BANNED_SECRETS:
        assert token not in text, token
    for name in ("IAP_SONG_DETAIL_SKU", "VAGENT_SESSION_SECRET", "TOSS_MTLS_KEY_PATH"):
        assert name not in text, name


def test_no_release_placeholders_in_public_legal_docs():
    text = _joined_docs()
    for token in RELEASE_BLOCKERS:
        assert token not in text, token
    for phrase in DRAFT_PHRASES:
        assert phrase not in text, phrase
    assert "2026년 8월 20일" in text
    assert "노래 실력 진단받기" in text


def test_terms_article1_has_no_todo_company_placeholder():
    html = client.get("/legal/terms").text
    article1 = html.split("제1조", 1)[-1].split("제2조", 1)[0]
    assert 'href="' not in article1
    assert "[TODO:" not in article1
    assert "사업자명" not in article1 or "등록" in html


def test_frontend_legal_copy_matches_docs():
    for name in PUBLIC_FILES:
        a = (LEGAL_DIR / name).read_text(encoding="utf-8")
        b = (MINI_LEGAL / name).read_text(encoding="utf-8")
        assert a == b, name
    app_src = (ROOT / "miniapp/src/App.tsx").read_text(encoding="utf-8")
    assert 'path="/legal/terms"' in app_src
    assert 'path="/legal/privacy"' in app_src
    assert 'path="/legal/privacy-consent"' in app_src
    home = (ROOT / "miniapp/src/pages/Home.tsx").read_text(encoding="utf-8")
    assert "/legal/terms" in home
    assert "/legal/privacy" in home
    assert "의료 진단이 아닙니다" not in home
    assert "노래 실력 진단받기" in home
    terms = (LEGAL_DIR / "TERMS_OF_SERVICE.ko.md").read_text(encoding="utf-8")
    assert terms.startswith("# 노래 실력 진단받기")
    assert "회원탈퇴" not in terms or "토스 계정" in terms


def _privacy_text() -> str:
    return (LEGAL_DIR / "PRIVACY_POLICY.ko.md").read_text(encoding="utf-8")


def test_privacy_does_not_claim_no_ad_feature_while_rewarded_ads_exist():
    """Rewarded ads are implemented; privacy must not read as 'no ads at all'."""
    rewarded_impl = (ROOT / "miniapp/src/lib/tossRewardedAd.ts").exists()
    assert rewarded_impl
    privacy = _privacy_text()
    outdated = "광고·분석(Analytics) SDK는 사용하지 않습니다."
    assert outdated not in privacy
    assert "리워드 광고" in privacy
    assert "Apps in Toss" in privacy or "앱인토스" in privacy


def test_privacy_discloses_rewarded_ad_processing_in_user_friendly_language():
    privacy = _privacy_text()
    assert "리워드 광고" in privacy
    assert "일일 이용" in privacy or "일일 이용 횟수" in privacy
    assert "상세 리포트" in privacy
    # Distinguishes platform ads from separate analytics/tracking tools
    assert "Google Analytics" in privacy or "행태 분석" in privacy


def test_privacy_hides_internal_rewarded_ad_implementation_names():
    privacy = _privacy_text()
    for banned in (
        "claim_token_hash",
        "principal_key",
        "rewarded_ad_daily_slots",
        "rewarded_ad_claims",
        "slot_index",
        "seoul_day",
    ):
        assert banned not in privacy, banned
