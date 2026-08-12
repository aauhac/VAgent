"""v2.13 — source balance vs register strategy (Mix) separation.

Chest/Head ratio is NEVER sufficient for Mix classification.
Mix-like labels require positive transition/continuity evidence.
"""

from __future__ import annotations

from typing import Any, Optional

from . import config as cfg


SOURCE_BALANCE = (
    "UNKNOWN",
    "CHEST_DOMINANT",
    "BALANCED",
    "HEAD_DOMINANT",
)

REGISTER_STRATEGY = (
    "UNRESOLVED",
    "CHEST_DOMINANT",
    "HEAD_DOMINANT",
    "MIX_LIKE_BALANCED",
    "MIX_LIKE_CHEST_DOMINANT",
    "MIX_LIKE_HEAD_DOMINANT",
    "TRANSITION_UNSTABLE",
)

# Map register strategy → legacy type_id (backward compatible where possible)
STRATEGY_TO_TYPE_ID = {
    "UNRESOLVED": "UNRESOLVED",
    "CHEST_DOMINANT": "CHEST_DOMINANT",
    "HEAD_DOMINANT": "HEAD_DOMINANT",
    "MIX_LIKE_BALANCED": "BALANCED_MIX",
    "MIX_LIKE_CHEST_DOMINANT": "CHEST_DOMINANT_MIX",
    "MIX_LIKE_HEAD_DOMINANT": "HEAD_DOMINANT_MIX",
    "TRANSITION_UNSTABLE": "TRANSITION_UNSTABLE",
}


def classify_source_balance(index: Optional[float]) -> dict[str, Any]:
    if index is None:
        return {
            "balance_class": "UNKNOWN",
            "label": "발성 성향 판단 보류",
            "confidence_label": "low",
        }
    if index <= cfg.CHEST_DOMINANT_MAX:
        return {
            "balance_class": "CHEST_DOMINANT",
            "label": "흉성 쪽 성향이 더 강한 편",
            "confidence_label": "medium",
        }
    if index >= cfg.HEAD_DOMINANT_MIN:
        return {
            "balance_class": "HEAD_DOMINANT",
            "label": "두성 쪽 성향이 더 강한 편",
            "confidence_label": "medium",
        }
    # Mid band — balanced tendency (NOT mix)
    if index < cfg.CHEST_LEAN_MAX:
        return {
            "balance_class": "CHEST_DOMINANT",
            "label": "흉성 쪽 성향이 다소 강한 편",
            "confidence_label": "medium",
            "lean": "chest",
        }
    if index > cfg.HEAD_LEAN_MIN:
        return {
            "balance_class": "HEAD_DOMINANT",
            "label": "두성 쪽 성향이 다소 강한 편",
            "confidence_label": "medium",
            "lean": "head",
        }
    return {
        "balance_class": "BALANCED",
        "label": "흉성·두성 균형형",
        "confidence_label": "medium",
    }


def positive_mix_transition_evidence(bridge: dict[str, Any]) -> dict[str, Any]:
    """
    Mix requires affirmative continuity evidence — absence of breaks is not enough.
    """
    btype = (bridge.get("type") or "UNDETERMINED").upper()
    score = bridge.get("score")
    suff = (bridge.get("register_sufficiency") or "").upper()
    split = bridge.get("split_eligibility") or {}
    n_opp = int(
        bridge.get("n_transition_opportunities")
        or split.get("n_opportunities")
        or 0
    )
    reasons_ok: list[str] = []
    reasons_block: list[str] = []

    if suff in ("INSUFFICIENT", "UNAVAILABLE"):
        reasons_block.append("register_measurement_insufficient")
    if n_opp < 1 and suff not in ("SUFFICIENT",):
        # Allow SMOOTH_BRIDGE with explicit score even if opp count missing
        if btype != "SMOOTH_BRIDGE":
            reasons_block.append("insufficient_transition_coverage")

    smooth = btype == "SMOOTH_BRIDGE" or (
        score is not None and float(score) >= cfg.BRIDGE_SMOOTH_MIN
    )
    if smooth and suff not in ("INSUFFICIENT", "UNAVAILABLE"):
        reasons_ok.append("smooth_bridge_or_score")
    elif smooth and suff in ("INSUFFICIENT", "UNAVAILABLE"):
        reasons_block.append("smooth_score_but_insufficient_register")
    else:
        reasons_block.append("no_positive_continuity_evidence")

    # Explicit disruption contra-evidence
    if btype == "ABRUPT_REGISTER_BREAK":
        reasons_block.append("abrupt_register_break")
    if bool(split.get("eligible")):
        reasons_block.append("register_split_eligible")
    if bool(split.get("f0_disrupted")) and bool(split.get("source_disrupted")):
        # Disrupted signals without eligibility still lower mix confidence
        if not smooth:
            reasons_block.append("f0_and_source_disrupted")

    ok = bool(reasons_ok) and not any(
        r in reasons_block
        for r in (
            "register_measurement_insufficient",
            "no_positive_continuity_evidence",
            "abrupt_register_break",
            "register_split_eligible",
            "smooth_score_but_insufficient_register",
        )
    )
    return {
        "ok": ok,
        "smooth": smooth,
        "reasons_ok": reasons_ok,
        "reasons_block": reasons_block,
        "mix_evidence": "SUFFICIENT" if ok else ("INSUFFICIENT" if reasons_block else "UNKNOWN"),
    }


def classify_register_strategy(
    *,
    index: Optional[float],
    bridge: dict[str, Any],
    confidence: str,
    neutral_collapse: bool = False,
    register_split_ok: Optional[bool] = None,
    family_agreement: float = 1.0,
    mix_coverage_ok: bool = True,
    modifiers: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Register / Mix-like strategy — independent of firmness and effort modifiers.
    """
    modifiers = modifiers or []
    void = {
        "status": "UNRESOLVED",
        "mix_evidence": "INSUFFICIENT",
        "continuity": None,
        "source_transition": (bridge.get("type") or None),
        "confidence_label": "low",
        "evidence": {},
        "type_id": "UNRESOLVED",
    }
    if index is None or confidence == "low" or neutral_collapse:
        void["evidence"] = {"reason": "insufficient_index_or_confidence"}
        return void

    split_gate = bridge.get("split_eligibility") or {}
    if register_split_ok is None:
        register_split_ok = bool(split_gate.get("eligible"))

    mix_gate = positive_mix_transition_evidence(bridge)
    btype = (bridge.get("type") or "UNDETERMINED").upper()
    score = bridge.get("score")

    evidence = {
        "source_balance_index": round(float(index), 4),
        "bridge_type": btype,
        "bridge_score": score,
        "register_sufficiency": bridge.get("register_sufficiency"),
        "transition_coverage": bridge.get("n_transition_opportunities")
        or split_gate.get("n_opportunities"),
        "f0_disrupted": split_gate.get("f0_disrupted"),
        "source_disrupted": split_gate.get("source_disrupted"),
        "mix_gate": mix_gate,
        "family_agreement": family_agreement,
        "mix_coverage_ok": mix_coverage_ok,
        # Explicit: modifiers do not drive mix
        "modifiers_ignored_for_mix": list(modifiers),
    }

    # Global register split
    if register_split_ok and btype == "ABRUPT_REGISTER_BREAK":
        return {
            "status": "TRANSITION_UNSTABLE",
            "mix_evidence": "CONTRA",
            "continuity": "disrupted",
            "source_transition": btype,
            "confidence_label": "medium",
            "evidence": evidence,
            "type_id": "REGISTER_SPLIT_GLOBAL",
        }

    # Abrupt / unstable without global split eligibility → not Mix
    if btype == "ABRUPT_REGISTER_BREAK" or (
        score is not None and float(score) <= cfg.BRIDGE_POOR_MAX and mix_gate["mix_evidence"] != "SUFFICIENT"
    ):
        return {
            "status": "TRANSITION_UNSTABLE",
            "mix_evidence": "CONTRA",
            "continuity": "disrupted",
            "source_transition": btype,
            "confidence_label": "medium" if confidence != "low" else "low",
            "evidence": evidence,
            "type_id": "TRANSITION_UNSTABLE",
        }

    chest_heavy = index <= cfg.CHEST_DOMINANT_MAX
    head_heavy = index >= cfg.HEAD_DOMINANT_MIN
    mid = cfg.MIX_LOW <= index <= cfg.MIX_HIGH

    # Light head falsetto-like remains a contact+head pattern (not mix)
    if "WEAK_CONTACT" in modifiers and head_heavy and family_agreement >= 0.5:
        return {
            "status": "HEAD_DOMINANT",
            "mix_evidence": mix_gate["mix_evidence"],
            "continuity": None,
            "source_transition": btype,
            "confidence_label": confidence,
            "evidence": evidence,
            "type_id": "LIGHT_HEAD_FALSETTO_LIKE",
        }

    if mix_gate["ok"] and mix_coverage_ok:
        # Positive Mix-like — balance can be chest/head dominant
        if family_agreement < 0.35 and mid and 0.45 <= index <= 0.55:
            return {
                **void,
                "evidence": {**evidence, "reason": "low_family_agreement_near_50"},
                "mix_evidence": "INSUFFICIENT",
            }
        if chest_heavy or (mid and index < cfg.CHEST_LEAN_MAX):
            status = "MIX_LIKE_CHEST_DOMINANT"
        elif head_heavy or (mid and index > cfg.HEAD_LEAN_MIN):
            status = "MIX_LIKE_HEAD_DOMINANT"
        else:
            status = "MIX_LIKE_BALANCED"
        return {
            "status": status,
            "mix_evidence": "SUFFICIENT",
            "continuity": "continuous",
            "source_transition": btype,
            "confidence_label": "high" if confidence == "high" else "medium",
            "evidence": evidence,
            "type_id": STRATEGY_TO_TYPE_ID[status],
        }

    # No positive mix evidence — source tendency only
    if chest_heavy or (mid and index < cfg.CHEST_LEAN_MAX):
        return {
            "status": "CHEST_DOMINANT",
            "mix_evidence": mix_gate["mix_evidence"],
            "continuity": None,
            "source_transition": btype,
            "confidence_label": confidence,
            "evidence": evidence,
            "type_id": "CHEST_DOMINANT",
        }
    if head_heavy or (mid and index > cfg.HEAD_LEAN_MIN):
        return {
            "status": "HEAD_DOMINANT",
            "mix_evidence": mix_gate["mix_evidence"],
            "continuity": None,
            "source_transition": btype,
            "confidence_label": confidence,
            "evidence": evidence,
            "type_id": "HEAD_DOMINANT",
        }
    # Balanced source, mix unresolved
    return {
        "status": "UNRESOLVED",
        "mix_evidence": mix_gate["mix_evidence"],
        "continuity": None,
        "source_transition": btype,
        "confidence_label": "low",
        "evidence": evidence,
        "type_id": "BALANCED_SOURCE",
    }


def source_balance_display(balance: dict[str, Any]) -> str:
    return balance.get("label") or "발성 성향 판단 보류"


def register_strategy_display(strategy: dict[str, Any]) -> dict[str, str]:
    status = (strategy.get("status") or "UNRESOLVED").upper()
    titles = {
        "UNRESOLVED": "추가 확인 필요",
        "CHEST_DOMINANT": "흉성 쪽 성향",
        "HEAD_DOMINANT": "두성 쪽 성향",
        "MIX_LIKE_BALANCED": "믹스 성향",
        "MIX_LIKE_CHEST_DOMINANT": "흉성 중심의 믹스 성향",
        "MIX_LIKE_HEAD_DOMINANT": "두성 중심의 믹스 성향",
        "TRANSITION_UNSTABLE": "전환이 급격한 구간",
    }
    bodies = {
        "UNRESOLVED": (
            "이번 녹음만으로 성구 연결 방식을 충분히 확인하기 어려웠어요."
        ),
        "CHEST_DOMINANT": "흉성 쪽 발성 특성이 우세하게 나타났어요.",
        "HEAD_DOMINANT": "두성 쪽 발성 특성이 우세하게 나타났어요.",
        "MIX_LIKE_BALANCED": (
            "음역이 올라갈 때 흉성·두성 쪽 음향 특성이 "
            "비교적 연속적으로 연결됐어요."
        ),
        "MIX_LIKE_CHEST_DOMINANT": (
            "중·고음에서도 흉성 쪽 특성이 유지되면서 "
            "연결되는 믹스 성향이 관찰됐어요."
        ),
        "MIX_LIKE_HEAD_DOMINANT": (
            "중음부터 두성 쪽 특성이 늘어나며 "
            "연결되는 믹스 성향이 관찰됐어요."
        ),
        "TRANSITION_UNSTABLE": (
            "음역이 올라가는 구간에서 발성 특성이 급격하게 바뀌는 구간이 관찰됐어요."
        ),
    }
    return {
        "title": titles.get(status, "추가 확인 필요"),
        "description": bodies.get(status, bodies["UNRESOLVED"]),
    }
