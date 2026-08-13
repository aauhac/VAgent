"""Canonical acoustic axes — single source of truth for Style / Profile / Diagnosis UI."""

from __future__ import annotations

from typing import Any, Optional


def _display_effort(value: str) -> str:
    return {
        "LOW": "낮은 편",
        "MID": "중간",
        "HIGH": "높은 편",
        "UNRESOLVED": "확인 부족",
    }.get(value, value)


def _display_contact(value: str) -> str:
    return {
        "LIGHT": "가벼운 편",
        "MID": "중간",
        "FIRM": "단단한 편",
        "UNRESOLVED": "확인 부족",
    }.get(value, value)


def _display_breath(value: str) -> str:
    return {
        "LOW": "낮은 편",
        "MID": "중간",
        "HIGH": "높은 편",
        "UNRESOLVED": "확인 부족",
    }.get(value, value)


def _axis(
    *,
    value: str,
    continuum: Optional[float] = None,
    confidence: str = "medium",
    available: bool = True,
    display: Optional[str] = None,
    evidence_source: Optional[list[str]] = None,
    concept: str = "",
    ui_label: str = "",
) -> dict[str, Any]:
    return {
        "value": value,
        "status": value,
        "continuum": continuum,
        "confidence": confidence,
        "available": available and value != "UNRESOLVED",
        "display": display or value,
        "evidence_source": evidence_source or [],
        "concept": concept,
        "ui_label": ui_label,
    }


def _effort_from_sources(
    *,
    modifiers: list[str],
    effort_assessment: Optional[dict[str, Any]],
    dimensions: dict[str, Any],
) -> dict[str, Any]:
    ea = effort_assessment or {}
    sev = str(ea.get("severity") or ea.get("global_severity") or "").upper()
    dim = dimensions.get("vocal_effort_strain") or {}
    dim_st = str(dim.get("status") or "").upper()
    continuum = None
    try:
        if ea.get("display_continuum") is not None:
            continuum = float(ea["display_continuum"])
        elif ea.get("continuum") is not None:
            continuum = float(ea["continuum"])
    except (TypeError, ValueError):
        continuum = None

    if "EXCESS_EFFORT" in modifiers or sev in ("HIGH", "REPEATED") or dim_st in ("HIGH", "REPEATED"):
        return _axis(
            value="HIGH",
            continuum=continuum if continuum is not None else 0.82,
            confidence="high" if "EXCESS_EFFORT" in modifiers or sev == "HIGH" else "medium",
            display=_display_effort("HIGH"),
            evidence_source=["effort_assessment", "modifiers"],
            concept="effort",
            ui_label="힘",
        )
    if sev in ("MODERATE",) or dim_st in ("MODERATE", "OCCASIONAL", "MILD"):
        return _axis(
            value="MID",
            continuum=continuum if continuum is not None else 0.55,
            confidence=str(ea.get("confidence_label") or "medium"),
            display=_display_effort("MID"),
            evidence_source=["effort_assessment"],
            concept="effort",
            ui_label="힘",
        )
    if sev == "LOW" or dim_st == "LOW":
        return _axis(
            value="LOW",
            continuum=continuum if continuum is not None else 0.22,
            confidence=str(ea.get("confidence_label") or "medium"),
            display=_display_effort("LOW"),
            evidence_source=["effort_assessment"],
            concept="effort",
            ui_label="힘",
        )
    if not ea and not dim:
        return _axis(
            value="UNRESOLVED",
            available=False,
            confidence="low",
            display=_display_effort("UNRESOLVED"),
            concept="effort",
            ui_label="힘",
        )
    return _axis(
        value="LOW",
        continuum=0.22,
        confidence="low",
        display=_display_effort("LOW"),
        evidence_source=["default"],
        concept="effort",
        ui_label="힘",
    )


def _contact_from_sources(
    *,
    modifiers: list[str],
    dimensions: dict[str, Any],
) -> dict[str, Any]:
    dim = dimensions.get("glottal_contact_profile") or {}
    summary = str(dim.get("summary") or "")
    st = str(dim.get("status") or "").upper()
    continuum = None
    for key in ("continuum", "display_continuum", "score"):
        if dim.get(key) is not None:
            try:
                continuum = float(dim[key])
                break
            except (TypeError, ValueError):
                pass

    # Prefer explicit modifiers, then summary/continuum — one shared mapping
    if "FIRM_CONTACT" in modifiers or "단단" in summary or (continuum is not None and continuum >= 0.62):
        val = "FIRM"
        cont = continuum if continuum is not None else 0.75
    elif "WEAK_CONTACT" in modifiers or "가볍" in summary or (continuum is not None and continuum <= 0.38):
        val = "LIGHT"
        cont = continuum if continuum is not None else 0.25
    elif st in ("UNKNOWN", "AMBIGUOUS", "") and continuum is None and "FIRM_CONTACT" not in modifiers and "WEAK_CONTACT" not in modifiers:
        if not dim:
            return _axis(
                value="UNRESOLVED",
                available=False,
                confidence="low",
                display=_display_contact("UNRESOLVED"),
                concept="contact",
                ui_label="접촉감",
            )
        val = "MID"
        cont = 0.5
    else:
        val = "MID"
        cont = continuum if continuum is not None else 0.5

    return _axis(
        value=val,
        continuum=cont,
        confidence="high" if ("FIRM_CONTACT" in modifiers or "WEAK_CONTACT" in modifiers) else "medium",
        display=_display_contact(val) if val != "FIRM" else ("매우 단단한 편" if "FIRM_CONTACT" in modifiers else "단단한 편"),
        evidence_source=["glottal_contact_profile", "modifiers"],
        concept="contact",
        ui_label="접촉감",
    )


def _functional_breathiness(
    *,
    modifiers: list[str],
    dimensions: dict[str, Any],
) -> dict[str, Any]:
    dim = dimensions.get("air_leakage_breathiness") or {}
    st = str(dim.get("status") or "").upper()
    continuum = None
    try:
        if dim.get("continuum") is not None:
            continuum = float(dim["continuum"])
    except (TypeError, ValueError):
        continuum = None

    if "AIR_LEAKAGE" in modifiers or st in ("HIGH", "MODERATE"):
        val = "HIGH"
        cont = continuum if continuum is not None else 0.75
    elif st == "OCCASIONAL":
        val = "MID"
        cont = continuum if continuum is not None else 0.5
    elif st == "LOW" or (dim and st not in ("UNKNOWN", "AMBIGUOUS", "")):
        val = "LOW"
        cont = continuum if continuum is not None else 0.22
    elif not dim and "AIR_LEAKAGE" not in modifiers:
        return _axis(
            value="UNRESOLVED",
            available=False,
            confidence="low",
            display=_display_breath("UNRESOLVED"),
            concept="functional_breathiness",
            ui_label="숨 섞임",
        )
    else:
        val = "MID"
        cont = 0.5

    return _axis(
        value=val,
        continuum=cont,
        confidence="medium",
        display=_display_breath(val),
        evidence_source=["air_leakage_breathiness"],
        concept="functional_breathiness",
        ui_label="숨 섞임",
    )


def _timbre_airiness(timbre_profile: Optional[dict[str, Any]]) -> dict[str, Any]:
    tp = timbre_profile or {}
    ax = (tp.get("axes") or {}).get("airiness") if isinstance(tp.get("axes"), dict) else None
    if not isinstance(ax, dict) or ax.get("continuum") is None:
        return _axis(
            value="UNRESOLVED",
            available=False,
            confidence="low",
            display="확인 부족",
            concept="timbre_airiness",
            ui_label="음색의 공기감",
        )
    try:
        cont = float(ax["continuum"])
    except (TypeError, ValueError):
        return _axis(
            value="UNRESOLVED",
            available=False,
            confidence="low",
            display="확인 부족",
            concept="timbre_airiness",
            ui_label="음색의 공기감",
        )
    if cont < 0.35:
        val = "LOW"
    elif cont > 0.65:
        val = "HIGH"
    else:
        val = "MID"
    return _axis(
        value=val,
        continuum=cont,
        confidence=str(ax.get("confidence_label") or "medium"),
        display=str(ax.get("status") or _display_breath(val)),
        evidence_source=["timbre_profile.airiness"],
        concept="timbre_airiness",
        ui_label="음색의 공기감",
    )


def _stability(dimensions: dict[str, Any]) -> dict[str, Any]:
    dim = dimensions.get("phonation_regularity") or {}
    st = str(dim.get("status") or "").upper()
    if not dim or st in ("UNKNOWN", "AMBIGUOUS", ""):
        return _axis(
            value="UNRESOLVED",
            available=False,
            confidence="low",
            display="확인 부족",
            concept="stability",
            ui_label="안정성",
        )
    if "STABLE" in st or st in ("GOOD", "HIGH"):
        val = "STABLE"
        display = "안정적인 편"
        cont = 0.78
    elif "UNSTABLE" in st or st in ("LOW", "POOR"):
        val = "UNSTABLE"
        display = "불안정한 편"
        cont = 0.28
    else:
        val = "MID"
        display = "중간"
        cont = 0.5
    return _axis(
        value=val,
        continuum=cont,
        confidence="medium",
        display=display,
        evidence_source=["phonation_regularity"],
        concept="stability",
        ui_label="안정성",
    )


def _presence_brightness(
    *,
    modifiers: list[str],
    dimensions: dict[str, Any],
    timbre_profile: Optional[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    tp = timbre_profile or {}
    axes = tp.get("axes") if isinstance(tp, dict) else None
    dim = dimensions.get("resonance_formant_strategy") or {}
    summary = str(dim.get("summary") or "")

    def from_timbre(key: str, concept: str, ui: str) -> Optional[dict[str, Any]]:
        if not isinstance(axes, dict):
            return None
        ax = axes.get(key)
        if not isinstance(ax, dict) or ax.get("continuum") is None:
            return None
        try:
            cont = float(ax["continuum"])
        except (TypeError, ValueError):
            return None
        if key == "brightness":
            val = "DARK" if cont < 0.35 else ("BRIGHT" if cont > 0.65 else "MID")
            display = str(ax.get("status") or ("어두운 편" if val == "DARK" else ("밝은 편" if val == "BRIGHT" else "중간")))
        else:
            val = "LOW" if cont < 0.35 else ("HIGH" if cont > 0.65 else "MID")
            display = str(ax.get("status") or ("낮은 편" if val == "LOW" else ("높은 편" if val == "HIGH" else "중간")))
        return _axis(
            value=val,
            continuum=cont,
            confidence=str(ax.get("confidence_label") or "medium"),
            display=display,
            evidence_source=[f"timbre_profile.{key}"],
            concept=concept,
            ui_label=ui,
        )

    presence = from_timbre("presence", "resonance_presence", "존재감")
    brightness = from_timbre("brightness", "brightness", "밝기")

    if presence is None:
        if "LOW_RESONANCE_PRESENCE" in modifiers or ("중역" in summary and ("낮" in summary or "부족" in summary)):
            presence = _axis(
                value="LOW",
                continuum=0.25,
                display="낮은 편",
                evidence_source=["modifiers" if "LOW_RESONANCE_PRESENCE" in modifiers else "dim"],
                concept="resonance_presence",
                ui_label="존재감",
            )
        elif "중역 높은" in summary:
            presence = _axis(
                value="HIGH",
                continuum=0.75,
                display="높은 편",
                evidence_source=["dim"],
                concept="resonance_presence",
                ui_label="존재감",
            )
        else:
            presence = _axis(
                value="UNRESOLVED",
                available=False,
                confidence="low",
                display="확인 부족",
                concept="resonance_presence",
                ui_label="존재감",
            )

    if brightness is None:
        if "밝기 어두운" in summary or "어두운 편" in summary:
            brightness = _axis(
                value="DARK",
                continuum=0.28,
                display="어두운 편",
                evidence_source=["dim"],
                concept="brightness",
                ui_label="밝기",
            )
        elif "밝기 밝은" in summary or "밝은 편" in summary:
            brightness = _axis(
                value="BRIGHT",
                continuum=0.75,
                display="밝은 편",
                evidence_source=["dim"],
                concept="brightness",
                ui_label="밝기",
            )
        else:
            brightness = _axis(
                value="UNRESOLVED",
                available=False,
                confidence="low",
                display="확인 부족",
                concept="brightness",
                ui_label="밝기",
            )

    return presence, brightness


def build_canonical_acoustic_axes(
    *,
    vocal_type_profile: Optional[dict[str, Any]] = None,
    dimensions: Optional[dict[str, Any]] = None,
    effort_assessment: Optional[dict[str, Any]] = None,
    timbre_profile: Optional[dict[str, Any]] = None,
    register_connection: Optional[dict[str, Any]] = None,
    source_balance: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    vt = vocal_type_profile or {}
    dims = dimensions or {}
    modifiers = list(vt.get("modifiers") or [])

    effort = _effort_from_sources(
        modifiers=modifiers, effort_assessment=effort_assessment, dimensions=dims
    )
    contact = _contact_from_sources(modifiers=modifiers, dimensions=dims)
    functional_breathiness = _functional_breathiness(modifiers=modifiers, dimensions=dims)
    timbre_airiness = _timbre_airiness(timbre_profile)
    stability = _stability(dims)
    presence, brightness = _presence_brightness(
        modifiers=modifiers, dimensions=dims, timbre_profile=timbre_profile
    )

    reg = register_connection or {}
    register_axis = _axis(
        value=str(reg.get("status") or reg.get("value") or "UNRESOLVED"),
        confidence=str(reg.get("confidence_label") or reg.get("confidence") or "low"),
        available=str(reg.get("status") or reg.get("value") or "UNRESOLVED") != "UNRESOLVED",
        display=str(reg.get("profile_label") or reg.get("display") or reg.get("title") or "추가 확인 필요"),
        evidence_source=list(reg.get("provenance") or reg.get("evidence_source") or []),
        concept="register_connection",
        ui_label="성구 연결",
    )

    sb = source_balance or vt.get("source_balance") or {}
    sb_val = str(sb.get("value") or sb.get("balance_class") or "UNRESOLVED").upper()
    if sb_val == "BALANCED":
        sb_val = "BALANCED_ACOUSTIC"
    source_axis = _axis(
        value=sb_val,
        confidence=str(sb.get("confidence") or sb.get("confidence_label") or "low"),
        available=sb_val not in ("UNRESOLVED", "UNKNOWN", ""),
        display=str(sb.get("display") or sb.get("label") or sb_val),
        evidence_source=["source_balance"],
        concept="source_balance",
        ui_label="흉성·두성 관련 음향 성향",
    )
    source_axis["show_ratio"] = sb.get("show_ratio")
    source_axis["chest_percent"] = sb.get("chest_percent")
    source_axis["head_percent"] = sb.get("head_percent")
    source_axis["label"] = sb.get("label")

    axes = {
        "effort": effort,
        "contact": contact,
        "functional_breathiness": functional_breathiness,
        "breathiness": functional_breathiness,  # alias for style engine
        "timbre_airiness": timbre_airiness,
        "register_connection": register_axis,
        "stability": stability,
        "resonance_presence": presence,
        "brightness": brightness,
        "source_balance": source_axis,
    }
    reliable = [
        k
        for k, v in axes.items()
        if k != "breathiness" and v.get("available") and v.get("value") not in (None, "UNRESOLVED")
    ]
    return {
        "version": "canonical-acoustic-axes-v1",
        "axes": axes,
        "reliable_axis_ids": reliable,
        "reliable_count": len(reliable),
    }
