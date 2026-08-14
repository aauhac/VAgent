"""Canonical effort assessment (v2.12).

Re-interprets existing v2.8–v2.10 effort evidence for absolute severity
presentation. Does NOT retune detector thresholds.
"""

from __future__ import annotations

from typing import Any, Optional


SEVERITY_ORDER = ("LOW", "MILD", "MODERATE", "HIGH")

# Representative UI axis positions — NOT engine measurement scores.
SEVERITY_DISPLAY_CONTINUUM = {
    "UNKNOWN": 0.5,
    "LOW": 0.18,
    "MILD": 0.38,
    "MODERATE": 0.62,
    "HIGH": 0.85,
}

SEVERITY_LABELS_KO = {
    "UNKNOWN": "이번 녹음에서 뚜렷하게 구분되지 않음",
    "LOW": "편안한 편",
    "MILD": "일부 구간에서 힘이 증가",
    "MODERATE": "힘이 들어가는 편",
    "HIGH": "힘이 많이 들어가는 편",
}


def _rank(sev: str) -> int:
    try:
        return SEVERITY_ORDER.index(sev)
    except ValueError:
        return -1


def _max_sev(a: str, b: str) -> str:
    if _rank(a) >= _rank(b):
        return a
    return b


def _confidence_label(raw: Optional[str]) -> str:
    s = (raw or "").lower()
    if s in ("high", "높음"):
        return "high"
    if s in ("medium", "med", "보통", "중"):
        return "medium"
    if s in ("low", "낮음"):
        return "low"
    return "medium" if raw else "low"


def _hit_ratio(profile: dict[str, Any], valid_n: int) -> float:
    hits = int(profile.get("hit_segments") or profile.get("effort_hit_segments") or 0)
    if valid_n <= 0:
        return 0.0
    return float(hits) / float(valid_n)


def _count_effort_episodes(episodes: Optional[list[dict[str, Any]]]) -> int:
    n = 0
    for e in episodes or []:
        t = (e.get("type") or "").upper()
        if t in ("GENERAL_EFFORT", "HIGH_NOTE") and (
            t == "GENERAL_EFFORT"
            or ((e.get("feature_matrix") or {}).get("effort") or {}).get("strain_like", 0) >= 0.35
            or e.get("concern")
        ):
            n += 1
    return n


def _high_note_severity(high_note_profile: Optional[dict[str, Any]]) -> Optional[str]:
    if not high_note_profile or not high_note_profile.get("available"):
        return None
    axes = high_note_profile.get("axes") or high_note_profile.get("profile") or {}
    effort_axis = (
        axes.get("high_note_effort_cost")
        or axes.get("effort_cost")
        or high_note_profile.get("high_note_effort_cost")
        or {}
    )
    st = (effort_axis.get("status") or "").upper()
    cont = effort_axis.get("continuum")
    if st == "INCREASED":
        if cont is not None and float(cont) >= 0.55:
            return "HIGH"
        return "MODERATE"
    if st == "STABLE":
        return "LOW"
    if st == "DECREASED":
        return "LOW"
    return None


def build_effort_assessment(
    effort_dim: Optional[dict[str, Any]],
    *,
    episodes: Optional[list[dict[str, Any]]] = None,
    high_note_profile: Optional[dict[str, Any]] = None,
    valid_segment_count: Optional[int] = None,
) -> dict[str, Any]:
    """
    Canonical interpretation shared by Main Finding, Vocal Profile, High-Note.

    Support-only evidence cannot produce MODERATE/HIGH (core families required).
    """
    dim = effort_dim or {}
    profile = dict(dim.get("profile") or {})
    status = (dim.get("status") or "UNKNOWN").upper()
    peak = float(profile.get("effort_score") or dim.get("continuum_0_to_1") or 0.0)
    mean_score = float(profile.get("mean_segment_effort_score") or 0.0)
    core = int(profile.get("core_family_count") or 0)
    support = int(profile.get("support_family_count") or 0)
    persistent_n = int(profile.get("persistent_segments") or profile.get("recovery_cost") or 0)
    persistent = persistent_n > 0
    hits = int(profile.get("hit_segments") or profile.get("effort_hit_segments") or 0)
    valid_n = int(
        valid_segment_count
        or dim.get("valid_segment_count")
        or (dim.get("evidence") or {}).get("n_valid")
        or 0
    )
    if valid_n <= 0 and hits:
        # Prefer explicit prevalence string when count unknown
        valid_n = max(hits * 4, hits)
    hit_ratio = _hit_ratio(profile, valid_n) if valid_n else (1.0 if hits else 0.0)
    prevalence = (dim.get("prevalence") or profile.get("prevalence") or "unknown")
    localized_episode_count = _count_effort_episodes(episodes)
    high_note_sev = _high_note_severity(high_note_profile)

    if status in ("UNKNOWN", "UNAVAILABLE", "AMBIGUOUS") or dim.get("hidden"):
        # Presentation: UNKNOWN is not LOW strength — do not retune detector thresholds
        global_sev = "UNKNOWN"
        conf = "low"
        evidence_source = ["insufficient_effort_dimension"]
    elif status == "LOW" or hits <= 0:
        global_sev = "LOW"
        conf = _confidence_label(dim.get("confidence_label"))
        evidence_source = ["no_elevated_effort_hits"]
    else:
        # --- multi-factor absolute severity (thresholds frozen at detector) ---
        evidence_source = [
            f"status:{status}",
            f"peak:{round(peak, 3)}",
            f"hit_ratio:{round(hit_ratio, 3)}",
            f"core:{core}",
            f"support:{support}",
            f"persistent:{persistent}",
            f"episodes:{localized_episode_count}",
        ]
        conf = _confidence_label(dim.get("confidence_label"))

        # Support-only guard
        if core < 1:
            global_sev = "MILD" if hits >= 1 else "LOW"
            evidence_source.append("support_only_capped_mild")
        elif status == "REPEATED":
            if core >= 2 and (persistent or hit_ratio >= 0.35):
                global_sev = "HIGH"
            else:
                global_sev = "MODERATE"
        elif status == "MODERATE":
            if core >= 2 and (persistent or hit_ratio >= 0.25 or peak >= 0.55):
                global_sev = "MODERATE"
            elif hits >= 2 and core >= 1 and peak >= 0.45:
                global_sev = "MODERATE"
            else:
                global_sev = "MILD"
        else:
            # OCCASIONAL (localized)
            # Strong localized: peak + core families + persistence → MODERATE
            if core >= 2 and persistent and peak >= 0.50:
                global_sev = "MODERATE"
                evidence_source.append("localized_strong_core_persistent")
            elif core >= 1 and peak >= 0.55 and localized_episode_count >= 1:
                global_sev = "MODERATE"
                evidence_source.append("localized_peak_with_episode")
            else:
                global_sev = "MILD"

    localized_peak_sev = global_sev
    if hits >= 1 and core >= 1 and peak >= 0.50:
        localized_peak_sev = _max_sev(global_sev, "MODERATE" if peak >= 0.50 else "MILD")
    if hits >= 1 and core >= 2 and peak >= 0.65 and persistent:
        localized_peak_sev = "HIGH"

    # High-note context (does not force global HIGH by itself)
    if high_note_sev == "HIGH" and global_sev == "LOW":
        context_note = "전반적으로는 편안하지만, 고음에서만 힘이 크게 증가해요."
    elif high_note_sev in ("MODERATE", "HIGH") and global_sev in ("MILD", "MODERATE", "HIGH"):
        context_note = "전반적으로 힘이 들어가는 편이며, 특히 높은 음에서 더 크게 증가해요."
    elif global_sev == "MODERATE" and hits <= 1:
        context_note = "특정 구간에서 힘이 크게 증가하는 패턴이 관찰됐어요."
    elif global_sev == "HIGH":
        context_note = "여러 구간에서 힘이 크게 증가하는 패턴이 반복됐어요."
    elif global_sev == "MILD":
        context_note = "일부 구간에서 힘이 증가하는 패턴이 관찰됐어요."
    elif global_sev == "LOW":
        context_note = "과도하게 힘이 증가하는 패턴은 두드러지지 않았어요."
    elif global_sev == "UNKNOWN":
        context_note = "힘 사용은 이번 녹음에서 뚜렷하게 구분되지 않았어요."
    else:
        context_note = None

    display_continuum = SEVERITY_DISPLAY_CONTINUUM.get(global_sev, 0.5)
    label = SEVERITY_LABELS_KO.get(global_sev, "이번 녹음에서 뚜렷하게 구분되지 않음")
    strength_eligible = (
        global_sev == "LOW"
        and conf in ("medium", "high")
        and status not in ("UNKNOWN", "UNAVAILABLE", "AMBIGUOUS")
        and not dim.get("hidden")
    )

    return {
        "continuum": round(peak, 4) if hits or status == "LOW" else None,
        "display_continuum": display_continuum,
        "severity": global_sev,
        "global_severity": global_sev,
        "localized_peak_severity": localized_peak_sev,
        "high_note_severity": high_note_sev,
        "status": status,
        "peak_event_score": round(peak, 4),
        "mean_score": round(mean_score, 4),
        "prevalence": prevalence,
        "hit_ratio": round(hit_ratio, 4),
        "hit_segments": hits,
        "core_family_count": core,
        "support_family_count": support,
        "persistent": persistent,
        "persistent_segments": persistent_n,
        "localized_episode_count": localized_episode_count,
        "confidence_label": conf,
        "confidence_source": "criteria_coverage_or_dimension",
        "label": label,
        "context_note": context_note,
        "strength_eligible": strength_eligible,
        "evidence_source": evidence_source,
        "derived_from": {
            "peak_event_score": round(peak, 4),
            "hit_ratio": round(hit_ratio, 4),
            "prevalence": prevalence,
            "core_family_count": core,
            "support_family_count": support,
            "persistent": persistent,
            "status": status,
            "localized_episode_count": localized_episode_count,
            "high_note_severity": high_note_sev,
        },
        "engine_version": "effort-assessment-v2.12",
    }


def effort_display_bundle(assessment: dict[str, Any]) -> dict[str, Any]:
    """User-facing presentation slice (no raw family counts)."""
    sev = assessment.get("global_severity") or assessment.get("severity") or "UNKNOWN"
    return {
        "severity": sev,
        "label": assessment.get("label") or SEVERITY_LABELS_KO.get(
            sev, "이번 녹음에서 뚜렷하게 구분되지 않음"
        ),
        "continuum": assessment.get("display_continuum"),
        "display_continuum": assessment.get("display_continuum"),
        "confidence_label": assessment.get("confidence_label") or "medium",
        "context_note": assessment.get("context_note"),
        "high_note_severity": assessment.get("high_note_severity"),
        "global_severity": assessment.get("global_severity"),
        "localized_peak_severity": assessment.get("localized_peak_severity"),
        "strength_eligible": bool(assessment.get("strength_eligible")),
    }


def check_effort_report_consistency(
    *,
    assessment: Optional[dict[str, Any]],
    coaching_decision: Optional[dict[str, Any]] = None,
    dimensions: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """
    Debug/audit warnings only — never mutates production results.
    """
    issues: list[dict[str, Any]] = []
    a = assessment or {}
    decision = coaching_decision or {}
    primary = decision.get("primary_bottleneck") or decision.get("primary") or {}
    pid = primary.get("id")
    pconf = (primary.get("confidence") or "medium").lower()
    support_ids = primary.get("supporting_episode_ids") or []
    sev = (a.get("global_severity") or a.get("severity") or "LOW").upper()
    label = a.get("label") or ""

    if pid == "GENERAL_EXCESS_EFFORT" and pconf in ("medium", "high"):
        if sev == "LOW" or label in ("보통", "편안한 편"):
            if len(support_ids) >= 1 or int(a.get("localized_episode_count") or 0) >= 1:
                issues.append(
                    {
                        "id": "general_excess_effort_vs_neutral_profile",
                        "severity": "WARN",
                        "message": (
                            "GENERAL_EXCESS_EFFORT with supporting evidence "
                            f"but effort severity={sev!r} / label={label!r}"
                        ),
                    }
                )

    if pid == "EXCESS_EFFORT_HIGH_NOTE":
        hn = (a.get("high_note_severity") or "").upper()
        if hn in ("LOW", "") and sev == "LOW":
            issues.append(
                {
                    "id": "high_note_effort_primary_vs_low_cost",
                    "severity": "WARN",
                    "message": "EXCESS_EFFORT_HIGH_NOTE but high_note_severity low",
                }
            )

    dims = dimensions or {}
    leak = dims.get("air_leakage_breathiness") or {}
    if pid == "AIR_LEAKAGE" and (leak.get("status") or "").upper() == "LOW":
        issues.append(
            {
                "id": "air_leakage_vs_breath_profile",
                "severity": "WARN",
                "message": "AIR_LEAKAGE primary but breathiness status LOW",
            }
        )

    rough = dims.get("phonation_regularity") or {}
    if pid == "APERIODIC_ROUGHNESS" and (rough.get("status") or "").upper() in (
        "STABLE",
        "LOW",
    ):
        issues.append(
            {
                "id": "aperiodic_roughness_vs_regularity",
                "severity": "WARN",
                "message": "APERIODIC_ROUGHNESS primary but regularity stable/low",
            }
        )

    # Allowed: global LOW + high-note HIGH
    if sev == "LOW" and (a.get("high_note_severity") or "").upper() == "HIGH":
        if not a.get("context_note"):
            issues.append(
                {
                    "id": "global_low_highnote_high_missing_context",
                    "severity": "DEBUG",
                    "message": "global LOW + high-note HIGH should explain context",
                }
            )

    return issues


def finding_copy_for_effort(assessment: dict[str, Any], primary_id: Optional[str] = None) -> dict[str, str]:
    """Severity-aware Main Finding copy (non-anatomical)."""
    sev = (assessment.get("global_severity") or assessment.get("severity") or "LOW").upper()
    hn = (assessment.get("high_note_severity") or "").upper()
    hits = int(assessment.get("hit_segments") or 0)
    note = assessment.get("context_note") or ""

    if primary_id == "EXCESS_EFFORT_HIGH_NOTE" or (hn in ("MODERATE", "HIGH") and sev in ("LOW", "MILD")):
        return {
            "title": "고음에서 힘이 증가하는 경향",
            "detail": note
            or "전반적으로는 편안하지만, 고음에서만 힘이 크게 증가해요.",
        }
    if sev == "HIGH":
        return {
            "title": "여러 구간에서 힘이 크게 증가하는 경향",
            "detail": note or "강한 음과 높은 음을 낼 때 힘을 밀어붙이는 패턴이 반복됐어요.",
        }
    if sev == "MODERATE":
        if hits <= 1:
            return {
                "title": "특정 구간에서 힘이 크게 증가하는 경향",
                "detail": note
                or "강한 음과 높은 음을 낼 때 힘을 밀어붙이는 패턴이 관찰됐어요.",
            }
        return {
            "title": "여러 구간에서 힘이 크게 증가하는 경향",
            "detail": note or "여러 구간에서 힘을 밀어붙이는 패턴이 관찰됐어요.",
        }
    if sev == "MILD":
        return {
            "title": "일부 구간에서 힘이 증가하는 경향",
            "detail": note or "일부 구간에서 힘이 늘어나는 패턴이 관찰됐어요.",
        }
    return {
        "title": "힘 증가 패턴은 두드러지지 않음",
        "detail": note
        or "이번 녹음에서는 과도하게 힘이 증가하는 패턴은 두드러지지 않았어요.",
    }
