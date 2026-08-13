"""Canonical style axes for Vocal Style Profile v1."""

from __future__ import annotations

from typing import Any, Optional


def _axis(
    *,
    value: str,
    status: str,
    confidence: str = "medium",
    evidence_source: Optional[list[str]] = None,
    available: bool = True,
    display: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "status": status,
        "confidence": confidence,
        "evidence_source": evidence_source or [],
        "available": available,
        "display": display or value,
    }


def _unavailable(name: str) -> dict[str, Any]:
    return _axis(
        value="UNRESOLVED",
        status="UNRESOLVED",
        confidence="low",
        available=False,
        display="확인 부족",
        evidence_source=[f"{name}:unavailable"],
    )


def derive_effort_axis(
    *,
    modifiers: list[str],
    effort_assessment: Optional[dict[str, Any]] = None,
    dimensions: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    ea = effort_assessment or {}
    sev = str(ea.get("severity") or ea.get("global_severity") or "").upper()
    dim = (dimensions or {}).get("vocal_effort_strain") or {}
    dim_st = str(dim.get("status") or "").upper()
    sources: list[str] = []

    if "EXCESS_EFFORT" in modifiers or sev in ("HIGH", "REPEATED") or dim_st in ("HIGH", "REPEATED"):
        sources.append("modifier:EXCESS_EFFORT" if "EXCESS_EFFORT" in modifiers else f"severity:{sev or dim_st}")
        return _axis(
            value="HIGH",
            status="HIGH",
            confidence="high" if "EXCESS_EFFORT" in modifiers or sev == "HIGH" else "medium",
            evidence_source=sources,
            display="높은 편",
        )
    if sev in ("MODERATE",) or dim_st in ("MODERATE", "OCCASIONAL", "MILD"):
        # Localized/moderate effort stays MID unless modifier escalates
        sources.append(f"severity:{sev or dim_st}")
        return _axis(
            value="MID",
            status="MID",
            confidence=str(ea.get("confidence_label") or "medium"),
            evidence_source=sources,
            display="중간",
        )
    if sev == "LOW" or dim_st == "LOW" or (not modifiers and not sev and not dim_st):
        if sev == "LOW" or dim_st == "LOW":
            return _axis(
                value="LOW",
                status="LOW",
                confidence=str(ea.get("confidence_label") or "medium"),
                evidence_source=[f"severity:{sev or dim_st}"],
                display="낮은 편",
            )
    if not ea and not dim:
        return _unavailable("effort")
    return _axis(
        value="LOW",
        status="LOW",
        confidence="low",
        evidence_source=["default:low"],
        display="낮은 편",
    )


def derive_contact_axis(
    *,
    modifiers: list[str],
    dimensions: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    dim = (dimensions or {}).get("glottal_contact_profile") or {}
    summary = str(dim.get("summary") or "")
    if "FIRM_CONTACT" in modifiers or "단단" in summary:
        return _axis(
            value="FIRM",
            status="FIRM",
            confidence="high" if "FIRM_CONTACT" in modifiers else "medium",
            evidence_source=["modifier:FIRM_CONTACT"] if "FIRM_CONTACT" in modifiers else ["dim:firm"],
            display="매우 단단한 편" if "FIRM_CONTACT" in modifiers else "단단한 편",
        )
    if "WEAK_CONTACT" in modifiers or "가볍" in summary:
        return _axis(
            value="LIGHT",
            status="LIGHT",
            confidence="high" if "WEAK_CONTACT" in modifiers else "medium",
            evidence_source=["modifier:WEAK_CONTACT"] if "WEAK_CONTACT" in modifiers else ["dim:light"],
            display="가벼운 편",
        )
    if not dim and "FIRM_CONTACT" not in modifiers and "WEAK_CONTACT" not in modifiers:
        return _unavailable("contact")
    return _axis(
        value="MID",
        status="MID",
        confidence="medium",
        evidence_source=["dim:mid"],
        display="중간",
    )


def derive_breathiness_axis(
    *,
    modifiers: list[str],
    dimensions: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    dim = (dimensions or {}).get("air_leakage_breathiness") or {}
    st = str(dim.get("status") or "").upper()
    if "AIR_LEAKAGE" in modifiers or st in ("HIGH", "MODERATE"):
        return _axis(
            value="HIGH",
            status="HIGH",
            confidence="medium",
            evidence_source=["modifier:AIR_LEAKAGE"] if "AIR_LEAKAGE" in modifiers else [f"status:{st}"],
            display="높은 편",
        )
    if st == "OCCASIONAL":
        return _axis(
            value="MID",
            status="MID",
            confidence="medium",
            evidence_source=[f"status:{st}"],
            display="중간",
        )
    if st == "LOW" or (dim and st not in ("UNKNOWN", "AMBIGUOUS", "")):
        return _axis(
            value="LOW",
            status="LOW",
            confidence="medium",
            evidence_source=[f"status:{st or 'LOW'}"],
            display="낮은 편",
        )
    if not dim and "AIR_LEAKAGE" not in modifiers:
        return _unavailable("breathiness")
    return _axis(value="MID", status="MID", confidence="low", display="중간")


def derive_stability_axis(dimensions: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    dim = (dimensions or {}).get("phonation_regularity") or {}
    st = str(dim.get("status") or "").upper()
    if not dim or st in ("UNKNOWN", "AMBIGUOUS", ""):
        return _unavailable("stability")
    if "STABLE" in st or st in ("GOOD", "HIGH"):
        return _axis(
            value="STABLE",
            status="STABLE",
            confidence="medium",
            evidence_source=[f"status:{st}"],
            display="안정적인 편",
        )
    if "UNSTABLE" in st or st in ("LOW", "POOR"):
        return _axis(
            value="UNSTABLE",
            status="UNSTABLE",
            confidence="medium",
            evidence_source=[f"status:{st}"],
            display="불안정한 편",
        )
    return _axis(
        value="MID",
        status="MID",
        confidence="medium",
        evidence_source=[f"status:{st}"],
        display="중간",
    )


def derive_presence_axis(
    *,
    modifiers: list[str],
    dimensions: Optional[dict[str, Any]] = None,
    timbre_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if "LOW_RESONANCE_PRESENCE" in modifiers:
        return _axis(
            value="LOW",
            status="LOW",
            confidence="medium",
            evidence_source=["modifier:LOW_RESONANCE_PRESENCE"],
            display="낮은 편",
        )
    dim = (dimensions or {}).get("resonance_formant_strategy") or {}
    summary = str(dim.get("summary") or "")
    tp = timbre_profile or {}
    axes = tp.get("axes") if isinstance(tp, dict) else None
    presence = None
    if isinstance(axes, dict):
        presence = axes.get("presence") or axes.get("mid_presence") or axes.get("resonance_presence")
    if isinstance(presence, dict):
        val = str(presence.get("value") or presence.get("status") or "").upper()
        if val in ("HIGH", "STRONG"):
            return _axis(value="HIGH", status="HIGH", confidence="medium", display="높은 편",
                         evidence_source=["timbre:presence"])
        if val in ("LOW", "WEAK"):
            return _axis(value="LOW", status="LOW", confidence="medium", display="낮은 편",
                         evidence_source=["timbre:presence"])
    if "중역 높은" in summary or "존재감" in summary and "높" in summary:
        return _axis(value="HIGH", status="HIGH", confidence="low", display="높은 편",
                     evidence_source=["dim:resonance"])
    if "중역" in summary and ("낮" in summary or "부족" in summary):
        return _axis(value="LOW", status="LOW", confidence="low", display="낮은 편",
                     evidence_source=["dim:resonance"])
    if not dim and not tp:
        return _unavailable("resonance_presence")
    return _axis(value="MID", status="MID", confidence="low", display="중간", evidence_source=["default:mid"])


def derive_brightness_axis(
    *,
    dimensions: Optional[dict[str, Any]] = None,
    timbre_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    dim = (dimensions or {}).get("resonance_formant_strategy") or {}
    summary = str(dim.get("summary") or "")
    tp = timbre_profile or {}
    axes = tp.get("axes") if isinstance(tp, dict) else None
    bright = None
    if isinstance(axes, dict):
        bright = axes.get("brightness") or axes.get("timbre_brightness")
    if isinstance(bright, dict):
        val = str(bright.get("value") or bright.get("status") or "").upper()
        if val in ("HIGH", "BRIGHT"):
            return _axis(value="BRIGHT", status="BRIGHT", confidence="medium", display="밝은 편",
                         evidence_source=["timbre:brightness"])
        if val in ("LOW", "DARK"):
            return _axis(value="DARK", status="DARK", confidence="medium", display="어두운 편",
                         evidence_source=["timbre:brightness"])
    if "밝기 어두운" in summary or "어두운 편" in summary:
        return _axis(value="DARK", status="DARK", confidence="low", display="어두운 편",
                     evidence_source=["dim:resonance"])
    if "밝기 밝은" in summary or "밝은 편" in summary:
        return _axis(value="BRIGHT", status="BRIGHT", confidence="low", display="밝은 편",
                     evidence_source=["dim:resonance"])
    if not dim and not tp:
        return _unavailable("brightness")
    return _axis(value="MID", status="MID", confidence="low", display="중간")


def derive_source_balance_axis(vocal_type_profile: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    vt = vocal_type_profile or {}
    sb = dict(vt.get("source_balance") or {})
    hc = vt.get("head_chest") or {}
    bclass = str(sb.get("balance_class") or "").upper()
    if not bclass or bclass == "UNKNOWN":
        return _unavailable("source_balance")
    # Normalize legacy BALANCED; promote mid+low-agreement to CONFLICTED
    agree = sb.get("family_agreement")
    if agree is None:
        agree = hc.get("family_agreement")
    direc = sb.get("directionality")
    if direc is None:
        direc = hc.get("directionality") or hc.get("global_ratio_directionality")
    idx = sb.get("index")
    if idx is None:
        idx = hc.get("index")
    if bclass in ("BALANCED", "BALANCED_ACOUSTIC") and agree is not None:
        try:
            a = float(agree)
            d = float(direc) if direc is not None else 1.0
            i = float(idx) if idx is not None else 0.5
            near_half = 0.45 <= i <= 0.55
            if a < 0.45 or (near_half and a < 0.55 and d < 0.2):
                bclass = "CONFLICTED"
                sb["label"] = "흉성·두성 관련 음향 특징이 서로 다른 방향으로 나타났어요"
                sb["show_ratio"] = False
            else:
                bclass = "BALANCED_ACOUSTIC"
        except (TypeError, ValueError):
            if bclass == "BALANCED":
                bclass = "BALANCED_ACOUSTIC"
    elif bclass == "BALANCED":
        bclass = "BALANCED_ACOUSTIC"
    mapping = {
        "CHEST_DOMINANT": ("CHEST_LEANING", "흉성 쪽"),
        "CHEST_LEANING": ("CHEST_LEANING", "흉성 쪽"),
        "HEAD_DOMINANT": ("HEAD_LEANING", "두성 쪽"),
        "HEAD_LEANING": ("HEAD_LEANING", "두성 쪽"),
        "BALANCED_ACOUSTIC": ("BALANCED_ACOUSTIC", "균형에 가까운 편"),
        "CONFLICTED": ("CONFLICTED", "방향이 엇갈림"),
        "UNRESOLVED": ("UNRESOLVED", "확인 부족"),
    }
    value, display = mapping.get(bclass, (bclass, sb.get("label") or bclass))
    show = sb.get("show_ratio")
    if show is None:
        show = value not in ("CONFLICTED", "UNRESOLVED") and bclass not in ("CONFLICTED", "UNKNOWN")
    if value == "CONFLICTED":
        show = False
    ax = _axis(
        value=value,
        status=value,
        confidence=str(sb.get("confidence_label") or "medium"),
        evidence_source=[f"balance:{bclass}"],
        display=display if value != "CONFLICTED" else (sb.get("label") or display),
    )
    ax["show_ratio"] = bool(show)
    ax["chest_percent"] = sb.get("chest_percent") if show else None
    ax["head_percent"] = sb.get("head_percent") if show else None
    ax["label"] = sb.get("label") or display
    return ax
