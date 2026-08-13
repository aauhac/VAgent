"""
diagnostic/protocol.py
----------------------
Standardized Vocal Diagnostic Protocol v1.1 (adaptive).
"""

from __future__ import annotations

from audio_analyzer.diagnostic.task_registry import PROTOCOL_VERSION
from audio_analyzer.physiology.config import PROTOCOL_VERSION as _PHYS_PROTOCOL

VOCAL_DIAGNOSTIC_PROTOCOL_VERSION = PROTOCOL_VERSION or _PHYS_PROTOCOL

TASKS = [
    {
        "task_id": "sustain_a",
        "order": 1,
        "title": "지속음 '아—'",
        "why": "노래 멜로디 영향을 줄이고 안정적인 발성 상태를 관찰해요.",
        "instruction": "가장 편한 음높이에서 '아—'를 4~5초 동안 편하게 유지해 주세요.",
        "target_sec": 4.5,
        "min_sec": 3.0,
        "max_attempts": 2,
        "observer": "sustained",
        "purpose_labels": ["접촉감", "숨 섞임"],
    },
    {
        "task_id": "sustain_i",
        "order": 2,
        "title": "지속음 '이—'",
        "why": "모음이 바뀌어도 발성·스펙트럼이 어떻게 유지되는지 봐요.",
        "instruction": "같은 편한 음높이에서 '이—'를 4~5초 동안 편하게 유지해 주세요.",
        "target_sec": 4.5,
        "min_sec": 3.0,
        "max_attempts": 2,
        "observer": "sustained",
        "purpose_labels": ["접촉감", "공명"],
    },
    {
        "task_id": "siren",
        "order": 3,
        "title": "사이렌",
        "why": "음높이가 바뀔 때 발성이 끊기지 않고 이어지는지 관찰해요.",
        "instruction": (
            "편한 낮은 음에서 시작해 무리하지 않는 범위까지 부드럽게 올라갔다가 "
            "다시 내려와 주세요. 더 높은 음을 목표로 하지 않아도 됩니다."
        ),
        "target_sec": 6.0,
        "min_sec": 4.0,
        "max_attempts": 2,
        "observer": "siren",
        "purpose_labels": ["성구 연결"],
    },
    {
        "task_id": "dynamic_swell",
        "order": 4,
        "title": "강약 스웰",
        "why": "숨과 발성 강도가 함께 바뀌는지 관찰해요. 클수록 점수가 높지 않아요.",
        "instruction": (
            "가장 편한 한 음에서 작게 시작해서 조금 크게 만들고 "
            "다시 편하게 작게 줄여 주세요. 약 5초."
        ),
        "target_sec": 5.0,
        "min_sec": 3.5,
        "max_attempts": 2,
        "observer": "swell",
        "purpose_labels": ["힘 사용", "강약 반응"],
    },
    {
        "task_id": "high_note_sustain_a",
        "order": 5,
        "title": "높은 음 '아—'",
        "why": "높은 음에서 힘·숨 섞임·안정이 어떻게 바뀌는지 관찰해요.",
        "instruction": (
            "무리하지 않는 범위에서 평소보다 높은 음으로 '아—'를 3~4초 유지해 주세요. "
            "통증·불편이 있으면 바로 멈추세요."
        ),
        "target_sec": 3.5,
        "min_sec": 2.5,
        "max_attempts": 2,
        "observer": "sustained",
        "purpose_labels": ["고음 힘", "고음 숨 섞임", "고음 안정"],
        "safety_note": "통증·불편·목소리 이상이 느껴지면 즉시 중단하세요.",
    },
]

SAFETY_QUESTIONS = [
    {"id": "pain_on_phonation", "label": "소리를 낼 때 통증이 있어요"},
    {"id": "severe_discomfort_after", "label": "발성 후 심한 불편감·피로감이 있어요"},
    {"id": "sudden_voice_change", "label": "갑자기 생긴 뚜렷한 음성 변화"},
    {"id": "persistent_severe_hoarseness", "label": "오랫동안 지속되는 심한 쉰 목소리"},
    {"id": "breathing_difficulty", "label": "호흡이 어려운 증상"},
]


def get_task(task_id: str) -> dict:
    for t in TASKS:
        if t["task_id"] == task_id:
            return dict(t)
    # Registry-backed fallback so planner IDs never silently vanish from task_plan
    from audio_analyzer.diagnostic.task_registry import TASK_REGISTRY

    meta = TASK_REGISTRY.get(task_id)
    if not meta:
        raise KeyError(task_id)
    return {
        "task_id": task_id,
        "order": 99,
        "title": str(meta.get("title") or task_id),
        "why": str(meta.get("why") or "추가 녹음으로 발성 특성을 확인해요."),
        "instruction": str(
            meta.get("user_prompt")
            or meta.get("instruction")
            or "안내된 대로 짧게 녹음해 주세요."
        ),
        "target_sec": float(meta.get("target_sec") or 4.0),
        "min_sec": float(meta.get("min_sec") or 2.5),
        "max_attempts": int(meta.get("max_attempts") or 2),
        "observer": str(meta.get("observer") or "sustained"),
        "purpose_labels": list(meta.get("purpose_labels") or []),
        "safety_note": meta.get("safety_note"),
    }


def tasks_for_ids(task_ids: list[str]) -> list[dict]:
    """Resolve UI metadata for planned IDs. Known registry tasks must not be dropped."""
    out: list[dict] = []
    for tid in task_ids:
        try:
            out.append(get_task(tid))
        except KeyError:
            # Unknown id — skip but keep others; caller/tests assert catalog coverage
            continue
    return out


def unresolved_task_ids(task_ids: list[str]) -> list[str]:
    missing: list[str] = []
    for tid in task_ids:
        try:
            get_task(tid)
        except KeyError:
            missing.append(tid)
    return missing
