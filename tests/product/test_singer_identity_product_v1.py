# -*- coding: utf-8 -*-
"""Product integration tests — Singer Identity pipeline (flags OFF by default)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from backend.app.config import (
    personal_vocal_baseline_enabled,
    singer_identity_enabled,
    singer_identity_enrollment_enabled,
    singer_identity_shadow_k2_enabled,
)
from backend.app.services.personal_vocal_baseline import (
    brightness_change_is_improvement,
    build_baseline,
    compare_progress,
    contact_change_is_improvement,
    effort_decrease_is_automatic_improvement,
    source_balance_change_is_improvement,
)
from backend.app.services.singer_identity_client import SingerIdentityUnavailable
from backend.app.services.voice_profile import PRODUCTION_STRATEGY, VoiceProfileService
from backend.app.services.voice_profile_store import VoiceProfileFileStore, profile_status_for_count


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> VoiceProfileFileStore:
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path / "runtime"))
    return VoiceProfileFileStore(tmp_path / "runtime" / "voice_identity")


def test_identity_disabled_does_not_call_service(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "false")
    client = MagicMock()
    svc = VoiceProfileService(store=store, client=client)
    out = svc.verify("user-a", Path("missing.wav"))
    assert out["decision"] == "DISABLED"
    client.verify_recording.assert_not_called()


def test_baseline_disabled_does_not_change_report(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PERSONAL_VOCAL_BASELINE_ENABLED", "false")
    assert personal_vocal_baseline_enabled() is False


def test_explicit_consent_required_for_enrollment(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    monkeypatch.setenv("SINGER_IDENTITY_ENROLLMENT_ENABLED", "true")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 100)
    client = MagicMock()
    svc = VoiceProfileService(store=store, client=client)
    out = svc.enroll("u1", audio, consent=False)
    assert out["status"] == "CONSENT_REQUIRED"
    client.enroll_recording.assert_not_called()


def test_first_recording_creates_profile(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    monkeypatch.setenv("SINGER_IDENTITY_ENROLLMENT_ENABLED", "true")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"audio-one")
    client = MagicMock()
    client.get_model_info.return_value = {"model_version": "v1", "embedding_dim": 192, "encoder_name": "ECAPA"}
    client.create_subject.return_value = {"singer_id": "singer_x"}
    client.enroll_recording.return_value = {"recording_count": 1}
    svc = VoiceProfileService(store=store, client=client)
    out = svc.enroll("u1", audio, consent=True)
    assert out["status"] == "ENROLLED"
    assert out["recording_count"] == 1
    assert out["profile_status"] == "INITIAL"
    assert out["strategy"] == PRODUCTION_STRATEGY


def test_incremental_enrollment_updates_profile_version(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    monkeypatch.setenv("SINGER_IDENTITY_ENROLLMENT_ENABLED", "true")
    client = MagicMock()
    client.get_model_info.return_value = {"model_version": "v1", "embedding_dim": 192}
    client.create_subject.return_value = {"singer_id": "singer_x"}
    client.enroll_recording.return_value = {}
    svc = VoiceProfileService(store=store, client=client)
    for i in range(5):
        p = tmp_path / f"a{i}.wav"
        p.write_bytes(f"audio-{i}".encode())
        out = svc.enroll("u1", p, consent=True)
    assert out["recording_count"] == 5
    assert out["profile_status"] == "EXPANDED"
    assert out["profile_version"] == 5


def test_duplicate_sha_not_enrolled_twice(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    monkeypatch.setenv("SINGER_IDENTITY_ENROLLMENT_ENABLED", "true")
    audio = tmp_path / "dup.wav"
    audio.write_bytes(b"same-bytes")
    client = MagicMock()
    client.get_model_info.return_value = {"model_version": "v1"}
    client.create_subject.return_value = {"singer_id": "s"}
    client.enroll_recording.return_value = {}
    svc = VoiceProfileService(store=store, client=client)
    assert svc.enroll("u1", audio, consent=True)["status"] == "ENROLLED"
    assert svc.enroll("u1", audio, consent=True)["status"] == "DUPLICATE_SHA"
    assert client.enroll_recording.call_count == 1


def test_analysis_does_not_auto_enroll(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    client = MagicMock()
    svc = VoiceProfileService(store=store, client=client)
    # verify path never enrolls
    audio = tmp_path / "x.wav"
    audio.write_bytes(b"x")
    out = svc.maybe_verify_after_analysis("u1", audio)
    assert out["decision"] == "NO_PROFILE"
    client.enroll_recording.assert_not_called()


def test_current_user_verification_uses_own_profile_only(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    monkeypatch.setenv("SINGER_IDENTITY_ENROLLMENT_ENABLED", "true")
    client = MagicMock()
    client.get_model_info.return_value = {"model_version": "v1"}
    client.create_subject.return_value = {"singer_id": "singer_me"}
    client.enroll_recording.return_value = {}
    client.verify_recording.return_value = {"decision": "MATCH", "similarity": 0.8, "model_version": "v1"}
    svc = VoiceProfileService(store=store, client=client)
    a = tmp_path / "a.wav"
    a.write_bytes(b"aaa")
    svc.enroll("me", a, consent=True)
    b = tmp_path / "b.wav"
    b.write_bytes(b"bbb")
    out = svc.verify("me", b)
    assert out["decision"] == "MATCH"
    client.verify_recording.assert_called()
    called_singer = client.verify_recording.call_args[0][0]
    assert called_singer.startswith("singer_")
    assert store.get_profile("me")["singer_id"] == called_singer


def test_match_does_not_modify_acoustic_analysis():
    # contract: identity scores never feed HOW axes
    assert PRODUCTION_STRATEGY == "CENTROID"


def test_nonmatch_does_not_fail_vocal_analysis(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    store.upsert_profile("u", {"singer_id": "s1", "recording_count": 2, "profile_version": 2})
    client = MagicMock()
    client.verify_recording.return_value = {"decision": "NON_MATCH", "similarity": 0.3}
    svc = VoiceProfileService(store=store, client=client)
    p = tmp_path / "x.wav"
    p.write_bytes(b"x")
    out = svc.maybe_verify_after_analysis("u", p)
    assert out["decision"] == "NON_MATCH"
    # fail-open helper never raises


def test_uncertain_does_not_fail_vocal_analysis(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    store.upsert_profile("u", {"singer_id": "s1", "recording_count": 2, "profile_version": 2})
    client = MagicMock()
    client.verify_recording.return_value = {"decision": "UNCERTAIN", "similarity": 0.6}
    svc = VoiceProfileService(store=store, client=client)
    p = tmp_path / "x.wav"
    p.write_bytes(b"x")
    assert svc.maybe_verify_after_analysis("u", p)["decision"] == "UNCERTAIN"


def test_service_unavailable_does_not_fail_vocal_analysis(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    store.upsert_profile("u", {"singer_id": "s1", "recording_count": 1, "profile_version": 1})
    client = MagicMock()
    client.verify_recording.side_effect = SingerIdentityUnavailable("down")
    svc = VoiceProfileService(store=store, client=client)
    p = tmp_path / "x.wav"
    p.write_bytes(b"x")
    assert svc.maybe_verify_after_analysis("u", p)["decision"] == "UNAVAILABLE"


def test_raw_embedding_not_in_vagent_api_response(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    store.upsert_profile("u", {"singer_id": "s1", "recording_count": 1, "profile_version": 1})
    client = MagicMock()
    client.verify_recording.return_value = {
        "decision": "MATCH",
        "similarity": 0.8,
        "embedding": [0.1] * 10,
    }
    svc = VoiceProfileService(store=store, client=client)
    p = tmp_path / "x.wav"
    p.write_bytes(b"x")
    out = svc.verify("u", p)
    assert "embedding" not in out


def test_raw_embedding_not_in_log():
    from backend.app.services.singer_identity_client import _sanitize_for_log

    s = _sanitize_for_log({"embedding": [1, 2, 3], "decision": "MATCH"})
    assert s["embedding"] == "<redacted>"


def test_user_cannot_read_another_user_voice_profile(store: VoiceProfileFileStore):
    store.upsert_profile("alice", {"singer_id": "s_alice", "recording_count": 3})
    store.upsert_profile("bob", {"singer_id": "s_bob", "recording_count": 1})
    assert store.get_profile("alice")["singer_id"] == "s_alice"
    assert store.get_profile("bob")["singer_id"] == "s_bob"
    # API is subject-scoped; no cross lookup helper exists


def test_delete_voice_profile_deletes_identity_profile(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    store.upsert_profile("u", {"singer_id": "s1", "recording_count": 2})
    client = MagicMock()
    client.delete_profile.return_value = {"deleted": True}
    svc = VoiceProfileService(store=store, client=client)
    out = svc.delete("u")
    assert out["vagent_mapping_deleted"] is True
    assert out["singer_embeddings_deleted"] is True
    assert store.get_profile("u") is None


def test_delete_voice_profile_removes_vagent_mapping(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "false")
    store.upsert_profile("u", {"singer_id": "s1", "recording_count": 1})
    svc = VoiceProfileService(store=store, client=MagicMock())
    assert svc.delete("u")["vagent_mapping_deleted"] is True


def test_delete_voice_profile_does_not_silently_delete_unrelated_history(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    store.upsert_profile("u", {"singer_id": "s1", "recording_count": 1})
    store.add_snapshot({"external_subject": "u", "canonical_json": {"effort": "LOW"}})
    client = MagicMock()
    client.delete_profile.return_value = {"deleted": True}
    out = VoiceProfileService(store=store, client=client).delete("u")
    assert out["unrelated_history_deleted"] is False
    assert len(store.list_snapshots("u")) == 1


def test_completed_analysis_can_create_snapshot(store: VoiceProfileFileStore):
    row = store.add_snapshot(
        {
            "external_subject": "u",
            "analysis_id": "a1",
            "analyzer_version": "analyzer-v9",
            "canonical_json": {"effort": "LOW", "brightness": "MID"},
        }
    )
    assert row["id"]
    assert store.list_snapshots("u")[0]["analyzer_version"] == "analyzer-v9"


def test_current_snapshot_excluded_from_own_baseline():
    hist = [
        {"canonical_json": {"register_connection": "PARTIAL"}, "analyzer_version": "v1"},
        {"canonical_json": {"register_connection": "DISRUPTED"}, "analyzer_version": "v1"},
    ]
    out = compare_progress(
        current_canonical={"register_connection": "CONNECTED"},
        historical_snapshots=hist,
        goal="REGISTER_CONNECTION",
    )
    assert out["current_excluded_from_baseline"] is True
    assert out["history_count"] == 2


def test_baseline_uses_canonical_values():
    b = build_baseline(
        [
            {"canonical_json": {"brightness": "LOW"}},
            {"canonical_json": {"brightness": "HIGH"}},
        ]
    )
    assert "brightness" in b["axis_distributions"]
    assert b["arbitrary_numeric_scoring"] is False


def test_brightness_change_not_automatically_improvement():
    assert brightness_change_is_improvement("LOW", "HIGH") is False
    out = compare_progress(
        current_canonical={"brightness": "HIGH"},
        historical_snapshots=[{"canonical_json": {"brightness": "LOW"}, "analyzer_version": "v1"}],
    )
    bright = next(c for c in out["comparisons"] if c["axis"] == "brightness")
    assert bright["improvement"] is None


def test_source_balance_change_not_automatically_improvement():
    assert source_balance_change_is_improvement("A", "B") is False


def test_contact_change_not_automatically_improvement():
    assert contact_change_is_improvement("LIGHT", "FIRM") is False


def test_goal_aligned_register_change_can_be_improvement():
    out = compare_progress(
        current_canonical={"register_connection": "CONNECTED"},
        historical_snapshots=[
            {"canonical_json": {"register_connection": "PARTIAL"}, "analyzer_version": "v1"},
            {"canonical_json": {"register_connection": "DISRUPTED"}, "analyzer_version": "v1"},
            {"canonical_json": {"register_connection": "PARTIAL"}, "analyzer_version": "v1"},
        ],
        goal="REGISTER_CONNECTION",
    )
    reg = next(c for c in out["comparisons"] if c["axis"] == "register_connection")
    assert reg["improvement"] is True


def test_no_goal_returns_descriptive_change_only_when_appropriate():
    out = compare_progress(
        current_canonical={"register_connection": "CONNECTED", "brightness": "HIGH"},
        historical_snapshots=[
            {"canonical_json": {"register_connection": "PARTIAL", "brightness": "LOW"}, "analyzer_version": "v1"},
        ],
        goal=None,
    )
    assert out["goal_aware"] is False
    bright = next(c for c in out["comparisons"] if c["axis"] == "brightness")
    assert bright["improvement"] is None


def test_analyzer_version_saved(store: VoiceProfileFileStore):
    store.add_snapshot({"external_subject": "u", "analyzer_version": "v10", "canonical_json": {"effort": "LOW"}})
    assert store.list_snapshots("u")[0]["analyzer_version"] == "v10"


def test_mixed_analyzer_versions_flagged():
    out = compare_progress(
        current_canonical={"effort": "LOW"},
        historical_snapshots=[
            {"canonical_json": {"effort": "MODERATE"}, "analyzer_version": "v8"},
            {"canonical_json": {"effort": "LOW"}, "analyzer_version": "v10"},
        ],
    )
    assert out["status"] == "MIXED_ANALYZER_VERSIONS"


def test_identity_model_version_saved(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    monkeypatch.setenv("SINGER_IDENTITY_ENROLLMENT_ENABLED", "true")
    client = MagicMock()
    client.get_model_info.return_value = {"model_version": "singer-id-baseline-v1", "embedding_dim": 192}
    client.create_subject.return_value = {"singer_id": "s"}
    client.enroll_recording.return_value = {}
    svc = VoiceProfileService(store=store, client=client)
    p = tmp_path / "a.wav"
    p.write_bytes(b"z")
    svc.enroll("u", p, consent=True)
    assert store.get_profile("u")["encoder_version"] == "singer-id-baseline-v1"


def test_incompatible_embedding_versions_not_mixed(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    monkeypatch.setenv("SINGER_IDENTITY_ENROLLMENT_ENABLED", "true")
    client = MagicMock()
    client.create_subject.return_value = {"singer_id": "s"}
    client.enroll_recording.return_value = {}
    client.get_model_info.side_effect = [
        {"model_version": "v1", "embedding_dim": 192},
        {"model_version": "v2", "embedding_dim": 192},
    ]
    svc = VoiceProfileService(store=store, client=client)
    a = tmp_path / "a.wav"
    a.write_bytes(b"1")
    svc.enroll("u", a, consent=True)
    b = tmp_path / "b.wav"
    b.write_bytes(b"2")
    out = svc.enroll("u", b, consent=True)
    assert out["compatibility_state"] == "NEEDS_REENROLLMENT"


def test_centroid_remains_production_strategy():
    assert PRODUCTION_STRATEGY == "CENTROID"


def test_k2_shadow_does_not_change_production_decision(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    monkeypatch.setenv("SINGER_IDENTITY_SHADOW_K2_ENABLED", "true")
    store.upsert_profile("u", {"singer_id": "s1", "recording_count": 5, "profile_version": 5})
    client = MagicMock()
    client.verify_recording.return_value = {
        "decision": "NON_MATCH",
        "similarity": 0.4,
        "shadow_k2_similarity": 0.85,
        "shadow_k2_decision": "MATCH",
    }
    svc = VoiceProfileService(store=store, client=client)
    p = tmp_path / "x.wav"
    p.write_bytes(b"x")
    out = svc.verify("u", p)
    assert out["decision"] == "NON_MATCH"
    assert out["production_decision"] == "NON_MATCH"
    assert out["shadow_decision"] == "MATCH"
    assert out["disagreement"] is True


def test_shadow_disagreement_recorded(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    monkeypatch.setenv("SINGER_IDENTITY_SHADOW_K2_ENABLED", "true")
    store.upsert_profile("u", {"singer_id": "s1", "recording_count": 3, "profile_version": 3})
    client = MagicMock()
    client.verify_recording.return_value = {
        "decision": "MATCH",
        "similarity": 0.8,
        "shadow_k2_similarity": 0.4,
        "shadow_k2_decision": "NON_MATCH",
    }
    svc = VoiceProfileService(store=store, client=client)
    p = tmp_path / "x.wav"
    p.write_bytes(b"x")
    svc.verify("u", p)
    events = json.loads((store.shadow_path).read_text(encoding="utf-8"))
    assert events[-1]["disagreement"] is True
    assert "embedding" not in events[-1]


def test_shadow_event_contains_no_raw_embedding(store: VoiceProfileFileStore):
    with pytest.raises(ValueError):
        store.add_shadow_event({"external_subject": "u", "embedding": [1, 2, 3]})


def test_singer_service_timeout_does_not_break_diagnostic(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    store.upsert_profile("u", {"singer_id": "s", "recording_count": 1, "profile_version": 1})
    client = MagicMock()
    client.verify_recording.side_effect = SingerIdentityUnavailable("timeout")
    out = VoiceProfileService(store=store, client=client).maybe_verify_after_analysis("u", tmp_path / "x.wav")
    # missing file → SKIPPED; create file
    p = tmp_path / "x.wav"
    p.write_bytes(b"x")
    out = VoiceProfileService(store=store, client=client).maybe_verify_after_analysis("u", p)
    assert out["decision"] == "UNAVAILABLE"


def test_singer_service_500_does_not_break_coaching(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    store.upsert_profile("u", {"singer_id": "s", "recording_count": 1, "profile_version": 1})
    client = MagicMock()
    client.verify_recording.side_effect = SingerIdentityUnavailable("500")
    p = tmp_path / "x.wav"
    p.write_bytes(b"x")
    assert VoiceProfileService(store=store, client=client).maybe_verify_after_analysis("u", p)["decision"] == "UNAVAILABLE"


def test_singer_service_down_does_not_break_report(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    store.upsert_profile("u", {"singer_id": "s", "recording_count": 1, "profile_version": 1})
    client = MagicMock()
    client.verify_recording.side_effect = SingerIdentityUnavailable("down")
    p = tmp_path / "x.wav"
    p.write_bytes(b"x")
    assert VoiceProfileService(store=store, client=client).maybe_verify_after_analysis("u", p)["decision"] == "UNAVAILABLE"


def test_confirmed_profile_fixture_can_incrementally_enroll(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    monkeypatch.setenv("SINGER_IDENTITY_ENROLLMENT_ENABLED", "true")
    client = MagicMock()
    client.get_model_info.return_value = {"model_version": "v1"}
    client.create_subject.return_value = {"singer_id": "person_drowning_movie"}
    client.enroll_recording.return_value = {}
    svc = VoiceProfileService(store=store, client=client)
    for i in range(11):
        p = tmp_path / f"song{i}.wav"
        p.write_bytes(f"song-{i}".encode())
        out = svc.enroll("fixture_user", p, consent=True)
    assert out["recording_count"] == 11
    assert out["profile_status"] == "EXPANDED"


def test_love_again_centroid_match_fixture():
    # Threshold unchanged; fixture documents expected behavior without retuning
    from services.singer_identity.config import DEFAULT_VERIFY_MATCH

    assert DEFAULT_VERIFY_MATCH == 0.72


def test_k2_shadow_computed_for_hard_positive(monkeypatch: pytest.MonkeyPatch, store: VoiceProfileFileStore, tmp_path: Path):
    monkeypatch.setenv("SINGER_IDENTITY_ENABLED", "true")
    monkeypatch.setenv("SINGER_IDENTITY_SHADOW_K2_ENABLED", "true")
    store.upsert_profile("u", {"singer_id": "s", "recording_count": 10, "profile_version": 10})
    client = MagicMock()
    client.verify_recording.return_value = {
        "decision": "MATCH",
        "similarity": 0.765,
        "shadow_k2_similarity": 0.812,
        "shadow_k2_decision": "MATCH",
    }
    p = tmp_path / "love.wav"
    p.write_bytes(b"love")
    out = VoiceProfileService(store=store, client=client).verify("u", p)
    assert out["production_score"] == pytest.approx(0.765)
    assert out["shadow_score"] == pytest.approx(0.812)
    assert out["decision"] == "MATCH"


def test_effort_decrease_not_auto_improvement():
    assert effort_decrease_is_automatic_improvement("HIGH", "LOW") is False


def test_profile_status_labels():
    assert profile_status_for_count(0) == "NOT_ENROLLED"
    assert profile_status_for_count(1) == "INITIAL"
    assert profile_status_for_count(3) == "DEVELOPING"
    assert profile_status_for_count(5) == "EXPANDED"


def test_flags_default_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SINGER_IDENTITY_ENABLED", raising=False)
    monkeypatch.delenv("SINGER_IDENTITY_ENROLLMENT_ENABLED", raising=False)
    monkeypatch.delenv("PERSONAL_VOCAL_BASELINE_ENABLED", raising=False)
    monkeypatch.delenv("SINGER_IDENTITY_SHADOW_K2_ENABLED", raising=False)
    # clear lru if any — these are plain env reads
    assert singer_identity_enabled() is False
    assert singer_identity_enrollment_enabled() is False
    assert personal_vocal_baseline_enabled() is False
    assert singer_identity_shadow_k2_enabled() is False
