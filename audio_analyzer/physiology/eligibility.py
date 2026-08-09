"""
eligibility.py
--------------
Mechanism eligibility gate for user-facing Premium cards.
"""

from __future__ import annotations

from typing import Any, Optional

from . import config as cfg
from .evidence import build_evidence_bundle, count_independent_families


def _tasks_present(task_results: list[dict[str, Any]]) -> set[str]:
    return {str(t.get("task_id")) for t in task_results if t.get("task_id")}


def _quality_ok(task_results: list[dict[str, Any]], task_id: str) -> bool:
    for t in task_results:
        if t.get("task_id") != task_id:
            continue
        q = (t.get("quality") or {}).get("status")
        if q == "fail":
            return False
        return True
    return False


def _unknown_reason(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def evaluate_eligibility(
    mechanism_id: str,
    mechanism: dict[str, Any],
    task_results: list[dict[str, Any]],
    bundle: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Returns:
      eligible: bool — may appear in reliable_findings
      user_visible: bool — may appear in user report (reliable or uncertain)
      reasons: list of why not eligible / unknown
      retry_tasks: suggested task retries when quality-related
    """
    mid = cfg.canonicalize_mechanism_id(mechanism_id)
    vis = cfg.product_visibility(mid)
    bundle = bundle or build_evidence_bundle(task_results)
    tasks = _tasks_present(task_results)
    families = list(mechanism.get("evidence_families_used") or [])
    status = mechanism.get("status")
    reasons: list[dict[str, str]] = []
    retry: list[str] = []

    # RESEARCH_ONLY: never main cards
    if vis == "RESEARCH_ONLY":
        return {
            "eligible": False,
            "user_visible": False,
            "product_visibility": vis,
            "reasons": [
                _unknown_reason(
                    "research_only",
                    "현재 문헌 근거가 약해 일반 리포트 핵심 카드에는 넣지 않아요.",
                )
            ],
            "retry_tasks": [],
        }

    if status == "unknown":
        # Still user_visible as uncertain for PRIMARY / CONDITIONAL_PRIMARY
        user_visible = vis in ("PRIMARY", "CONDITIONAL_PRIMARY", "SECONDARY")
        # Collect reasons from mechanism
        contra = mechanism.get("contradicting_evidence") or []
        if any("cross-vowel" in str(c).lower() or "cross_vowel" in str(c) for c in contra):
            reasons.append(
                _unknown_reason(
                    "cross_vowel_inconsistency",
                    "/a/와 /i/에서 방향이 달라 단정하지 않았어요.",
                )
            )
        if any("missing_cross_vowel" in str(c) for c in contra):
            reasons.append(
                _unknown_reason(
                    "missing_cross_vowel",
                    "두 모음에서 같은 방향이 반복되지 않아 판단하지 않았어요.",
                )
            )
            retry.extend(["sustain_a", "sustain_i"])
        if len(families) < cfg.MIN_INDEPENDENT_FAMILIES_FOR_DIRECTION and mid not in (
            "phonation_stability",
            "register_transition_coordination",
        ):
            reasons.append(
                _unknown_reason(
                    "insufficient_evidence_families",
                    "독립된 근거 계열이 부족해 판단하지 않았어요.",
                )
            )
        if not reasons:
            reasons.append(
                _unknown_reason(
                    "not_enough_evidence",
                    "이번 녹음에서는 충분한 근거가 없어 이 항목은 판단하지 않았어요.",
                )
            )
        return {
            "eligible": False,
            "user_visible": user_visible and vis != "SECONDARY",
            "product_visibility": vis,
            "reasons": reasons,
            "retry_tasks": sorted(set(retry)),
        }

    # status assessed — check eligibility by mechanism
    if mid == "phonation_stability":
        if "sustain_a" not in tasks and "sustain_i" not in tasks:
            reasons.append(_unknown_reason("missing_sustain", "지속음 Task가 필요해요."))
            retry.extend(["sustain_a"])
        elif not (_quality_ok(task_results, "sustain_a") or _quality_ok(task_results, "sustain_i")):
            reasons.append(_unknown_reason("quality", "지속음 녹음 품질이 부족해요."))
            retry.extend([t for t in ("sustain_a", "sustain_i") if t in tasks])
        elif "temporal_stability" not in families:
            reasons.append(_unknown_reason("missing_family", "시간 안정성 근거가 부족해요."))

    elif mid == "register_transition_coordination":
        if "siren" not in tasks:
            reasons.append(_unknown_reason("missing_siren", "사이렌 Task가 필요해요."))
            retry.append("siren")
        elif not _quality_ok(task_results, "siren"):
            reasons.append(_unknown_reason("quality", "사이렌 녹음 품질이 부족해요."))
            retry.append("siren")
        elif "register_continuity" not in families:
            reasons.append(_unknown_reason("missing_family", "음역 연속성 근거가 부족해요."))

    elif mid == "phonation_contact_pattern":
        n_fam = count_independent_families(
            bundle, ["periodicity", "spectral_source", "onset"]
        )
        if n_fam < 2 and len(families) < 2:
            reasons.append(
                _unknown_reason(
                    "insufficient_evidence_families",
                    "최소 2개의 독립 근거 계열이 필요해요.",
                )
            )
        if cfg.CONTACT_REQUIRES_CROSS_VOWEL:
            cross = bundle.get("cross_vowel") or {}
            inconsistent = set(cross.get("inconsistent_metrics") or [])
            cep_tasks = set(
                ((bundle.get("by_metric") or {}).get("cepstral_prominence_proxy_db") or {}).get(
                    "tasks"
                )
                or []
            )
            if not ({"sustain_a", "sustain_i"} <= cep_tasks):
                reasons.append(
                    _unknown_reason(
                        "missing_cross_vowel",
                        "더 일정한 /a/·/i/ 지속음이 있어야 신뢰도 있게 분석할 수 있어요.",
                    )
                )
                retry.extend(["sustain_a", "sustain_i"])
            if "cepstral_prominence_proxy_db" in inconsistent:
                reasons.append(
                    _unknown_reason(
                        "cross_vowel_inconsistency",
                        "모음 간 결과가 달라 단정하지 않았어요.",
                    )
                )

    elif mid == "intensity_phonation_coordination":
        if "dynamic_swell" not in tasks:
            reasons.append(_unknown_reason("missing_swell", "강약 스웰 Task가 필요해요."))
            retry.append("dynamic_swell")
        elif not _quality_ok(task_results, "dynamic_swell"):
            reasons.append(_unknown_reason("quality", "스웰 녹음 품질이 부족해요."))
            retry.append("dynamic_swell")
        if "intensity_coordination" not in families:
            reasons.append(
                _unknown_reason("missing_envelope", "강도 envelope 근거가 부족해요.")
            )
        # need second family — not envelope alone as "호흡 지지"
        if len(families) < 2:
            reasons.append(
                _unknown_reason(
                    "insufficient_evidence_families",
                    "강도 변화만으로 호흡·발성 협응을 단정하지 않아요.",
                )
            )

    elif mid == "onset_coordination":
        if "onset" not in families:
            reasons.append(_unknown_reason("missing_onset", "소리 시작 근거가 없어요."))
        if len(families) < 2:
            reasons.append(
                _unknown_reason(
                    "onset_alone",
                    "소리 시작 에너지만으로는 핵심 결론을 만들지 않아요.",
                )
            )
            # SECONDARY: not user_visible as conclusion
            return {
                "eligible": False,
                "user_visible": False,
                "product_visibility": vis,
                "reasons": reasons,
                "retry_tasks": [],
            }

    eligible = len(reasons) == 0 and status != "unknown"
    user_visible = True
    if vis == "CONDITIONAL_PRIMARY" and not eligible and status == "unknown":
        user_visible = True  # show in uncertain
    if vis == "SECONDARY":
        user_visible = eligible  # only if assessed with corroboration

    return {
        "eligible": eligible,
        "user_visible": user_visible,
        "product_visibility": vis,
        "reasons": reasons,
        "retry_tasks": sorted(set(retry)),
    }
