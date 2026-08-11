"""Centralized vocal-type naming (v1.2) — global type vs local modifiers."""

from __future__ import annotations

from typing import Any, Optional

from . import config as cfg


def classify_base_type(
    *,
    index: Optional[float],
    bridge: dict[str, Any],
    modifiers: list[str],
    confidence: str,
    neutral_collapse: bool = False,
    register_split_ok: Optional[bool] = None,
    family_agreement: float = 1.0,
    mix_coverage_ok: bool = True,
) -> str:
    if index is None or confidence == "low":
        return "UNRESOLVED"

    btype = (bridge.get("type") or "UNDETERMINED").upper()
    score = bridge.get("score")
    split_gate = bridge.get("split_eligibility") or {}
    if register_split_ok is None:
        register_split_ok = bool(split_gate.get("eligible"))

    # Only global split eligibility can produce REGISTER_SPLIT_GLOBAL
    if register_split_ok and btype == "ABRUPT_REGISTER_BREAK":
        return "REGISTER_SPLIT_GLOBAL"

    if neutral_collapse:
        return "UNRESOLVED"

    # CHEST_PULL is NEVER a global type driver — handled as local events
    chest_heavy = index <= cfg.CHEST_DOMINANT_MAX
    head_heavy = index >= cfg.HEAD_DOMINANT_MIN
    mid = cfg.MIX_LOW <= index <= cfg.MIX_HIGH
    smooth = btype == "SMOOTH_BRIDGE" or (
        score is not None and float(score) >= cfg.BRIDGE_SMOOTH_MIN
    )
    # Mostly continuous transitions also count as mix-capable
    prev = float(split_gate.get("break_prevalence") or 0)
    mostly_continuous = (not register_split_ok) and (
        smooth or prev < cfg.REGISTER_SPLIT_MIN_PREVALENCE * 0.75 or btype == "UNSTABLE_BRIDGE"
    )

    if "WEAK_CONTACT" in modifiers and head_heavy and family_agreement >= 0.5:
        return "LIGHT_HEAD_FALSETTO_LIKE"

    if chest_heavy:
        if mostly_continuous and mix_coverage_ok:
            return "CHEST_DOMINANT_MIX"
        return "CHEST_DOMINANT"
    if head_heavy:
        if mostly_continuous and mix_coverage_ok:
            return "HEAD_DOMINANT_MIX"
        return "HEAD_DOMINANT"
    if mid:
        # Balanced Mix hardening: need coherence + bridge evidence, not ratio alone
        if mostly_continuous and mix_coverage_ok:
            if 0.45 <= index <= 0.55:
                if family_agreement >= 0.45 and (
                    smooth or score is not None and float(score) >= 0.45
                ):
                    return "BALANCED_MIX"
                return "UNRESOLVED" if family_agreement < 0.35 else "BALANCED_MIX"
            if index < cfg.CHEST_LEAN_MAX:
                return "CHEST_DOMINANT_MIX"
            if index > cfg.HEAD_LEAN_MIN:
                return "HEAD_DOMINANT_MIX"
            return "BALANCED_MIX" if family_agreement >= 0.4 else "UNRESOLVED"
        # Mid + not continuous — NOT automatic REGISTER_SPLIT
        if register_split_ok:
            return "REGISTER_SPLIT_GLOBAL"
        if index < cfg.CHEST_LEAN_MAX:
            return "CHEST_DOMINANT_MIX"
        if index > cfg.HEAD_LEAN_MIN:
            return "HEAD_DOMINANT_MIX"
        return "UNRESOLVED"

    return "UNRESOLVED"


def compose_display_name(
    base_type: str,
    modifiers: list[str],
    *,
    local_events: Optional[list[dict[str, Any]]] = None,
) -> str:
    """Global naming — local CHEST_PULL must NOT rename the whole singer."""
    local_events = local_events or []
    # REGISTER_SPLIT_GLOBAL only
    if base_type in ("REGISTER_SPLIT", "REGISTER_SPLIT_GLOBAL"):
        return cfg.TYPE_DISPLAY["REGISTER_SPLIT_GLOBAL"]

    if base_type == "LIGHT_HEAD_FALSETTO_LIKE":
        return cfg.TYPE_DISPLAY["LIGHT_HEAD_FALSETTO_LIKE"]

    base = cfg.TYPE_DISPLAY.get(base_type, cfg.TYPE_DISPLAY["UNRESOLVED"])

    # Soft contact wording on mix types only
    if base_type in ("CHEST_DOMINANT_MIX", "BALANCED_MIX", "HEAD_DOMINANT_MIX"):
        if "WEAK_CONTACT" in modifiers:
            if base_type == "HEAD_DOMINANT_MIX":
                return "접촉이 가벼운 두성 우세 믹스보이스"
            return "접촉이 가벼운 믹스보이스"
        if "FIRM_CONTACT" in modifiers and "EXCESS_EFFORT" in modifiers:
            return "단단한 믹스보이스 · 힘이 함께 증가"
        if "FIRM_CONTACT" in modifiers:
            return "단단한 접촉의 믹스보이스"

    return base


def one_line_description(
    *,
    base_type: str,
    display_name: str,
    head_chest: dict[str, Any],
    bridge: dict[str, Any],
    modifiers: list[str],
    local_events: Optional[list[dict[str, Any]]] = None,
) -> str:
    chest = head_chest.get("chest_ratio")
    head = head_chest.get("head_ratio")
    local_events = local_events or []
    has_local_pull = any(e.get("type") == "LOCAL_CHEST_PULL" for e in local_events)

    if base_type == "UNRESOLVED" or chest is None:
        return "이번 녹음에서는 발성 타입을 충분히 구분하지 못했어요."

    if base_type in ("REGISTER_SPLIT", "REGISTER_SPLIT_GLOBAL"):
        return "흉성·두성 쪽 발성 성향이 전환에서 비교적 분리되어 나타나요."
    if base_type == "CHEST_DOMINANT_MIX":
        base = (
            "중·고음에서도 흉성 비중이 비교적 강하게 유지되면서 "
            "믹스 형태로 연결되는 발성입니다."
        )
        if has_local_pull:
            return base + " 일부 구간에서는 흉성 비중을 더 오래 유지해요."
        return base
    if base_type == "HEAD_DOMINANT_MIX":
        if "WEAK_CONTACT" in modifiers:
            return (
                "성구 연결은 믹스 형태로 이어지지만, "
                "접촉이 비교적 가벼워 일부 구간에서 소리 중심이 약해지는 경향이 있어요."
            )
        return "중음부터 두성 비중이 비교적 빠르게 늘어나는 믹스보이스입니다."
    if base_type == "BALANCED_MIX":
        base = "흉성과 두성 쪽 발성 성향을 비교적 균형 있게 연결하는 믹스보이스입니다."
        if has_local_pull:
            return base + " 일부 고음에서는 흉성 비중을 오래 유지하는 구간이 있어요."
        return base
    if base_type == "CHEST_DOMINANT":
        return f"전체적으로 흉성 쪽 발성 성향(약 {chest}%)이 우세하게 나타나요."
    if base_type == "HEAD_DOMINANT":
        return f"전체적으로 두성 쪽 발성 성향(약 {head}%)이 우세하게 나타나요."
    if base_type == "LIGHT_HEAD_FALSETTO_LIKE":
        return "가벼운 접촉의 두성 중심 발성 성향이 관찰돼요."
    return display_name


def coaching_link_sentence(
    *,
    base_type: str,
    primary: Optional[dict[str, Any]],
    modifiers: list[str],
) -> Optional[str]:
    if not primary:
        return None
    pid = primary.get("id") or ""
    if pid == "AIR_LEAKAGE":
        return (
            "전체 발성 타입보다, 이번 녹음에서 가장 먼저 확인할 부분은 "
            "기식성 증가입니다."
        )
    if pid == "EXCESS_EFFORT_HIGH_NOTE" and base_type in (
        "CHEST_DOMINANT_MIX",
        "CHEST_DOMINANT",
        "BALANCED_MIX",
    ):
        return (
            "현재 핵심은 발성 타입 자체가 아니라, "
            "고음에서 힘이 함께 증가하는 점이에요."
        )
    if pid == "REGISTER_TRANSITION_DISRUPTION":
        return "발성 타입보다, 성구가 바뀌는 순간의 연결 안정성을 먼저 다듬어 보세요."
    return None


def key_traits(
    *,
    modifiers: list[str],
    bridge: dict[str, Any],
    dimensions: dict[str, Any],
    local_events: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, str]]:
    traits: list[dict[str, str]] = []
    local_events = local_events or []

    if "FIRM_CONTACT" in modifiers:
        traits.append({"key": "contact", "label": "접촉", "value": "단단한 편"})
    elif "WEAK_CONTACT" in modifiers:
        traits.append({"key": "contact", "label": "접촉", "value": "가벼운 편"})

    btype = (bridge.get("type") or "").upper()
    split_ok = bool((bridge.get("split_eligibility") or {}).get("eligible"))
    if btype == "SMOOTH_BRIDGE" or ("GOOD_BRIDGE" in modifiers and not split_ok):
        traits.append({"key": "passaggio", "label": "파사지오", "value": "대체로 연결됨"})
    elif split_ok:
        traits.append({"key": "passaggio", "label": "파사지오", "value": "분리·단절 경향"})
    elif btype == "UNSTABLE_BRIDGE":
        traits.append({"key": "passaggio", "label": "파사지오", "value": "일부 불안정"})

    for ev in local_events:
        et = ev.get("type")
        label = cfg.LOCAL_EVENT_DISPLAY.get(et or "", "")
        if not label:
            continue
        t0 = ev.get("start_sec")
        t1 = ev.get("end_sec")
        if t0 is not None and t1 is not None:
            value = f"{float(t0):.0f}–{float(t1):.0f}초 · {label}"
        else:
            value = label
        traits.append({"key": et.lower(), "label": "국소 구간", "value": value})

    if "EXCESS_EFFORT" in modifiers and not any(
        e.get("type") == "LOCAL_EFFORT_SPIKE" for e in local_events
    ):
        traits.append({"key": "effort", "label": "고음 effort", "value": "일부 증가"})

    if "LOW_RESONANCE_PRESENCE" in modifiers:
        traits.append({"key": "resonance", "label": "공명", "value": "중역 존재감 부족"})
    if "AIR_LEAKAGE" in modifiers:
        traits.append({"key": "breathiness", "label": "기식성", "value": "일부 관찰"})

    return traits[:6]
