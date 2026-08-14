"""ABCD coaching protocol audit — human-intent fixtures, no threshold retune.

Usage:
  python -m scripts.audit_coaching_protocol_abcd_v1
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from audio_analyzer.diagnostic.goal_planner import plan_coaching_goal
from audio_analyzer.diagnostic.song_evidence import build_song_evidence_snapshot
from audio_analyzer.vocal_function.derived.effort_assessment import build_effort_assessment


def _song(**kw):
    effort = kw.get("effort", "LOW")
    contact = kw.get("contact", "MID")
    register = kw.get("register", "CONNECTED")
    presence = kw.get("presence", 0.5)
    breath = kw.get("breath", "LOW")
    stability = kw.get("stability", "STABLE")
    conf = kw.get("effort_conf", "medium")
    cont = {"FIRM": 0.72, "LIGHT": 0.28, "MID": 0.5}.get(contact, 0.5)
    peak = kw.get("peak", 0.1 if effort == "LOW" else 0.6)
    hits = kw.get("hits", 0 if effort == "LOW" else 2)
    dim = {
        "status": effort if effort != "UNKNOWN" else "UNKNOWN",
        "confidence_label": conf,
        "continuum_0_to_1": peak,
        "profile": {
            "effort_score": peak,
            "mean_segment_effort_score": peak * 0.5,
            "hit_segments": hits,
            "core_family_count": 0 if hits == 0 else 2,
            "support_family_count": 0 if hits == 0 else 1,
            "persistent_segments": 0 if hits == 0 else 1,
        },
    }
    assessment = build_effort_assessment(dim, valid_segment_count=12)
    return {
        "vocal_function_profile": {
            "effort_assessment": assessment,
            "dimensions": {
                "vocal_effort_strain": dim,
                "glottal_contact_profile": {"status": "OBSERVED", "continuum_0_to_1": cont},
                "air_leakage_breathiness": {"status": breath},
                "phonation_regularity": {"status": stability},
            },
            "vocal_type_profile": {
                "register_strategy": {"status": register},
                "canonical_register": {"status": register},
            },
            "timbre_profile": {
                "available": True,
                "axes": {"presence": {"continuum": presence}, "brightness": {"continuum": 0.5}},
            },
        }
    }


def _ev(cid, focus):
    return {
        "concern_id": cid,
        "primary_focus": focus,
        "guidance_level": "SONG_DIRECT",
        "status": "PARTIALLY_SUPPORTED",
        "counts_for_consensus": True,
        "secondary_factors": [],
    }


CASES = [
    {
        "label": "A",
        "human_intent": "RELAXED",
        "song": lambda: _song(effort="LOW", peak=0.08, hits=0, register="CONNECTED", contact="MID", presence=0.55),
        "concerns": [{"id": "TIMBRE_DISSATISFIED"}],
        "evals": [_ev("TIMBRE_DISSATISFIED", "TIMBRE")],
        "timbre_goal": {"id": "SOFT_SWEET"},
    },
    {
        "label": "B",
        "human_intent": "PUSHED",
        "song": lambda: _song(effort="HIGH", peak=0.62, hits=2, register="PARTIAL", contact="FIRM", presence=0.45),
        "concerns": [{"id": "THROAT_EFFORT"}],
        "evals": [_ev("THROAT_EFFORT", "EFFORT")],
        "timbre_goal": None,
    },
    {
        "label": "C",
        "human_intent": "PUSHED_REGISTER_FAIL",
        # Detector may still report LOW (known miss) — register DISRUPTED should drive protocol
        "song": lambda: _song(
            effort="LOW", peak=0.12, hits=0, register="DISRUPTED", contact="FIRM", presence=0.4, stability="UNSTABLE"
        ),
        "concerns": [{"id": "HIGH_NOTE_FLIPS"}, {"id": "REGISTER_CONNECTION_DIFFICULT"}],
        "evals": [
            _ev("HIGH_NOTE_FLIPS", "REGISTER_CONNECTION"),
            _ev("REGISTER_CONNECTION_DIFFICULT", "REGISTER_CONNECTION"),
        ],
        "timbre_goal": {"id": "BRIGHT_CLEAR"},
    },
    {
        "label": "D",
        "human_intent": "HIGH_NOTE_PUSH",
        "song": lambda: _song(
            effort="HIGH", peak=0.65, hits=3, register="PARTIAL", contact="FIRM", presence=0.4, stability="UNSTABLE"
        ),
        "concerns": [{"id": "HIGH_NOTE_TOO_EFFORTFUL"}],
        "evals": [_ev("HIGH_NOTE_TOO_EFFORTFUL", "EFFORT")],
        "timbre_goal": None,
    },
]


def main() -> None:
    rows = []
    for case in CASES:
        song = case["song"]()
        snap = build_song_evidence_snapshot(song)
        goal = plan_coaching_goal(
            user_concerns=case["concerns"],
            timbre_goal=case["timbre_goal"],
            concern_evaluations=case["evals"],
            song_profile=song,
        )
        proto = goal.get("coaching_protocol") or {}
        effort_raw = (song.get("vocal_function_profile") or {}).get("effort_assessment") or {}
        rows.append(
            {
                "label": case["label"],
                "human_intent": case["human_intent"],
                "canonical": {
                    "effort": snap.get("effort"),
                    "contact": snap.get("contact"),
                    "breathiness": snap.get("breathiness"),
                    "register": snap.get("register"),
                    "stability": snap.get("stability"),
                    "presence": (snap.get("timbre") or {}).get("presence"),
                },
                "raw_effort": {
                    "global_severity": effort_raw.get("global_severity"),
                    "peak_event_score": effort_raw.get("peak_event_score"),
                    "hit_segments": effort_raw.get("hit_segments"),
                    "hit_ratio": effort_raw.get("hit_ratio"),
                    "confidence_label": effort_raw.get("confidence_label"),
                    "strength_eligible": effort_raw.get("strength_eligible"),
                },
                "focus": goal.get("primary_focus"),
                "protocol_id": proto.get("protocol_id"),
                "entry_title": (proto.get("entry_step") or {}).get("title"),
                "steps": [
                    {"level": s.get("level"), "id": s.get("id"), "title": s.get("title")}
                    for s in (proto.get("steps") or [])
                ],
                "threshold_changed": False,
            }
        )

    ids = [r["protocol_id"] for r in rows]
    out = {
        "audit": "coaching-protocol-abcd-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold_changed": False,
        "protocol_ids": ids,
        "meaningfully_different": len(set(ids)) >= 2,
        "cases": rows,
    }
    path = Path(f".coaching_protocol_abcd_v1_{int(datetime.now().timestamp() * 1000)}.json")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(path), "ids": ids, "different": out["meaningfully_different"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
