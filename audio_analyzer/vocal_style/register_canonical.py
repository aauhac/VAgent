"""Canonical register assessment — single source of truth for UI."""

from __future__ import annotations

from typing import Any, Optional


CANONICAL_STATUS = (
    "CONNECTED",
    "PARTIAL",
    "DISRUPTED",
    "CONFLICTED",
    "UNRESOLVED",
)

_DISPLAY = {
    "CONNECTED": {
        "title": "연속적으로 연결",
        "profile_label": "비교적 자연스러움",
        "description": "음역이 올라갈 때 성구 쪽 음향 특성이 비교적 연속적으로 연결됐어요.",
    },
    "PARTIAL": {
        "title": "부분적으로 연결",
        "profile_label": "보통",
        "description": "성구 연결이 일부 구간에서만 확인됐어요.",
    },
    "DISRUPTED": {
        "title": "전환이 급격한 구간",
        "profile_label": "다소 급한 편",
        "description": "음역이 올라가는 구간에서 발성 특성이 급격하게 바뀌는 패턴이 관찰됐어요.",
    },
    "CONFLICTED": {
        "title": "추가 확인 필요",
        "profile_label": "추가 확인 필요",
        "description": "성구 연결 관련 신호가 서로 다른 방향으로 나타나 이번 녹음만으로 확정하기 어려워요.",
    },
    "UNRESOLVED": {
        "title": "추가 확인 필요",
        "profile_label": "추가 확인 필요",
        "description": "이번 녹음만으로 성구 연결 방식을 충분히 확인하기 어려웠어요.",
    },
}


def _strategy_to_status(register_strategy: Optional[dict[str, Any]]) -> tuple[str, str]:
    rs = register_strategy or {}
    status = str(rs.get("status") or "").upper()
    mix = str(rs.get("mix_evidence") or "").upper()
    if status.startswith("MIX_LIKE"):
        if mix in ("SUFFICIENT", "POSITIVE", "STRONG") or mix == "":
            return "CONNECTED", "register_strategy:mix_like"
        return "PARTIAL", "register_strategy:mix_partial"
    if status in ("TRANSITION_UNSTABLE", "REGISTER_SPLIT", "REGISTER_SPLIT_GLOBAL"):
        return "DISRUPTED", f"register_strategy:{status}"
    if status in ("CHEST_DOMINANT", "HEAD_DOMINANT"):
        # Source tendency, not register connection
        return "UNRESOLVED", f"register_strategy:source_tendency:{status}"
    return "UNRESOLVED", "register_strategy:unresolved"


def _dimension_to_status(dimensions: Optional[dict[str, Any]]) -> tuple[str, str]:
    dim = (dimensions or {}).get("register_configuration") or {}
    st = str(dim.get("status") or "").upper()
    if not dim or st in ("UNKNOWN", "AMBIGUOUS", ""):
        return "UNRESOLVED", "dimension:unavailable"
    # STABLE_LIKE without positive transition evidence ≠ proven connection
    if st in ("STABLE_LIKE", "STABLE"):
        return "PARTIAL", f"dimension:{st}"
    if "SMOOTH" in st or "GOOD" in st or st == "CONNECTED":
        return "CONNECTED", f"dimension:{st}"
    if any(x in st for x in ("EVENT", "DISRUPT", "TRANSITION", "UNSTABLE", "SPLIT")):
        return "DISRUPTED", f"dimension:{st}"
    if "MIXED" in st or "PARTIAL" in st:
        return "PARTIAL", f"dimension:{st}"
    return "UNRESOLVED", f"dimension:{st}"


def _siren_to_status(controlled_siren: Optional[dict[str, Any]]) -> tuple[Optional[str], str]:
    if not controlled_siren:
        return None, "siren:absent"
    if controlled_siren.get("user_skipped") or controlled_siren.get("status") == "USER_SKIPPED":
        return None, "siren:skipped"
    st = str(controlled_siren.get("register_status") or controlled_siren.get("status") or "").upper()
    if not st or st in ("UNKNOWN", "INSUFFICIENT", "FAILED"):
        return None, "siren:insufficient"
    if st in ("CONNECTED", "SMOOTH", "STABLE", "PASS"):
        return "CONNECTED", "controlled_siren"
    if st in ("DISRUPTED", "BREAK", "UNSTABLE", "FAIL"):
        return "DISRUPTED", "controlled_siren"
    if st in ("PARTIAL", "MIXED"):
        return "PARTIAL", "controlled_siren"
    return None, f"siren:{st}"


def build_canonical_register_assessment(
    *,
    register_strategy: Optional[dict[str, Any]] = None,
    bridge: Optional[dict[str, Any]] = None,
    dimensions: Optional[dict[str, Any]] = None,
    controlled_siren: Optional[dict[str, Any]] = None,
    mode: str = "SONG_DETAIL",
) -> dict[str, Any]:
    """Authority-based register status — never blind-average conflicting evidence."""
    del bridge  # bridge already folded into register_strategy by coach_profile
    mode_u = (mode or "SONG_DETAIL").upper()
    candidates: list[tuple[int, str, str]] = []  # priority, status, provenance

    siren_status, siren_prov = _siren_to_status(controlled_siren)
    strat_status, strat_prov = _strategy_to_status(register_strategy)
    dim_status, dim_prov = _dimension_to_status(dimensions)

    if mode_u == "PRECISION":
        if siren_status:
            candidates.append((1, siren_status, siren_prov))
        if strat_status != "UNRESOLVED" and str(
            (register_strategy or {}).get("status") or ""
        ).upper().startswith("MIX_LIKE"):
            candidates.append((2, strat_status, strat_prov))
        elif strat_status == "DISRUPTED":
            candidates.append((2, strat_status, strat_prov))
        if dim_status != "UNRESOLVED":
            candidates.append((3, dim_status, dim_prov))
    else:
        if strat_status != "UNRESOLVED" and (
            str((register_strategy or {}).get("status") or "").upper().startswith("MIX_LIKE")
            or strat_status == "DISRUPTED"
        ):
            candidates.append((1, strat_status, strat_prov))
        if dim_status != "UNRESOLVED":
            candidates.append((2, dim_status, dim_prov))
        if strat_status != "UNRESOLVED" and not candidates:
            candidates.append((3, strat_status, strat_prov))

    if not candidates:
        status = "UNRESOLVED"
        provenance = ["none"]
        conflict = False
    else:
        candidates.sort(key=lambda x: x[0])
        top = candidates[0]
        status = top[1]
        provenance = [c[2] for c in candidates]
        # Conflict only when higher-authority CONNECTED-like vs DISRUPTED disagree
        statuses = {c[1] for c in candidates if c[1] != "UNRESOLVED"}
        conflict = "CONNECTED" in statuses and "DISRUPTED" in statuses
        if conflict:
            # Prefer positive transition evidence when present at priority 1
            if top[1] in ("CONNECTED", "PARTIAL") and top[0] == 1 and str(
                (register_strategy or {}).get("status") or ""
            ).upper().startswith("MIX_LIKE"):
                status = top[1]
            elif mode_u == "PRECISION" and siren_status:
                status = siren_status
            else:
                status = "CONFLICTED"

    copy = _DISPLAY.get(status, _DISPLAY["UNRESOLVED"])
    return {
        "status": status,
        "title": copy["title"],
        "description": copy["description"],
        "profile_label": copy["profile_label"],
        "confidence_label": "medium" if status not in ("UNRESOLVED", "CONFLICTED") else "low",
        "provenance": provenance,
        "mode": mode_u,
        "axis_value": status,
        "available": status != "UNRESOLVED",
    }


def apply_canonical_to_register_strategy(
    register_strategy: Optional[dict[str, Any]],
    canonical: dict[str, Any],
) -> dict[str, Any]:
    """Overwrite user-facing register_strategy fields from canonical assessment."""
    rs = dict(register_strategy or {})
    rs["canonical_status"] = canonical.get("status")
    rs["title"] = canonical.get("title")
    rs["description"] = canonical.get("description")
    rs["profile_label"] = canonical.get("profile_label")
    return rs
