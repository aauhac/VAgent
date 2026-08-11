"""Build all-dimension criteria matrix from engine dimensions + segments.

measurement_sufficiency ≠ finding ≠ coaching_eligibility.
"""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.vocal_function import config as cfg
from audio_analyzer.vocal_function.criteria_registry import (
    BOTTLENECK_DIMENSION,
    DIMENSION_ORDER,
    coaching_min_required,
    criteria_for,
)
from audio_analyzer.vocal_evidence.phonation_quality import (
    breathy_family_flags,
    classify_rough_segment,
    vocal_presence_ok,
)
from audio_analyzer.vocal_function.validity import dim_valid


def _avail(ok: bool | None, *, unavailable: bool = False) -> str:
    if unavailable:
        return "NOT_AVAILABLE"
    if ok is None:
        return "INSUFFICIENT"
    return "SUFFICIENT" if ok else "INSUFFICIENT"


def _criterion_row(
    *,
    criterion_id: str,
    label: str,
    required: bool,
    availability: str,
    direction: str = "NEUTRAL",
    evidence: Optional[list[str]] = None,
    segments_used: int = 0,
) -> dict[str, Any]:
    return {
        "criterion_id": criterion_id,
        "label": label,
        "required": required,
        "availability": availability,
        "direction": direction,
        "evidence": evidence or [],
        "segments_used": segments_used,
    }


def _finding_from_status(status: str, sufficiency: str) -> str:
    if sufficiency in ("INSUFFICIENT", "UNAVAILABLE"):
        return "UNDETERMINED"
    st = (status or "").upper()
    if st in ("UNKNOWN", "AMBIGUOUS", ""):
        return "UNDETERMINED"
    if st in (
        "LOW",
        "STABLE",
        "STABLE_LIKE",
        "SMOOTH",
        "BALANCED_LIKE",
        "SOFT_LIKE",
        "OBSERVED",  # contact continuum-only without concern — still "observed profile"
    ):
        # LOW / STABLE with sufficient measurement → tendency not prominent
        if st in ("LOW", "STABLE", "STABLE_LIKE", "SMOOTH", "BALANCED_LIKE", "SOFT_LIKE"):
            return "NOT_PROMINENT"
        return "OBSERVED"
    if st in (
        "HIGH",
        "MODERATE",
        "OCCASIONAL",
        "INTERMITTENT",
        "REPEATED",
        "REPEATED_IRREGULAR",
        "TRANSITION_EVENTS",
        "ABRUPT_LIKE",
        "AIRY_LIKE",
    ):
        return "OBSERVED"
    return "OBSERVED" if st else "UNDETERMINED"


def _user_sufficiency(s: str) -> str:
    return {
        "SUFFICIENT": "충분",
        "PARTIAL": "일부 부족",
        "INSUFFICIENT": "부족",
        "UNAVAILABLE": "측정 불가",
    }.get(s, s)


def _user_finding(f: str) -> str:
    return {
        "OBSERVED": "경향 관찰",
        "NOT_PROMINENT": "뚜렷하지 않음",
        "UNDETERMINED": "판단 보류",
    }.get(f, f)


def _user_eligibility(e: str) -> str:
    return {
        "YES": "교정 가능",
        "NO": "교정 우선순위 아님",
        "NEEDS_CONFIRMATION": "추가 확인 필요",
    }.get(e, e)


def _breathiness_criteria(segments: list[dict[str, Any]], dim: dict[str, Any]) -> list[dict[str, Any]]:
    cov = dim.get("breathiness_coverage") or dim.get("profile") or {}
    n_eval = int(cov.get("n_evaluable_segments") or cov.get("evaluable") or 0)
    n_pos = int(cov.get("n_positive_segments") or cov.get("positive") or 0)
    n_total = int(cov.get("n_total_segments") or len(segments) or 0)

    presence_n = sum(1 for s in segments if vocal_presence_ok(s))
    period_pos = period_neg = spectral_pos = spectral_neg = spectral_avail = 0
    source_avail = source_pos = 0
    for s in segments:
        if not dim_valid(s, "breathiness") and not vocal_presence_ok(s):
            continue
        fam = breathy_family_flags(s)
        if "periodicity_noise" in (fam.get("available_families") or []):
            if fam.get("periodicity_noise"):
                period_pos += 1
            else:
                period_neg += 1
        if "harmonic_spectral" in (fam.get("available_families") or []):
            spectral_avail += 1
            if fam.get("harmonic_spectral"):
                spectral_pos += 1
            else:
                spectral_neg += 1
        if "glottal_source" in (fam.get("available_families") or []):
            source_avail += 1
            if fam.get("glottal_source"):
                source_pos += 1

    spec = criteria_for("air_leakage_breathiness")
    by_id = {c["criterion_id"]: c for c in spec}
    rows = []

    rows.append(
        _criterion_row(
            criterion_id="vocal_presence",
            label=by_id["vocal_presence"]["label"],
            required=True,
            availability=_avail(presence_n >= cfg.MIN_SEGMENTS_GLOBAL),
            direction="PRESENT" if presence_n else "ABSENT",
            evidence=[f"presence_segments={presence_n}"],
            segments_used=presence_n,
        )
    )
    per_dir = (
        "BREATHY_POSITIVE"
        if period_pos > period_neg and period_pos
        else ("BREATHY_NEGATIVE" if period_neg > period_pos else "NEUTRAL")
    )
    rows.append(
        _criterion_row(
            criterion_id="periodicity_noise",
            label=by_id["periodicity_noise"]["label"],
            required=True,
            availability=_avail((period_pos + period_neg) >= 1),
            direction=per_dir,
            evidence=[f"positive={period_pos}", f"negative={period_neg}"],
            segments_used=period_pos + period_neg,
        )
    )
    if spectral_avail == 0:
        spec_avail = "INSUFFICIENT"
        spec_dir = "NEUTRAL"
    else:
        spec_avail = "SUFFICIENT"
        spec_dir = (
            "BREATHY_POSITIVE"
            if spectral_pos > spectral_neg
            else ("BREATHY_NEGATIVE" if spectral_neg > spectral_pos else "NEUTRAL")
        )
    rows.append(
        _criterion_row(
            criterion_id="spectral_harmonic",
            label=by_id["spectral_harmonic"]["label"],
            required=True,
            availability=spec_avail,
            direction=spec_dir,
            evidence=[f"available={spectral_avail}", f"positive={spectral_pos}"],
            segments_used=spectral_avail,
        )
    )
    rows.append(
        _criterion_row(
            criterion_id="glottal_source",
            label=by_id["glottal_source"]["label"],
            required=False,
            availability="NOT_AVAILABLE" if source_avail == 0 else "SUFFICIENT",
            direction="BREATHY_POSITIVE" if source_pos else "NEUTRAL",
            evidence=[f"gif_valid_segments={source_avail}"],
            segments_used=source_avail,
        )
    )
    cov_ok = n_eval >= cfg.MIN_SEGMENTS_GLOBAL
    rows.append(
        _criterion_row(
            criterion_id="evaluable_coverage",
            label=by_id["evaluable_coverage"]["label"],
            required=True,
            availability=_avail(cov_ok),
            direction="NEUTRAL",
            evidence=[f"evaluable={n_eval}/{n_total or len(segments)}"],
            segments_used=n_eval,
        )
    )
    rep_ok = n_pos >= 2 or (n_eval >= cfg.MIN_SEGMENTS_GLOBAL and n_pos == 0)
    rows.append(
        _criterion_row(
            criterion_id="repetition",
            label=by_id["repetition"]["label"],
            required=True,
            availability=_avail(bool(rep_ok) if n_eval >= cfg.MIN_SEGMENTS_GLOBAL else False),
            direction="BREATHY_POSITIVE" if n_pos >= 2 else "NEUTRAL",
            evidence=[f"positive_hits={n_pos}/{n_eval}"],
            segments_used=n_pos,
        )
    )
    return rows


def _roughness_criteria(segments: list[dict[str, Any]], dim: dict[str, Any]) -> list[dict[str, Any]]:
    cov = dim.get("roughness_coverage") or {}
    n_pos = int(cov.get("positive") or 0)
    n_rej = int(cov.get("rejected_periodicity_only") or 0)
    n_eval = int(cov.get("evaluable") or 0)
    presence = sum(1 for s in segments if vocal_presence_ok(s))
    irreg = sum(
        1
        for s in segments
        if classify_rough_segment(s).get("verdict") == "POSITIVE"
    )
    period_loss_only = n_rej
    spec = {c["criterion_id"]: c for c in criteria_for("phonation_regularity")}
    return [
        _criterion_row(
            criterion_id="vocal_presence",
            label=spec["vocal_presence"]["label"],
            required=True,
            availability=_avail(presence >= 2),
            segments_used=presence,
        ),
        _criterion_row(
            criterion_id="periodicity_loss",
            label=spec["periodicity_loss"]["label"],
            required=True,
            availability=_avail(n_eval >= 1 or period_loss_only >= 1 or irreg >= 1),
            direction="ROUGH_POSITIVE" if (irreg or period_loss_only) else "NEUTRAL",
            evidence=[f"periodicity_only_rejects={period_loss_only}"],
            segments_used=n_eval,
        ),
        _criterion_row(
            criterion_id="irregularity_specific",
            label=spec["irregularity_specific"]["label"],
            required=True,
            availability=_avail(irreg >= 1 or n_pos >= 1),
            direction="ROUGH_POSITIVE" if irreg or n_pos else "NEUTRAL",
            evidence=[f"irregularity_hits={n_pos or irreg}"],
            segments_used=n_pos or irreg,
        ),
        _criterion_row(
            criterion_id="repetition",
            label=spec["repetition"]["label"],
            required=True,
            availability=_avail((n_pos or irreg) >= 2 or ((n_pos or irreg) == 0 and n_eval >= 3)),
            direction="ROUGH_POSITIVE" if (n_pos or irreg) >= 2 else "NEUTRAL",
            evidence=[f"hits={n_pos or irreg}"],
            segments_used=n_pos or irreg,
        ),
    ]


def _register_criteria(dim: dict[str, Any], episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prof = dim.get("profile") or {}
    events = prof.get("events") or []
    rejected = prof.get("rejected_events") or []
    reg_eps = [e for e in episodes if e.get("type") == "REGISTER_TRANSITION"]
    has_core = any((e.get("core_evidence_span") or {}).get("start_sec") is not None for e in reg_eps)
    vocal_ok = any((ev.get("validity") or {}).get("vocal_specific") for ev in events) or bool(events)
    f0_ok = any(abs(float(ev.get("f0_jump_cents") or 0)) >= 350 for ev in events)
    src_ok = any((ev.get("evidence") or {}).get("source_change") or (ev.get("evidence") or {}).get("naq_change") for ev in events)
    accomp_ok = bool(events)  # accepted events already passed accompaniment/vocal-specific gate
    vib_ok = True  # events not vibrato-masked if present in profile
    spec = {c["criterion_id"]: c for c in criteria_for("register_configuration")}
    return [
        _criterion_row(
            criterion_id="vocal_specific",
            label=spec["vocal_specific"]["label"],
            required=True,
            availability=_avail(vocal_ok),
            evidence=[f"events={len(events)}", f"rejected={len(rejected)}"],
            segments_used=len(events),
        ),
        _criterion_row(
            criterion_id="f0_transition",
            label=spec["f0_transition"]["label"],
            required=True,
            availability=_avail(f0_ok),
            direction="TRANSITION" if f0_ok else "NEUTRAL",
            evidence=[f"f0_events={sum(1 for e in events if e.get('f0_jump_cents'))}"],
            segments_used=len(events),
        ),
        _criterion_row(
            criterion_id="source_shift",
            label=spec["source_shift"]["label"],
            required=True,
            availability=_avail(src_ok),
            direction="TRANSITION" if src_ok else "NEUTRAL",
            segments_used=len(events),
        ),
        _criterion_row(
            criterion_id="accompaniment_reject",
            label=spec["accompaniment_reject"]["label"],
            required=True,
            availability=_avail(accomp_ok if events else False),
            evidence=[f"rejected_contam={len(rejected)}"],
            segments_used=len(events),
        ),
        _criterion_row(
            criterion_id="vibrato_mask",
            label=spec["vibrato_mask"]["label"],
            required=True,
            availability=_avail(vib_ok if events else False),
            segments_used=len(events),
        ),
        _criterion_row(
            criterion_id="localization",
            label=spec["localization"]["label"],
            required=True,
            availability=_avail(has_core or bool(reg_eps)),
            evidence=[
                f"episodes={len(reg_eps)}",
                f"core_span={'yes' if has_core else 'no'}",
            ],
            segments_used=len(reg_eps),
        ),
    ]


def _contact_criteria(segments: list[dict[str, Any]], dim: dict[str, Any]) -> list[dict[str, Any]]:
    gif_n = sum(
        1
        for s in segments
        if ((s.get("level2_proxies") or {}).get("glottal_source") or {}).get("valid")
    )
    harm_n = sum(
        1
        for s in segments
        if (s.get("observations") or {}).get("raw_h1_h2_proxy_db") is not None
    )
    presence = sum(1 for s in segments if vocal_presence_ok(s))
    contact_valid = sum(1 for s in segments if dim_valid(s, "glottal_contact"))
    spec = {c["criterion_id"]: c for c in criteria_for("glottal_contact_profile")}
    return [
        _criterion_row(
            criterion_id="vocal_presence",
            label=spec["vocal_presence"]["label"],
            required=True,
            availability=_avail(presence >= 2),
            segments_used=presence,
        ),
        _criterion_row(
            criterion_id="glottal_source",
            label=spec["glottal_source"]["label"],
            required=True,
            availability="NOT_AVAILABLE" if gif_n == 0 else _avail(gif_n >= 2),
            evidence=[f"gif_valid={gif_n}"],
            segments_used=gif_n,
        ),
        _criterion_row(
            criterion_id="harmonic",
            label=spec["harmonic"]["label"],
            required=True,
            availability=_avail(harm_n >= 2),
            evidence=[f"h1h2_segments={harm_n}"],
            segments_used=harm_n,
        ),
        _criterion_row(
            criterion_id="evaluable_coverage",
            label=spec["evaluable_coverage"]["label"],
            required=True,
            availability=_avail(contact_valid >= cfg.MIN_SEGMENTS_GLOBAL),
            evidence=[f"contact_valid={contact_valid}"],
            segments_used=contact_valid,
        ),
    ]


def _generic_criteria(
    dimension_id: str,
    dim: dict[str, Any],
    segments: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fallback evaluator for dims without specialized builders."""
    valid_n = int(dim.get("valid_segment_count") or len([s for s in segments if s.get("valid")]))
    status = (dim.get("status") or "UNKNOWN").upper()
    hidden = bool(dim.get("hidden"))
    conf = dim.get("confidence_label") or "low"
    rows = []
    for c in criteria_for(dimension_id):
        cid = c["criterion_id"]
        if cid in ("evaluable_coverage", "phrase_energy", "proxy_available", "vibrato_detection"):
            ok = valid_n >= 2 and status != "UNKNOWN" and conf != "low"
            if dimension_id == "vibrato_control":
                ok = status not in ("UNKNOWN",) and not hidden
            rows.append(
                _criterion_row(
                    criterion_id=cid,
                    label=c["label"],
                    required=c["required"],
                    availability=_avail(ok) if not (hidden and status == "UNKNOWN") else "INSUFFICIENT",
                    segments_used=valid_n,
                )
            )
        elif cid == "localization":
            typemap = {
                "vocal_effort_strain": ("HIGH_NOTE", "GENERAL_EFFORT"),
                "onset_offset_coordination": ("ABRUPT_ONSET",),
            }
            types = typemap.get(dimension_id, ())
            n = sum(1 for e in episodes if e.get("type") in types)
            rows.append(
                _criterion_row(
                    criterion_id=cid,
                    label=c["label"],
                    required=c["required"],
                    availability=_avail(n >= 1),
                    evidence=[f"episodes={n}"],
                    segments_used=n,
                )
            )
        elif cid == "effort_multi_sign":
            ok = status in ("OCCASIONAL", "MODERATE", "REPEATED", "HIGH") or (
                status == "LOW" and conf in ("medium", "high")
            )
            rows.append(
                _criterion_row(
                    criterion_id=cid,
                    label=c["label"],
                    required=c["required"],
                    availability=_avail(ok or (status == "LOW" and valid_n >= 3)),
                    segments_used=valid_n,
                )
            )
        elif cid in ("onset_metric", "repetition", "spectral_evidence", "formant_or_band", "regularity_depth"):
            ok = status not in ("UNKNOWN",) and conf != "low"
            rows.append(
                _criterion_row(
                    criterion_id=cid,
                    label=c["label"],
                    required=c["required"],
                    availability=_avail(ok),
                    segments_used=valid_n,
                )
            )
        else:
            rows.append(
                _criterion_row(
                    criterion_id=cid,
                    label=c["label"],
                    required=c["required"],
                    availability="INSUFFICIENT" if hidden or status == "UNKNOWN" else "SUFFICIENT",
                    segments_used=valid_n,
                )
            )
    return rows


def _sufficiency_from_criteria(criteria: list[dict[str, Any]], dimension_id: str) -> str:
    req = [c for c in criteria if c.get("required")]
    if not req:
        return "UNAVAILABLE"
    met = sum(1 for c in req if c.get("availability") == "SUFFICIENT")
    unavailable = sum(1 for c in req if c.get("availability") == "NOT_AVAILABLE")
    if unavailable == len(req):
        return "UNAVAILABLE"
    need = coaching_min_required(dimension_id)
    # For sufficiency of *measurement*, require majority of required criteria available
    if met >= max(need, int(0.75 * len(req) + 0.5)):
        return "SUFFICIENT"
    if met >= 1:
        return "PARTIAL"
    return "INSUFFICIENT"


def _eligibility(
    *,
    sufficiency: str,
    finding: str,
    dimension_id: str,
    criteria: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
    dim: dict[str, Any],
) -> str:
    if sufficiency in ("INSUFFICIENT", "UNAVAILABLE"):
        return "NEEDS_CONFIRMATION"
    req = [c for c in criteria if c.get("required")]
    met = sum(1 for c in req if c.get("availability") == "SUFFICIENT")
    if met < coaching_min_required(dimension_id):
        return "NEEDS_CONFIRMATION"
    # Finding must be an observed concern-like state for coaching YES
    status = (dim.get("status") or "").upper()
    concern_statuses = {
        "HIGH",
        "MODERATE",
        "OCCASIONAL",
        "INTERMITTENT",
        "REPEATED",
        "REPEATED_IRREGULAR",
        "TRANSITION_EVENTS",
        "ABRUPT_LIKE",
        "AIRY_LIKE",
    }
    if finding != "OBSERVED" or status not in concern_statuses:
        return "NO"
    # Localization for coachable dims
    needs_loc = dimension_id in (
        "air_leakage_breathiness",
        "phonation_regularity",
        "register_configuration",
        "vocal_effort_strain",
        "onset_offset_coordination",
    )
    if needs_loc:
        type_map = {
            "air_leakage_breathiness": ("AIR_LEAKAGE",),
            "phonation_regularity": ("ROUGHNESS",),
            "register_configuration": ("REGISTER_TRANSITION",),
            "vocal_effort_strain": ("HIGH_NOTE", "GENERAL_EFFORT"),
            "onset_offset_coordination": ("ABRUPT_ONSET",),
        }
        types = type_map.get(dimension_id, ())
        if not any(e.get("type") in types for e in episodes):
            return "NEEDS_CONFIRMATION"
    if sufficiency != "SUFFICIENT":
        return "NEEDS_CONFIRMATION"
    return "YES"


def _summary_line(row: dict[str, Any]) -> str:
    suf = row["measurement_sufficiency_label"]
    finding = row["finding_label"]
    miss = [
        c["label"]
        for c in row.get("criteria") or []
        if c.get("required") and c.get("availability") in ("INSUFFICIENT", "NOT_AVAILABLE")
    ]
    if row["measurement_sufficiency"] in ("INSUFFICIENT", "UNAVAILABLE"):
        miss_txt = "·".join(miss[:3]) if miss else "필수 단서"
        return f"판단 근거 {suf} → {finding}. 부족한 기준: {miss_txt}."
    if row["finding"] == "NOT_PROMINENT":
        return f"판단 근거 {suf} → {finding}. 충분히 관찰했지만 뚜렷한 경향은 없었어요."
    return f"판단 근거 {suf} → {finding}."


def build_dimension_row(
    dimension_id: str,
    dim: dict[str, Any],
    *,
    segments: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
) -> dict[str, Any]:
    if dimension_id == "air_leakage_breathiness":
        criteria = _breathiness_criteria(segments, dim)
    elif dimension_id == "phonation_regularity":
        criteria = _roughness_criteria(segments, dim)
    elif dimension_id == "register_configuration":
        criteria = _register_criteria(dim, episodes)
    elif dimension_id == "glottal_contact_profile":
        criteria = _contact_criteria(segments, dim)
    else:
        criteria = _generic_criteria(dimension_id, dim, segments, episodes)

    sufficiency = _sufficiency_from_criteria(criteria, dimension_id)
    # Force UNDETERMINED when insufficient — never treat as LOW finding
    finding = _finding_from_status(dim.get("status") or "UNKNOWN", sufficiency)
    eligibility = _eligibility(
        sufficiency=sufficiency,
        finding=finding,
        dimension_id=dimension_id,
        criteria=criteria,
        episodes=episodes,
        dim=dim,
    )
    cov = dim.get("breathiness_coverage") or dim.get("roughness_coverage") or dim.get("profile") or {}
    req = [c for c in criteria if c.get("required")]
    met = sum(1 for c in req if c.get("availability") == "SUFFICIENT")
    row = {
        "dimension_id": dimension_id,
        "display_name": dim.get("display_name")
        or cfg.DIMENSION_DISPLAY.get(dimension_id, dimension_id),
        "measurement_sufficiency": sufficiency,
        "measurement_sufficiency_label": _user_sufficiency(sufficiency),
        "finding": finding,
        "finding_label": _user_finding(finding),
        "engine_status": dim.get("status"),
        "coaching_eligibility": eligibility,
        "coaching_eligibility_label": _user_eligibility(eligibility),
        "criteria": criteria,
        "required_total": len(req),
        "required_satisfied": met,
        "required_minimum": coaching_min_required(dimension_id),
        "evaluable_segments": cov.get("n_evaluable_segments")
        or cov.get("evaluable")
        or dim.get("valid_segment_count"),
        "total_segments": cov.get("n_total_segments") or len(segments),
        "positive_segments": cov.get("n_positive_segments") or cov.get("positive"),
        "negative_segments": cov.get("n_negative_segments") or cov.get("negative"),
        "insufficient_segments": cov.get("n_insufficient_segments") or cov.get("insufficient"),
        "confidence_label": dim.get("confidence_label"),
        "hidden_from_main_cards": bool(dim.get("hidden")),
        "note": "기준 충족/미충족은 측정 근거 충분 여부이며 발성 좋고 나쁨이 아닙니다.",
    }
    row["summary"] = _summary_line(row)
    return row


def build_criteria_matrix(
    *,
    dimensions: dict[str, Any],
    segments: Optional[list[dict[str, Any]]] = None,
    episodes: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    segments = segments or []
    episodes = episodes or []
    out = []
    for dim_id in DIMENSION_ORDER:
        dim = dimensions.get(dim_id) or {
            "dimension_id": dim_id,
            "display_name": cfg.DIMENSION_DISPLAY.get(dim_id, dim_id),
            "status": "UNKNOWN",
            "hidden": True,
            "confidence_label": "low",
        }
        out.append(
            build_dimension_row(dim_id, dim, segments=segments, episodes=episodes)
        )
    return out


def build_candidate_comparison(
    criteria_matrix: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Why register (or another) became primary — transparent ranking inputs."""
    by_dim = {r["dimension_id"]: r for r in criteria_matrix}
    rows = []
    for h in hypotheses:
        if h.get("id") == "_MEASUREMENT_ONLY":
            continue
        dim_id = BOTTLENECK_DIMENSION.get(h.get("id") or "")
        crow = by_dim.get(dim_id) if dim_id else None
        rows.append(
            {
                "bottleneck_id": h.get("id"),
                "label": h.get("user_title") or h.get("id"),
                "dimension_id": dim_id,
                "criterion_coverage": (
                    f"{crow['required_satisfied']}/{crow['required_total']}" if crow else None
                ),
                "measurement_sufficiency": crow.get("measurement_sufficiency") if crow else "UNAVAILABLE",
                "finding": crow.get("finding") if crow else "UNDETERMINED",
                "evidence_strength": h.get("confidence_label"),
                "localization_available": bool(h.get("supporting_episode_ids")),
                "confidence": h.get("confidence_label"),
                "coaching_eligible": (crow or {}).get("coaching_eligibility") == "YES",
                "coaching_eligibility": (crow or {}).get("coaching_eligibility"),
                "impact": h.get("impact"),
            }
        )
    return rows


def attach_primary_criteria_explanation(
    primary: Optional[dict[str, Any]],
    criteria_matrix: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    if not primary:
        return primary
    dim_id = BOTTLENECK_DIMENSION.get(primary.get("id") or "")
    crow = next((r for r in criteria_matrix if r["dimension_id"] == dim_id), None)
    if not crow:
        return primary
    primary = dict(primary)
    primary["criteria_matrix_row"] = {
        "dimension_id": crow["dimension_id"],
        "measurement_sufficiency": crow["measurement_sufficiency"],
        "finding": crow["finding"],
        "coaching_eligibility": crow["coaching_eligibility"],
        "required_satisfied": crow["required_satisfied"],
        "required_total": crow["required_total"],
    }
    primary["satisfied_criteria"] = [
        {
            "criterion_id": c["criterion_id"],
            "label": c["label"],
            "availability": c["availability"],
            "direction": c.get("direction"),
        }
        for c in crow.get("criteria") or []
        if c.get("availability") == "SUFFICIENT"
    ]
    primary["missing_criteria"] = [
        {
            "criterion_id": c["criterion_id"],
            "label": c["label"],
            "availability": c["availability"],
        }
        for c in crow.get("criteria") or []
        if c.get("required") and c.get("availability") != "SUFFICIENT"
    ]
    primary["criteria_user_summary"] = crow.get("summary")
    return primary
