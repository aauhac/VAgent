"""v2.5 UI contracts — recording choice + concern-only copy."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINI = ROOT / "miniapp" / "src"


def test_safety_recovers_without_home():
    text = (MINI / "pages" / "SafetyCheck.tsx").read_text(encoding="utf-8")
    assert "resolveDiagnosticRoute" in text or "nextDiagnosticRoute" in text
    assert "nav('/')" not in text and 'nav("/")' not in text
    assert "진단 진행 상태를 다시 확인했어요" in text
    # Recording Choice via helper (never Home) — literal "/recordings" lives in diagnosticEntry
    assert "recordingChoicePath" in text
    entry = (MINI / "lib" / "diagnosticEntry.ts").read_text(encoding="utf-8")
    assert "/recordings" in entry


def test_recording_choice_start_api_used():
    text = (MINI / "pages" / "DiagnosticRecordingIntro.tsx").read_text(encoding="utf-8")
    assert "startControlledRecordings" in text
    assert "추가 녹음 없이 결과 보기" in text


def test_route_resolver_has_recording_choice():
    text = (MINI / "lib" / "diagnosticEntry.ts").read_text(encoding="utf-8")
    assert "RECORDING_CHOICE" in text
    assert "/recordings" in text


def test_concern_only_copy_mentions_song():
    text = (MINI / "pages" / "PremiumReport.tsx").read_text(encoding="utf-8")
    assert "기존 노래에서 확인된 발성 특징" in text
    assert "이번 노래에서 보이는 핵심 특징" in text
    assert "표준 발성 과제를 분석한 결과" not in text


def test_q_card_does_not_render_detailed_practice():
    text = (MINI / "pages" / "PremiumReport.tsx").read_text(encoding="utf-8")
    # detailed practice block under Q removed; takeaway only
    assert "practice_direction" not in text or "qa.practice_direction" not in text
    assert "맞춤 연습 방향" in text
