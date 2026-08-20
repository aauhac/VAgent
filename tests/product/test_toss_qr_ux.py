# -*- coding: utf-8 -*-
"""Toss QR UX: identity, preview, Home cleanup, no internal headers."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINI = ROOT / "miniapp" / "src"


def _read(rel: str) -> str:
    return (MINI / rel).read_text(encoding="utf-8")


def test_home_has_no_vocal_report_tier_section():
    home = _read("pages/Home.tsx")
    assert "home-product-compare" not in home
    assert "보컬 리포트" not in home
    assert "home-hero" in home
    assert "home-input" in home
    assert "home-depth" in home
    assert "home-service-info" in home
    assert "home-legal" not in home
    assert "녹음 시작" in home
    assert home.find("home-input") < home.find("home-depth") < home.find("home-links")


def test_production_pages_do_not_render_subpage_header():
    pages = [
        "pages/Home.tsx",
        "pages/Record.tsx",
        "pages/Upload.tsx",
        "pages/History.tsx",
        "pages/ProgressInsight.tsx",
        "pages/Result.tsx",
        "pages/SongDetailReport.tsx",
        "pages/PremiumUnlock.tsx",
        "pages/ConcernIntake.tsx",
        "pages/SafetyCheck.tsx",
        "pages/DiagnosticRecordingIntro.tsx",
        "pages/DiagnosticTask.tsx",
        "pages/DiagnosticResume.tsx",
        "pages/PremiumReport.tsx",
        "pages/Analyzing.tsx",
        "pages/Legal.tsx",
        "pages/QualityResult.tsx",
    ]
    for rel in pages:
        src = _read(rel)
        assert "SubPageHeader" not in src, rel
        assert "sub-page-header" not in src, rel


def test_flow_internal_back_buttons_remain():
    concern = _read("pages/ConcernIntake.tsx")
    assert "고민 선택으로 돌아가기" in concern
    task = _read("pages/DiagnosticTask.tsx")
    assert "다시 시도" in task or "다시 불러오기" in task


def test_audio_preview_does_not_disable_on_property_detection():
    panel = _read("components/ui/AudioReadyPanel.tsx")
    assert "canPlayType" not in panel
    assert "MediaRecorder.isTypeSupported" not in panel
    record = _read("pages/Record.tsx")
    assert "AudioReadyPanel" in record
    assert "previewUrl" in record
    assert "revokeObjectURL" in record
    assert "onAnalyze={analyze}" in record
    assert "disabled={!controlsEnabled}" in panel
    assert "markElementPlayable" in panel
    assert "onError={() => {" not in panel


def test_anonymous_key_uses_official_sdk_hash_shape():
    ident = _read("lib/userIdentity.ts")
    assert "@apps-in-toss/web-framework" in ident
    assert "getAnonymousKey" in ident
    assert "type === 'HASH'" in ident
    assert "rec.hash" in ident
    assert "INVALID_CATEGORY" in ident
    assert "SDK_UNSUPPORTED" in ident
    assert "key.result" not in ident
    assert "AppsInToss.getAnonymousKey" not in ident
    assert "window as any)?.AppsInToss" not in ident
    assert "import.meta.env.PROD" in ident
    assert "demo-user" in ident
    assert "provider: 'DEV'" in ident


def test_create_analysis_separates_identity_from_network():
    client = _read("api/client.ts")
    errors = _read("lib/userFacingErrors.ts")
    assert "reqHeaders = await headers()" in client
    assert "isIdentityUnavailableError" in client
    assert "NETWORK_UNAVAILABLE" in client
    assert "서버에 연결할 수 없어요" in errors
    idx_ident = client.find("reqHeaders = await headers()")
    idx_fetch = client.find("fetch(apiUrl(`/v1/analyses`)")
    assert 0 <= idx_ident < idx_fetch
    ident = _read("lib/userIdentity.ts")
    assert "사용자 정보를 확인하지 못했어요" in ident
    assert "ANALYSIS_FAILED" in client
    assert "분석 요청 처리 중 문제가 발생했어요" in errors
