"""Cross-layer consistency validator for coaching / vocal-type reports."""

from __future__ import annotations

from typing import Any, Optional


PRIMARY_MODIFY_FAMILY = {
    "AIR_LEAKAGE": ("air_leakage", "AIR_LEAKAGE"),
    "EXCESS_EFFORT_HIGH_NOTE": ("high_note_entry_effort", "EXCESS_EFFORT"),
    "GENERAL_EXCESS_EFFORT": ("general_effort", "EXCESS_EFFORT"),
    "REGISTER_TRANSITION_DISRUPTION": ("register_transition", "REGISTER"),
    "RESONANCE_MID_PRESENCE_LOSS": ("resonance_strategy", "RESONANCE"),
    "RESONANCE_HIGH_NOTE_COLLAPSE": ("resonance_strategy", "RESONANCE"),
    "ABRUPT_ONSET": ("onset", "ONSET"),
    "APERIODIC_ROUGHNESS": ("roughness", "ROUGHNESS"),
    "EXCESS_FIRMNESS_WITH_STRAIN": ("high_note_entry_effort", "EFFORT"),
    "PHRASE_END_SUPPORT_LOSS": ("phrase_end", "SUPPORT"),
}

EPISODE_CORE_LABELS = {
    "AIR_LEAKAGE": "핵심 기식 구간",
    "EXCESS_EFFORT_HIGH_NOTE": "힘이 증가한 핵심 구간",
    "GENERAL_EXCESS_EFFORT": "힘이 증가한 핵심 구간",
    "REGISTER_TRANSITION_DISRUPTION": "핵심 전환 구간",
    "RESONANCE_MID_PRESENCE_LOSS": "공명 변화 핵심 구간",
    "RESONANCE_HIGH_NOTE_COLLAPSE": "공명 변화 핵심 구간",
    "ABRUPT_ONSET": "발성 시작 핵심 구간",
    "APERIODIC_ROUGHNESS": "불규칙 음질 핵심 구간",
    "EXCESS_FIRMNESS_WITH_STRAIN": "힘이 증가한 핵심 구간",
    "PHRASE_END_SUPPORT_LOSS": "구절 말 지지 핵심 구간",
}

EPISODE_TYPE_LABELS = {
    "AIR_LEAKAGE": "핵심 기식 구간",
    "HIGH_NOTE": "힘이 증가한 핵심 구간",
    "REGISTER_TRANSITION": "핵심 전환 구간",
    "ROUGHNESS": "불규칙 음질 핵심 구간",
    "ABRUPT_ONSET": "발성 시작 핵심 구간",
    "GENERAL_EFFORT": "힘이 증가한 핵심 구간",
    "PHRASE_END_DROP": "구절 말 지지 핵심 구간",
}


def core_span_label(primary: Optional[dict[str, Any]], target: Optional[dict[str, Any]]) -> str:
    if primary and primary.get("id") in EPISODE_CORE_LABELS:
        return EPISODE_CORE_LABELS[primary["id"]]
    if target and target.get("type") in EPISODE_TYPE_LABELS:
        return EPISODE_TYPE_LABELS[target["type"]]
    return "핵심 구간"


def _suf(criteria_matrix: list[dict[str, Any]], dim_id: str) -> Optional[str]:
    for row in criteria_matrix or []:
        if row.get("dimension_id") == dim_id:
            return (row.get("measurement_sufficiency") or "").upper()
    return None


def validate_report_consistency(
    *,
    vocal_type: Optional[dict[str, Any]] = None,
    coaching_decision: Optional[dict[str, Any]] = None,
    criteria_matrix: Optional[list[dict[str, Any]]] = None,
    dimensions: Optional[dict[str, Any]] = None,
    performance: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Returns issues with severity ERROR/WARN/DEBUG and optional patches.
    ERROR → strip user-facing claim; WARN → downgrade/hide; DEBUG → log only.
    """
    issues: list[dict[str, Any]] = []
    patches: dict[str, Any] = {}
    vt = vocal_type or {}
    decision = coaching_decision or {}
    matrix = criteria_matrix or []
    dims = dimensions or {}

    # TYPE vs REGISTER criteria
    reg_suf = _suf(matrix, "register_configuration") or (
        "INSUFFICIENT"
        if (dims.get("register_configuration") or {}).get("confidence_label") == "low"
        else None
    )
    btype = ((vt.get("bridge") or {}).get("type") or "").upper()
    tid = (vt.get("type_id") or vt.get("base_type") or vt.get("global_type") or "").upper()
    if tid in ("REGISTER_SPLIT", "REGISTER_SPLIT_GLOBAL") and reg_suf in (
        "INSUFFICIENT",
        "UNAVAILABLE",
    ):
        issues.append(
            {
                "id": "type_vs_register_insufficient",
                "severity": "ERROR",
                "message": "REGISTER_SPLIT_GLOBAL with insufficient register criteria",
            }
        )
        patches.setdefault("vocal_type", {})["type_id"] = "UNRESOLVED"
        patches["vocal_type"]["base_type"] = "UNRESOLVED"
        patches["vocal_type"]["global_type"] = "UNRESOLVED"
        patches["vocal_type"]["display_name"] = "발성 성향 판단 보류"
        patches["vocal_type"]["available"] = False

    if btype == "SMOOTH_BRIDGE" and reg_suf in ("INSUFFICIENT", "UNAVAILABLE"):
        issues.append(
            {
                "id": "smooth_bridge_vs_register_insufficient",
                "severity": "ERROR",
                "message": "SMOOTH_BRIDGE claim with insufficient register criteria",
            }
        )
        patches.setdefault("vocal_type", {}).setdefault("bridge", {})["type"] = "UNDETERMINED"
        # Strip passaggio stable trait
        traits = list(vt.get("key_traits") or [])
        patches.setdefault("vocal_type", {})["key_traits"] = [
            t for t in traits if t.get("key") != "passaggio"
        ]

    # HEAD/CHEST ratio vs evidence mass
    hc = vt.get("head_chest") or {}
    ev = vt.get("evidence") or {}
    mass = hc.get("evidence_mass")
    if mass is None:
        mass = ev.get("mass")
    if hc.get("available") and mass is not None and float(mass) < 1.0:
        issues.append(
            {
                "id": "ratio_without_mass",
                "severity": "ERROR",
                "message": "Published head/chest ratio with low evidence mass",
            }
        )
        patches.setdefault("vocal_type", {}).setdefault("head_chest", {}).update(
            {"available": False, "chest_ratio": None, "head_ratio": None}
        )

    # PRIMARY vs MODIFY
    primary = decision.get("primary_bottleneck") or {}
    modify = list(decision.get("modify") or [])
    pid = primary.get("id")
    if pid and modify:
        want = PRIMARY_MODIFY_FAMILY.get(pid)
        first = modify[0]
        first_id = first.get("id") or first.get("triggered_by")
        if want and first_id not in want and first.get("triggered_by") != pid:
            issues.append(
                {
                    "id": "primary_modify_mismatch",
                    "severity": "ERROR",
                    "message": f"primary {pid} but modify[0]={first_id}",
                }
            )
            # Reorder patch
            matched = [m for m in modify if m.get("id") in (want or ()) or m.get("triggered_by") == pid]
            rest = [m for m in modify if m not in matched]
            patches.setdefault("coaching_decision", {})["modify"] = (matched + rest) if matched else modify

    # PRESERVE vibrato vs criteria
    vib_suf = _suf(matrix, "vibrato_control")
    vibrato_dim = dims.get("vibrato_control") or {}
    preserve = list(decision.get("preserve") or [])
    if any(p.get("id") == "vibrato" for p in preserve):
        bad = vib_suf in ("INSUFFICIENT", "UNAVAILABLE") or (
            vibrato_dim.get("status") not in ("OBSERVED",) and vib_suf != "SUFFICIENT"
        )
        if vib_suf in ("INSUFFICIENT", "UNAVAILABLE") or vibrato_dim.get("status") in (
            "UNKNOWN",
            "UNAVAILABLE",
            "INSUFFICIENT",
        ):
            issues.append(
                {
                    "id": "vibrato_preserve_insufficient",
                    "severity": "ERROR",
                    "message": "Vibrato preserve without sufficient evidence",
                }
            )
            patches.setdefault("coaching_decision", {})["preserve"] = [
                p for p in preserve if p.get("id") != "vibrato"
            ]

    # Performance wording: high score + "중간 수준"
    if performance:
        for area in performance.get("areas") or []:
            sc = area.get("score")
            headline = (area.get("headline") or area.get("interpretation") or "")
            if sc is not None and float(sc) >= 70 and "중간 수준" in str(headline):
                issues.append(
                    {
                        "id": "performance_mid_wording",
                        "severity": "WARN",
                        "message": f"{area.get('area_id')} score={sc} uses 중간 수준",
                    }
                )

    # CONTACT / RESONANCE modifier vs criteria (warn only)
    for mod, dim in (
        ("FIRM_CONTACT", "glottal_contact_profile"),
        ("WEAK_CONTACT", "glottal_contact_profile"),
        ("LOW_RESONANCE_PRESENCE", "resonance_formant_strategy"),
    ):
        if mod in (vt.get("modifiers") or []):
            suf = _suf(matrix, dim)
            if suf in ("INSUFFICIENT", "UNAVAILABLE"):
                issues.append(
                    {
                        "id": f"modifier_{mod}_vs_criteria",
                        "severity": "WARN",
                        "message": f"Modifier {mod} with {suf} criteria",
                    }
                )

    # Effort Main Finding vs profile (debug/warn only — no production overwrite)
    effort_dim = dims.get("vocal_effort_strain") or {}
    assessment = effort_dim.get("effort_assessment")
    primary_bn = decision.get("primary_bottleneck") or decision.get("primary") or {}
    primary_id = primary_bn.get("id")
    if assessment and primary_id == "GENERAL_EXCESS_EFFORT":
        sev = (assessment.get("global_severity") or assessment.get("severity") or "").upper()
        if sev == "LOW":
            issues.append(
                {
                    "id": "general_excess_effort_vs_low_severity",
                    "severity": "WARN",
                    "message": "GENERAL_EXCESS_EFFORT primary with LOW canonical effort severity",
                }
            )

    return {
        "ok": not any(i["severity"] == "ERROR" for i in issues),
        "issues": issues,
        "patches": patches,
    }


def apply_consistency_patches(
    *,
    vocal_type: dict[str, Any],
    coaching_decision: dict[str, Any],
    report: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    result = validate_report_consistency(
        vocal_type=vocal_type,
        coaching_decision=coaching_decision,
        criteria_matrix=(report or {}).get("criteria_matrix"),
        dimensions=(report or {}).get("dimensions") or vocal_type.get("_dimensions"),
        performance=(report or {}).get("performance_supplement"),
    )
    patches = result.get("patches") or {}
    vt = dict(vocal_type)
    dec = dict(coaching_decision)
    if "vocal_type" in patches:
        for k, v in patches["vocal_type"].items():
            if isinstance(v, dict) and isinstance(vt.get(k), dict):
                vt[k] = {**vt[k], **v}
            else:
                vt[k] = v
    if "coaching_decision" in patches:
        for k, v in patches["coaching_decision"].items():
            dec[k] = v
    vt["consistency_audit"] = {
        "ok": result["ok"],
        "issues": result["issues"],
    }
    return vt, dec, result
