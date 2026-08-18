# -*- coding: utf-8 -*-
"""Apps in Toss non-game release guide — static contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINI = ROOT / "miniapp" / "src"


def _read(rel: str) -> str:
    return (MINI / rel).read_text(encoding="utf-8")


def test_no_production_subpage_header():
    for path in (MINI / "pages").glob("*.tsx"):
        src = path.read_text(encoding="utf-8")
        assert "SubPageHeader" not in src, path.name
        assert "sub-page-header" not in src, path.name


def test_login_is_not_forced_on_free_analysis():
    main = _read("main.tsx")
    assert "loginWithTossApp" not in main
    assert "ReactDOM.createRoot" in main
    app = _read("App.tsx")
    assert "afterFirstPaint" in app
    assert "bootstrapTossSession" in app
    assert "loginWithTossApp" not in app
    assert "LOGIN_FAILED" not in app
    for rel in ("pages/Home.tsx", "pages/Record.tsx", "pages/Upload.tsx"):
        src = _read(rel)
        assert "loginWithTossApp" not in src, rel
        assert "ensureTossLogin" not in src, rel
    auth = _read("lib/tossAuth.ts")
    assert "APP_LOGIN_FUNCTION_UNAVAILABLE" in auth
    assert "APP_LOGIN_CANCELLED" in auth
    assert "APP_LOGIN_FAILED" in auth
    assert "AUTHORIZATION_CODE_MISSING" in auth
    assert "BACKEND_LOGIN_FAILED" in auth
    assert "[TOSS_LOGIN]" in auth
    assert "app_login_start" in auth
    assert "authorization_code_received" in auth
    assert "backend_exchange_start" in auth
    assert "backend_exchange_failed" in auth
    boot = auth[auth.find("export async function bootstrapTossSession") :]
    assert "loginWithTossApp" not in boot
    assert "ensureTossLogin" in auth
    iap = _read("lib/tossIap.ts")
    assert "ensureTossLogin" in iap
    errors = _read("lib/userFacingErrors.ts")
    assert "토스 로그인을 시작하지 못했어요" in errors
    assert "로그인 정보를 확인하지 못했어요" in errors


def test_disconnect_clears_client_caches_not_server_data():
    session = _read("lib/clientSession.ts")
    assert "vocalfb_" in session
    assert "vagent_" in session
    assert "clearUserIdentity" in session
    assert "SESSION_CLEARED_EVENT" in session
    assert "Does not delete server" in session or "Does not delete server analyses" in session
    client = _read("api/client.ts")
    assert "throwIfAuthLost" in client
    assert "handleUnauthorizedSession" in client
    assert "getAuthMe" in client
    disconnect = (ROOT / "backend" / "app" / "api" / "auth_routes.py").read_text(encoding="utf-8")
    assert "Session revoke only" in disconnect
    assert "Does not delete analyses" in disconnect


def test_iap_pauses_audio_and_payments_stay_disabled():
    iap = _read("lib/tossIap.ts")
    assert "pauseAllMediaPlayback" in iap
    assert iap.find("pauseAllMediaPlayback") < iap.find("createOneTimePurchaseOrder")
    media = _read("lib/mediaPlayback.ts")
    assert "media.pause()" in media
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "PAYMENTS_ENABLED=false" in env


def test_microphone_pre_consent_and_upload_validation():
    record = _read("pages/Record.tsx")
    task = _read("pages/DiagnosticTask.tsx")
    errors = _read("lib/userFacingErrors.ts")
    assert "MIC_PRE_CONSENT" in record
    assert "MIC_PRE_CONSENT" in task
    assert "노래를 분석하려면 마이크 사용 권한이 필요해요." in errors
    assert "microphoneErrorMessage" in record
    assert "/upload" in record
    upload = _read("pages/Upload.tsx")
    assert "validateUploadFile" in upload
    assert "UPLOAD_TOO_LARGE" in upload
    validation = _read("lib/uploadValidation.ts")
    assert "30 * 1024 * 1024" in validation
    assert ".m4a" in validation
    granite = (ROOT / "miniapp" / "granite.config.ts").read_text(encoding="utf-8")
    assert "microphone" in granite


def test_light_mode_and_pinch_zoom_viewport():
    html = (ROOT / "miniapp" / "index.html").read_text(encoding="utf-8")
    assert 'name="color-scheme" content="light"' in html
    assert "user-scalable=no" in html
    assert "maximum-scale=1.0" in html
    css = _read("styles/app.css")
    assert "color-scheme: light" in css


def test_home_explains_voice_analysis_without_product_tiers():
    home = _read("pages/Home.tsx")
    assert "노래나 음성을 분석해서" in home
    assert "보컬 리포트" not in home
    assert "home-product-compare" not in home
    assert "FREE" not in home
    assert "DETAIL" not in home
    assert "PRECISION" not in home
    assert "₩" not in home
    assert "이용약관" in home
    assert "무료 리포트" in home
    assert "상세 리포트" in home
    assert "보컬 진단" in home
    assert "15~60초 한 구절이면 충분해요." in home
    assert home.find("home-input") < home.find("home-depth") < home.find("home-links")


def test_no_eval_new_function_or_insecure_ws_in_src():
    banned = ("eval(", "new Function", "ws://", "window.location.replace")
    for path in MINI.rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        if "qa" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path}: {token}"


def test_qa_checklist_exists():
    qa = ROOT / "docs" / "apps_in_toss_release_qa.md"
    text = qa.read_text(encoding="utf-8")
    assert "Toss 뒤로가기" in text
    assert "PAYMENTS_ENABLED=false" in text
