"""User-facing vocal-type copy. Engine may keep raw UNRESOLVED labels internally."""

from __future__ import annotations

from typing import Any

INTERNAL_UNRESOLVED_LABEL = "발성 성향 판단 보류"

UNRESOLVED_PUBLIC_COPY: dict[str, dict[str, str]] = {
    "INSUFFICIENT_EVIDENCE": {
        "title": "이번 녹음에서는 발성 성향을 충분히 구분하기 어려웠어요.",
        "description": "분석 가능한 발성 구간이 더 필요해요.",
    },
    "CONFLICTED_EVIDENCE": {
        "title": "이번 녹음에서는 발성 성향을 한쪽으로 단정하기 어려웠어요.",
        "description": "여러 음향 특징이 서로 다른 방향으로 나타났어요.",
    },
    "NEUTRAL_EVIDENCE": {
        "title": "이번 녹음에서는 한쪽으로 치우친 발성 성향이 뚜렷하지 않았어요.",
        "description": "흉성·두성 관련 특징이 비교적 비슷하게 나타났어요.",
    },
}


def normalize_resolution_state(
    *,
    resolution_state: str | None = None,
    base_type: str | None = None,
    type_id: str | None = None,
    available: bool | None = None,
    display_name: str | None = None,
) -> str:
    state = str(resolution_state or "").strip().upper()
    if state in UNRESOLVED_PUBLIC_COPY or state == "RESOLVED":
        return state
    base = str(base_type or type_id or "").strip().upper()
    name = str(display_name or "")
    if available is False or base == "UNRESOLVED" or INTERNAL_UNRESOLVED_LABEL in name:
        return "INSUFFICIENT_EVIDENCE"
    if not state:
        # Legacy history rows may only store display_name without resolution flags.
        return "RESOLVED"
    return state


def unresolved_public_copy(resolution_state: str | None) -> dict[str, str]:
    state = normalize_resolution_state(resolution_state=resolution_state)
    return dict(UNRESOLVED_PUBLIC_COPY.get(state) or UNRESOLVED_PUBLIC_COPY["INSUFFICIENT_EVIDENCE"])


def apply_public_vocal_type_copy(payload: dict[str, Any]) -> dict[str, Any]:
    """Rewrite display_name/description for public payloads. Mutates and returns payload."""
    if not isinstance(payload, dict):
        return payload
    state = normalize_resolution_state(
        resolution_state=payload.get("resolution_state"),
        base_type=payload.get("base_type"),
        type_id=payload.get("type_id"),
        available=payload.get("available"),
        display_name=payload.get("display_name"),
    )
    payload["resolution_state"] = state
    if state == "RESOLVED":
        name = str(payload.get("display_name") or "")
        if INTERNAL_UNRESOLVED_LABEL in name:
            # Defensive: never leak internal label even if state says resolved.
            copy = unresolved_public_copy("INSUFFICIENT_EVIDENCE")
            payload["resolution_state"] = "INSUFFICIENT_EVIDENCE"
            payload["display_name"] = copy["title"]
            payload["description"] = copy["description"]
        return payload
    copy = unresolved_public_copy(state)
    payload["display_name"] = copy["title"]
    payload["description"] = copy["description"]
    return payload


def public_vocal_type_label(
    *,
    resolution_state: str | None = None,
    display_name: str | None = None,
    base_type: str | None = None,
    type_id: str | None = None,
    available: bool | None = None,
) -> str | None:
    state = normalize_resolution_state(
        resolution_state=resolution_state,
        base_type=base_type,
        type_id=type_id,
        available=available,
        display_name=display_name,
    )
    if state != "RESOLVED":
        return unresolved_public_copy(state)["title"]
    name = str(display_name or "").strip()
    if not name or INTERNAL_UNRESOLVED_LABEL in name:
        return unresolved_public_copy("INSUFFICIENT_EVIDENCE")["title"]
    return name
