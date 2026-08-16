# -*- coding: utf-8 -*-
"""Audit report readability v2 — titles, Korean axes, Effort/Register/Source separation."""

from __future__ import annotations

import re
from pathlib import Path

from scripts.vocal_behavioral_audit.artifacts import build_html_report, enrich_audio_axes_display
from scripts.vocal_behavioral_audit.audio_review import build_canonical_review
from scripts.vocal_behavioral_audit.markdown_reports import (
    render_audio_markdown,
    write_all_markdown_reports,
)
from scripts.vocal_behavioral_audit.report_labels import (
    display_audio_name,
    display_effort,
    display_register_connection,
    display_source_balance,
    natural_one_line_summary,
)


def _snap(**kwargs):
    base = {
        "effort": {"level": "MODERATE", "reliable_for_preserve": True, "confidence_label": "medium"},
        "contact": {"status": "FIRM"},
        "breathiness": {"level": "LOW"},
        "register": {"status": "PARTIAL", "available": True},
        "source_balance": {"status": "CHEST_DOMINANT", "available": True},
        "stability": {"status": "STABLE"},
        "timbre": {"presence": 0.3, "brightness": 0.3, "axes": {}},
        "availability": {},
        "high_note": {"available": False},
    }
    base.update(kwargs)
    return base


def test_audio_report_title_prefers_original_filename():
    name = display_audio_name(path=r"C:\VocalAgent\목잡이.m4a", audio_id="0ada85fffc84")
    assert name == "목잡이.m4a"
    rev = build_canonical_review(
        audio_id="0ada85fffc84",
        path=r"C:\VocalAgent\목잡이.m4a",
        sha256="0ada85fffc84deadbeef",
        snap=_snap(),
    )
    rev["display_name"] = name
    md = render_audio_markdown(
        index=1,
        review=rev,
        singletons=[],
        targets=[],
        collapse={},
        audit_status="PASS",
        relative_json_hint="../x.jsonl",
    )
    assert md.startswith("# 목잡이.m4a")
    assert "내부 ID: `0ada85fffc84`" in md


def test_audio_report_title_does_not_default_to_hash_when_filename_exists():
    name = display_audio_name(path="samples/breathy_test_03.wav", audio_id="99023e55f0f5")
    assert name == "breathy_test_03.wav"
    assert name != "99023e55f0f5"
    assert not re.fullmatch(r"[0-9a-f]{8,}", name)


def test_duplicate_filenames_get_short_id_disambiguation():
    dups = {"recording.m4a"}
    a = display_audio_name(
        path="a/recording.m4a", audio_id="0ada85fffc84", duplicate_basenames=dups
    )
    b = display_audio_name(
        path="b/recording.m4a", audio_id="3f18ac21abcd", duplicate_basenames=dups
    )
    assert a.startswith("recording.m4a")
    assert b.startswith("recording.m4a")
    assert "0ada85ff" in a
    assert "3f18ac21" in b
    assert a != b


def test_effort_and_register_are_separate_columns(tmp_path: Path):
    rev = build_canonical_review(
        audio_id="t1", path="목잡이.m4a", sha256="aa", snap=_snap()
    )
    write_all_markdown_reports(
        output_dir=tmp_path,
        reviews=[rev],
        singleton_by_audio={"t1": []},
    )
    summary = (tmp_path / "audio_reports" / "summary.md").read_text(encoding="utf-8")
    header = summary.splitlines()[2]
    assert "힘 사용" in header
    assert "성구 연결" in header
    assert header.index("힘 사용") < header.index("성구 연결")


def test_register_connection_and_source_balance_are_separate():
    rev = build_canonical_review(
        audio_id="t1", path="x.wav", sha256="a", snap=_snap()
    )
    md = render_audio_markdown(
        index=1,
        review=rev,
        singletons=[],
        targets=[],
        collapse={},
        audit_status="PASS",
        relative_json_hint="../x.jsonl",
    )
    assert "성구 연결" in md
    assert "흉성·두성 음향 성향" in md
    c = rev["canonical"]
    assert c["register_connection"]["status"] == "PARTIAL"
    assert c["source_balance"]["status"] == "CHEST_DOMINANT"
    assert c["register_connection"]["status"] != c["source_balance"]["status"]


def test_partial_register_displays_korean_partial_label():
    assert display_register_connection("PARTIAL") == "일부 구간만 연결"


def test_connected_register_displays_korean_connected_label():
    assert display_register_connection("CONNECTED") == "자연스럽게 연결되는 편"


def test_disrupted_register_displays_korean_disrupted_label():
    assert display_register_connection("DISRUPTED") == "전환이 급격한 편"


def test_chest_dominant_never_used_as_register_connection_state():
    for sb in ("CHEST_DOMINANT", "HEAD_LEANING", "CHEST_LEANING", "HEAD_DOMINANT"):
        assert display_register_connection(sb) != display_source_balance(sb)
        assert "흉성" not in display_register_connection(sb)
        assert "두성" not in display_register_connection(sb)


def test_one_line_summary_is_natural_korean():
    rev = build_canonical_review(
        audio_id="t1", path="x.wav", sha256="a", snap=_snap()
    )
    s = rev["one_line_summary"]
    assert "이에요" in s or "어요" in s
    assert s.count(".") >= 1


def test_one_line_summary_does_not_join_raw_axis_fragments():
    canon = {
        "effort": {"status": "MODERATE", "reliable": True},
        "contact": {"status": "FIRM"},
        "breathiness": {"status": "LOW"},
        "register_connection": {"status": "PARTIAL"},
        "stability": {"status": "STABLE"},
        "presence": {"status": "LOW"},
        "brightness": {"status": "LOW"},
    }
    s = natural_one_line_summary(canon)
    assert "편이지만, 성구 연결이 일부 구간에서만 안정적으로 이어지는, 발성" not in s
    assert "편인," not in s


def test_one_line_summary_contains_no_raw_connected_partial_disrupted_tokens():
    for st in ("CONNECTED", "PARTIAL", "DISRUPTED"):
        canon = {
            "effort": {"status": "LOW", "reliable": True},
            "contact": {"status": "FIRM"},
            "breathiness": {"status": "LOW"},
            "register_connection": {"status": st},
            "stability": {"status": "STABLE"},
            "presence": {"status": "MID"},
            "brightness": {"status": "LOW"},
        }
        s = natural_one_line_summary(canon)
        assert "CONNECTED" not in s
        assert "PARTIAL" not in s
        assert "DISRUPTED" not in s


def test_human_validation_uses_display_labels():
    from scripts.vocal_behavioral_audit.human_validation import compare_audio_to_label

    rev = build_canonical_review(audio_id="t1", path="x.wav", sha256="a", snap=_snap())
    label = {
        "name": "B",
        "intent": ["PUSHED"],
        "ratings": {"effort": "HIGH", "breathiness": "HIGH"},
    }
    cmp = compare_audio_to_label(rev, label)
    rev["human_comparison"] = cmp
    rev["display_name"] = "x.wav"
    md = render_audio_markdown(
        index=1,
        review=rev,
        singletons=[],
        targets=[],
        collapse={},
        audit_status="REVIEW",
        relative_json_hint="../x.jsonl",
    )
    assert "사람이 의도한 상태" in md
    assert "VAgent 분석" in md
    assert "높은 편" in md or "중간 정도" in md


def test_html_audio_card_uses_display_name():
    html = build_html_report(
        {"audios": 1},
        cases_sample=[
            {
                "audio_id": "00ae450b11f1",
                "display_name": "목잡이.m4a",
                "one_line": "접촉감은 단단하고…",
                "file": r"C:\VocalAgent\목잡이.m4a",
            }
        ],
    )
    assert "목잡이.m4a" in html
    assert "display_name" in html
    assert "fName" in html


def test_html_audio_search_supports_filename():
    html = build_html_report({"audios": 1}, cases_sample=[{"audio_id": "x", "display_name": "a.wav"}])
    assert "fName" in html
    assert "hay(row)" in html


def test_every_report_has_internal_id_but_not_as_primary_title(tmp_path: Path):
    rev = build_canonical_review(
        audio_id="0ada85fffc84",
        path="목잡이.m4a",
        sha256="0ada85fffc84",
        snap=_snap(),
    )
    write_all_markdown_reports(
        output_dir=tmp_path, reviews=[rev], singleton_by_audio={"0ada85fffc84": []}
    )
    md = next((tmp_path / "audio_reports").glob("audio_*.md")).read_text(encoding="utf-8")
    first = md.splitlines()[0]
    assert first.startswith("# 목잡이.m4a")
    assert "0ada85fffc84" in md
    assert first != "# 0ada85fffc84"


def test_index_links_display_filename(tmp_path: Path):
    reviews = [
        build_canonical_review(audio_id="a1", path="목잡이.m4a", sha256="1", snap=_snap()),
        build_canonical_review(audio_id="a2", path="test_high.wav", sha256="2", snap=_snap()),
    ]
    write_all_markdown_reports(
        output_dir=tmp_path,
        reviews=reviews,
        singleton_by_audio={"a1": [], "a2": []},
    )
    idx = (tmp_path / "audio_reports" / "index.md").read_text(encoding="utf-8")
    assert "목잡이.m4a" in idx
    assert "test_high.wav" in idx
    assert "- [a1]" not in idx


def test_summary_first_column_is_audio_filename(tmp_path: Path):
    rev = build_canonical_review(
        audio_id="00ae450b11f1", path="목잡이.m4a", sha256="x", snap=_snap()
    )
    write_all_markdown_reports(
        output_dir=tmp_path, reviews=[rev], singleton_by_audio={"00ae450b11f1": []}
    )
    summary = (tmp_path / "audio_reports" / "summary.md").read_text(encoding="utf-8")
    assert summary.splitlines()[2].startswith("| 음원 |")
    assert "목잡이.m4a" in summary


def test_csv_keeps_raw_and_display():
    row = enrich_audio_axes_display(
        {
            "audio_id": "x",
            "file": "a.wav",
            "effort_status": "LOW",
            "register_connection": "PARTIAL",
            "source_balance": "CHEST_DOMINANT",
            "contact": "FIRM",
            "breathiness": "LOW",
            "stability": "STABLE",
            "presence": "LOW",
            "brightness": "LOW",
        }
    )
    assert row["effort_raw"] == "LOW"
    assert row["effort_display"] == display_effort("LOW")
    assert row["register_connection_raw"] == "PARTIAL"
    assert row["register_connection_display"] == "일부 구간만 연결"
    assert row["source_balance_raw"] == "CHEST_DOMINANT"
    assert "흉성" in row["source_balance_display"]
    assert row["register_connection_display"] != row["source_balance_display"]


def test_effort_display_korean():
    assert display_effort("LOW") == "낮은 편"
    assert display_effort("MODERATE") == "중간 정도"
    assert display_effort("HIGH") == "높은 편"


def test_generated_basename_not_preferred():
    name = display_audio_name(
        path="runtime/abc/analysis.wav",
        audio_id="abcdef12",
        aliases=["uploads/목잡이.m4a"],
    )
    assert name == "목잡이.m4a"
