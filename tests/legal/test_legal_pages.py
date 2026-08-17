"""Public legal pages: unauthenticated 200, no secrets, placeholders visible."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)

ROOT = Path(__file__).resolve().parents[2]
LEGAL_DIR = ROOT / "docs" / "legal"

BANNED = [
    "BEGIN PRIVATE",
    "BEGIN RSA",
    "VAGENT_SESSION_SECRET",
    "TOSS_MTLS",
    "DATABASE_URL=postgres",
    "accessToken",
    "refreshToken",
    "authorizationCode",
]


def test_legal_routes_ok_without_auth():
    for path in ("/legal/terms", "/legal/privacy", "/legal/privacy-consent"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "text/html" in r.headers.get("content-type", "")
        assert "<h1" in r.text
        body = r.text
        for token in BANNED:
            assert token not in body, token


def test_legal_markdown_has_no_secrets_or_env_names():
    files = (
        "TERMS_OF_SERVICE.ko.md",
        "PRIVACY_POLICY.ko.md",
        "PRIVACY_COLLECTION_CONSENT.ko.md",
    )
    text = "".join((LEGAL_DIR / n).read_text(encoding="utf-8") for n in files)
    for token in BANNED:
        assert token not in text, token
    for name in ("IAP_SONG_DETAIL_SKU", "VAGENT_SESSION_SECRET", "TOSS_MTLS_KEY_PATH"):
        assert name not in text, name


def test_placeholders_present_so_release_is_not_claimed():
    joined = "".join(
        (LEGAL_DIR / n).read_text(encoding="utf-8")
        for n in (
            "TERMS_OF_SERVICE.ko.md",
            "PRIVACY_POLICY.ko.md",
            "PRIVACY_COLLECTION_CONSENT.ko.md",
        )
    )
    assert "[TODO: 사업자명]" in joined
    assert "[TODO: 시행일]" in joined
    assert "[TODO: 이메일]" in joined


def test_todo_company_placeholder_is_not_a_markdown_link():
    html = client.get("/legal/terms").text
    article1 = html.split("제1조", 1)[-1].split("제2조", 1)[0]
    assert 'href="' not in article1
    assert "[TODO: 사업자명]" in article1


def test_frontend_legal_copy_matches_docs():
    src = ROOT / "miniapp/src/legal"
    for name in (
        "TERMS_OF_SERVICE.ko.md",
        "PRIVACY_POLICY.ko.md",
        "PRIVACY_COLLECTION_CONSENT.ko.md",
    ):
        a = (LEGAL_DIR / name).read_text(encoding="utf-8")
        b = (src / name).read_text(encoding="utf-8")
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

