# -*- coding: utf-8 -*-
"""Acoustic claim classification for behavioral audit (audit-only)."""

from __future__ import annotations

import re
from typing import Any, Optional


# Affirmative claim patterns → (axis, claimed_state)
CLAIM_REGISTRY: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"밝기가\s*어두운"), "brightness", "LOW"),
    (re.compile(r"어두운\s*쪽(으로|에)"), "brightness", "LOW"),
    (re.compile(r"밝기가\s*밝은"), "brightness", "HIGH"),
    (re.compile(r"숨\s*섞임이\s*(높|크|두드러)"), "breathiness", "HIGH"),
    (re.compile(r"숨이\s*많이\s*섞"), "breathiness", "HIGH"),
    (re.compile(r"숨이\s*많이\s*새"), "breathiness", "HIGH"),
    (re.compile(r"숨\s*섞임이\s*(낮|적)"), "breathiness", "LOW"),
    (re.compile(r"성구\s*연결이\s*급격"), "register", "DISRUPTED"),
    (re.compile(r"연결이\s*급격히\s*달라"), "register", "DISRUPTED"),
    (re.compile(r"전환이\s*급격"), "register", "DISRUPTED"),
    (re.compile(r"힘\s*사용이\s*(낮|작은)"), "effort", "LOW"),
    (re.compile(r"힘\s*사용이\s*(크|높|커지)"), "effort", "HIGH"),
    (re.compile(r"중역\s*존재감이\s*(낮|흐려)"), "presence", "LOW"),
    (re.compile(r"중역\s*존재감이\s*(높|분명|유지)"), "presence", "HIGH"),
]

# Negation / contrast cues → not an affirmative measurement claim
NEGATION_CUES = (
    "보이지 않",
    "두드러지지",
    "단정하기",
    "보다는",
    "어려워",
    "아니라고",
    "아닌",
    "없었어",
    "없었습니다",
    "잡히지 않았",
    "확인하기 어려",
)

# Coaching instructions — never measurement claims
INSTRUCTION_CUES = (
    "해보세요",
    "하세요",
    "키우지 않",
    "밀지 않",
    "유지하세요",
    "비교해",
    "시도해",
)


def _negated(sentence: str) -> bool:
    return any(n in sentence for n in NEGATION_CUES)


def _is_instruction(sentence: str) -> bool:
    return any(i in sentence for i in INSTRUCTION_CUES) and not any(
        k in sentence for k in ("보여요", "나타", "관찰", "편이에요", "보여 ")
    )


def classify_claim_spans(text: str) -> list[dict[str, Any]]:
    """Extract candidate acoustic claims from user-facing text."""
    t = str(text or "")
    if not t:
        return []
    # Sentence-ish split (fixed-width lookbehind only)
    parts = re.split(r"[.!?。]\s+", t)
    if len(parts) == 1:
        parts = re.split(r"(?:요\.|다\.)\s+", t)
    if len(parts) == 1:
        parts = [t]
    out: list[dict[str, Any]] = []
    for sent in parts:
        s = sent.strip()
        if not s:
            continue
        for pat, axis, state in CLAIM_REGISTRY:
            if not pat.search(s):
                continue
            if _negated(s):
                out.append(
                    {
                        "sentence": s,
                        "axis": axis,
                        "claimed_state": state,
                        "classification": "FALSE_POSITIVE_LINT",
                        "detail": "negated_or_contrast",
                    }
                )
                continue
            if _is_instruction(s):
                out.append(
                    {
                        "sentence": s,
                        "axis": axis,
                        "claimed_state": state,
                        "classification": "FALSE_POSITIVE_LINT",
                        "detail": "instruction_not_measurement",
                    }
                )
                continue
            out.append(
                {
                    "sentence": s,
                    "axis": axis,
                    "claimed_state": state,
                    "classification": "CANDIDATE",
                    "detail": pat.pattern,
                }
            )
    return out


def evaluate_claim_against_axes(
    claim: dict[str, Any],
    axes: dict[str, Any],
) -> dict[str, Any]:
    """Compare candidate claim to canonical axes."""
    axis = claim.get("axis")
    claimed = str(claim.get("claimed_state") or "").upper()
    out = dict(claim)
    if claim.get("classification") != "CANDIDATE":
        return out

    if axis == "brightness":
        avail = axes.get("brightness") not in (None, "UNAVAILABLE", "")
        val = str(axes.get("brightness") or "UNAVAILABLE").upper()
    elif axis == "breathiness":
        avail = axes.get("breathiness") not in (None, "UNKNOWN", "UNAVAILABLE", "")
        val = str(axes.get("breathiness") or "UNKNOWN").upper()
    elif axis == "register":
        # Connection only
        avail = axes.get("register_connection") not in (None, "UNKNOWN", "UNAVAILABLE", "UNRESOLVED", "")
        val = str(axes.get("register_connection") or axes.get("register") or "UNKNOWN").upper()
        # Map
        if val in ("TRANSITION_EVENTS", "TRANSITION_UNSTABLE", "UNSTABLE"):
            val = "DISRUPTED"
    elif axis == "effort":
        avail = axes.get("effort_status") not in (None, "UNKNOWN", "")
        val = str(axes.get("effort_status") or "UNKNOWN").upper()
    elif axis == "presence":
        avail = axes.get("presence") not in (None, "UNAVAILABLE", "")
        val = str(axes.get("presence") or "UNAVAILABLE").upper()
    else:
        out["classification"] = "FALSE_POSITIVE_LINT"
        out["detail"] = "unknown_axis"
        return out

    out["canonical_available"] = bool(avail)
    out["canonical_value"] = val

    if not avail:
        out["classification"] = "TRUE_POSITIVE"
        out["detail"] = f"claimed_{claimed}_but_unavailable"
        return out

    # Compatible?
    if axis == "register":
        if claimed == "DISRUPTED" and val in ("CONNECTED", "PARTIAL"):
            # Claiming disruption when connected/partial is wrong for CONNECTED;
            # PARTIAL is softer — treat CONNECTED as TP, PARTIAL as scope/soft
            if val == "CONNECTED":
                out["classification"] = "TRUE_POSITIVE"
                out["detail"] = "claimed_disrupted_but_connected"
            else:
                out["classification"] = "FALSE_POSITIVE_LINT"
                out["detail"] = "partial_not_disrupted_claim_soft"
            return out
    if claimed == val:
        out["classification"] = "FALSE_POSITIVE_LINT"
        out["detail"] = "matches_canonical"
        return out
    # Opposite buckets
    opposites = {
        ("brightness", "LOW"): {"HIGH"},
        ("brightness", "HIGH"): {"LOW"},
        ("breathiness", "HIGH"): {"LOW"},
        ("breathiness", "LOW"): {"HIGH"},
        ("effort", "LOW"): {"HIGH", "MODERATE"},
        ("effort", "HIGH"): {"LOW"},
        ("presence", "LOW"): {"HIGH"},
        ("presence", "HIGH"): {"LOW"},
    }
    if val in opposites.get((axis, claimed), set()):
        out["classification"] = "TRUE_POSITIVE"
        out["detail"] = f"claimed_{claimed}_canonical_{val}"
        return out

    out["classification"] = "FALSE_POSITIVE_LINT"
    out["detail"] = f"non_contradictory_{claimed}_vs_{val}"
    return out
