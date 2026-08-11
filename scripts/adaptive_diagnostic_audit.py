#!/usr/bin/env python3
"""Adaptive diagnostic planner audit (Track B)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio_analyzer.diagnostic.planner import (  # noqa: E402
    build_uncertainty_profile,
    explain_task_selection,
    select_diagnostic_tasks,
)


def _row(dim, *, suf="INSUFFICIENT", conf="low", finding="UNDETERMINED", req_s=0, req_t=2):
    return {
        "dimension_id": dim,
        "measurement_sufficiency": suf,
        "confidence_label": conf,
        "finding": finding,
        "required_satisfied": req_s,
        "required_total": req_t,
        "criteria": [],
        "coaching_eligibility": "NEEDS_MEASUREMENT" if suf == "INSUFFICIENT" else "ELIGIBLE",
    }


CASES = {
    "contact_only": [
        _row("glottal_contact_profile"),
        _row("air_leakage_breathiness", suf="SUFFICIENT", conf="high", finding="OK", req_s=2),
        _row("vocal_effort_strain", suf="SUFFICIENT", conf="high", finding="OK", req_s=2),
        _row("register_configuration", suf="SUFFICIENT", conf="high", finding="OK", req_s=2),
        _row("phonation_regularity", suf="SUFFICIENT", conf="high", finding="OK", req_s=2),
    ],
    "register_only": [
        _row("register_configuration"),
        _row("glottal_contact_profile", suf="SUFFICIENT", conf="high", finding="OK", req_s=2),
    ],
    "effort_only": [
        _row("vocal_effort_strain"),
        _row("glottal_contact_profile", suf="SUFFICIENT", conf="high", finding="OK", req_s=2),
    ],
    "contact_breath_stability": [
        _row("glottal_contact_profile"),
        _row("air_leakage_breathiness"),
        _row("phonation_regularity"),
    ],
    "contact_register_effort": [
        _row("glottal_contact_profile"),
        _row("register_configuration"),
        _row("vocal_effort_strain"),
    ],
    "all_resolved": [
        _row("glottal_contact_profile", suf="SUFFICIENT", conf="high", finding="OK", req_s=2),
        _row("air_leakage_breathiness", suf="SUFFICIENT", conf="high", finding="OK", req_s=2),
        _row("vocal_effort_strain", suf="SUFFICIENT", conf="high", finding="OK", req_s=2),
        _row("register_configuration", suf="SUFFICIENT", conf="high", finding="OK", req_s=2),
        _row("phonation_regularity", suf="SUFFICIENT", conf="high", finding="OK", req_s=2),
        _row("resonance_formant_strategy", suf="SUFFICIENT", conf="high", finding="OK", req_s=2),
        _row("onset_offset_coordination", suf="SUFFICIENT", conf="high", finding="OK", req_s=2),
        _row("respiratory_phonatory_coordination", suf="SUFFICIENT", conf="high", finding="OK", req_s=2),
    ],
}


def main() -> int:
    out = ROOT / "runtime" / "audits" / "adaptive_diagnostic"
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, matrix in CASES.items():
        profile = build_uncertainty_profile(criteria_matrix=matrix)
        plan = select_diagnostic_tasks(profile)
        explain = explain_task_selection(plan)
        report[name] = {
            "UNRESOLVED": plan.get("unresolved_dimensions"),
            "SELECTED": plan.get("selected_tasks"),
            "EXPECTED_COVERAGE": plan.get("expected_coverage"),
            "OFFER": explain.get("diagnostic_offer"),
            "RATIONALE": plan.get("rationale"),
        }
        print("=" * 50)
        print(name)
        print("UNRESOLVED", plan.get("unresolved_dimensions"))
        print("SELECTED", plan.get("selected_tasks"))
    path = out / "adaptive_diagnostic_audit.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
