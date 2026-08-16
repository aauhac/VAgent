# -*- coding: utf-8 -*-
"""User-facing vocal goal catalog — reuses coaching primitive focus IDs (no new ontology)."""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.diagnostic.coaching_primitives import COACHING_PRIMITIVES
from audio_analyzer.diagnostic.goal_planner import FOCUS_LABELS
from audio_analyzer.diagnostic.timbre_goals import TARGET_TIMBRE_OPTIONS

# Sources (product convention)
SOURCE_USER_SELECTED = "USER_SELECTED"
SOURCE_CONCERN_DERIVED = "CONCERN_DERIVED"
SOURCE_COACHING_GOAL = "COACHING_GOAL"
SOURCE_RECOMMENDED = "RECOMMENDED"

GOAL_STATUSES = ("ACTIVE", "COMPLETED", "PAUSED", "REPLACED")

# Functional focuses: can show goal-aligned improvement with reliable evidence
FUNCTIONAL_FOCUSES = frozenset(
    {
        "REGISTER_CONNECTION",
        "HIGH_NOTE_ACCESS",
        "STABILITY",
        "PITCH_STABILITY",
        "PHRASE_ENDURANCE",
        "VIBRATO_CONTROL",
    }
)

# Style/descriptive: only with explicit target direction
STYLE_FOCUSES = frozenset(
    {
        "BRIGHTNESS",
        "TIMBRE_STYLE",
        "TIMBRE",
        "STYLE",
        "PRESENCE",
        "CONTACT",
        "BREATHINESS",
        "SOURCE_BALANCE",
    }
)

# Effort: only with explicit reduce-excessive intent
EFFORT_FOCUSES = frozenset({"EFFORT"})

# Never gamified
EXCLUDED_FOCUSES = frozenset({"SAFETY", "MAINTAIN"})

# User-selectable catalog entries (compact Result/Home selector)
USER_GOAL_OPTIONS: list[dict[str, Any]] = [
    {
        "focus": "REGISTER_CONNECTION",
        "label": "고음 구간을 더 안정적으로 연결하기",
        "axis": "register_connection",
        "kind": "FUNCTIONAL",
        "target": "CONNECTED",
    },
    {
        "focus": "EFFORT",
        "label": "힘을 덜 밀어붙이고 편하게 내기",
        "axis": "effort",
        "kind": "EFFORT_REDUCE",
        "target": "LOWER",
    },
    {
        "focus": "STABILITY",
        "label": "음높이 흔들림 줄이기",
        "axis": "stability",
        "kind": "FUNCTIONAL",
        "target": "STABLE",
    },
    {
        "focus": "PITCH_STABILITY",
        "label": "짧은 구간에서 음정 더 안정적으로 유지하기",
        "axis": "stability",
        "kind": "FUNCTIONAL",
        "target": "STABLE",
    },
    {
        "focus": "BREATHINESS",
        "label": "숨이 많이 섞이는 느낌 줄이기",
        "axis": "breathiness",
        "kind": "EXPLICIT_DIRECTION",
        "target": "LOWER",
    },
    {
        "focus": "PHRASE_ENDURANCE",
        "label": "긴 구절을 더 안정적으로 이어가기",
        "axis": "stability",
        "kind": "FUNCTIONAL",
        "target": "STABLE",
    },
    {
        "focus": "BRIGHTNESS",
        "label": "더 밝고 선명한 음색",
        "axis": "brightness",
        "kind": "STYLE",
        "target": "HIGHER",
        "style_id": "BRIGHT_CLEAR",
        "wording": "STYLE_DIRECTION",
    },
    {
        "focus": "TIMBRE_STYLE",
        "label": "더 부드럽고 감미로운 음색",
        "axis": "brightness",
        "kind": "STYLE",
        "target": "LOWER",
        "style_id": "SOFT_SWEET",
        "wording": "STYLE_DIRECTION",
    },
]


def option_for_focus(focus: str, *, style_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    focus_u = str(focus or "").upper()
    for opt in USER_GOAL_OPTIONS:
        if opt["focus"] != focus_u:
            continue
        if style_id and opt.get("style_id") and opt["style_id"] != style_id:
            continue
        return dict(opt)
    # fallback from coaching primitive
    prim = COACHING_PRIMITIVES.get(focus_u)
    if prim:
        return {
            "focus": focus_u,
            "label": prim.get("goal") or FOCUS_LABELS.get(focus_u, focus_u),
            "axis": _default_axis(focus_u),
            "kind": _kind_for(focus_u),
            "target": None,
        }
    return None


def _default_axis(focus: str) -> str:
    mapping = {
        "REGISTER_CONNECTION": "register_connection",
        "HIGH_NOTE_ACCESS": "register_connection",
        "EFFORT": "effort",
        "STABILITY": "stability",
        "PITCH_STABILITY": "stability",
        "BREATHINESS": "breathiness",
        "CONTACT": "contact",
        "PRESENCE": "presence",
        "BRIGHTNESS": "brightness",
        "TIMBRE_STYLE": "brightness",
        "TIMBRE": "brightness",
        "STYLE": "brightness",
        "PHRASE_ENDURANCE": "stability",
        "VIBRATO_CONTROL": "stability",
        "SOURCE_BALANCE": "source_balance",
    }
    return mapping.get(focus, "register_connection")


def _kind_for(focus: str) -> str:
    if focus in EXCLUDED_FOCUSES:
        return "EXCLUDED"
    if focus in FUNCTIONAL_FOCUSES:
        return "FUNCTIONAL"
    if focus in EFFORT_FOCUSES:
        return "EFFORT_REDUCE"
    if focus in STYLE_FOCUSES:
        return "STYLE"
    return "OTHER"


def list_user_goal_catalog() -> list[dict[str, Any]]:
    """Compact selector options — only focuses we can evidence-evaluate."""
    out = []
    for opt in USER_GOAL_OPTIONS:
        if opt["focus"] in EXCLUDED_FOCUSES:
            continue
        out.append(
            {
                "focus": opt["focus"],
                "label": opt["label"],
                "kind": opt["kind"],
                "axis": opt["axis"],
                "target": opt.get("target"),
                "style_id": opt.get("style_id"),
                "primary_focus_label": FOCUS_LABELS.get(opt["focus"], opt["focus"]),
            }
        )
    return out


def list_style_timbre_options() -> list[dict[str, Any]]:
    return [
        {"id": o["id"], "label": o["label"], "description": o.get("description")}
        for o in TARGET_TIMBRE_OPTIONS
        if o["id"] != "RECOMMEND_FOR_ME"
    ]


def normalize_goal_payload(raw: Any) -> Optional[dict[str, Any]]:
    """Accept focus string / coaching goal dict / catalog option → normalized goal dict."""
    if raw is None:
        return None
    if isinstance(raw, str):
        opt = option_for_focus(raw)
        if not opt:
            return {"focus": raw.upper(), "label": FOCUS_LABELS.get(raw.upper(), raw), "kind": _kind_for(raw.upper())}
        return opt
    if isinstance(raw, dict):
        focus = str(raw.get("focus") or raw.get("primary_focus") or raw.get("goal_focus") or "").upper()
        if not focus:
            return None
        opt = option_for_focus(focus, style_id=raw.get("style_id") or raw.get("target_style"))
        label = (
            raw.get("label")
            or raw.get("goal_label")
            or raw.get("primary_focus_label")
            or (opt or {}).get("label")
            or FOCUS_LABELS.get(focus, focus)
        )
        return {
            "focus": focus,
            "label": label,
            "kind": raw.get("kind") or (opt or {}).get("kind") or _kind_for(focus),
            "axis": raw.get("axis") or (opt or {}).get("axis") or _default_axis(focus),
            "target": raw.get("target") or (opt or {}).get("target"),
            "style_id": raw.get("style_id") or (opt or {}).get("style_id"),
            "source": raw.get("source") or SOURCE_USER_SELECTED,
            "wording": raw.get("wording") or (opt or {}).get("wording"),
        }
    return None
