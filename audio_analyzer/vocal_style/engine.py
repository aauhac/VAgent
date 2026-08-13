"""Vocal Style Profile engine — multi-axis descriptive style."""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.canonical.acoustic_axes import build_canonical_acoustic_axes

from .archetypes import ARCHETYPES, VOCAL_STYLE_VERSION
from .register_canonical import (
    apply_canonical_to_register_strategy,
    build_canonical_register_assessment,
)


def _score_candidates(axes: dict[str, dict[str, Any]]) -> list[tuple[str, int, list[str]]]:
    effort = (axes.get("effort") or {}).get("value")
    contact = (axes.get("contact") or {}).get("value")
    breath = (axes.get("breathiness") or axes.get("functional_breathiness") or {}).get("value")
    reg = (axes.get("register_connection") or {}).get("value")
    stab = (axes.get("stability") or {}).get("value")
    presence = (axes.get("resonance_presence") or {}).get("value")
    bright = (axes.get("brightness") or {}).get("value")
    source = (axes.get("source_balance") or {}).get("value")
    source_conf = (axes.get("source_balance") or {}).get("confidence")

    out: list[tuple[str, int, list[str]]] = []

    if effort == "HIGH" and contact == "FIRM":
        out.append(("FIRM_HIGH_EFFORT", ARCHETYPES["FIRM_HIGH_EFFORT"]["priority"], ["effort", "contact"]))
    if effort == "LOW" and reg == "CONNECTED":
        out.append(("EASY_CONNECTED", ARCHETYPES["EASY_CONNECTED"]["priority"], ["effort", "register_connection"]))
    if stab == "STABLE" and reg == "CONNECTED":
        out.append(("STABLE_CONNECTED", ARCHETYPES["STABLE_CONNECTED"]["priority"], ["stability", "register_connection"]))
    if contact == "LIGHT" and breath == "HIGH":
        out.append(("LIGHT_AIRY", ARCHETYPES["LIGHT_AIRY"]["priority"], ["contact", "breathiness"]))
    if contact == "LIGHT" and breath == "LOW" and presence in ("MID", "HIGH"):
        out.append(("LIGHT_CLEAR", ARCHETYPES["LIGHT_CLEAR"]["priority"], ["contact", "breathiness", "resonance_presence"]))
    if bright == "BRIGHT" and presence == "HIGH":
        out.append(("BRIGHT_PRESENT", ARCHETYPES["BRIGHT_PRESENT"]["priority"], ["brightness", "resonance_presence"]))

    secondary_ok = any(
        (axes.get(k) or {}).get("available") and (axes.get(k) or {}).get("value") not in (None, "UNRESOLVED")
        for k in ("effort", "contact", "breathiness", "functional_breathiness", "stability", "resonance_presence", "brightness")
    )
    if (
        source in ("CHEST_LEANING", "CHEST_DOMINANT")
        and source_conf in ("high", "medium")
        and secondary_ok
        and (axes.get("source_balance") or {}).get("show_ratio") is not False
    ):
        out.append(("CHEST_DRIVEN", ARCHETYPES["CHEST_DRIVEN"]["priority"], ["source_balance"]))
    if (
        source in ("HEAD_LEANING", "HEAD_DOMINANT")
        and source_conf in ("high", "medium")
        and secondary_ok
        and (axes.get("source_balance") or {}).get("show_ratio") is not False
    ):
        out.append(("HEAD_DRIVEN", ARCHETYPES["HEAD_DRIVEN"]["priority"], ["source_balance"]))

    out.sort(key=lambda t: (t[1], -len(t[2])))
    return out


def _primary_traits(axes: dict[str, dict[str, Any]], max_n: int = 3) -> list[dict[str, str]]:
    order = [
        ("effort", "힘"),
        ("contact", "접촉감"),
        ("breathiness", "숨 섞임"),
        ("stability", "안정성"),
        ("resonance_presence", "존재감"),
        ("brightness", "밝기"),
        ("register_connection", "성구 연결"),
    ]
    traits: list[dict[str, str]] = []
    for key, label in order:
        a = axes.get(key) or axes.get("functional_breathiness" if key == "breathiness" else key) or {}
        if key == "breathiness":
            a = axes.get("breathiness") or axes.get("functional_breathiness") or {}
        if not a.get("available"):
            continue
        if a.get("value") in (None, "UNRESOLVED", "MID") and key not in ("effort", "contact", "breathiness"):
            continue
        if a.get("value") == "MID" and key in ("stability", "brightness", "resonance_presence"):
            continue
        traits.append({"key": key, "label": label, "value": str(a.get("display") or a.get("value"))})
        if len(traits) >= max_n:
            break
    return traits


def _composite_from_axes(axes: dict[str, dict[str, Any]]) -> tuple[str, str, list[str]]:
    """Build descriptive title/body from top distinctive axes — no hardcode of sample names."""
    snippets: list[tuple[int, str, str]] = []
    # weight: higher = more distinctive for naming
    effort = axes.get("effort") or {}
    contact = axes.get("contact") or {}
    breath = axes.get("breathiness") or axes.get("functional_breathiness") or {}
    presence = axes.get("resonance_presence") or {}
    bright = axes.get("brightness") or {}
    stab = axes.get("stability") or {}

    if effort.get("available") and effort.get("value") == "LOW":
        snippets.append((10, "편안하고", "힘 사용이 비교적 편안하고"))
    elif effort.get("available") and effort.get("value") == "HIGH":
        snippets.append((12, "힘이 두드러지는", "힘 사용이 크게 나타나고"))

    if contact.get("available") and contact.get("value") == "FIRM":
        snippets.append((11, "접촉이 단단한", "접촉감이 단단하며"))
    elif contact.get("available") and contact.get("value") == "LIGHT":
        snippets.append((9, "가벼운", "접촉감이 가벼운 편이며"))

    if breath.get("available") and breath.get("value") == "LOW":
        snippets.append((10, "숨 섞임이 적은", "숨 섞임이 적으며"))
    elif breath.get("available") and breath.get("value") == "HIGH":
        snippets.append((10, "숨 섞임이 있는", "숨 섞임이 함께 나타나며"))

    if presence.get("available") and presence.get("value") == "LOW":
        snippets.append((7, "차분한 음색 성향의", "존재감이 차분한 편으로"))
    elif presence.get("available") and presence.get("value") == "HIGH":
        snippets.append((8, "존재감이 있는", "존재감이 비교적 분명하고"))

    if bright.get("available") and bright.get("value") == "DARK":
        snippets.append((6, "어두운 음색의", "밝기가 어두운 편이며"))
    elif bright.get("available") and bright.get("value") == "BRIGHT":
        snippets.append((6, "밝은 음색의", "밝기가 비교적 두드러지며"))

    if stab.get("available") and stab.get("value") == "STABLE":
        snippets.append((5, "안정적인", "발성 안정성이 유지되며"))

    snippets.sort(key=lambda x: -x[0])
    top = snippets[:3]
    if not top:
        return (
            ARCHETYPES["UNRESOLVED"]["display_name"],
            ARCHETYPES["UNRESOLVED"]["description"],
            [],
        )

    title_bits = [t[1] for t in top[:2]]
    # Join with spaces so "편안하고" + "숨 섞임이 적은" does not glue
    title = " ".join(b.strip() for b in title_bits if b and str(b).strip())
    if not title.endswith("발성형"):
        title = f"{title} 발성형".replace("  ", " ").strip()

    body_bits = [t[2] for t in top]
    if len(body_bits) == 1:
        description = f"이번 노래에서는 {body_bits[0]} 발성 경향이 나타났어요."
    elif len(body_bits) == 2:
        description = f"이번 노래에서는 {body_bits[0]} {body_bits[1]} 발성 경향이 나타났어요."
    else:
        description = (
            f"이번 노래에서는 {body_bits[0]} {body_bits[1]} "
            f"{body_bits[2]} 발성 경향이 나타났어요."
        )
    matched = []
    for key in ("effort", "contact", "breathiness", "resonance_presence", "brightness", "stability"):
        a = axes.get(key) or axes.get("functional_breathiness" if key == "breathiness" else "")
        if isinstance(a, dict) and a.get("available"):
            matched.append(key)
    return title, description, matched[:3]


def build_vocal_style_profile(
    *,
    vocal_type_profile: Optional[dict[str, Any]] = None,
    dimensions: Optional[dict[str, Any]] = None,
    effort_assessment: Optional[dict[str, Any]] = None,
    timbre_profile: Optional[dict[str, Any]] = None,
    controlled_siren: Optional[dict[str, Any]] = None,
    mode: str = "SONG_DETAIL",
) -> dict[str, Any]:
    vt = vocal_type_profile or {}
    dims = dimensions or {}

    canonical_reg = build_canonical_register_assessment(
        register_strategy=vt.get("register_strategy"),
        bridge=vt.get("bridge"),
        dimensions=dims,
        controlled_siren=controlled_siren,
        mode=mode,
    )

    # Derive source balance axis first for canonical pack
    from . import axes as legacy_ax

    source_balance = legacy_ax.derive_source_balance_axis(vt)

    canon = build_canonical_acoustic_axes(
        vocal_type_profile=vt,
        dimensions=dims,
        effort_assessment=effort_assessment,
        timbre_profile=timbre_profile,
        register_connection=canonical_reg,
        source_balance=source_balance,
    )
    axes_map = dict(canon.get("axes") or {})
    # Style-facing alias
    if "functional_breathiness" in axes_map:
        axes_map["breathiness"] = axes_map["functional_breathiness"]

    register_connection = {
        "value": canonical_reg.get("status"),
        "status": canonical_reg.get("status"),
        "confidence": canonical_reg.get("confidence_label") or "low",
        "evidence_source": canonical_reg.get("provenance") or [],
        "available": canonical_reg.get("status") != "UNRESOLVED",
        "display": canonical_reg.get("profile_label") or canonical_reg.get("title"),
        "title": canonical_reg.get("title"),
        "description": canonical_reg.get("description"),
    }
    axes_map["register_connection"] = register_connection
    axes_map["source_balance"] = source_balance

    available_axes = [
        k
        for k, v in axes_map.items()
        if k not in ("functional_breathiness",)
        and v.get("available")
        and v.get("value") not in (None, "UNRESOLVED")
    ]
    # Unique conceptual axes for reliability count
    reliable_ids = [
        k
        for k in (
            "effort",
            "contact",
            "breathiness",
            "register_connection",
            "stability",
            "resonance_presence",
            "brightness",
        )
        if (axes_map.get(k) or {}).get("available")
        and (axes_map.get(k) or {}).get("value") not in (None, "UNRESOLVED")
    ]
    candidates = _score_candidates(axes_map)

    style_id = "UNRESOLVED"
    matched: list[str] = []
    if candidates:
        top = candidates[0]
        if len(top[2]) >= 2 or (
            top[0] in ("CHEST_DRIVEN", "HEAD_DRIVEN") and len(reliable_ids) >= 2
        ):
            style_id = top[0]
            matched = top[2]

    if len(reliable_ids) < 2:
        style_id = "UNRESOLVED"
        matched = []
    elif style_id == "UNRESOLVED" and len(reliable_ids) >= 3:
        style_id = "COMPOSITE_DESCRIPTIVE"

    arch = ARCHETYPES.get(style_id, ARCHETYPES["UNRESOLVED"])
    primary_traits = _primary_traits(axes_map)

    if style_id == "COMPOSITE_DESCRIPTIVE":
        display_name, description, matched = _composite_from_axes(axes_map)
    else:
        display_name = arch["display_name"]
        description = arch["description"]
        if style_id == "FIRM_HIGH_EFFORT" and (axes_map.get("breathiness") or {}).get("value") == "LOW":
            description = (
                "이번 노래에서는 접촉감이 단단하고 "
                "힘 사용이 크게 나타나는 구간이 두드러졌어요. "
                "숨 섞임은 적은 편입니다."
            )
        if style_id == "UNRESOLVED":
            display_name = "이번 노래에서 확인된 발성 특징"
            description = "이번 노래에서는 발성 스타일을 충분히 정리하기 어려웠어요."

    evidence_summary = []
    for k in matched or reliable_ids[:3]:
        a = axes_map.get(k) or {}
        evidence_summary.append(f"{k}:{a.get('value')}")

    vt_register = apply_canonical_to_register_strategy(vt.get("register_strategy"), canonical_reg)

    conf = "medium"
    if style_id == "UNRESOLVED":
        conf = "low"
    elif style_id == "COMPOSITE_DESCRIPTIVE":
        conf = "medium"

    return {
        "version": VOCAL_STYLE_VERSION,
        "available": True,
        "style_id": style_id,
        "style_mode": (
            "NAMED"
            if style_id not in ("UNRESOLVED", "COMPOSITE_DESCRIPTIVE")
            else style_id
        ),
        "display_name": display_name,
        "description": description,
        "primary_traits": primary_traits,
        "axes": axes_map,
        "canonical_acoustic_axes": canon,
        "confidence_label": conf,
        "evidence_summary": evidence_summary,
        "canonical_register": canonical_reg,
        "register_strategy_public": {
            "status": canonical_reg.get("status"),
            "title": canonical_reg.get("title"),
            "description": canonical_reg.get("description"),
            "profile_label": canonical_reg.get("profile_label"),
        },
        "source_balance_presentation": {
            "balance_class": source_balance.get("value"),
            "label": source_balance.get("label") or source_balance.get("display"),
            "show_ratio": bool(source_balance.get("show_ratio")),
            "chest_percent": source_balance.get("chest_percent"),
            "head_percent": source_balance.get("head_percent"),
            "conflicted": source_balance.get("value") == "CONFLICTED",
        },
        "_patched_register_strategy": vt_register,
    }
