# -*- coding: utf-8 -*-
"""Per-audio Markdown + human validation + baseline reclassification tests."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.vocal_behavioral_audit.audio_review import (
    build_canonical_review,
    build_one_line_summary,
)
from scripts.vocal_behavioral_audit.baseline_reclass import (
    reclassify_claims_from_singletons,
    reclassify_collapse_from_singletons,
)
from scripts.vocal_behavioral_audit.claim_lint import classify_claim_spans
from scripts.vocal_behavioral_audit.detectors import generic_collapse_pairs
from scripts.vocal_behavioral_audit.human_labels import resolve_label
from scripts.vocal_behavioral_audit.human_validation import compare_audio_to_label
from scripts.vocal_behavioral_audit.markdown_reports import (
    render_audio_markdown,
    write_all_markdown_reports,
)


def _snap(**kwargs):
    base = {
        "effort": {"level": "LOW", "reliable_for_preserve": True, "confidence_label": "medium"},
        "contact": {"status": "FIRM"},
        "breathiness": {"level": "LOW"},
        "register": {"status": "DISRUPTED", "available": True},
        "source_balance": {"status": "CHEST_DOMINANT", "available": True},
        "stability": {"status": "UNSTABLE"},
        "timbre": {"presence": 0.3, "brightness": 0.3, "axes": {}},
        "availability": {},
        "high_note": {"available": False},
    }
    base.update(kwargs)
    return base


def test_markdown_summary_uses_canonical_only():
    rev = build_canonical_review(
        audio_id="t1",
        path="x.wav",
        sha256="abc",
        snap=_snap(),
    )
    assert rev["concern_independent"] is True
    assert "성구" in rev["one_line_summary"] or "연결" in rev["one_line_summary"]
    # must not invent anatomy
    assert "연구개" not in rev["one_line_summary"]
    assert "성대" not in rev["one_line_summary"]


def test_concern_does_not_change_audio_summary():
    snap = _snap()
    a = build_canonical_review(audio_id="t1", path="x.wav", sha256="a", snap=snap)
    b = build_canonical_review(audio_id="t1", path="x.wav", sha256="a", snap=snap)
    assert a["one_line_summary"] == b["one_line_summary"]
    # injecting fake concern into snap must not be read by builder
    snap2 = dict(snap)
    snap2["concern_primary_focus"] = "PRESENCE"
    c = build_canonical_review(audio_id="t1", path="x.wav", sha256="a", snap=snap2)
    assert c["one_line_summary"] == a["one_line_summary"]


def test_markdown_has_register_and_source_balance_separately():
    rev = build_canonical_review(audio_id="t1", path="x.wav", sha256="a", snap=_snap())
    md = render_audio_markdown(
        index=1,
        review=rev,
        singletons=[],
        targets=[],
        collapse={},
        audit_status="PASS",
        relative_json_hint="../concern_singletons.jsonl",
    )
    assert "성구 연결" in md
    assert "흉성·두성 음향 성향" in md or "흉성/두성 음향 성향" in md
    # raw states only in debug details, not as primary table values
    assert "일부 구간만 연결" in md or "전환이 급격한 편" in md
    assert "<details>" in md
    assert "DISRUPTED" in md  # inside details
    assert "CHEST_DOMINANT" in md  # inside details
    # primary table uses Korean, not bare CONNECTED as the result cell exclusive label
    assert "| 성구 연결 | DISRUPTED |" not in md
    assert "| 흉성·두성 음향 성향 | CHEST_DOMINANT |" not in md


def test_unknown_axis_not_described_as_low():
    snap = _snap(effort={"level": "UNKNOWN", "reliable_for_preserve": False})
    rev = build_canonical_review(audio_id="t1", path="x.wav", sha256="a", snap=snap)
    assert "힘 사용이 낮은" not in rev["one_line_summary"]
    # description for unknown
    assert "단정하기 어려" in (rev["canonical"]["effort"]["description"] or "")


def test_human_label_comparison_when_label_exists():
    rev = build_canonical_review(audio_id="t1", path="x.wav", sha256="a", snap=_snap())
    label = {
        "name": "C",
        "intent": ["PUSHED", "REGISTER_FAIL"],
        "ratings": {"effort": "HIGH", "register_connection": "DISRUPTED"},
    }
    cmp = compare_audio_to_label(rev, label)
    by_axis = {r["axis"]: r for r in cmp["axis_comparison"]}
    assert by_axis["register_connection"]["result"] == "MATCH"
    assert by_axis["effort"]["result"] in ("MISS", "UNAVAILABLE", "PARTIAL_MATCH")


def test_no_human_claim_when_label_missing():
    rev = build_canonical_review(audio_id="t1", path="x.wav", sha256="a", snap=_snap())
    assert rev.get("human_comparison") is None


def test_every_audio_has_markdown_report(tmp_path: Path):
    reviews = [
        build_canonical_review(audio_id="a1", path="a.wav", sha256="1", snap=_snap()),
        build_canonical_review(
            audio_id="a2",
            path="b.wav",
            sha256="2",
            snap=_snap(register={"status": "CONNECTED"}),
        ),
    ]
    info = write_all_markdown_reports(
        output_dir=tmp_path,
        reviews=reviews,
        singleton_by_audio={"a1": [], "a2": []},
    )
    assert info["count"] == 2
    assert (tmp_path / "audio_reports" / "index.md").exists()
    assert (tmp_path / "audio_reports" / "summary.md").exists()
    for f in info["files"]:
        assert (tmp_path / "audio_reports" / f).exists()


def test_markdown_links_are_valid(tmp_path: Path):
    reviews = [
        build_canonical_review(audio_id="a1", path="sample.wav", sha256="1", snap=_snap()),
    ]
    info = write_all_markdown_reports(
        output_dir=tmp_path,
        reviews=reviews,
        singleton_by_audio={"a1": []},
    )
    index = (tmp_path / "audio_reports" / "index.md").read_text(encoding="utf-8")
    for f in info["files"]:
        assert f"./"+f in index or f in index
        assert (tmp_path / "audio_reports" / f).exists()


def test_summary_contains_all_unique_audio(tmp_path: Path):
    reviews = [
        build_canonical_review(audio_id="x1", path="a.wav", sha256="1", snap=_snap()),
        build_canonical_review(audio_id="x2", path="b.wav", sha256="2", snap=_snap()),
    ]
    write_all_markdown_reports(
        output_dir=tmp_path,
        reviews=reviews,
        singleton_by_audio={"x1": [], "x2": []},
    )
    summary = (tmp_path / "audio_reports" / "summary.md").read_text(encoding="utf-8")
    assert "`x1`" in summary and "`x2`" in summary


def test_manual_review_priority_generated(tmp_path: Path):
    rev = build_canonical_review(
        audio_id="rare",
        path="c.wav",
        sha256="3",
        snap=_snap(register={"status": "CONNECTED"}, stability={"status": "STABLE"}),
    )
    info = write_all_markdown_reports(
        output_dir=tmp_path,
        reviews=[rev],
        singleton_by_audio={"rare": []},
    )
    assert any(q["audio_id"] == "rare" for q in info["manual_review_queue"])


def test_baseline_claims_use_same_classifier_as_after():
    # shared classifier entrypoint
    spans = classify_claim_spans("밝기가 어두운 편이에요.")
    assert spans
    singles = [
        {
            "audio_id": "a",
            "concern_id": "VOICE_TOO_DARK_MUFFLED",
            "canonical_axes": {"brightness": "UNAVAILABLE"},
            "qa": {"answer": "밝기가 어두운 편이에요."},
        }
    ]
    out = reclassify_claims_from_singletons(singles)
    assert out["classifier"] == "claim_lint_v1"
    assert out["true_unsupported"] >= 1


def test_baseline_collapse_uses_same_classifier_as_after():
    cases = [
        {
            "audio_id": "a1",
            "concern_id": "HIGH_NOTE_FLIPS",
            "primary_focus": "REGISTER_CONNECTION",
            "protocol_id": "REGISTER_CONNECTION",
            "question_type": "FUNCTIONAL",
            "qa": {"prescription": {"instruction": "same", "success_cues": ["s1"]}},
        },
        {
            "audio_id": "a1",
            "concern_id": "REGISTER_CONNECTION_DIFFICULT",
            "primary_focus": "REGISTER_CONNECTION",
            "protocol_id": "REGISTER_CONNECTION",
            "question_type": "CONTROL",
            "qa": {"prescription": {"instruction": "same", "success_cues": ["s2"]}},
        },
    ]
    a = generic_collapse_pairs(cases, threshold=0.5)
    b = reclassify_collapse_from_singletons(cases)
    assert a[0]["classification"] == "EXPECTED_SHARED_PROTOCOL"
    assert b["expected"] == 1
    assert b["classifier"].startswith("generic_collapse")


def test_before_after_comparison_is_apples_to_apples():
    # both sides use same function family
    assert reclassify_claims_from_singletons([])["classifier"] == "claim_lint_v1"
    assert "generic_collapse" in reclassify_collapse_from_singletons([])["classifier"]
