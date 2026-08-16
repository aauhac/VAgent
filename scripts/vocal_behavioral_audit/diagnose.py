# -*- coding: utf-8 -*-
"""Canonical fingerprint + pure diagnosis cases (no DB)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional

from audio_analyzer.diagnostic.concerns import (
    CONCERN_CATALOG,
    PAIN_CONCERN_IDS,
    build_personalized_qa,
    has_pain_safety_flag,
    normalize_user_concerns,
)
from audio_analyzer.diagnostic.goal_planner import plan_coaching_goal
from audio_analyzer.diagnostic.song_evidence import (
    get_canonical_snapshot,
    wrap_song_profile_with_snapshot,
)
from audio_analyzer.diagnostic.timbre_goals import (
    TARGET_TIMBRE_OPTIONS,
    normalize_timbre_goal,
)


def catalog_concern_ids() -> list[str]:
    return list(CONCERN_CATALOG.keys())


def safety_concern_ids() -> list[str]:
    return [c for c in catalog_concern_ids() if c in PAIN_CONCERN_IDS or CONCERN_CATALOG[c]["category"] == "safety"]


def target_timbre_ids() -> list[str]:
    return [str(o["id"]) for o in TARGET_TIMBRE_OPTIONS]


def _bucket_float(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "UNAVAILABLE"
    if x <= 0.42:
        return "LOW"
    if x >= 0.58:
        return "HIGH"
    return "MID"


def axes_from_snap(snap: dict[str, Any]) -> dict[str, Any]:
    timbre = snap.get("timbre") or {}
    effort = snap.get("effort") or {}
    contact = snap.get("contact") or {}
    breath = snap.get("breathiness") or {}
    register = snap.get("register") or {}
    stability = snap.get("stability") or {}
    high = snap.get("high_note") or {}
    avail = snap.get("availability") or {}
    sb = snap.get("source_balance") or {}
    # Connection (CONNECTED/PARTIAL/DISRUPTED/UNRESOLVED) — never mix with chest/head lean
    reg_conn = str(register.get("status") or "UNKNOWN").upper()
    sb_status = str(sb.get("status") or sb.get("balance_class") or "").upper()
    if not sb_status:
        raw = str(register.get("raw_strategy_status") or "").upper()
        if raw in ("CHEST_DOMINANT", "HEAD_DOMINANT", "MIX_LIKE_CHEST_DOMINANT", "MIX_LIKE"):
            sb_status = raw
    return {
        "effort_status": str(effort.get("level") or effort.get("status") or "UNKNOWN").upper(),
        "effort_confidence": str(effort.get("confidence_label") or ""),
        "effort_reliable": bool(effort.get("reliable_for_preserve")),
        "contact": str(contact.get("status") or "UNKNOWN").upper(),
        "breathiness": str(breath.get("level") or breath.get("status") or "UNKNOWN").upper(),
        "register_connection": reg_conn,
        # Backward-compatible alias for connection only
        "register": reg_conn,
        "stability": str(stability.get("status") or "UNKNOWN").upper(),
        "presence": _bucket_float(timbre.get("presence")),
        "brightness": _bucket_float(timbre.get("brightness")),
        "airiness": _bucket_float(timbre.get("airiness")),
        "texture": str((timbre.get("axes") or {}).get("texture") or timbre.get("texture") or "UNKNOWN"),
        "harmonic_concentration": str(
            (timbre.get("axes") or {}).get("harmonic_concentration") or "UNKNOWN"
        ),
        "source_balance": sb_status or "UNKNOWN",
        "high_note_available": bool(high.get("available") or avail.get("high_note")),
        "availability": dict(avail) if isinstance(avail, dict) else {},
    }


def fingerprint_from_axes(axes: dict[str, Any]) -> str:
    keys = (
        "effort_status",
        "contact",
        "breathiness",
        "register_connection",
        "source_balance",
        "stability",
        "presence",
        "brightness",
    )
    return "|".join(str(axes.get(k) or "?") for k in keys)


def canonical_acoustic_object(snap: dict[str, Any]) -> dict[str, Any]:
    """Concern-independent acoustic truth for hashing."""
    axes = axes_from_snap(snap)
    # Drop volatile nested objects that could include concern-derived fields
    return {
        "effort": {
            "level": axes["effort_status"],
            "confidence": axes["effort_confidence"],
            "reliable": axes["effort_reliable"],
        },
        "contact": axes["contact"],
        "breathiness": axes["breathiness"],
        "register_connection": axes["register_connection"],
        "source_balance": axes["source_balance"],
        "stability": axes["stability"],
        "presence": axes["presence"],
        "brightness": axes["brightness"],
        "airiness": axes["airiness"],
        "high_note_available": axes["high_note_available"],
        "availability": axes["availability"],
        "key_features": list(snap.get("key_features") or []),
    }


def canonical_hash(snap: dict[str, Any]) -> str:
    obj = canonical_acoustic_object(snap)
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def wrap_song(analysis: dict[str, Any]) -> dict[str, Any]:
    return wrap_song_profile_with_snapshot(analysis)


def diagnose_case(
    song_wrapped: dict[str, Any],
    *,
    concern_ids: list[str],
    timbre_goal: Any = None,
) -> dict[str, Any]:
    concerns = normalize_user_concerns([{"id": c} for c in concern_ids])
    tg = None
    if timbre_goal is not None:
        tg = normalize_timbre_goal(timbre_goal, concerns=concerns)
    qa = build_personalized_qa(
        user_concerns=concerns,
        song_profile=song_wrapped,
        task_results=[],
        fused_profile=None,
        timbre_goal=tg,
    )
    pain = has_pain_safety_flag(concerns)
    goal = plan_coaching_goal(
        user_concerns=concerns,
        timbre_goal=tg,
        concern_evaluations=qa.get("concern_evaluations") or [],
        song_profile=song_wrapped,
        pain=pain,
    )
    snap = get_canonical_snapshot(song_wrapped)
    axes = axes_from_snap(snap)
    protocol = goal.get("coaching_protocol") or {}
    entry = protocol.get("entry_step") or ((protocol.get("steps") or [{}])[0] if protocol else {})
    questions = qa.get("questions") or []
    primary_q = questions[0] if questions else {}
    presc = primary_q.get("prescription") or {}
    practices = goal.get("practices") or []
    practice_id = None
    if practices:
        practice_id = practices[0].get("practice_id") or practices[0].get("id")
    elif goal.get("practice_ids"):
        practice_id = (goal.get("practice_ids") or [None])[0]

    # Audit-only selection trace (why this focus)
    focus_selection: dict[str, Any] = {
        "selected": goal.get("primary_focus") or primary_q.get("primary_focus"),
        "reason": None,
        "candidate_factors": [],
        "evidence_available": [],
        "fallback_used": False,
    }
    for ev in qa.get("concern_evaluations") or []:
        fh = ev.get("functional_hypothesis") or {}
        reason = fh.get("focus_selection_reason") or ev.get("focus_selection_reason")
        if reason:
            focus_selection["reason"] = reason
            focus_selection["selected"] = ev.get("primary_focus") or focus_selection["selected"]
            focus_selection["fallback_used"] = reason in (
                "GENERAL_HIGH_NOTE_ACCESS",
                "SEMANTIC_FALLBACK",
            )
            evidence = fh.get("evidence") or fh.get("evidence_used") or []
            focus_selection["evidence_available"] = [
                e if isinstance(e, str) else str((e or {}).get("axis") or e) for e in evidence
            ]
            break
    if not focus_selection["reason"] and primary_q.get("primary_focus"):
        focus_selection["reason"] = "GOAL_OR_QA_FOCUS"

    return {
        "concern_ids": [c["id"] for c in concerns],
        "concern_id": (concerns[0]["id"] if concerns else None),
        "question_type": primary_q.get("question_type"),
        "canonical_hash": canonical_hash(snap),
        "canonical_fingerprint": fingerprint_from_axes(axes),
        "canonical_axes": axes,
        "qa": {
            "question": primary_q.get("question"),
            "answer": primary_q.get("answer") or qa.get("answer_summary"),
            "prescription": presc or None,
            "what_to_change": primary_q.get("what_to_change"),
            "success_cues": primary_q.get("success_cues") or (presc.get("success_cues") if presc else []),
            "questions": [
                {
                    "concern_id": q.get("concern_id"),
                    "question": q.get("question"),
                    "answer": q.get("answer"),
                    "primary_focus": q.get("primary_focus"),
                    "question_type": q.get("question_type"),
                    "prescription": q.get("prescription"),
                    "success_cues": q.get("success_cues"),
                }
                for q in questions
            ],
        },
        "primary_focus": goal.get("primary_focus") or primary_q.get("primary_focus"),
        "goal": {
            "goal_title": goal.get("goal_title"),
            "goal_description": goal.get("goal_description"),
            "primary_focus": goal.get("primary_focus"),
            "primary_focus_label": goal.get("primary_focus_label"),
            "mode": goal.get("mode"),
            "why_this_first": goal.get("why_this_first"),
            "practice_ids": goal.get("practice_ids"),
            "secondary_target": goal.get("secondary_target"),
            "supporting_factors": goal.get("supporting_factors"),
        },
        "protocol_id": protocol.get("protocol_id"),
        "protocol_entry_id": (entry or {}).get("id"),
        "protocol_entry_title": (entry or {}).get("title"),
        "protocol_instruction": (entry or {}).get("instruction"),
        "practice_id": practice_id,
        "focus_selection": focus_selection,
        "safety": {
            "pain": pain,
            "concern_ids": [c for c in concern_ids if c in PAIN_CONCERN_IDS],
        },
        "timbre_goal": (tg or {}).get("id") if isinstance(tg, dict) else tg,
        "answer_summary": qa.get("answer_summary"),
    }


def normalize_text(text: str) -> str:
    t = str(text or "").lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w가-힣\s~·]", "", t)
    return t.strip()


def coaching_fingerprint(case: dict[str, Any]) -> str:
    presc = ((case.get("qa") or {}).get("prescription") or {})
    action = presc.get("instruction") or (case.get("qa") or {}).get("what_to_change") or ""
    parts = [
        str(case.get("concern_id") or ""),
        str(case.get("question_type") or ""),
        str(case.get("primary_focus") or ""),
        str(case.get("protocol_id") or ""),
        str(case.get("practice_id") or ""),
        str(presc.get("title") or ""),
        normalize_text(action)[:240],
    ]
    return "||".join(parts)


def prescription_family(case: dict[str, Any]) -> str:
    presc = ((case.get("qa") or {}).get("prescription") or {})
    inst = str(presc.get("instruction") or (case.get("qa") or {}).get("what_to_change") or "")
    if "립트릴" in inst or "빨대" in inst:
        return "SOVT_GLIDE"
    if "자음" in inst:
        return "ARTICULATION"
    if "모음" in inst and ("연결" in inst or "이어" in inst):
        return "VOWEL_CONNECT"
    if "1~2초" in inst or "유지" in inst:
        return "SUSTAIN_HOLD"
    if "쉬" in inst or "중단" in inst or "휴식" in inst:
        return "SAFETY_REST"
    focus = str(case.get("primary_focus") or "")
    return focus or "UNKNOWN"
