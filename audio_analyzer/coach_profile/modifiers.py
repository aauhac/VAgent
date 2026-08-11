"""Modifiers from Functional dimensions + local register events (v1.2)."""

from __future__ import annotations

from typing import Any


def collect_modifiers(
    *,
    dimensions: dict[str, Any],
    bridge: dict[str, Any],
    head_chest: dict[str, Any],
) -> list[str]:
    dims = dimensions or {}
    mods: list[str] = []

    contact = dims.get("glottal_contact_profile") or {}
    effort = dims.get("vocal_effort_strain") or {}
    leakage = dims.get("air_leakage_breathiness") or {}
    regularity = dims.get("phonation_regularity") or {}
    onset = dims.get("onset_offset_coordination") or {}
    resonance = dims.get("resonance_formant_strategy") or {}

    continuum = contact.get("continuum_0_to_1")
    clabel = (contact.get("continuum_label") or contact.get("summary") or "").lower()
    if continuum is not None:
        if float(continuum) <= 0.35 and contact.get("confidence_label") in ("medium", "high"):
            mods.append("WEAK_CONTACT")
        elif float(continuum) >= 0.65 and contact.get("confidence_label") in ("medium", "high"):
            mods.append("FIRM_CONTACT")
    elif "가벼" in clabel or "light" in clabel:
        mods.append("WEAK_CONTACT")
    elif "단단" in clabel or "firm" in clabel:
        mods.append("FIRM_CONTACT")

    if (effort.get("status") or "").upper() in ("OCCASIONAL", "MODERATE", "REPEATED", "HIGH"):
        if effort.get("confidence_label") != "low" and not effort.get("hidden"):
            mods.append("EXCESS_EFFORT")

    if (leakage.get("status") or "").upper() in ("OCCASIONAL", "MODERATE", "HIGH"):
        if leakage.get("confidence_label") != "low" and not leakage.get("hidden"):
            mods.append("AIR_LEAKAGE")

    if (regularity.get("status") or "").upper() in ("INTERMITTENT", "REPEATED_IRREGULAR"):
        if not regularity.get("hidden"):
            mods.append("ROUGHNESS")

    if (onset.get("status") or "").upper() in ("ABRUPT_LIKE",):
        mods.append("HARD_ONSET")

    prof = resonance.get("profile") or {}
    mid = (prof.get("mid_presence") or "").lower()
    if "낮" in mid or mid == "낮은 편":
        mods.append("LOW_RESONANCE_PRESENCE")

    # Local events → modifiers (not global type overrides)
    for ev in bridge.get("local_register_events") or []:
        et = ev.get("type")
        if et == "LOCAL_CHEST_PULL":
            mods.append("CHEST_PULL")
        elif et == "LOCAL_EARLY_HEAD_SHIFT":
            mods.append("EARLY_HEAD_SHIFT")
        elif et == "LOCAL_ABRUPT_BREAK":
            mods.append("PASSAGGIO_BREAK")
        elif et == "LOCAL_EFFORT_SPIKE":
            mods.append("EXCESS_EFFORT")

    btype = (bridge.get("type") or "").upper()
    if btype == "SMOOTH_BRIDGE":
        mods.append("GOOD_BRIDGE")
    elif btype in ("ABRUPT_REGISTER_BREAK",) and (bridge.get("split_eligibility") or {}).get(
        "eligible"
    ):
        mods.append("PASSAGGIO_BREAK")

    return list(dict.fromkeys(mods))
