# -*- coding: utf-8 -*-
"""Harness unit tests for behavioral audit v1 (no production mutation)."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from scripts.vocal_behavioral_audit.analyze import get_or_analyze, save_analysis_cache
from scripts.vocal_behavioral_audit.artifacts import build_html_report
from scripts.vocal_behavioral_audit.detectors import generic_collapse_pairs, lint_case
from scripts.vocal_behavioral_audit.diagnose import (
    catalog_concern_ids,
    diagnose_case,
    wrap_song,
)
from scripts.vocal_behavioral_audit.discovery import discover_audio_assets, sha256_file
from scripts.vocal_behavioral_audit.runner import run_audit


def _write_silent_wav(path: Path, *, seconds: float = 0.5, sr: int = 16000) -> None:
    n = int(seconds * sr)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x00" * n)


def _fake_analysis(**kw) -> dict:
    effort = kw.get("effort", "LOW")
    contact = kw.get("contact", "MID")
    register = kw.get("register", "CONNECTED")
    breath = kw.get("breath", "LOW")
    presence = kw.get("presence", 0.55)
    brightness = kw.get("brightness", 0.45)
    return {
        "vocal_function_profile": {
            "effort_assessment": {
                "level": effort,
                "status": effort,
                "confidence_label": "medium",
                "reliable_for_preserve": True,
            },
            "dimensions": {
                "vocal_effort_strain": {
                    "status": effort,
                    "confidence_label": "medium",
                    "continuum_0_to_1": 0.2 if effort == "LOW" else 0.7,
                },
                "glottal_contact_profile": {
                    "status": "OBSERVED",
                    "continuum_0_to_1": {"FIRM": 0.72, "LIGHT": 0.28, "MID": 0.5}.get(contact, 0.5),
                },
                "air_leakage_breathiness": {"status": breath},
                "phonation_regularity": {"status": "STABLE"},
            },
            "vocal_type_profile": {
                "register_strategy": {"status": register},
                "canonical_register": {"status": register},
            },
            "timbre_profile": {
                "available": True,
                "axes": {
                    "presence": {"continuum": presence},
                    "brightness": {"continuum": brightness},
                    "airiness": {"continuum": 0.4},
                },
            },
        }
    }


def test_audio_discovery_deduplicates_sha(tmp_path: Path):
    a = tmp_path / "sample1.wav"
    b = tmp_path / "copy" / "sample2.wav"
    _write_silent_wav(a)
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_bytes(a.read_bytes())
    assets = discover_audio_assets(tmp_path, audio_roots=[str(tmp_path)], include_generated=True)
    assert len(assets) == 1
    assert len(assets[0].aliases) == 2
    assert assets[0].sha256 == sha256_file(a)


def test_analysis_runs_once_per_audio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls = {"n": 0}

    def fake_run(path, *, audit_runtime, recording_id):
        calls["n"] += 1
        return _fake_analysis()

    monkeypatch.setattr(
        "scripts.vocal_behavioral_audit.analyze.run_production_analysis",
        fake_run,
    )
    from scripts.vocal_behavioral_audit.discovery import AudioAsset

    asset = AudioAsset(
        audio_id="abc123",
        path=str(tmp_path / "x.wav"),
        sha256="deadbeef" * 8,
        aliases=[],
    )
    _write_silent_wav(Path(asset.path))
    cache = tmp_path / "cache"
    rt = tmp_path / "rt"
    a1, m1 = get_or_analyze(asset, cache_root=cache, audit_runtime=rt, force_reanalyze=True)
    a2, m2 = get_or_analyze(asset, cache_root=cache, audit_runtime=rt, force_reanalyze=False)
    assert calls["n"] == 1
    assert m2["cache_hit"] is True
    assert a1 and a2


def test_same_audio_all_concerns_same_canonical_hash():
    song = wrap_song(_fake_analysis(effort="LOW", register="PARTIAL", presence=0.7, brightness=0.3))
    hashes = set()
    for cid in catalog_concern_ids()[:8]:
        case = diagnose_case(song, concern_ids=[cid])
        hashes.add(case["canonical_hash"])
    assert len(hashes) == 1


def test_every_catalog_concern_is_swept():
    ids = catalog_concern_ids()
    assert len(ids) >= 27
    assert "VOICE_TOO_THIN" in ids
    assert "PAIN_WHILE_SINGING" in ids


def test_target_does_not_mutate_canonical():
    song = wrap_song(_fake_analysis())
    hashes = set()
    for tid in ["BRIGHT_CLEAR", "DENSE_SOLID", "AIRY_DELICATE"]:
        case = diagnose_case(
            song,
            concern_ids=["TIMBRE_DISSATISFIED"],
            timbre_goal={"id": tid},
        )
        hashes.add(case["canonical_hash"])
    assert len(hashes) == 1


def test_safety_blocks_active_protocol():
    song = wrap_song(_fake_analysis(effort="HIGH", register="DISRUPTED"))
    case = diagnose_case(song, concern_ids=["PAIN_WHILE_SINGING"])
    assert case.get("safety", {}).get("pain") is True


def test_generic_collapse_detector():
    base = {
        "audio_id": "a1",
        "concern_id": "VOICE_TOO_THIN",
        "primary_focus": "STYLE",
        "protocol_id": "TIMBRE_STYLE",
        "qa": {"prescription": {"instruction": "같은 문장으로 연습하세요 자음 시작을 분명하게"}},
    }
    other = dict(base)
    other["concern_id"] = "VOICE_TOO_DARK_MUFFLED"
    rows = generic_collapse_pairs([base, other], threshold=0.88)
    assert rows
    assert rows[0]["similarity"] >= 0.88


def test_focus_protocol_coherence_detector():
    case = {
        "concern_id": "HIGH_NOTE_FLIPS",
        "primary_focus": "REGISTER_CONNECTION",
        "protocol_id": "TIMBRE_STYLE",
        "practice_id": "STYLE_BRIGHT_CLEAR",
        "qa": {
            "answer": "x",
            "prescription": {"instruction": "립트릴로 3~5회 연결하세요", "success_cues": ["ok"]},
        },
        "canonical_axes": {"effort_status": "LOW", "breathiness": "LOW", "register": "PARTIAL"},
    }
    findings = lint_case(case)
    assert any(f["code"] == "FOCUS_PROTOCOL_MISMATCH" for f in findings)


def test_qa_lint_detector():
    case = {
        "concern_id": "VOICE_TOO_THIN",
        "primary_focus": "PRESENCE",
        "qa": {
            "answer": "얇아요",
            "what_to_change": "소리 중심을 유지하세요",
            "prescription": {"instruction": "소리 중심을 유지하세요", "success_cues": ["a"]},
        },
        "canonical_axes": {},
    }
    findings = lint_case(case)
    assert any(f["code"] == "ABSTRACT_ACTION" for f in findings)


def test_html_report_generated(tmp_path: Path):
    html = build_html_report(
        {
            "audios": 1,
            "concerns_swept": 27,
            "concerns_catalog": 27,
            "singleton_cases": 27,
            "canonical_mutations": 0,
            "missing_prescriptions": 0,
            "generic_collapse_warnings": 0,
            "focus_protocol_mismatches": 0,
            "safety_violations": 0,
            "anatomical_claims": 0,
            "abstract_actions": 0,
            "top_failures": [],
            "top_warnings": [],
        },
        cases_sample=[{"audio_id": "x", "concern_id": "VOICE_TOO_THIN", "audit_status": "PASS"}],
    )
    out = tmp_path / "report.html"
    out.write_text(html, encoding="utf-8")
    assert "VAgent Behavioral Audit" in html
    assert out.exists()


def test_run_audit_smoke_with_cached_analysis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "repo"
    audio = repo / "sample.wav"
    _write_silent_wav(audio)
    sha = sha256_file(audio)
    out = tmp_path / "audit_output"
    cache = out / "cache"
    save_analysis_cache(cache, sha, _fake_analysis(), source="test")

    monkeypatch.setattr(
        "scripts.vocal_behavioral_audit.analyze.run_production_analysis",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("should not analyze")),
    )

    summary = run_audit(
        repo_root=repo,
        output_dir=out,
        quick=True,
        full=False,
        skip_pairs=True,
        skip_target_sweep=False,
        max_audios=1,
    )
    assert summary["audios"] == 1
    assert summary["singleton_cases"] == len(catalog_concern_ids())
    assert (out / "summary.json").exists()
    assert (out / "concern_singletons.jsonl").exists()
    assert (out / "report.html").exists()
    assert summary["canonical_mutations"] == 0
