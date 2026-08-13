"""Centralized vocal-type naming (v1.3) — source balance vs Mix separation."""

from __future__ import annotations

from typing import Any, Optional

from . import config as cfg
from .register_strategy import (
    classify_register_strategy,
    classify_source_balance,
    register_strategy_display,
    source_balance_display,
)


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
    """
    Legacy type_id entrypoint.

    Mix labels require positive transition evidence (see register_strategy).
    Chest/Head ratio alone never implies Mix.
    """
    strategy = classify_register_strategy(
        index=index,
        bridge=bridge,
        confidence=confidence,
        neutral_collapse=neutral_collapse,
        register_split_ok=register_split_ok,
        family_agreement=family_agreement,
        mix_coverage_ok=mix_coverage_ok,
        modifiers=modifiers,
    )
    return strategy.get("type_id") or "UNRESOLVED"


def compose_display_name(
    base_type: str,
    modifiers: list[str],
    *,
    local_events: Optional[list[dict[str, Any]]] = None,
    source_balance: Optional[dict[str, Any]] = None,
    register_strategy: Optional[dict[str, Any]] = None,
) -> str:
    """
    Main title = source balance / register strategy only.

    Firmness and effort modifiers must NOT compound into Mix titles
    (e.g. no "단단한 믹스보이스 · 힘이 함께 증가").
    """
    del local_events  # local events stay in key_traits, not global title
    del modifiers  # modifiers are separate UI axes

    if register_strategy and (register_strategy.get("status") or "").startswith("MIX_LIKE"):
        return register_strategy_display(register_strategy)["title"]

    if base_type in ("REGISTER_SPLIT", "REGISTER_SPLIT_GLOBAL"):
        return cfg.TYPE_DISPLAY["REGISTER_SPLIT_GLOBAL"]
    if base_type == "TRANSITION_UNSTABLE":
        return cfg.TYPE_DISPLAY["TRANSITION_UNSTABLE"]
    if base_type == "LIGHT_HEAD_FALSETTO_LIKE":
        return cfg.TYPE_DISPLAY["LIGHT_HEAD_FALSETTO_LIKE"]

    # Prefer source-balance wording when Mix is unresolved
    if base_type in ("BALANCED_SOURCE", "UNRESOLVED") and source_balance:
        return source_balance_display(source_balance)
    if base_type in ("CHEST_DOMINANT", "HEAD_DOMINANT") and source_balance:
        return source_balance_display(source_balance)

    if base_type in ("CHEST_DOMINANT_MIX", "BALANCED_MIX", "HEAD_DOMINANT_MIX"):
        return cfg.TYPE_DISPLAY.get(base_type, cfg.TYPE_DISPLAY["UNRESOLVED"])

    return cfg.TYPE_DISPLAY.get(base_type, cfg.TYPE_DISPLAY.get("BALANCED_SOURCE", "흉성·두성 관련 음향 성향"))


def one_line_description(
    *,
    base_type: str,
    display_name: str,
    head_chest: dict[str, Any],
    bridge: dict[str, Any],
    modifiers: list[str],
    local_events: Optional[list[dict[str, Any]]] = None,
    source_balance: Optional[dict[str, Any]] = None,
    register_strategy: Optional[dict[str, Any]] = None,
) -> str:
    chest = head_chest.get("chest_ratio")
    head = head_chest.get("head_ratio")
    local_events = local_events or []
    has_local_pull = any(e.get("type") == "LOCAL_CHEST_PULL" for e in local_events)

    if register_strategy and (register_strategy.get("status") or "").startswith("MIX_LIKE"):
        body = register_strategy_display(register_strategy)["description"]
        if has_local_pull:
            return body + " 일부 구간에서는 흉성 비중을 더 오래 유지해요."
        return body

    if base_type == "TRANSITION_UNSTABLE" or base_type in (
        "REGISTER_SPLIT",
        "REGISTER_SPLIT_GLOBAL",
    ):
        return register_strategy_display(
            {"status": "TRANSITION_UNSTABLE"}
        )["description"]

    if chest is not None and head is not None:
        bal = source_balance or classify_source_balance(head_chest.get("index"))
        bclass = (bal.get("balance_class") or "").upper()
        if bal.get("show_ratio") is False or bclass == "CONFLICTED":
            return (
                "흉성·두성 관련 음향 특징이 서로 다른 방향으로 나타났어요."
            )
        if bclass in ("BALANCED", "BALANCED_ACOUSTIC"):
            return (
                "흉성·두성 관련 음향 성향이 비교적 비슷한 비중으로 나타났어요."
            )
        if bclass in ("CHEST_DOMINANT", "CHEST_LEANING"):
            return f"전체적으로 흉성 쪽 음향 성향(약 {chest}%)이 우세하게 나타나요."
        if bclass in ("HEAD_DOMINANT", "HEAD_LEANING"):
            return f"전체적으로 두성 쪽 음향 성향(약 {head}%)이 우세하게 나타나요."

    if base_type in ("UNRESOLVED", "BALANCED_SOURCE") or chest is None:
        if chest is not None and head is not None:
            return (
                "흉성·두성 관련 음향 성향이 비교적 비슷한 비중으로 나타났어요."
            )
        return "이번 녹음에서는 발성 성향을 충분히 구분하지 못했어요."

    if base_type == "LIGHT_HEAD_FALSETTO_LIKE":
        return "가벼운 접촉의 두성 중심 발성 성향이 관찰돼요."
    if base_type == "CHEST_DOMINANT":
        return f"전체적으로 흉성 쪽 발성 성향(약 {chest}%)이 우세하게 나타나요."
    if base_type == "HEAD_DOMINANT":
        return f"전체적으로 두성 쪽 발성 성향(약 {head}%)이 우세하게 나타나요."

    # Legacy mix type_ids (when strategy not passed)
    if base_type == "CHEST_DOMINANT_MIX":
        return cfg.TYPE_DISPLAY["CHEST_DOMINANT_MIX"] + "이 관찰됐어요."
    if base_type == "HEAD_DOMINANT_MIX":
        return "중음부터 두성 비중이 비교적 빠르게 늘어나는 믹스 성향이 관찰됐어요."
    if base_type == "BALANCED_MIX":
        return (
            "음역이 올라갈 때 흉성·두성 쪽 음향 특성이 "
            "비교적 연속적으로 연결됐어요."
        )
    del modifiers
    del bridge
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
            "전체 발성 성향보다, 이번 녹음에서 가장 먼저 확인할 부분은 "
            "숨이 섞이는 경향이에요."
        )
    if pid in ("EXCESS_EFFORT_HIGH_NOTE", "GENERAL_EXCESS_EFFORT") and base_type in (
        "CHEST_DOMINANT_MIX",
        "CHEST_DOMINANT",
        "BALANCED_MIX",
        "BALANCED_SOURCE",
    ):
        return (
            "현재 핵심은 발성 성향 자체가 아니라, "
            "일부 구간에서 힘이 함께 증가하는 점이에요."
        )
    if pid == "REGISTER_TRANSITION_DISRUPTION":
        return "발성 성향보다, 성구가 바뀌는 순간의 연결을 먼저 확인해 보세요."
    del modifiers
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
        traits.append({"key": "passaggio", "label": "성구 연결", "value": "대체로 연결됨"})
    elif split_ok:
        traits.append({"key": "passaggio", "label": "성구 연결", "value": "급격한 전환 경향"})
    elif btype == "UNSTABLE_BRIDGE":
        traits.append({"key": "passaggio", "label": "성구 연결", "value": "일부 불안정"})

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
        traits.append({"key": et.lower(), "label": "특징 구간", "value": value})

    if "EXCESS_EFFORT" in modifiers and not any(
        e.get("type") == "LOCAL_EFFORT_SPIKE" for e in local_events
    ):
        traits.append({"key": "effort", "label": "힘", "value": "일부 증가"})

    if "LOW_RESONANCE_PRESENCE" in modifiers:
        traits.append({"key": "resonance", "label": "공명", "value": "중역 존재감 부족"})
    if "AIR_LEAKAGE" in modifiers:
        traits.append({"key": "breathiness", "label": "숨 섞임", "value": "일부 관찰"})

    del dimensions
    return traits[:6]
