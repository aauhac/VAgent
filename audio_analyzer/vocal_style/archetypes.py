"""Archetype definitions for Vocal Style Profile v1."""

from __future__ import annotations

from typing import Any

VOCAL_STYLE_VERSION = "vocal-style-v1.0"

ARCHETYPES: dict[str, dict[str, Any]] = {
    "FIRM_HIGH_EFFORT": {
        "display_name": "힘과 접촉이 강하게 나타나는 발성형",
        "description": (
            "이번 노래에서는 접촉감이 단단하고 "
            "힘 사용이 크게 나타나는 구간이 두드러졌어요."
        ),
        "priority": 10,
    },
    "EASY_CONNECTED": {
        "display_name": "편안하고 연결이 좋은 발성형",
        "description": (
            "이번 노래에서는 힘 사용이 비교적 낮고 "
            "성구 연결이 부드럽게 이어지는 편으로 보여요."
        ),
        "priority": 20,
    },
    "STABLE_CONNECTED": {
        "display_name": "안정적인 연결 발성형",
        "description": (
            "이번 노래에서는 발성 안정성이 유지되고 "
            "성구 연결이 비교적 자연스러운 편으로 보여요."
        ),
        "priority": 30,
    },
    "LIGHT_AIRY": {
        "display_name": "가볍고 공기감 있는 발성형",
        "description": (
            "이번 노래에서는 접촉감이 가볍고 "
            "숨 섞임이 함께 나타나는 편으로 보여요."
        ),
        "priority": 40,
    },
    "LIGHT_CLEAR": {
        "display_name": "가볍고 선명한 발성형",
        "description": (
            "이번 노래에서는 접촉감이 가벼운 편이며 "
            "숨 섞임은 적고 존재감이 유지되는 쪽으로 보여요."
        ),
        "priority": 50,
    },
    "BRIGHT_PRESENT": {
        "display_name": "선명한 존재감이 두드러지는 발성형",
        "description": (
            "이번 노래에서는 밝기와 중역 존재감이 "
            "비교적 두드러지는 편으로 보여요."
        ),
        "priority": 60,
    },
    "CHEST_DRIVEN": {
        "display_name": "흉성 쪽 음향 성향이 두드러지는 발성형",
        "description": (
            "이번 노래에서는 흉성 쪽 음향 성향이 "
            "비교적 분명히 나타났어요."
        ),
        "priority": 80,
    },
    "HEAD_DRIVEN": {
        "display_name": "두성 쪽 음향 성향이 두드러지는 발성형",
        "description": (
            "이번 노래에서는 두성 쪽 음향 성향이 "
            "비교적 분명히 나타났어요."
        ),
        "priority": 90,
    },
    "COMPOSITE_DESCRIPTIVE": {
        "display_name": "이번 노래에서 확인된 발성 스타일",
        "description": "이번 노래에서 확인된 발성 경향을 조합해 설명해요.",
        "priority": 100,
    },
    "UNRESOLVED": {
        "display_name": "이번 노래에서 확인된 발성 특징",
        "description": (
            "이번 노래에서는 발성 스타일을 충분히 정리하기 어려웠어요."
        ),
        "priority": 999,
    },
}
