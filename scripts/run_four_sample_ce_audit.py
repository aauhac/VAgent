#!/usr/bin/env python3
"""Run contact/effort audit on the four controlled samples."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.contact_effort_audit import _analyze, _print_audit, _print_pair  # noqa: E402


SAMPLES = [
    ("편하게.m4a", "comfortable"),
    ("목잡이.m4a", "squeezed"),
    ("호흡많고헤드.m4a", "breathy_head"),
    ("편안세게.m4a", "firm_mix"),  # firm contact + mix candidate
]


def main() -> int:
    out = ROOT / "runtime" / "audits" / "contact_effort"
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    for audio, sid in SAMPLES:
        p = ROOT / audio
        print("=" * 60)
        print("ANALYZING", sid, p.name, "exists=", p.exists())
        if not p.exists():
            continue
        s = _analyze(p, out, sid)
        _print_audit(s)
        results[sid] = s

    if "comfortable" in results and "squeezed" in results:
        print("\n### PAIR: comfortable vs squeezed")
        _print_pair(results["comfortable"], results["squeezed"])
    if "firm_mix" in results and "squeezed" in results:
        print("\n### PAIR: firm_mix vs squeezed")
        _print_pair(results["firm_mix"], results["squeezed"])
    if "comfortable" in results and "breathy_head" in results:
        print("\n### PAIR: comfortable vs breathy_head")
        _print_pair(results["comfortable"], results["breathy_head"])
    if "comfortable" in results and "firm_mix" in results:
        print("\n### PAIR: comfortable vs firm_mix")
        _print_pair(results["comfortable"], results["firm_mix"])

    rows = []
    for sid, s in results.items():
        rows.append(
            {
                "id": sid,
                "g_valid_pct": round(100 * s["n_global_valid"] / max(1, s["n_total"]), 1),
                "c_valid_pct": round(100 * s["n_contact_valid"] / max(1, s["n_total"]), 1),
                "e_valid_pct": round(100 * s["n_effort_valid"] / max(1, s["n_total"]), 1),
                "gif": s["n_gif_valid"],
                "contact_score": s["contact"].get("score"),
                "contact_status": s["contact"].get("status"),
                "contact_conf": s["contact"].get("confidence"),
                "effort_score": s["effort"].get("score"),
                "effort_status": s["effort"].get("status"),
                "effort_conf": s["effort"].get("confidence"),
                "effort_hits": s["effort"].get("hit_segments"),
                "family_hits": s["effort"].get("family_hits"),
                "rough_hits": s["roughness"].get("hits"),
                "rough_status": s["roughness"].get("status"),
                "pressed": s.get("pressed_observation_hits"),
                "primary": s.get("primary"),
                "vocal_type": s.get("vocal_type"),
            }
        )
        print(rows[-1])

    # Ordinal checks (labels are audit-only)
    checks = {}
    if "comfortable" in results and "squeezed" in results:
        ec = results["comfortable"]["effort"].get("score") or 0
        es = results["squeezed"]["effort"].get("score") or 0
        checks["squeezed_effort_gt_comfortable"] = es > ec
        checks["comfortable_effort"] = ec
        checks["squeezed_effort"] = es
    if "firm_mix" in results and "squeezed" in results:
        ef = results["firm_mix"]["effort"].get("score") or 0
        es = results["squeezed"]["effort"].get("score") or 0
        checks["squeezed_effort_gt_firm_mix"] = es > ef
        checks["firm_mix_effort"] = ef
    if "comfortable" in results and "breathy_head" in results:
        checks["breathy_contact"] = results["breathy_head"]["contact"].get("score")
        checks["comfortable_contact"] = results["comfortable"]["contact"].get("score")

    payload = {
        "samples": rows,
        "ordinal_checks": checks,
        "mapping": {
            "comfortable": "편하게.m4a",
            "squeezed": "목잡이.m4a",
            "breathy_head": "호흡많고헤드.m4a",
            "firm_mix": "편안세게.m4a",
        },
    }
    path = out / "four_sample_summary.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nORDINAL", json.dumps(checks, ensure_ascii=False, indent=2))
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
