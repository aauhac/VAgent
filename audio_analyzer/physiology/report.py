"""
physiology/report.py
--------------------
Deterministic premium report — v1.3 product visibility policy.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .coaching import build_coaching, build_training_routine, safety_disclaimer
from .config import (
    ATTEMPTED_PRIMARY_MECHANISMS,
    AUXILIARY_UX_MECHANISMS,
    CONDITIONAL_PRIMARY_MECHANISMS,
    INFERENCE_VERSION,
    LITERATURE_REGISTRY_VERSION,
    MECHANISM_DISPLAY,
    PRIMARY_UX_MECHANISMS,
    REPORT_VERSION,
    RESEARCH_ONLY_MECHANISMS,
    SAFETY_DISCLAIMER,
    SAFETY_STOP_INSTRUCTION,
    product_visibility,
)
from .eligibility import evaluate_eligibility
from .evidence import build_evidence_bundle
from .inference import infer_mechanisms
from .literature_registry import registry_meta


def _why_easy(m: dict[str, Any]) -> str:
    prov = m.get("evidence_family_provenance") or []
    tasks = m.get("source_tasks") or []
    parts = []
    if tasks:
        pretty = []
        for t in tasks:
            pretty.append(
                {
                    "sustain_a": "'아—' 지속음",
                    "sustain_i": "'이—' 지속음",
                    "siren": "사이렌",
                    "dynamic_swell": "강약 스웰",
                }.get(t, t)
            )
        parts.append(" · ".join(pretty) + "에서 비슷한 방향")
    if prov:
        parts.append("근거 계열: " + " / ".join(prov))
    return " · ".join(parts) if parts else "관련 관측이 모였어요."


def _scrub_evidence_bits(parts: list[str]) -> str:
    """Drop raw metric dumps from user-facing observation strings."""
    import re

    keep: list[str] = []
    banned = re.compile(
        r"(sustained_residual|f0_continuity|voiced_dropout|cepstral|hnr_|h1_h2|"
        r"onset_slope|≈|GIF|source proxy|evidence_mass|directionality)",
        re.I,
    )
    for p in parts:
        s = str(p).strip()
        if not s or banned.search(s):
            continue
        keep.append(s)
    return " · ".join(keep[:4])


def _public_card(
    m: dict[str, Any],
    coaching: list[dict[str, Any]],
    *,
    eligibility: dict[str, Any],
) -> dict[str, Any]:
    coach = next((c for c in coaching if c["mechanism_id"] == m["mechanism_id"]), None)
    observed = _scrub_evidence_bits(m.get("supporting_evidence") or []) or "관련 음향 특성이 관찰됐어요."
    may_mean = m.get("summary") or ""
    cannot = (m.get("limitations") or ["이 녹음만으로 해부학적 사실을 확인할 수 없습니다."])[0]
    return {
        "mechanism_id": m["mechanism_id"],
        "display_name": m["display_name"],
        "status": m["status"],
        "status_label": m.get("status_label") or m["status"],
        "confidence_label": m.get("confidence_label"),
        "summary": m["summary"],
        "what_was_observed": observed,
        "what_it_may_mean": may_mean,
        "what_we_cannot_know": cannot,
        "why_this_judgment": _why_easy(m),
        "alternative_explanations": (m.get("alternative_explanations") or [])[:4],
        "evidence_family_provenance": m.get("evidence_family_provenance") or [],
        "source_tasks": m.get("source_tasks") or [],
        "product_visibility": eligibility.get("product_visibility")
        or product_visibility(m["mechanism_id"]),
        "user_visible": True,
        "eligible": bool(eligibility.get("eligible")),
        "motor_cue": (coach or {}).get("motor_cue"),
        "exercise": (
            {
                "exercise_id": coach.get("exercise_id"),
                "duration": coach.get("duration"),
                "stop_conditions": coach.get("stop_conditions"),
            }
            if coach
            else None
        ),
    }


def _uncertain_card(
    m: dict[str, Any],
    eligibility: dict[str, Any],
) -> dict[str, Any]:
    reasons = eligibility.get("reasons") or []
    return {
        "mechanism_id": m["mechanism_id"],
        "display_name": m["display_name"],
        "status": "unknown",
        "status_label": "판단 어려움",
        "summary": (
            reasons[0]["message"]
            if reasons
            else "이번 녹음에서는 충분한 근거가 없어 이 항목은 판단하지 않았어요."
        ),
        "why_not_judged": [r["message"] for r in reasons],
        "why_codes": [r["code"] for r in reasons],
        "retry_tasks": eligibility.get("retry_tasks") or [],
        "product_visibility": eligibility.get("product_visibility"),
        "user_visible": True,
        "eligible": False,
    }


def _supporting_observation(m: dict[str, Any]) -> Optional[dict[str, Any]]:
    """WEAK / research-only → observation wording only, not diagnosis."""
    mid = m["mechanism_id"]
    if mid not in RESEARCH_ONLY_MECHANISMS:
        return None
    support = m.get("supporting_evidence") or []
    if not support:
        return None
    # Very limited observation-level text
    if mid == "vocal_tract_resonance_balance":
        text = "모음에 따라 스펙트럼 분포가 달라지는 경향이 관찰됐어요."
    elif mid == "release_coordination":
        text = "끝음 구간의 에너지 변화가 관측됐어요. 끝음 조절 결론은 내리지 않았어요."
    elif mid == "phonatory_efficiency":
        text = "주기성 관련 관측이 있으나 ‘발성 효율’로 점수화하지는 않았어요."
    else:
        text = "보조 관측만 남겼어요."
    return {
        "mechanism_id": mid,
        "display_name": MECHANISM_DISPLAY[mid],
        "observation": text,
        "note": "메커니즘 진단이 아니라 보조 관찰입니다.",
    }


def physiology_debug_enabled() -> bool:
    return (os.environ.get("PHYSIOLOGY_DEBUG") or "").lower() in ("1", "true", "yes")


def build_premium_report(
    *,
    session_id: str,
    task_results: list[dict[str, Any]],
    song_summary: Optional[dict[str, Any]] = None,
    safety_flags: Optional[list[str]] = None,
    include_scientific_debug: Optional[bool] = None,
) -> dict[str, Any]:
    safety_flags = safety_flags or []
    if include_scientific_debug is None:
        include_scientific_debug = physiology_debug_enabled()

    mechanisms = infer_mechanisms(task_results, safety_flags=safety_flags)
    bundle = build_evidence_bundle(task_results)
    by_id = {m["mechanism_id"]: m for m in mechanisms}

    # Attach eligibility
    elig_map: dict[str, dict[str, Any]] = {}
    for m in mechanisms:
        elig_map[m["mechanism_id"]] = evaluate_eligibility(
            m["mechanism_id"], m, task_results, bundle
        )
        m["eligibility"] = elig_map[m["mechanism_id"]]
        m["user_visible"] = elig_map[m["mechanism_id"]].get("user_visible", False)
        m["product_visibility"] = elig_map[m["mechanism_id"]].get("product_visibility")

    coaching = build_coaching(
        [
            m
            for m in mechanisms
            if elig_map[m["mechanism_id"]].get("eligible")
            and m.get("status") != "unknown"
            and product_visibility(m["mechanism_id"])
            in ("PRIMARY", "CONDITIONAL_PRIMARY", "SECONDARY")
        ],
        safety_flags=safety_flags,
    )
    routine = build_training_routine(coaching)

    reliable_findings: list[dict[str, Any]] = []
    uncertain_findings: list[dict[str, Any]] = []

    # PRIMARY always attempted
    for mid in PRIMARY_UX_MECHANISMS:
        m = by_id.get(mid)
        if not m:
            continue
        elig = elig_map[mid]
        if elig.get("eligible") and m["status"] != "unknown":
            reliable_findings.append(_public_card(m, coaching, eligibility=elig))
        else:
            uncertain_findings.append(_uncertain_card(m, elig))

    # CONDITIONAL_PRIMARY only when eligible → reliable; else uncertain if unknown/attempted
    for mid in CONDITIONAL_PRIMARY_MECHANISMS:
        m = by_id.get(mid)
        if not m:
            continue
        elig = elig_map[mid]
        if elig.get("eligible") and m["status"] != "unknown":
            reliable_findings.append(_public_card(m, coaching, eligibility=elig))
        else:
            uncertain_findings.append(_uncertain_card(m, elig))

    # SECONDARY: only if eligible (corroborated)
    supporting_observations: list[dict[str, Any]] = []
    for mid in AUXILIARY_UX_MECHANISMS:
        m = by_id.get(mid)
        if not m:
            continue
        elig = elig_map[mid]
        if elig.get("eligible") and m["status"] != "unknown":
            card = _public_card(m, coaching, eligibility=elig)
            card["tier_note"] = "보조 관찰"
            supporting_observations.append(
                {
                    "mechanism_id": mid,
                    "display_name": m["display_name"],
                    "observation": m["summary"],
                    "note": "주요 카드가 아닌 보조 관찰입니다.",
                    "confidence_label": m.get("confidence_label"),
                }
            )

    for mid in RESEARCH_ONLY_MECHANISMS:
        m = by_id.get(mid)
        if not m:
            continue
        obs = _supporting_observation(m)
        if obs:
            supporting_observations.append(obs)

    # Coverage
    eligible_count = sum(
        1
        for mid in ATTEMPTED_PRIMARY_MECHANISMS
        if elig_map.get(mid, {}).get("eligible")
        and (by_id.get(mid) or {}).get("status") != "unknown"
    )
    attempted = len(ATTEMPTED_PRIMARY_MECHANISMS)
    coverage = {
        "eligible_mechanisms": eligible_count,
        "attempted_primary_mechanisms": attempted,
        "uncertain_mechanisms": len(uncertain_findings),
        "ratio": round(eligible_count / max(attempted, 1), 3),
    }

    retry_tasks = sorted(
        {
            t
            for u in uncertain_findings
            for t in (u.get("retry_tasks") or [])
        }
    )
    low_coverage = eligible_count < max(2, attempted // 2)
    coverage_note = None
    if low_coverage:
        coverage_note = (
            "조금 더 정확한 진단을 위해 일부 Task를 다시 녹음해보세요."
            if retry_tasks
            else "이번 측정에서는 판단할 근거가 적은 편이에요. 억지로 결론을 채우지 않았어요."
        )

    n_rel = len(reliable_findings)
    n_unc = len(uncertain_findings)
    if reliable_findings:
        focus = next(
            (
                f
                for f in reliable_findings
                if f["status"] not in ("balanced", "unknown")
            ),
            reliable_findings[0],
        )
        summary_text = focus["summary"]
        headline = summary_text
    else:
        summary_text = (
            "표준 발성 과제를 분석했어요. "
            "이번 세션에서 확인된 특징을 중심으로 정리했어요."
        )
        headline = summary_text

    task_metrics = []
    for tr in task_results:
        task_metrics.append(
            {
                "task_id": tr.get("task_id"),
                "attempt": tr.get("attempt"),
                "quality_status": (tr.get("quality") or {}).get("status"),
                "observations": [
                    {
                        "metric_id": o.get("metric_id"),
                        "value": o.get("value"),
                        "unit": o.get("unit"),
                        "valid": o.get("valid"),
                    }
                    for o in (tr.get("observations") or [])
                ],
            }
        )

    report: dict[str, Any] = {
        "report_version": REPORT_VERSION,
        "inference_version": INFERENCE_VERSION,
        "literature_registry_version": LITERATURE_REGISTRY_VERSION,
        "session_id": session_id,
        "summary": {
            "title": "정밀 발성 진단",
            "lead": "표준 발성 과제로 확인한 기본 발성 특성이에요.",
            "text": summary_text,
            "headline": headline,
            "reliable_count": n_rel,
            "uncertain_count": n_unc,
            "coverage_note": coverage_note,
            "safety_note": (
                "불편 신호가 있어 강한 훈련은 제한했어요." if safety_flags else None
            ),
        },
        "reliable_findings": reliable_findings,
        "uncertain_findings": uncertain_findings,
        "supporting_observations": supporting_observations,
        "training_plan": {
            "title": "오늘의 3분 연습",
            "items": routine,
            "stop_conditions": SAFETY_STOP_INSTRUCTION,
            "motor_cues": [
                {"mechanism_id": c["mechanism_id"], "cue": c["motor_cue"], "duration": c["duration"]}
                for c in coaching
            ],
        },
        "safety": {
            "disclaimer": SAFETY_DISCLAIMER,
            "stop_conditions": SAFETY_STOP_INSTRUCTION,
            "flags": safety_flags,
        },
        "mechanism_coverage": coverage,
        "retry_recommendation": {
            "tasks": retry_tasks,
            "message": coverage_note,
        },
        # Back-compat section keys for existing UI
        "sections": {
            "A_summary": {
                "title": "오늘의 핵심",
                "text": summary_text,
                "headline": headline,
                "note": "항목을 억지로 채우지 않습니다. 근거가 부족하면 판단하지 않습니다.",
                "safety_note": (
                    "불편 신호가 있어 강한 훈련은 제한했어요." if safety_flags else None
                ),
            },
            "B_reliable": {
                "title": "신뢰할 수 있게 본 항목",
                "items": reliable_findings,
            },
            "B_uncertain": {
                "title": "이번에는 판단하기 어려운 항목",
                "items": uncertain_findings,
            },
            "B_needs_more": {
                "title": "추가 측정이 필요한 항목",
                "items": [
                    {
                        "mechanism_id": mid,
                        "display_name": MECHANISM_DISPLAY[mid],
                        "reason": "현재 음향 관측만으로는 신뢰할 수 있는 결론을 내리기 어려워요.",
                    }
                    for mid in RESEARCH_ONLY_MECHANISMS
                ],
            },
            "B_supporting": {
                "title": "보조 관찰",
                "items": supporting_observations,
            },
            "C_mechanism_details": {
                "title": "상세 설명",
                "items": reliable_findings,
            },
            "D_song_highlights": {
                "title": "일반 노래에서 발견된 대표 구간",
                "items": (song_summary or {}).get("timeline_preview") or [],
            },
            "E_diagnostic_tasks": {"title": "Diagnostic Task 결과", "items": task_metrics},
            "F_training_routine": {
                "title": "오늘의 3분 연습",
                "items": routine,
                "stop_conditions": SAFETY_STOP_INSTRUCTION,
            },
            "G_next_compare": {
                "title": "다시 확인할 항목",
                "items": retry_tasks
                or [
                    "cepstral_prominence_proxy_db",
                    "f0_continuity_ratio",
                    "envelope_smoothness_index",
                ],
            },
            "H_disclaimer": {"title": "안내", "text": SAFETY_DISCLAIMER},
        },
        "physiology_assessments": mechanisms,
        "coaching_recommendations": coaching,
        "llm_json": None,
        "disclaimer": safety_disclaimer(),
    }

    if include_scientific_debug:
        report["scientific_debug"] = {
            "literature": registry_meta(),
            "mechanisms_trace": [
                {
                    "mechanism_id": m["mechanism_id"],
                    "rule_id": m.get("rule_id"),
                    "rule_version": m.get("rule_version"),
                    "literature_strength": m.get("literature_strength"),
                    "confidence_numeric": m.get("confidence"),
                    "confidence_cap": m.get("confidence_cap"),
                    "evidence_families": m.get("evidence_families_used"),
                    "product_visibility": m.get("product_visibility"),
                    "eligibility": m.get("eligibility"),
                    "scientific_trace": m.get("scientific_trace"),
                }
                for m in mechanisms
            ],
        }

    return report


def public_premium_report(report: dict[str, Any]) -> dict[str, Any]:
    """Strip engineering fields for end-user API."""
    out = {k: v for k, v in report.items() if k != "scientific_debug"}
    slim = []
    for m in out.get("physiology_assessments") or []:
        slim.append(
            {
                "mechanism_id": m.get("mechanism_id"),
                "display_name": m.get("display_name"),
                "status": m.get("status"),
                "status_label": m.get("status_label"),
                "confidence_label": m.get("confidence_label"),
                "summary": m.get("summary"),
                "product_visibility": m.get("product_visibility"),
                "user_visible": m.get("user_visible"),
                "evidence_family_provenance": m.get("evidence_family_provenance"),
            }
        )
    out["physiology_assessments"] = slim
    return out
