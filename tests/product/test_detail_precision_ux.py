# -*- coding: utf-8 -*-
"""Detail/Precision UX sweep — diagnosis-only copy, headers, prices, sample root cause."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINI = ROOT / "miniapp" / "src"
SLICE = Path(__file__).resolve().parent / "fixtures" / "analysis_9dff_profile_slice.json"

BANNED_NORMAL_UX = [
    "내 연습 목표",
    "목표 바꾸기",
    "무엇부터 연습",
    "단계별 연습",
    "Task 불러오는 중",
    "업그레이드 요금",
    "측정 근거 부족",
    "판단 근거 부족",
    "녹음 품질이 나쁩니다",
    "잘못 녹음했습니다",
]


def _read(rel: str) -> str:
    return (MINI / rel).read_text(encoding="utf-8")


def test_shared_header_on_detail_and_precision_flow():
    pages = {
        "pages/SongDetailReport.tsx": "상세 리포트",
        "pages/PremiumUnlock.tsx": "정밀 발성 진단",
        "pages/ConcernIntake.tsx": "정밀 발성 진단",
        "pages/SafetyCheck.tsx": "정밀 발성 진단",
        "pages/DiagnosticRecordingIntro.tsx": "정밀 발성 진단",
        "pages/DiagnosticTask.tsx": "정밀 발성 진단",
        "pages/PremiumReport.tsx": "정밀 발성 진단",
        "pages/DiagnosticResume.tsx": "정밀 발성 진단",
    }
    for rel, title in pages.items():
        src = _read(rel)
        assert "SubPageHeader" not in src, rel
        assert "← 뒤로" not in src, rel
        if rel != "pages/DiagnosticResume.tsx":
            assert title in src, rel


def test_normal_ux_bans_training_and_quality_blame():
    paths = [
        "pages/SongDetailReport.tsx",
        "pages/PremiumUnlock.tsx",
        "pages/Result.tsx",
        "pages/Home.tsx",
        "lib/diagnosticOffer.ts",
        "components/report/VocalProfile.tsx",
        "components/report/DiagnosticCTA.tsx",
        "pages/DiagnosticTask.tsx",
    ]
    joined = "\n".join(_read(p) for p in paths)
    for token in BANNED_NORMAL_UX:
        assert token not in joined, token
    assert "녹음 준비 중" in _read("pages/DiagnosticTask.tsx")
    assert "약 2~3분" not in _read("pages/DiagnosticRecordingIntro.tsx")


def test_mock_payment_copy_is_debug_only():
    unlock = _read("pages/PremiumUnlock.tsx")
    assert "개발 환경 Mock 결제" in unlock
    assert "showDebug && !import.meta.env.PROD" in unlock


def test_unavailable_reason_adapter_has_evidence_categories():
    src = _read("lib/unavailableAxisReason.ts")
    assert "INSUFFICIENT_VOCAL_COVERAGE" in src
    assert "INSUFFICIENT_RANGE_TRANSITION" in src
    assert "INSUFFICIENT_DYNAMIC_VARIATION" in src
    assert "CONTACT_EVIDENCE_UNAVAILABLE" in src
    assert "RESONANCE_EVIDENCE_UNAVAILABLE" in src
    assert "SIGNAL_CONTAMINATION" in src
    assert "ESTIMATE_UNAVAILABLE" in src
    assert "녹음 품질" not in src
    assert "음성이 짧아서 분석하지 못했어요" not in src
    assert "vocalCoverageInsufficient" in src


def test_profile_completeness_fixtures_a_to_h_exist():
    src = _read("qa/vocalProfileFixtures.ts")
    for key in (
        "fixtureAFiveAxes",
        "fixtureBThreeAxes",
        "fixtureCOneAxis",
        "fixtureDZeroAxes",
        "fixtureEShortCoverage",
        "fixtureFHighRangeAbsent",
        "fixtureGContamination",
        "fixtureHCanonicalFallback",
    ):
        assert key in src, key


def test_sample_9dff_root_cause_a_plus_c():
    data = json.loads(SLICE.read_text(encoding="utf-8"))
    assert data["root_cause"] == "A+C"
    vf = data["vocal_function_profile"]
    dims = vf["dimensions"]
    breath = dims["air_leakage_breathiness"]
    assert breath["status"] == "LOW"
    assert breath.get("hidden") is False
    for key in (
        "glottal_contact_profile",
        "vocal_effort_strain",
        "register_configuration",
        "resonance_formant_strategy",
    ):
        row = dims[key]
        assert row.get("hidden") is True or row.get("status") in ("UNKNOWN", "UNAVAILABLE")
    assert not data.get("canonical_acoustic_axes")
    register = dims["register_configuration"]
    assert register.get("status") == "STABLE_LIKE"
    assert register.get("hidden") is True
    assert register.get("confidence_label") == "low"
    assert data["quality"]["voiced_duration_sec"] > 8


def test_high_note_and_timbre_unavailable_hidden_from_main():
    high = _read("components/report/HighNoteFunctionSection.tsx")
    timbre = _read("components/report/TimbreProfileSection.tsx")
    assert "return null" in high
    assert "return null" in timbre
    detail = _read("pages/SongDetailReport.tsx")
    assert "HighNoteFunctionSection" not in detail
    assert "TimbreProfileSection" not in detail
    more = _read("components/report/MoreDetails.tsx")
    assert "이번 녹음에서 확인하기 어려웠던 항목" in more
    assert "분석 방법과 한계" in more


def test_canonical_fallback_not_dropped_when_raw_hidden():
    src = _read("lib/reportPresentation.ts")
    assert "sourcedFromCanonical" in src
    assert "if (dim?.hidden && !sourcedFromCanonical) return null" in src


def test_dev_price_fallbacks_match_catalog_policy():
    result = _read("pages/Result.tsx")
    assert "₩990" not in result
    assert "₩1,980" not in result
    assert "useIapProductPrices" in result
    catalog = (ROOT / "backend" / "app" / "products" / "catalog.py").read_text(encoding="utf-8")
    assert 'mock_amount_krw": 990' in catalog
    assert 'mock_amount_krw": 1980' in catalog
    iap = _read("lib/iapCatalog.ts")
    assert "import.meta.env.PROD" in iap
    assert "display_amount" in iap
    assert "₩990" not in iap
