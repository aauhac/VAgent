"""Presentation vocabulary contracts for Product UI v1.2."""

import re
from pathlib import Path


def test_report_presentation_effort_vocab_never_uses_stability_word():
    src = (Path(__file__).resolve().parents[2] / "miniapp/src/lib/reportPresentation.ts").read_text(
        encoding="utf-8"
    )
    # effort branch should not assign '안정' labels
    m = re.search(r"if \(kind === 'effort'\) \{([\s\S]*?)\n  if \(kind === 'register'\)", src)
    assert m, "effort vocabulary block missing"
    block = m.group(1)
    assert "안정" not in block


def test_scrub_builders_exist():
    src = (Path(__file__).resolve().parents[2] / "miniapp/src/lib/reportPresentation.ts").read_text(
        encoding="utf-8"
    )
    assert "function techTokenRegex" in src
    assert "function caveatSentenceRegex" in src
    assert "String.fromCharCode" in src
    assert "0xc131" in src  # 성… encoded
