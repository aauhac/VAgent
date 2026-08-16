# -*- coding: utf-8 -*-
"""Dev-only Goal Progress demo — synthetic TEST_GOAL, not claimed as real user goal."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.services.goal_progress import build_goal_progress

OUT = Path("singer_identity_output/goal_progress_demo")


def main() -> None:
    # Synthetic fixture labels (not the singer's real stated goal)
    goal = {
        "id": "TEST_GOAL_REGISTER_CONNECTION",
        "focus": "REGISTER_CONNECTION",
        "label": "[DEMO] 고음 구간을 더 안정적으로 연결하기",
        "source": "USER_SELECTED",
        "kind": "FUNCTIONAL",
        "axis": "register_connection",
        "target": "CONNECTED",
        "started_at": "2026-08-01T00:00:00+00:00",
    }
    labels_prev = ["PARTIAL", "DISRUPTED", "PARTIAL", "PARTIAL", "CONNECTED"]
    labels_recent = ["PARTIAL", "DISRUPTED", "PARTIAL", "CONNECTED", "PARTIAL"]
    snaps = []
    for i, lab in enumerate(labels_prev + labels_recent):
        snaps.append(
            {
                "canonical_json": {"register_connection": lab},
                "analyzer_version": "demo-v1",
                "created_at": f"2026-08-{i+1:02d}T12:00:00+00:00",
                "goal_id_at_analysis": goal["id"],
                "goal_focus_at_analysis": "REGISTER_CONNECTION",
                "analysis_quality": "pass",
            }
        )
    out = build_goal_progress(
        goal=goal,
        historical_snapshots=snaps,
        current_canonical={"register_connection": "CONNECTED"},
        recent_n=5,
    )
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "demo": True,
        "note": "Synthetic TEST_GOAL — not a real user goal claim",
        "goal": goal,
        "progress": out,
        "scenario": "B",
    }
    (OUT / "goal_progress_demo.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = [
        "# Goal Progress Demo (synthetic)",
        "",
        f"- Goal: `{goal['label']}`",
        f"- Status: **{out['status']}**",
        f"- Recent aligned: **{out['window']['goal_aligned_count']} / {out['window']['size']}**",
        f"- Previous aligned: **{(out.get('previous_window') or {}).get('goal_aligned_count')}**",
        f"- Sequence: `{' '.join(out.get('dots') or [])}`",
        f"- Summary: {out.get('summary')}",
        "",
        "No fake percent. Identity similarity unused.",
        "",
    ]
    (OUT / "goal_progress_demo.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "status": out["status"], "window": out["window"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
