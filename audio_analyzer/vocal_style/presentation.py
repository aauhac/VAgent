"""User-facing copy helpers for Vocal Style Profile (thin layer)."""

from __future__ import annotations

from typing import Any


def style_eyebrow() -> str:
    return "내 발성 스타일"


def source_balance_eyebrow() -> str:
    return "흉성·두성 관련 음향 성향"


def ratio_disclaimer() -> str:
    return "음향 성향 참고값이며, 실제 성구 사용 시간 비율이 아니에요."


def conflicted_balance_copy() -> str:
    return "여러 음향 특징이 서로 다른 방향으로 나타났어요."


def public_style_card(style: dict[str, Any] | None) -> dict[str, Any]:
    if not style or not style.get("available", True):
        return {
            "eyebrow": style_eyebrow(),
            "title": "이번 노래에서 확인된 발성 특징",
            "description": "",
            "traits": [],
        }
    return {
        "eyebrow": style_eyebrow(),
        "title": style.get("display_name"),
        "description": style.get("description"),
        "traits": style.get("primary_traits") or [],
        "source_balance": style.get("source_balance_presentation"),
        "register": style.get("canonical_register"),
    }
