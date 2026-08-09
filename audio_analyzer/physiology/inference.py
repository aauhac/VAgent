"""
inference.py — physiology-inference-v1.3
Evidence families + rule registry + confidence caps.
"""

from __future__ import annotations

from typing import Any, Optional

from . import config as cfg
from .evidence import build_evidence_bundle, count_independent_families
from .knowledge import ALTERNATIVE_POOL, LIMITATIONS_POOL, NOT_IDENTIFIABLE_FROM_AUDIO
from .literature_registry import LITERATURE_REGISTRY_VERSION
from .rules import get_rules_for


def _label(conf: float, mechanism_id: str = "") -> str:
    return cfg.confidence_label(conf, mechanism_id=mechanism_id or None)


def _provenance(families: list[str]) -> list[str]:
    return [cfg.EVIDENCE_FAMILY_LABELS.get(f, f) for f in families]


def _status_label(status: str) -> str:
    return {
        "unknown": "판단 어려움",
        "balanced": "뚜렷한 방향 없음",
        "possibly_light_contact": "가벼운 접촉과 일치하는 경향",
        "possibly_firm_contact": "상대적으로 단단한 접촉과 일치하는 경향",
        "needs_attention": "주의해 볼 경향",
    }.get(status, status)


def _cross_vowel_ok(bundle: dict, inconsistent: set) -> bool:
    block = (bundle.get("by_metric") or {}).get("cepstral_prominence_proxy_db") or {}
    tasks = set(block.get("tasks") or [])
    if not ({"sustain_a", "sustain_i"} <= tasks):
        return False
    if "cepstral_prominence_proxy_db" in inconsistent:
        return False
    return True


def _base_unknown(mechanism_id: str, summary: str, alts: list[str], lims: list[str]) -> dict[str, Any]:
    mechanism_id = cfg.canonicalize_mechanism_id(mechanism_id)
    return {
        "mechanism_id": mechanism_id,
        "display_name": cfg.MECHANISM_DISPLAY[mechanism_id],
        "status": "unknown",
        "confidence": 0.2,
        "confidence_label": _label(0.2, mechanism_id),
        "status_label": "판단 어려움",
        "evidence_family_provenance": [],
        "ux_tier": cfg.ux_tier(mechanism_id),
        "user_facing_primary": mechanism_id in cfg.PRIMARY_UX_MECHANISMS,
        "summary": summary,
        "supporting_evidence": [],
        "contradicting_evidence": [],
        "alternative_explanations": alts,
        "limitations": lims,
        "source_tasks": [],
        "inference_version": cfg.INFERENCE_VERSION,
        "literature_strength": cfg.MECHANISM_AUDIT.get(mechanism_id, "WEAK"),
        "literature_registry_version": LITERATURE_REGISTRY_VERSION,
        "rule_id": None,
        "rule_version": None,
        "evidence_families_used": [],
        "independent_family_count": 0,
        "confidence_cap": cfg.MECHANISM_CONFIDENCE_CAPS.get(mechanism_id, 0.5),
        "scientific_trace": {
            "not_identifiable_examples": NOT_IDENTIFIABLE_FROM_AUDIO[:8],
        },
    }


def _finalize(
    *,
    mechanism_id: str,
    status: str,
    confidence: float,
    summary: str,
    supporting: list[str],
    contradicting: list[str],
    alternatives: list[str],
    limitations: list[str],
    source_tasks: list[str],
    families: list[str],
    rule: Optional[dict[str, Any]] = None,
    literature_strength: Optional[str] = None,
) -> dict[str, Any]:
    mechanism_id = cfg.canonicalize_mechanism_id(mechanism_id)
    cap = cfg.MECHANISM_CONFIDENCE_CAPS.get(mechanism_id, 0.5)
    if rule:
        cap = min(cap, float(rule.get("confidence_cap", cap)))
    confidence = min(confidence, cap, cfg.AUDIO_ONLY_GLOBAL_CONFIDENCE_CAP)

    # Weak mechanisms: never emit directional user conclusions
    if mechanism_id in cfg.WEAK_MECHANISMS_USER_SUPPRESS and status not in ("balanced", "unknown"):
        # Allow needs_attention only if explicitly not weak-suppress — these are suppressed
        status = "unknown"
        summary = (
            "이 항목은 현재 문헌 근거가 약해 상세 결론을 내리지 않아요. "
            "연습 참고용 관측만 남깁니다."
        )
        confidence = min(confidence, 0.35)

    n_fam = len(families)
    if status != "unknown" and status != "balanced":
        if n_fam < cfg.MIN_INDEPENDENT_FAMILIES_FOR_DIRECTION and mechanism_id not in (
            "register_transition_coordination",
            "phonation_stability",
        ):
            status = "unknown"
            summary = "독립된 근거 계열이 부족해 경향을 단정하지 않아요."
            confidence = min(confidence, 0.35)

    if contradicting:
        confidence *= 0.7
    if confidence < 0.35 and status not in ("balanced", "unknown"):
        status = "unknown"
        summary = "이번 측정만으로는 경향을 신뢰하기 어려워요."

    strength = literature_strength or (
        (rule or {}).get("literature_strength")
        or cfg.MECHANISM_AUDIT.get(mechanism_id, "WEAK")
    )
    # WEAK strength may not drive non-unknown directional claims
    if strength == "WEAK" and status not in ("balanced", "unknown"):
        status = "unknown"
        summary = "문헌 근거가 약해 이 항목의 방향성 결론을 표시하지 않아요."
        confidence = min(confidence, 0.32)

    return {
        "mechanism_id": mechanism_id,
        "display_name": cfg.MECHANISM_DISPLAY[mechanism_id],
        "status": status,
        "confidence": round(float(confidence), 3),
        "confidence_label": _label(confidence, mechanism_id),
        "status_label": _status_label(status),
        "evidence_family_provenance": _provenance(families),
        "ux_tier": cfg.ux_tier(mechanism_id),
        "user_facing_primary": cfg.canonicalize_mechanism_id(mechanism_id) in cfg.PRIMARY_UX_MECHANISMS,
        "summary": summary,
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "alternative_explanations": alternatives,
        "limitations": limitations,
        "source_tasks": source_tasks,
        "inference_version": cfg.INFERENCE_VERSION,
        "literature_strength": strength,
        "literature_registry_version": LITERATURE_REGISTRY_VERSION,
        "rule_id": (rule or {}).get("rule_id"),
        "rule_version": (rule or {}).get("version"),
        "evidence_families_used": families,
        "independent_family_count": n_fam,
        "confidence_cap": cap,
        "scientific_trace": {
            "rule_id": (rule or {}).get("rule_id"),
            "references": (rule or {}).get("references") or [],
            "forbidden_claims": (rule or {}).get("forbidden_claims") or [],
            "families": families,
        },
    }


def _metric(bundle: dict, mid: str) -> tuple[Optional[float], list[str]]:
    block = (bundle.get("by_metric") or {}).get(mid)
    if not block:
        return None, []
    return block.get("mean"), list(block.get("tasks") or [])


def _periodicity_direction(bundle: dict) -> tuple[Optional[str], list[str], list[str]]:
    """Return light|firm|None, support notes, contra notes — single family vote."""
    cep, t_c = _metric(bundle, "cepstral_prominence_proxy_db")
    hnr, t_h = _metric(bundle, "hnr_ac_proxy_db")
    notes: list[str] = []
    contra: list[str] = []
    if cep is not None:
        notes.append(f"cepstral_prominence_proxy_db≈{cep:.1f}")
    if hnr is not None:
        notes.append(f"hnr_ac_proxy_db≈{hnr:.1f}")
    # Contradictory within family
    if cep is not None and hnr is not None:
        cep_light = cep < cfg.CEPSTRAL_LOW_PERIODICITY_BELOW
        cep_firm = cep > cfg.CEPSTRAL_HIGH_PERIODICITY_ABOVE
        hnr_light = hnr < cfg.HNR_PROXY_LOW_BELOW
        hnr_firm = hnr > cfg.HNR_PROXY_HIGH_ABOVE
        if (cep_light and hnr_firm) or (cep_firm and hnr_light):
            contra.append("periodicity family internal contradiction (cepstral vs HNR proxy)")
            return None, notes, contra
    # Prefer cepstral if present
    val = cep if cep is not None else hnr
    if val is None:
        return None, notes, contra
    thr_lo = (
        cfg.CEPSTRAL_LOW_PERIODICITY_BELOW if cep is not None else cfg.HNR_PROXY_LOW_BELOW
    )
    thr_hi = (
        cfg.CEPSTRAL_HIGH_PERIODICITY_ABOVE if cep is not None else cfg.HNR_PROXY_HIGH_ABOVE
    )
    if val < thr_lo:
        return "light", notes, contra
    if val > thr_hi:
        return "firm", notes, contra
    return "balanced", notes, contra


def _spectral_direction(bundle: dict) -> tuple[Optional[str], list[str]]:
    h1, t = _metric(bundle, "raw_h1_h2_proxy_db")
    notes: list[str] = []
    if h1 is None:
        return None, notes
    notes.append(f"raw_h1_h2_proxy_db≈{h1:.1f} (uncorrected; NOT H1*-H2*)")
    if h1 > cfg.RAW_H1H2_LIGHT_ABOVE:
        return "light", notes
    if h1 < cfg.RAW_H1H2_FIRM_BELOW:
        return "firm", notes
    return "balanced", notes


def infer_mechanisms(
    task_results: list[dict[str, Any]],
    *,
    safety_flags: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    bundle = build_evidence_bundle(task_results)
    safety_flags = safety_flags or []
    alts = list(ALTERNATIVE_POOL)
    lims = list(LIMITATIONS_POOL)
    cross = bundle.get("cross_vowel") or {}
    inconsistent = set(cross.get("inconsistent_metrics") or [])

    mechanisms: list[dict[str, Any]] = []

    # --- 1 phonation_contact_pattern ---
    per_dir, per_notes, per_contra = _periodicity_direction(bundle)
    spec_dir, spec_notes = _spectral_direction(bundle)
    onset_v, t_on = _metric(bundle, "onset_slope_db_per_sec")

    support = per_notes + spec_notes
    contra = list(per_contra)
    families: list[str] = []
    if per_dir is not None:
        families.append("periodicity")
    if spec_dir is not None:
        families.append("spectral_source")

    # Cross-vowel inconsistency on periodicity metrics → downweight
    if "cepstral_prominence_proxy_db" in inconsistent or "hnr_ac_proxy_db" in inconsistent:
        contra.append("cross-vowel inconsistency on periodicity proxies")
    if "raw_h1_h2_proxy_db" in inconsistent:
        contra.append("cross-vowel inconsistency on raw H1-H2 (expected without formant correction)")

    votes_light = 0
    votes_firm = 0
    if per_dir == "light":
        votes_light += 1
    elif per_dir == "firm":
        votes_firm += 1
    if spec_dir == "light":
        votes_light += 1
    elif spec_dir == "firm":
        votes_firm += 1

    # Onset alone never decides; may add family if corroborates light/firm with others
    if onset_v is not None and (votes_light >= 1 or votes_firm >= 1):
        families.append("onset")
        support.append(f"onset_slope_db_per_sec≈{onset_v:.1f}")

    n_fam = len(set(families))
    tasks = sorted(
        {
            *(bundle.get("by_metric", {}).get("cepstral_prominence_proxy_db", {}).get("tasks") or []),
            *(bundle.get("by_metric", {}).get("raw_h1_h2_proxy_db", {}).get("tasks") or []),
            *t_on,
        }
    )

    cross_ok = _cross_vowel_ok(bundle, inconsistent)
    conf_boost = 0.04 if cross_ok else 0.0

    if votes_light >= 1 and votes_firm >= 1:
        mechanisms.append(
            _finalize(
                mechanism_id="phonation_contact_pattern",
                status="unknown",
                confidence=0.28,
                summary="관측 계열이 서로 다른 방향을 가리켜 성대 접촉 관련 경향을 단정하지 않아요.",
                supporting=support,
                contradicting=contra + ["opposing family directions"],
                alternatives=alts,
                limitations=lims + ["오디오만으로 성문의 실제 모양을 볼 수 없습니다."],
                source_tasks=tasks,
                families=sorted(set(families)),
                literature_strength="CONDITIONAL",
            )
        )
    elif votes_light >= 1 and n_fam >= 2 and cross_ok:
        rule = get_rules_for("phonation_contact_pattern")[0]
        mechanisms.append(
            _finalize(
                mechanism_id="phonation_contact_pattern",
                status="possibly_light_contact",
                confidence=0.48 + 0.03 * n_fam + conf_boost,
                summary=rule["allowed_user_claim"],
                supporting=support,
                contradicting=contra,
                alternatives=rule["alternative_explanations"] + alts[:3],
                limitations=lims + ["오디오만으로 성문의 실제 모양을 볼 수 없습니다."],
                source_tasks=tasks,
                families=sorted(set(families)),
                rule=rule,
            )
        )
    elif votes_firm >= 1 and n_fam >= 2 and cross_ok:
        rule = get_rules_for("phonation_contact_pattern")[1]
        mechanisms.append(
            _finalize(
                mechanism_id="phonation_contact_pattern",
                status="possibly_firm_contact",
                confidence=0.46 + 0.03 * n_fam + conf_boost,
                summary=rule["allowed_user_claim"],
                supporting=support,
                contradicting=contra,
                alternatives=rule["alternative_explanations"] + alts[:3],
                limitations=lims,
                source_tasks=tasks,
                families=sorted(set(families)),
                rule=rule,
            )
        )
    elif votes_light + votes_firm >= 1 and n_fam >= 2 and not cross_ok:
        mechanisms.append(
            _finalize(
                mechanism_id="phonation_contact_pattern",
                status="unknown",
                confidence=0.32,
                summary=(
                    "한 모음만으로는 성대 접촉 관련 경향을 단정하지 않아요. "
                    "/a/와 /i/에서 같은 방향이 반복될 때 판단합니다."
                ),
                supporting=support,
                contradicting=contra + ["missing_cross_vowel_replication"],
                alternatives=alts,
                limitations=lims + ["오디오만으로 성문의 실제 모양을 볼 수 없습니다."],
                source_tasks=tasks,
                families=sorted(set(families)),
                literature_strength="CONDITIONAL",
            )
        )
    elif n_fam >= 2 and cross_ok and per_dir == "balanced" and (spec_dir in (None, "balanced")):
        mechanisms.append(
            _finalize(
                mechanism_id="phonation_contact_pattern",
                status="balanced",
                confidence=0.48,
                summary="성대 접촉과 관련된 발성 경향이 극단적으로 치우치지 않았어요.",
                supporting=support,
                contradicting=contra,
                alternatives=alts,
                limitations=lims,
                source_tasks=tasks,
                families=sorted(set(families)),
                literature_strength="CONDITIONAL",
            )
        )
    else:
        mechanisms.append(
            _base_unknown(
                "phonation_contact_pattern",
                "성대 접촉과 관련된 발성 경향을 말할 독립 근거·교차 모음 확인이 부족해요.",
                alts,
                lims,
            )
        )

    # --- 2 phonatory_efficiency (WEAK → always suppressed directional) ---
    mechanisms.append(
        _finalize(
            mechanism_id="phonatory_efficiency",
            status="unknown",
            confidence=0.25,
            summary=(
                "‘발성 효율’은 공기역학·EGG 없이 오디오 주기성만으로 단정하기 어려워 "
                "현재 리포트에서는 방향성 결론을 내지 않아요."
            ),
            supporting=per_notes,
            contradicting=[],
            alternatives=alts,
            limitations=lims + ["true glottal efficiency / collision not measured"],
            source_tasks=tasks,
            families=["periodicity"] if per_notes else [],
            literature_strength="WEAK",
        )
    )

    # --- 3 intensity_phonation_coordination ---
    smooth, t_sm = _metric(bundle, "envelope_smoothness_index")
    release, t_rel = _metric(bundle, "release_drop_db")
    rmsv, t_rms = _metric(bundle, "rms_variation_db")
    bp_support = []
    bp_fam = []
    if smooth is not None:
        bp_support.append(f"envelope_smoothness_index≈{smooth:.3f}")
        bp_fam.append("intensity_coordination")
    if release is not None:
        bp_support.append(f"release_drop_db≈{release:.1f}")
        bp_fam.append("release")
    if rmsv is not None:
        bp_support.append(f"rms_variation_db≈{rmsv:.1f}")
        bp_fam.append("temporal_stability")
    bp_fam = sorted(set(bp_fam))
    awkward = (smooth is not None and smooth < 0.35) or (release is not None and release > 18)
    if len(bp_fam) < 2:
        mechanisms.append(
            _base_unknown(
                "intensity_phonation_coordination",
                "발성 강도 변화 조절을 말할 독립 근거가 부족해요.",
                alts,
                lims,
            )
        )
    elif awkward:
        rule = get_rules_for("intensity_phonation_coordination")[0]
        mechanisms.append(
            _finalize(
                mechanism_id="intensity_phonation_coordination",
                status="needs_attention",
                confidence=0.52,
                summary=rule["allowed_user_claim"],
                supporting=bp_support,
                contradicting=[],
                alternatives=rule["alternative_explanations"],
                limitations=lims + ["복압·폐활량·횡격막 활성도는 측정하지 않습니다."],
                source_tasks=sorted(set(t_sm + t_rel + t_rms)),
                families=bp_fam,
                rule=rule,
            )
        )
    else:
        mechanisms.append(
            _finalize(
                mechanism_id="intensity_phonation_coordination",
                status="balanced",
                confidence=0.50,
                summary="강도 변화와 발성 에너지가 비교적 자연스럽게 맞물리는 편이에요. (복압을 측정한 것은 아님)",
                supporting=bp_support,
                contradicting=[],
                alternatives=alts,
                limitations=lims,
                source_tasks=sorted(set(t_sm + t_rel + t_rms)),
                families=bp_fam,
                literature_strength="CONDITIONAL",
            )
        )

    # --- 4 onset ---
    if onset_v is None:
        mechanisms.append(
            _base_unknown("onset_coordination", "소리 시작 조절을 측정하기 어려웠어요.", alts, lims)
        )
    else:
        abrupt = onset_v > 120
        soft = onset_v < 25
        on_fam = ["onset"]
        on_support = [f"onset_slope_db_per_sec≈{onset_v:.1f}"]
        if per_dir is not None:
            on_fam.append("periodicity")
            on_support += per_notes
        if (abrupt or soft) and len(set(on_fam)) >= 2:
            rule = get_rules_for("onset_coordination")[0]
            mechanisms.append(
                _finalize(
                    mechanism_id="onset_coordination",
                    status="needs_attention",
                    confidence=0.48,
                    summary=rule["allowed_user_claim"],
                    supporting=on_support,
                    contradicting=[],
                    alternatives=rule["alternative_explanations"],
                    limitations=lims,
                    source_tasks=t_on,
                    families=sorted(set(on_fam)),
                    rule=rule,
                )
            )
        elif abrupt or soft:
            mechanisms.append(
                _finalize(
                    mechanism_id="onset_coordination",
                    status="unknown",
                    confidence=0.32,
                    summary="소리 시작이 급격하게 변하는 경향만으로는 단정하지 않아요.",
                    supporting=on_support,
                    contradicting=[],
                    alternatives=alts,
                    limitations=lims,
                    source_tasks=t_on,
                    families=["onset"],
                    literature_strength="CONDITIONAL",
                )
            )
        else:
            mechanisms.append(
                _finalize(
                    mechanism_id="onset_coordination",
                    status="balanced",
                    confidence=0.48,
                    summary="소리 시작 에너지 상승이 비교적 자연스러운 편이에요.",
                    supporting=on_support,
                    contradicting=[],
                    alternatives=alts,
                    limitations=lims,
                    source_tasks=t_on,
                    families=sorted(set(on_fam)),
                    literature_strength="CONDITIONAL",
                )
            )

    # --- 5 release (WEAK → suppress directional) ---
    if release is None:
        mechanisms.append(
            _base_unknown("release_coordination", "끝음 조절 관측이 부족해요.", alts, lims)
        )
    else:
        mechanisms.append(
            _finalize(
                mechanism_id="release_coordination",
                status="unknown",
                confidence=0.30,
                summary=(
                    f"끝음 에너지 변화(release_drop≈{release:.1f} dB)는 관측되지만, "
                    "문헌 근거가 약해 방향성 결론은 내지 않아요."
                ),
                supporting=[f"release_drop_db≈{release:.1f}"],
                contradicting=[],
                alternatives=alts,
                limitations=lims,
                source_tasks=t_rel,
                families=["release"],
                literature_strength="WEAK",
            )
        )

    # --- 6 register ---
    cont, t_c = _metric(bundle, "f0_continuity_ratio")
    drop, t_d = _metric(bundle, "voiced_dropout_count")
    if cont is None:
        mechanisms.append(
            _base_unknown(
                "register_transition_coordination",
                "음역 전환 Task 관측이 없어요.",
                alts,
                lims,
            )
        )
    else:
        interrupted = (cont < 0.7) or (drop is not None and drop > 8)
        reg_support = [f"f0_continuity_ratio≈{cont:.2f}"]
        if drop is not None:
            reg_support.append(f"voiced_dropout_count≈{drop:.0f}")
        if interrupted:
            rule = get_rules_for("register_transition_coordination")[0]
            mechanisms.append(
                _finalize(
                    mechanism_id="register_transition_coordination",
                    status="needs_attention",
                    confidence=0.55,
                    summary=rule["allowed_user_claim"],
                    supporting=reg_support,
                    contradicting=[],
                    alternatives=rule["alternative_explanations"],
                    limitations=lims + ["최고 음 높이는 skill score가 아닙니다.", "TA/CT 미추정"],
                    source_tasks=sorted(set(t_c + t_d)),
                    families=["register_continuity"],
                    rule=rule,
                )
            )
        else:
            mechanisms.append(
                _finalize(
                    mechanism_id="register_transition_coordination",
                    status="balanced",
                    confidence=0.55,
                    summary="편한 범위 안에서 음높이 이동이 비교적 연속적으로 이어졌어요.",
                    supporting=reg_support,
                    contradicting=[],
                    alternatives=alts,
                    limitations=lims,
                    source_tasks=sorted(set(t_c + t_d)),
                    families=["register_continuity"],
                    literature_strength="CONDITIONAL",
                )
            )

    # --- 7 vocal tract (WEAK) ---
    tilt, t_t = _metric(bundle, "spectral_tilt_db_per_oct")
    mechanisms.append(
        _finalize(
            mechanism_id="vocal_tract_resonance_balance",
            status="unknown",
            confidence=0.28,
            summary=(
                "스펙트럼 기울기만으로 혀/턱/인두 형태를 추정하지 않아요. "
                "공명·성도 균형 결론은 현재 제한합니다."
                + (f" (tilt≈{tilt:.1f})" if tilt is not None else "")
            ),
            supporting=([f"spectral_tilt_db_per_oct≈{tilt:.1f}"] if tilt is not None else []),
            contradicting=[],
            alternatives=alts + ["모음 차이", "마이크 주파수 응답", "singer's formant"],
            limitations=lims + ["혀/후두 위치를 직접 관찰하지 않습니다."],
            source_tasks=t_t,
            families=["spectral_source"] if tilt is not None else [],
            literature_strength="WEAK",
        )
    )

    # --- 8 phonation stability ---
    res, t_r = _metric(bundle, "sustained_residual_f0_cents")
    if res is None:
        mechanisms.append(
            _base_unknown("phonation_stability", "지속음 안정성 관측이 부족해요.", alts, lims)
        )
    else:
        unstable = res > 35
        if unstable:
            rule = get_rules_for("phonation_stability")[0]
            mechanisms.append(
                _finalize(
                    mechanism_id="phonation_stability",
                    status="needs_attention",
                    confidence=0.58,
                    summary=rule["allowed_user_claim"],
                    supporting=[f"sustained_residual_f0_cents≈{res:.1f}"],
                    contradicting=[],
                    alternatives=rule["alternative_explanations"],
                    limitations=lims,
                    source_tasks=t_r,
                    families=["temporal_stability"],
                    rule=rule,
                )
            )
        else:
            mechanisms.append(
                _finalize(
                    mechanism_id="phonation_stability",
                    status="balanced",
                    confidence=0.55,
                    summary="지속음 국소 구간에서 F0 잔차가 비교적 안정적이에요.",
                    supporting=[f"sustained_residual_f0_cents≈{res:.1f}"],
                    contradicting=[],
                    alternatives=alts,
                    limitations=lims,
                    source_tasks=t_r,
                    families=["temporal_stability"],
                    literature_strength="CONDITIONAL",
                )
            )

    if safety_flags:
        for m in mechanisms:
            m["limitations"] = list(m.get("limitations") or []) + [
                "안전 확인에서 불편 신호가 있어 강한 훈련 처방은 제한합니다."
            ]
            m["confidence"] = round(min(float(m["confidence"]), 0.50), 3)
            m["confidence_label"] = _label(m["confidence"], m["mechanism_id"])

    return mechanisms
