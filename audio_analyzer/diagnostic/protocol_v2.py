"""
Diagnostic Protocol v2 — adaptive battery schema.

Core 4 tasks first; additional tasks only when evidence is insufficient.
Full 9-task UX is NOT forced on users.
"""

from __future__ import annotations

from typing import Any, Optional

PROTOCOL_V2_VERSION = "diagnostic-protocol-v2.0"

CORE_TASKS = [
    {
        "task_id": "sustain_a_comfortable",
        "title": "편한 '아' 지속음",
        "observer": "sustained",
        "intensity": "comfortable",
        "vowel": "a",
        "core": True,
    },
    {
        "task_id": "sustain_i_comfortable",
        "title": "편한 '이' 지속음",
        "observer": "sustained",
        "intensity": "comfortable",
        "vowel": "i",
        "core": True,
    },
    {
        "task_id": "siren",
        "title": "사이렌",
        "observer": "siren",
        "core": True,
    },
    {
        "task_id": "messa_di_voce",
        "title": "메사 디 보체(짧게)",
        "observer": "swell",
        "core": True,
    },
]

OPTIONAL_TASKS = [
    {"task_id": "speech_baseline", "title": "편한 말소리", "observer": "speech", "core": False},
    {"task_id": "sustain_u_comfortable", "title": "편한 '우'", "observer": "sustained", "core": False},
    {"task_id": "sustain_a_soft", "title": "작은 '아'", "observer": "sustained", "intensity": "soft", "core": False},
    {"task_id": "sustain_a_strong", "title": "조금 강한 '아'", "observer": "sustained", "intensity": "strong", "core": False},
    {"task_id": "five_tone", "title": "5음 스케일", "observer": "scale", "core": False},
    {"task_id": "staccato", "title": "스타카토 onset", "observer": "staccato", "core": False},
    {"task_id": "vibrato_sustain", "title": "비브라토 지속(선택)", "observer": "vibrato", "core": False},
    {"task_id": "song_phrase", "title": "노래 한 구절", "observer": "phrase", "core": False},
]


def select_adaptive_tasks(
    song_function_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Active measurement: pick optional tasks that reduce uncertainty."""
    song_function_profile = song_function_profile or {}
    dims = song_function_profile.get("dimensions") or {}
    extra = []
    effort = (dims.get("vocal_effort_strain") or {}).get("status")
    if effort in ("OCCASIONAL", "MODERATE", "REPEATED", "UNKNOWN"):
        extra.append("sustain_a_strong")
        extra.append("siren")  # already core — keep as reinforcement note
    leak = (dims.get("air_leakage_breathiness") or {}).get("status")
    if leak in ("OCCASIONAL", "MODERATE", "HIGH", "UNKNOWN"):
        extra.append("sustain_a_soft")
    reg = (dims.get("register_configuration") or {}).get("status")
    if reg in ("TRANSITION_EVENTS", "UNKNOWN"):
        extra.append("five_tone")
    onset = (dims.get("onset_offset_coordination") or {}).get("status")
    if onset in ("ABRUPT_LIKE", "UNKNOWN"):
        extra.append("staccato")

    # Dedup while preserving order; never expand to full 9 by default
    seen = set()
    optional = []
    for tid in extra:
        if tid in seen:
            continue
        seen.add(tid)
        for t in OPTIONAL_TASKS:
            if t["task_id"] == tid:
                optional.append(t)
                break
    return {
        "protocol_version": PROTOCOL_V2_VERSION,
        "core_tasks": CORE_TASKS,
        "optional_tasks": optional[:3],
        "max_forced_tasks": 4,
        "philosophy": "adaptive_vocal_examination",
        "note": "Diagnostic rules remain independent of Song bias; Song only selects tasks.",
    }
