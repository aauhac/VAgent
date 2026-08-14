"""Precision Diagnostic v2.2 — Concern evidence contracts + task contrast resolver.

USER_REPORTED ≠ AUDIO_OBSERVED ≠ CONTROLLED_TASK_CONFIRMED

Concerns prioritize which evidence to inspect; they never become acoustic truth.
"""

from __future__ import annotations

from typing import Any, Optional

CONCERN_EVIDENCE_CONTRACT: dict[str, dict[str, Any]] = {
    "HIGH_NOTE_TOO_EFFORTFUL": {
        "required": ["baseline_effort", "high_note_effort"],
        "supporting": ["contact_shift", "stability_shift", "breathiness_shift"],
        "preferred_tasks": ["sustain_a", "high_note_sustain_a"],
    },
    "HIGH_NOTE_CANNOT_REACH": {
        "required": ["high_note_compliance"],
        "supporting": ["effort_contrast", "stability_shift", "register"],
        "preferred_tasks": ["high_note_sustain_a", "siren"],
    },
    "HIGH_NOTE_UNSTABLE": {
        "required": ["baseline_stability", "high_note_stability"],
        "supporting": ["effort_contrast"],
        "preferred_tasks": ["sustain_a", "high_note_sustain_a"],
    },
    "HIGH_NOTE_THINS": {
        "required": ["baseline_timbre", "high_note_timbre"],
        "supporting": ["breathiness_shift", "presence_shift"],
        "preferred_tasks": ["sustain_a", "high_note_sustain_a"],
    },
    "HIGH_NOTE_FLIPS": {
        "required": ["register_transition"],
        "supporting": ["siren_continuity"],
        "preferred_tasks": ["siren"],
    },
    "THROAT_EFFORT": {
        "required": ["effort_any"],
        "supporting": ["contact", "stability"],
        "preferred_tasks": ["sustain_a", "high_note_sustain_a", "dynamic_swell"],
    },
    "TIMBRE_DISSATISFIED": {
        "required": ["timbre_axes"],
        "supporting": ["breathiness", "contact", "consistency"],
        "preferred_tasks": ["sustain_a", "sustain_i", "high_note_sustain_a"],
    },
    "VOICE_TOO_DARK_MUFFLED": {
        "required": ["brightness_or_presence"],
        "supporting": ["airiness", "contact", "resonance"],
        "preferred_tasks": ["sustain_a", "sustain_i"],
    },
    "VOICE_TOO_THIN": {
        "required": ["airiness_or_presence"],
        "supporting": ["contact", "brightness"],
        "preferred_tasks": ["sustain_a", "high_note_sustain_a"],
    },
    "VOICE_TOO_BREATHY": {
        "required": ["breathiness"],
        "supporting": ["contact", "airiness"],
        "preferred_tasks": ["sustain_a"],
    },
    "VOICE_TOO_SHARP": {
        "required": ["brightness"],
        "supporting": ["presence", "texture"],
        "preferred_tasks": ["sustain_a", "sustain_i"],
    },
    "VOICE_ROUGH": {
        "required": ["stability_or_texture"],
        "supporting": ["contact", "breathiness"],
        "preferred_tasks": ["sustain_a"],
    },
    "VOICE_TOO_NASAL_PERCEPT": {
        "required": ["resonance_proxy"],
        "supporting": [],
        "preferred_tasks": ["sustain_a", "sustain_i"],
        "caution": "nasality_not_directly_measured",
    },
    "TIMBRE_CHANGES_HIGH": {
        "required": ["baseline_timbre", "high_note_timbre"],
        "supporting": ["brightness_shift", "airiness_shift"],
        "preferred_tasks": ["sustain_a", "high_note_sustain_a"],
    },
    "REGISTER_CONNECTION_DIFFICULT": {
        "required": ["register_transition"],
        "supporting": ["siren_continuity"],
        "preferred_tasks": ["siren"],
    },
}

_BANNED_CAUSES = frozenset(
    {
        "LOW_ABDOMINAL_PRESSURE",
        "WEAK_DIAPHRAGM",
        "HIGH_LARYNX",
        "TA_WEAK",
        "CT_WEAK",
        "LCA_WEAK",
        "PASAGGIO_FORCED",
        "PASSAGGIO_FORCED",
    }
)


def _task_ok(tr: dict[str, Any]) -> bool:
    if tr.get("invalid"):
        return False
    q = tr.get("quality") or {}
    if str(q.get("status") or "").lower() == "fail":
        return False
    c = tr.get("compliance") or {}
    if c and c.get("ok") is False:
        return False
    return True


def _dim(tr: dict[str, Any], dim: str) -> dict[str, Any]:
    ev = (tr.get("dimension_evidence") or {}).get(dim) or {}
    return ev if isinstance(ev, dict) else {}


def _estimate(ev: dict[str, Any]) -> Optional[float]:
    for key in ("estimate", "evidence_mass", "confidence_score"):
        v = ev.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    status = str(ev.get("status") or "").upper()
    mapping = {
        "HIGH": 0.8,
        "INCREASED": 0.65,
        "ELEVATED": 0.65,
        "UNSTABLE": 0.7,
        "FIRM": 0.7,
        "LOW": 0.25,
        "STABLE": 0.3,
        "LIGHT": 0.25,
        "OBSERVED": 0.5,
        "AVAILABLE": 0.5,
    }
    return mapping.get(status)


def _status_rank(status: Any) -> float:
    s = str(status or "").upper()
    return {
        "HIGH": 3.0,
        "INCREASED": 2.0,
        "ELEVATED": 2.0,
        "UNSTABLE": 2.5,
        "FIRM": 2.0,
        "OBSERVED": 1.0,
        "AVAILABLE": 1.0,
        "LOW": 0.0,
        "STABLE": 0.0,
        "LIGHT": 0.0,
        "INSUFFICIENT": -1.0,
    }.get(s, 0.5)


def build_task_profiles(task_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for tr in task_results or []:
        tid = tr.get("task_id")
        if not tid:
            continue
        valid = _task_ok(tr)
        dims = {}
        for dim, ev in (tr.get("dimension_evidence") or {}).items():
            if not isinstance(ev, dict):
                continue
            dims[dim] = {
                "status": ev.get("status"),
                "estimate": ev.get("estimate"),
                "available": bool(ev.get("available")),
                "resolution_eligible": bool(ev.get("resolution_eligible")) and valid,
                "reason": ev.get("reason"),
                "confidence_score": ev.get("confidence_score"),
                "extra": {
                    k: ev.get(k)
                    for k in ("rms", "periodicity_primary_db", "effort_cues", "availability")
                    if k in ev
                },
            }
        profiles[str(tid)] = {
            "task_id": tid,
            "valid": valid,
            "quality": (tr.get("quality") or {}).get("status"),
            "compliance_ok": (tr.get("compliance") or {}).get("ok"),
            "dimensions": dims,
        }
    return profiles


def _contrast_dim(
    baseline: dict[str, Any] | None,
    high: dict[str, Any] | None,
    *,
    dim: str,
) -> dict[str, Any]:
    if not baseline or not high:
        return {
            "dimension": dim,
            "available": False,
            "reason": "MISSING_BASELINE" if not baseline else "MISSING_HIGH",
        }
    if not baseline.get("resolution_eligible") and not baseline.get("available"):
        return {"dimension": dim, "available": False, "reason": "INVALID_BASELINE"}
    if not high.get("resolution_eligible") and not high.get("available"):
        return {"dimension": dim, "available": False, "reason": "INVALID_HIGH_NOTE_TASK"}
    b_est = _estimate(baseline)
    h_est = _estimate(high)
    delta = None
    if b_est is not None and h_est is not None:
        delta = round(h_est - b_est, 3)
    b_rank = _status_rank(baseline.get("status"))
    h_rank = _status_rank(high.get("status"))
    if delta is not None:
        if delta >= 0.18:
            direction = "INCREASED"
        elif delta <= -0.18:
            direction = "DECREASED"
        else:
            direction = "SIMILAR"
    else:
        if h_rank - b_rank >= 1.5:
            direction = "INCREASED"
        elif b_rank - h_rank >= 1.5:
            direction = "DECREASED"
        else:
            direction = "SIMILAR"
    conf = "medium"
    if baseline.get("resolution_eligible") and high.get("resolution_eligible"):
        conf = "medium"
    else:
        conf = "low"
    return {
        "dimension": dim,
        "available": True,
        "baseline": baseline.get("status"),
        "high": high.get("status"),
        "baseline_estimate": b_est,
        "high_estimate": h_est,
        "delta": delta if delta is not None else round(h_rank - b_rank, 3),
        "direction": direction,
        "confidence": conf,
    }


def build_controlled_contrasts(
    task_profiles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    base = task_profiles.get("sustain_a") or {}
    high = task_profiles.get("high_note_sustain_a") or {}
    base_dims = base.get("dimensions") or {}
    high_dims = high.get("dimensions") or {}
    if base or high:
        dims = {}
        for dim in ("effort", "contact", "breathiness", "stability", "resonance"):
            dims[dim] = _contrast_dim(base_dims.get(dim), high_dims.get(dim), dim=dim)
        out["baseline_vs_high"] = {
            "pair": "sustain_a__vs__high_note_sustain_a",
            "baseline_valid": bool(base.get("valid")),
            "high_valid": bool(high.get("valid")),
            "dimensions": dims,
        }
        out["sustain_a__vs__high_note_sustain_a"] = out["baseline_vs_high"]

    a = task_profiles.get("sustain_a") or {}
    i = task_profiles.get("sustain_i") or {}
    if a and i:
        a_dims = a.get("dimensions") or {}
        i_dims = i.get("dimensions") or {}
        out["a_vs_i"] = {
            "pair": "sustain_a__vs__sustain_i",
            "note": "vowel_difference_is_not_pathology",
            "dimensions": {
                "resonance": _contrast_dim(a_dims.get("resonance"), i_dims.get("resonance"), dim="resonance"),
                "breathiness": _contrast_dim(
                    a_dims.get("breathiness"), i_dims.get("breathiness"), dim="breathiness"
                ),
                "contact": _contrast_dim(a_dims.get("contact"), i_dims.get("contact"), dim="contact"),
            },
        }
        out["sustain_a__vs__sustain_i"] = out["a_vs_i"]

    swell = task_profiles.get("dynamic_swell") or {}
    if swell:
        out["soft_vs_swell"] = {
            "pair": "dynamic_swell",
            "valid": bool(swell.get("valid")),
            "dimensions": swell.get("dimensions") or {},
            "note": "swell_task_captures_intensity_coordination",
        }

    siren = task_profiles.get("siren") or {}
    if siren:
        out["siren_transition"] = {
            "pair": "siren",
            "valid": bool(siren.get("valid")),
            "dimensions": siren.get("dimensions") or {},
        }
    return out


def extract_timbre_snapshot(song_profile: dict[str, Any]) -> dict[str, Any]:
    """Timbre axes from canonical song evidence (shared with coaching)."""
    from .song_evidence import get_canonical_snapshot

    snap = get_canonical_snapshot(song_profile)
    timbre = snap.get("timbre") or {}
    axes: dict[str, Any] = {}
    for name in (
        "brightness",
        "presence",
        "airiness",
        "texture",
        "harmonic_concentration",
        "consistency",
    ):
        val = timbre.get(name)
        if val is None and isinstance(timbre.get("axes"), dict):
            val = (timbre.get("axes") or {}).get(name)
        if val is None:
            continue
        if isinstance(val, dict):
            axes[name] = val
        else:
            axes[name] = {"continuum": float(val), "status": None}
    return {
        "available": bool(timbre.get("available") or axes),
        "axes": axes,
        "summary": (snap.get("vocal_function_profile") or {}).get("timbre_profile", {}).get("summary")
        if snap.get("vocal_function_profile")
        else None,
        "canonical": snap,
        "source": timbre.get("source"),
    }


def _empty_eval(concern_id: str, status: str, **kwargs: Any) -> dict[str, Any]:
    return {
        "concern": concern_id,
        "concern_id": concern_id,
        "status": status,
        "evidence_level": kwargs.get("evidence_level"),
        "support": kwargs.get("support") or [],
        "against": kwargs.get("against") or [],
        "missing": kwargs.get("missing") or [],
        "task_ids_used": kwargs.get("task_ids_used") or [],
        "song_evidence_used": kwargs.get("song_evidence_used") or [],
        "contrast_evidence": kwargs.get("contrast_evidence") or [],
        "candidate_causes": [
            c for c in (kwargs.get("candidate_causes") or []) if c not in _BANNED_CAUSES
        ],
        "confidence_label": kwargs.get("confidence_label") or "low",
        "unresolved_reason": kwargs.get("unresolved_reason"),
        "note": kwargs.get("note"),
        "answer_hint": kwargs.get("answer_hint"),
        "interpretation": kwargs.get("interpretation") or kwargs.get("answer_hint"),
        "controlled_confirmation": kwargs.get("controlled_confirmation"),
        "guidance_level": kwargs.get("guidance_level"),
        "primary_focus": kwargs.get("primary_focus"),
    }


def _song_effort_level(song: dict[str, Any]) -> str:
    vf = song.get("vocal_function_profile") or {}
    effort = vf.get("effort_assessment") or {}
    sev = (effort.get("severity") or effort.get("global_severity") or "").upper()
    if sev in ("MODERATE", "HIGH", "EXCESS"):
        return "HIGH"
    if sev == "LOW":
        return "LOW"
    return "UNKNOWN"


def evaluate_concern(
    concern_id: str,
    *,
    song_profile: dict[str, Any],
    task_evidence: Optional[dict[str, Any]] = None,
    task_results: Optional[list[dict[str, Any]]] = None,
    timbre_goal: Any = None,
) -> dict[str, Any]:
    """Full provenance concern evaluation using song + controlled contrasts."""
    from .concerns import PAIN_CONCERN_IDS
    from .functional_hypothesis import ensure_actionable_guidance

    if concern_id in PAIN_CONCERN_IDS:
        ev = _empty_eval(
            concern_id,
            "SAFETY_ONLY",
            note="통증·불편은 음향 분석만으로 원인을 판단할 수 없어요.",
        )
        return ensure_actionable_guidance(
            ev, song_profile=song_profile, timbre_goal=timbre_goal
        )

    fused = task_evidence or {}
    profiles = fused.get("task_profiles") or build_task_profiles(task_results or [])
    contrasts = fused.get("controlled_contrasts") or build_controlled_contrasts(profiles)
    skipped = set(
        (fused.get("task_evidence") or {}).get("user_skipped_tasks")
        or fused.get("user_skipped_tasks")
        or []
    )
    timbre = extract_timbre_snapshot(song_profile)
    song_effort = _song_effort_level(song_profile)

    if concern_id == "HIGH_NOTE_TOO_EFFORTFUL":
        ev = _resolve_high_note_effort(
            song_effort=song_effort,
            profiles=profiles,
            contrasts=contrasts,
            concern_id=concern_id,
            user_skipped_tasks=skipped,
            song_profile=song_profile,
        )
    elif concern_id in ("THROAT_EFFORT", "LOUD_VOICE_DIFFICULT", "VOCAL_FATIGUE"):
        ev = _resolve_general_effort(
            concern_id=concern_id,
            song_effort=song_effort,
            profiles=profiles,
            contrasts=contrasts,
            user_skipped_tasks=skipped,
            song_profile=song_profile,
        )
    elif concern_id in ("HIGH_NOTE_CANNOT_REACH", "HIGH_NOTE_FLIPS", "REGISTER_CONNECTION_DIFFICULT"):
        ev = _resolve_registerish(
            concern_id, profiles, contrasts, song_profile, user_skipped_tasks=skipped
        )
    elif concern_id == "HIGH_NOTE_UNSTABLE":
        ev = _resolve_high_note_stability(
            profiles, contrasts, user_skipped_tasks=skipped, song_profile=song_profile
        )
    elif concern_id in (
        "TIMBRE_DISSATISFIED",
        "VOICE_TOO_DARK_MUFFLED",
        "VOICE_TOO_THIN",
        "VOICE_TOO_BREATHY",
        "VOICE_TOO_SHARP",
        "VOICE_ROUGH",
        "VOICE_TOO_NASAL_PERCEPT",
        "TIMBRE_CHANGES_HIGH",
        "HIGH_NOTE_THINS",
    ):
        ev = _resolve_timbre(concern_id, timbre, profiles, contrasts, song_profile)
    else:
        ev = _empty_eval(
            concern_id,
            "UNRESOLVED",
            unresolved_reason="NO_RELEVANT_TASK_EVIDENCE",
            missing=["dedicated_resolver"],
        )

    return ensure_actionable_guidance(
        ev, song_profile=song_profile, user_skipped_tasks=skipped, timbre_goal=timbre_goal
    )


def _resolve_high_note_effort(
    *,
    song_effort: str,
    profiles: dict[str, dict[str, Any]],
    contrasts: dict[str, Any],
    concern_id: str,
    user_skipped_tasks: Optional[set[str]] = None,
    song_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    skipped = user_skipped_tasks or set()
    base = profiles.get("sustain_a") or {}
    high = profiles.get("high_note_sustain_a") or {}
    contrast = (contrasts.get("baseline_vs_high") or {}).get("dimensions") or {}
    effort_c = contrast.get("effort") or {}
    used = [t for t in ("sustain_a", "high_note_sustain_a") if t in profiles]
    support: list[str] = []
    against: list[str] = []
    missing: list[str] = []
    causes: list[str] = []

    # Skip = no controlled confirmation — do NOT terminate; song guidance fills in later
    if "high_note_sustain_a" in skipped and not high:
        return _empty_eval(
            concern_id,
            "UNRESOLVED",
            support=["song_effort_high"] if song_effort == "HIGH" else [],
            missing=["high_note_sustain_a"],
            unresolved_reason="USER_SKIPPED_RELEVANT_TASK",
            controlled_confirmation="NOT_AVAILABLE_USER_SKIPPED",
            song_evidence_used=[f"song_effort_{song_effort}"],
            task_ids_used=used,
            confidence_label="low",
            answer_hint=None,
        )

    if not high:
        missing.append("high_note_sustain_a")
    elif not high.get("valid"):
        return _empty_eval(
            concern_id,
            "UNRESOLVED",
            missing=["VALID_HIGH_NOTE_TASK"],
            unresolved_reason="INVALID_HIGH_NOTE_TASK",
            task_ids_used=used,
            answer_hint="높은 음 과제에서 비교 가능한 구간이 충분하지 않아 편한 음과 고음의 힘 차이를 확인하지 못했어요.",
        )
    if not base or not base.get("valid"):
        missing.append("baseline_sustain_a")
        # Absolute high only — cap confidence
        high_eff = (high.get("dimensions") or {}).get("effort") or {}
        st = str(high_eff.get("status") or "").upper()
        if st in ("HIGH", "INCREASED"):
            return _empty_eval(
                concern_id,
                "PARTIALLY_SUPPORTED",
                support=[f"high_effort_{st}"],
                missing=missing,
                task_ids_used=used,
                confidence_label="low",
                candidate_causes=["EFFORT_ESCALATION_WITH_HEIGHT"],
                answer_hint="높은 음 과제에서 힘 관련 패턴이 보였지만, 편한 음 baseline이 없어 증가량을 확정하기 어려워요.",
            )
        return _empty_eval(
            concern_id,
            "UNRESOLVED",
            missing=missing,
            unresolved_reason="MISSING_BASELINE",
            task_ids_used=used,
            answer_hint="편한 지속음 baseline이 없어 고음에서의 힘 증가를 비교하지 못했어요.",
        )

    if not effort_c.get("available"):
        return _empty_eval(
            concern_id,
            "UNRESOLVED",
            missing=["effort_contrast"],
            unresolved_reason=effort_c.get("reason") or "INSUFFICIENT",
            task_ids_used=used,
            answer_hint="편한 음과 고음의 힘 차이를 계산할 근거가 부족했어요.",
        )

    direction = effort_c.get("direction")
    delta = float(effort_c.get("delta") or 0)
    high_st = str(effort_c.get("high") or "").upper()
    base_st = str(effort_c.get("baseline") or "").upper()

    if direction == "INCREASED" and (delta >= 0.18 or high_st in ("HIGH", "INCREASED")):
        support.append(f"effort_delta_{delta}")
        support.append(f"baseline_{base_st}_to_high_{high_st}")
        causes.append("EFFORT_ESCALATION_WITH_HEIGHT")
        stab = contrast.get("stability") or {}
        if stab.get("direction") == "SIMILAR" or str(stab.get("high") or "").upper() in ("STABLE", "LOW"):
            against.append("high_note_stability_maintained")
        breath = contrast.get("breathiness") or {}
        if breath.get("direction") != "INCREASED":
            against.append("breathiness_increase_not_primary")
        status = "CONFIRMED" if delta >= 0.22 or high_st == "HIGH" else "PARTIALLY_SUPPORTED"
        # Song disagreement → context dependent
        if song_effort == "LOW" and status == "CONFIRMED":
            # task shows increase even if song low — task-specific
            pass
        if song_effort == "HIGH" and direction != "INCREASED":
            status = "CONTEXT_DEPENDENT"
        return _empty_eval(
            concern_id,
            status,
            support=support,
            against=against,
            missing=missing,
            task_ids_used=used,
            song_evidence_used=[f"song_effort_{song_effort}"],
            contrast_evidence=[effort_c],
            candidate_causes=causes,
            confidence_label=effort_c.get("confidence") or "medium",
            answer_hint=(
                "편한 지속음보다 높은 음 과제에서 힘 관련 음향 패턴이 크게 증가했습니다. "
                "고음 자체의 안정성은 비교적 유지되는 편이라, 현재는 음높이 유지보다 힘 증가가 더 두드러진 제한으로 보입니다."
                if "high_note_stability_maintained" in against
                else "편한 음 대비 고음에서 힘 관련 패턴이 증가하는 것이 확인됐어요."
            ),
        )

    if direction == "SIMILAR" and base_st in ("LOW", "STABLE") and high_st in ("LOW", "STABLE", ""):
        against.append("baseline_and_high_both_low")
        status = "NOT_SUPPORTED_IN_THIS_RECORDING"
        if song_effort == "HIGH":
            status = "CONTEXT_DEPENDENT"
            support.append("song_effort_high_but_controlled_low")
        return _empty_eval(
            concern_id,
            status,
            support=support,
            against=against,
            task_ids_used=used,
            song_evidence_used=[f"song_effort_{song_effort}"],
            contrast_evidence=[effort_c],
            confidence_label="medium",
            answer_hint=(
                "노래에서는 힘 증가가 있었지만, 표준 고음 과제에서는 같은 변화가 반복되지 않았어요. "
                "곡의 강도나 표현 상황에 따라 힘 사용이 달라지는 것으로 보입니다."
                if status == "CONTEXT_DEPENDENT"
                else "편한 음과 고음 과제 모두에서 과도한 힘 증가 패턴이 뚜렷하지 않았어요."
            ),
        )

    return _empty_eval(
        concern_id,
        "UNRESOLVED",
        support=support,
        against=against,
        missing=missing or ["clear_effort_direction"],
        unresolved_reason="LOW_CONFIDENCE",
        task_ids_used=used,
        contrast_evidence=[effort_c],
        answer_hint="고음 힘 변화에 대한 근거가 엇갈려 보여요. 작은 강도에서 짧게 유지하며 힘 증가가 덜한 쪽을 비교해보세요.",
    )


def _resolve_general_effort(
    *,
    concern_id: str,
    song_effort: str,
    profiles: dict[str, dict[str, Any]],
    contrasts: dict[str, Any],
    user_skipped_tasks: Optional[set[str]] = None,
    song_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    high_eval = _resolve_high_note_effort(
        song_effort=song_effort,
        profiles=profiles,
        contrasts=contrasts,
        concern_id="HIGH_NOTE_TOO_EFFORTFUL",
        user_skipped_tasks=user_skipped_tasks,
        song_profile=song_profile,
    )
    # Prefer controlled contrast when available
    if high_eval["status"] in ("CONFIRMED", "PARTIALLY_SUPPORTED", "CONTEXT_DEPENDENT"):
        out = dict(high_eval)
        out["concern"] = concern_id
        out["concern_id"] = concern_id
        if concern_id == "THROAT_EFFORT" and high_eval["status"] == "CONFIRMED":
            out["answer_hint"] = (
                "노래·표준 과제에서 확인된 힘 증가 패턴이 현재 더 두드러진 제한으로 보입니다."
            )
        return out
    if song_effort == "HIGH":
        return _empty_eval(
            concern_id,
            "PARTIALLY_SUPPORTED",
            support=["song_effort_high"],
            song_evidence_used=["effort_assessment"],
            evidence_level="SONG_SUPPORTED",
            confidence_label="medium",
            candidate_causes=["GENERAL_EXCESS_EFFORT"],
            answer_hint=(
                "이번 노래에서는 일부 구간에서 힘 사용이 증가하는 발성 경향이 보여요."
            ),
        )
    if song_effort == "LOW":
        # Song low + no controlled confirmation → not supported (concern ≠ truth)
        return _empty_eval(
            concern_id,
            "NOT_SUPPORTED_IN_THIS_RECORDING",
            against=["song_effort_low"],
            support=high_eval.get("support") or [],
            song_evidence_used=["effort_assessment"],
            task_ids_used=high_eval.get("task_ids_used") or [],
            answer_hint=(
                "체감상 힘을 느끼셨지만, 이번 노래·표준 녹음에서는 "
                "과도한 effort와 일치하는 음향 패턴이 뚜렷하지 않았어요."
            ),
        )
    return _empty_eval(
        concern_id,
        high_eval.get("status") or "UNRESOLVED",
        support=high_eval.get("support") or [],
        against=high_eval.get("against") or [],
        missing=high_eval.get("missing") or [],
        unresolved_reason=high_eval.get("unresolved_reason"),
        task_ids_used=high_eval.get("task_ids_used") or [],
        answer_hint=high_eval.get("answer_hint"),
    )


def _resolve_high_note_stability(
    profiles: dict[str, dict[str, Any]],
    contrasts: dict[str, Any],
    user_skipped_tasks: Optional[set[str]] = None,
    song_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    skipped = user_skipped_tasks or set()
    if "high_note_sustain_a" in skipped and "high_note_sustain_a" not in profiles:
        return _empty_eval(
            "HIGH_NOTE_UNSTABLE",
            "UNRESOLVED",
            unresolved_reason="USER_SKIPPED_RELEVANT_TASK",
            controlled_confirmation="NOT_AVAILABLE_USER_SKIPPED",
            missing=["high_note_sustain_a"],
            answer_hint=None,
        )
    contrast = ((contrasts.get("baseline_vs_high") or {}).get("dimensions") or {}).get("stability") or {}
    used = [t for t in ("sustain_a", "high_note_sustain_a") if t in profiles]
    if not contrast.get("available"):
        return _empty_eval(
            "HIGH_NOTE_UNSTABLE",
            "UNRESOLVED",
            unresolved_reason=contrast.get("reason") or "MISSING_BASELINE",
            task_ids_used=used,
            answer_hint="고음 안정성 비교에 필요한 baseline/고음 근거가 부족했어요.",
        )
    if contrast.get("direction") == "INCREASED" or str(contrast.get("high") or "").upper() == "UNSTABLE":
        return _empty_eval(
            "HIGH_NOTE_UNSTABLE",
            "CONFIRMED",
            support=[f"stability_{contrast.get('direction')}"],
            contrast_evidence=[contrast],
            task_ids_used=used,
            candidate_causes=["HIGH_NOTE_STABILITY_DROP"],
            answer_hint="편한 음보다 고음 과제에서 발성 안정성이 떨어지는 패턴이 확인됐어요.",
        )
    return _empty_eval(
        "HIGH_NOTE_UNSTABLE",
        "NOT_SUPPORTED_IN_THIS_RECORDING",
        against=["stability_maintained"],
        contrast_evidence=[contrast],
        task_ids_used=used,
        answer_hint="고음 과제에서도 발성 안정성은 비교적 유지되는 편이었어요.",
    )


def _resolve_registerish(
    concern_id: str,
    profiles: dict[str, dict[str, Any]],
    contrasts: dict[str, Any],
    song_profile: dict[str, Any],
    user_skipped_tasks: Optional[set[str]] = None,
) -> dict[str, Any]:
    skipped = user_skipped_tasks or set()
    siren = profiles.get("siren") or {}
    # Skip siren ≠ stop reasoning — fall through to song register evidence
    siren_skipped = "siren" in skipped and "siren" not in profiles
    reg = ((contrasts.get("siren_transition") or {}).get("dimensions") or {}).get("register") or {}
    vt = (song_profile.get("vocal_function_profile") or {}).get("vocal_type_profile") or {}
    song_reg = str((vt.get("register_strategy") or {}).get("status") or "").upper()
    canon = (vt.get("canonical_register") or {})
    if not song_reg and canon.get("status"):
        song_reg = str(canon.get("status") or "").upper()
    song_unresolved = song_reg in ("", "UNRESOLVED", "UNKNOWN", "INSUFFICIENT")

    if siren.get("valid") and reg and not siren_skipped:
        st = str(reg.get("status") or "").upper()
        if st in ("DISRUPTED", "UNSTABLE", "INSUFFICIENT"):
            return _empty_eval(
                concern_id,
                "CONFIRMED",
                support=[f"siren_{st}"],
                task_ids_used=["siren"],
                candidate_causes=["REGISTER_TRANSITION_DISRUPTION"],
                answer_hint="사이렌 과제에서 중음→고음 연결이 끊기거나 불안정한 패턴이 보였어요.",
            )
        if st in ("CONNECTED", "SMOOTH", "STABLE", "CONTINUOUS"):
            # Effort may still explain high-note concern
            if concern_id == "HIGH_NOTE_CANNOT_REACH":
                effort = _resolve_high_note_effort(
                    song_effort=_song_effort_level(song_profile),
                    profiles=profiles,
                    contrasts=contrasts,
                    concern_id="HIGH_NOTE_TOO_EFFORTFUL",
                    user_skipped_tasks=skipped,
                    song_profile=song_profile,
                )
                if effort["status"] in ("CONFIRMED", "PARTIALLY_SUPPORTED"):
                    out = dict(effort)
                    out["concern"] = concern_id
                    out["concern_id"] = concern_id
                    out["against"] = list(out.get("against") or []) + ["register_transition_ok"]
                    out["answer_hint"] = (
                        "이번 검사에서는 성구 전환 자체보다 높은 음에서 힘이 크게 증가하는 패턴이 더 두드러졌습니다. "
                        "전환 문제는 이번 녹음만으로 단정하기 어려워요."
                    )
                    return out
            return _empty_eval(
                concern_id,
                "NOT_SUPPORTED_IN_THIS_RECORDING",
                against=["siren_continuous"],
                task_ids_used=["siren"],
                answer_hint="사이렌에서는 연결이 비교적 연속적으로 보였어요.",
            )

    # Song register direct / partial — actionable via ensure_actionable_guidance
    if song_reg in ("DISRUPTED", "UNSTABLE", "TRANSITION_EVENTS", "PARTIAL", "MIXED"):
        return _empty_eval(
            concern_id,
            "PARTIALLY_SUPPORTED",
            support=[f"song_register_{song_reg}"],
            song_evidence_used=["register_strategy"],
            evidence_level="SONG_SUPPORTED",
            confidence_label="medium",
            candidate_causes=["REGISTER_TRANSITION_DISRUPTION"],
            controlled_confirmation=(
                "NOT_AVAILABLE_USER_SKIPPED" if siren_skipped else None
            ),
            unresolved_reason="USER_SKIPPED_RELEVANT_TASK" if siren_skipped else None,
            missing=["siren"] if siren_skipped else [],
            answer_hint=None,
        )

    if song_unresolved:
        return _empty_eval(
            concern_id,
            "UNRESOLVED",
            unresolved_reason="REGISTER_INSUFFICIENT",
            controlled_confirmation=(
                "NOT_AVAILABLE_USER_SKIPPED" if siren_skipped else None
            ),
            song_evidence_used=["register_strategy"],
            missing=["siren"] if siren_skipped else [],
            answer_hint=None,
        )
    return _empty_eval(
        concern_id,
        "UNRESOLVED",
        unresolved_reason="NO_RELEVANT_TASK_EVIDENCE",
        controlled_confirmation=(
            "NOT_AVAILABLE_USER_SKIPPED" if siren_skipped else None
        ),
        missing=["siren_or_register"],
        answer_hint=None,
    )


def _axis_continuum(timbre: dict[str, Any], name: str) -> Optional[float]:
    ax = (timbre.get("axes") or {}).get(name) or {}
    v = ax.get("continuum")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _axis_status(timbre: dict[str, Any], name: str) -> str:
    ax = (timbre.get("axes") or {}).get(name) or {}
    return str(ax.get("status") or "").upper()


def _task_timbre_proxies(
    profiles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Controlled-task proxies when song timbre axes are unavailable. No invented physiology."""
    base = (profiles.get("sustain_a") or {}).get("dimensions") or {}
    i_dims = (profiles.get("sustain_i") or {}).get("dimensions") or {}
    res = base.get("resonance") or i_dims.get("resonance") or {}
    breath = base.get("breathiness") or {}
    contact = base.get("contact") or {}
    out: dict[str, Any] = {"sources": [], "bits": [], "bright": None, "presence": None, "airiness": None}
    res_st = str(res.get("status") or "").upper()
    if res.get("available"):
        out["sources"].append("task_resonance")
        if res_st in ("DARK", "MUFFLED", "LOW_PRESENCE"):
            out["bright"] = 0.32
            out["presence"] = 0.32
            out["bits"].append("스펙트럼이 어두운 편")
        elif res_st in ("BRIGHT", "FORWARD", "HIGH_PRESENCE"):
            out["bright"] = 0.65
            out["presence"] = 0.58
            out["bits"].append("스펙트럼이 밝은 편")
        else:
            out["bits"].append(f"공명 경향 {res_st.lower()}")
    if breath.get("available") and str(breath.get("status") or "").upper() != "INSUFFICIENT":
        out["sources"].append("task_breathiness")
        bst = str(breath.get("status") or "").upper()
        if bst == "HIGH":
            out["airiness"] = 0.7
            out["bits"].append("숨 섞임이 있는 편")
        elif bst == "LOW":
            out["airiness"] = 0.25
            out["bits"].append("숨 섞임이 적은 편")
        else:
            out["airiness"] = 0.45
            out["bits"].append("숨 섞임은 보통")
    if contact.get("available"):
        out["sources"].append("task_contact")
        cst = str(contact.get("status") or "").upper()
        if cst in ("FIRM", "FIRM_LEANING"):
            out["bits"].append("접촉감이 단단한 편")
        elif cst in ("LIGHT", "LIGHT_LEANING"):
            out["bits"].append("접촉감이 가벼운 편")
        elif cst == "MID":
            out["bits"].append("접촉감은 중간")
    return out


def _resolve_timbre(
    concern_id: str,
    timbre: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
    contrasts: dict[str, Any],
    song_profile: dict[str, Any],
) -> dict[str, Any]:
    axes = timbre.get("axes") or {}
    used_tasks = [t for t in ("sustain_a", "sustain_i", "high_note_sustain_a") if t in profiles]
    bright = _axis_continuum(timbre, "brightness")
    presence = _axis_continuum(timbre, "presence")
    airiness = _axis_continuum(timbre, "airiness")
    texture = _axis_continuum(timbre, "texture")
    consistency = _axis_continuum(timbre, "timbre_consistency")
    song_timbre_ok = bool(axes) and bool(timbre.get("available", True))
    proxies = _task_timbre_proxies(profiles) if not song_timbre_ok else {"bits": [], "sources": []}

    # Fallback proxies from controlled resonance/breathiness when song timbre thin
    if not song_timbre_ok:
        if bright is None:
            bright = proxies.get("bright")
        if presence is None:
            presence = proxies.get("presence")
        if airiness is None:
            airiness = proxies.get("airiness")

    support: list[str] = []
    against: list[str] = []
    missing: list[str] = []
    causes: list[str] = []

    if concern_id == "VOICE_TOO_NASAL_PERCEPT":
        return _empty_eval(
            concern_id,
            "UNRESOLVED",
            unresolved_reason="NASALITY_NOT_DIRECTLY_MEASURED",
            missing=["direct_nasality_metric"],
            note="답답함≠콧소리. 비강/연구개 생리는 현재 확정하지 않아요.",
            answer_hint="콧소리처럼 들린다는 인상은 이번 음향 지표만으로 단정하기 어려워요. 답답한 인상과는 별개로 다뤄요.",
            confidence_label="low",
        )

    if concern_id == "TIMBRE_DISSATISFIED":
        bits: list[str] = []
        if bright is not None:
            bits.append("밝은 편" if bright >= 0.58 else "어두운 편" if bright <= 0.42 else "밝기는 보통")
            support.append(f"brightness={bright:.2f}")
        if presence is not None:
            bits.append(
                "중역 존재감이 낮은 편"
                if presence <= 0.42
                else "중역 존재감이 있는 편"
                if presence >= 0.58
                else "중역 존재감은 보통"
            )
            support.append(f"presence={presence:.2f}")
        if airiness is not None:
            bits.append(
                "숨 섞임이 적은 편"
                if airiness <= 0.4
                else "숨 섞임이 있는 편"
                if airiness >= 0.55
                else "숨 섞임은 보통"
            )
            support.append(f"airiness={airiness:.2f}")
        if texture is not None:
            bits.append("질감이 거친 편" if texture >= 0.58 else "질감이 매끈한 편" if texture <= 0.42 else "질감은 보통")
            support.append(f"texture={texture:.2f}")
        if consistency is not None and consistency <= 0.4:
            bits.append("구간별 음색 변화가 큰 편")
            support.append(f"consistency={consistency:.2f}")
        # Controlled-task descriptive bits when song axes missing
        for b in proxies.get("bits") or []:
            if b not in bits:
                bits.append(b)
        if not bits and not support:
            return _empty_eval(
                concern_id,
                "UNRESOLVED",
                unresolved_reason="INSUFFICIENT_TIMBRE_FAMILIES",
                missing=["timbre_axes"],
                evidence_level="INSUFFICIENT",
                answer_hint="이번 분석에서 음색 특징을 설명할 수 있는 근거가 충분하지 않았어요.",
            )
        hint = "이번 노래의 음색은 " + ", ".join(bits[:3]) + "으로 보여요."
        if not song_timbre_ok and proxies.get("sources"):
            hint += " (노래 음색 축이 부족해 표준 과제 음향 특징으로 보완했어요.)"
        return _empty_eval(
            concern_id,
            "PARTIALLY_SUPPORTED",
            support=support or list(proxies.get("sources") or ["task_timbre_proxy"]),
            task_ids_used=used_tasks,
            song_evidence_used=["timbre_profile"] if song_timbre_ok else [],
            evidence_level="SONG_SUPPORTED" if song_timbre_ok else "SONG_INFERRED",
            confidence_label="medium" if (song_timbre_ok and len(support) >= 2) else "low",
            answer_hint=hint,
        )

    if concern_id == "VOICE_TOO_DARK_MUFFLED":
        if bright is None and presence is None and airiness is None:
            return _empty_eval(
                concern_id,
                "UNRESOLVED",
                unresolved_reason="INSUFFICIENT_TIMBRE_FAMILIES",
                missing=["brightness", "presence", "airiness"],
                answer_hint=(
                    "이번 분석에서 답답한 인상을 설명할 수 있는 "
                    "밝기·중역 존재감·숨 섞임 근거가 충분하지 않았어요."
                ),
                evidence_level="INSUFFICIENT",
            )
        if presence is not None and presence <= 0.42:
            support.append(f"low_presence={presence:.2f}")
            causes.append("LOW_PRESENCE")
        if bright is not None and bright <= 0.42:
            support.append(f"low_brightness={bright:.2f}")
            causes.append("LOW_BRIGHTNESS")
        # Firm/low-air alone is only a supporting cue — not enough to confirm muffled
        firm_low_air = airiness is not None and airiness <= 0.35
        if presence is not None and presence >= 0.55:
            against.append(f"presence_ok={presence:.2f}")
        if bright is not None and bright >= 0.55:
            against.append(f"brightness_ok={bright:.2f}")
        dark_support = [s for s in support if s.startswith("low_")]
        if firm_low_air and dark_support:
            support.append(f"low_airiness={airiness:.2f}")
            causes.append("FIRM_LOW_AIRINESS_PATTERN")
        elif firm_low_air and not dark_support:
            against.append(f"low_airiness_alone={airiness:.2f}")
        if len(dark_support) >= 2 or (len(dark_support) >= 1 and firm_low_air and not against):
            # Song-only: never CONTROLLED_CONFIRMED language; keep PARTIAL unless tasks present
            has_task = any((profiles.get(t) or {}).get("valid") for t in profiles)
            status = "CONFIRMED" if (has_task and len(dark_support) >= 2) else "PARTIALLY_SUPPORTED"
        elif against and not dark_support:
            status = "NOT_SUPPORTED_IN_THIS_RECORDING"
        elif dark_support and against:
            status = "PARTIALLY_SUPPORTED"
        else:
            status = "UNRESOLVED"
            missing.extend(
                x
                for x in ("brightness", "presence")
                if (bright is None if x == "brightness" else presence is None)
            )
        hint = None
        if status in ("CONFIRMED", "PARTIALLY_SUPPORTED") and dark_support:
            bits = []
            if bright is not None and bright <= 0.42:
                bits.append("밝기")
            if presence is not None and presence <= 0.42:
                bits.append("중역 존재감")
            hint = (
                "이번 노래에서는 일부 구간에서 "
                + ("와 ".join(bits) if bits else "음색 특징")
                + "이 낮아지는 경향이 있어, 답답하게 느껴지는 인상과 관련된 것으로 보여요."
            )
            if firm_low_air:
                hint += " 숨 섞임은 많지 않은 편이에요."
        elif status == "NOT_SUPPORTED_IN_THIS_RECORDING":
            hint = (
                "전체적으로 어둡거나 막힌 음색으로 보이지는 않아요. "
                "이번 노래에서는 밝기와 중역 존재감이 비교적 유지되는 편입니다."
            )
        else:
            hint = (
                "이번 분석에서 답답한 인상의 원인을 하나로 좁힐 수 있는 "
                "근거가 충분하지 않았어요."
            )
        el = (
            "CONTROLLED_CONFIRMED"
            if status == "CONFIRMED"
            else "SONG_SUPPORTED"
            if status in ("PARTIALLY_SUPPORTED", "NOT_SUPPORTED_IN_THIS_RECORDING")
            else "INSUFFICIENT"
        )
        return _empty_eval(
            concern_id,
            status,
            support=support,
            against=against,
            missing=missing,
            candidate_causes=causes,
            task_ids_used=used_tasks,
            song_evidence_used=["timbre_profile"] if song_timbre_ok else list(proxies.get("sources") or []),
            evidence_level=el,
            confidence_label="medium" if len(dark_support) >= 2 else "low",
            answer_hint=hint,
            unresolved_reason=None
            if status != "UNRESOLVED"
            else ("INSUFFICIENT_TIMBRE_FAMILIES" if missing else "CONFLICTING_TASK_RESULTS"),
        )

    if concern_id == "VOICE_TOO_THIN":
        if airiness is not None and airiness >= 0.55:
            support.append(f"high_airiness={airiness:.2f}")
            causes.append("HIGH_AIRINESS")
        if presence is not None and presence <= 0.42:
            support.append(f"low_presence={presence:.2f}")
            causes.append("LOW_PRESENCE")
        from .song_evidence import get_canonical_snapshot

        c_snap = (get_canonical_snapshot(song_profile).get("contact") or {})
        contact = ((profiles.get("sustain_a") or {}).get("dimensions") or {}).get("contact") or {}
        cst = str(c_snap.get("status") or contact.get("status") or "").upper()
        if cst in ("LIGHT", "LIGHT_LEANING"):
            support.append("light_contact")
            causes.append("LIGHT_CONTACT")
        if not support:
            return _empty_eval(
                concern_id,
                "NOT_SUPPORTED_IN_THIS_RECORDING" if (airiness is not None or presence is not None) else "UNRESOLVED",
                against=["thin_cues_absent"],
                missing=[] if axes else ["timbre_axes"],
                unresolved_reason=None if axes else "INSUFFICIENT_TIMBRE_FAMILIES",
                evidence_level="SONG_SUPPORTED" if axes else "INSUFFICIENT",
                answer_hint=(
                    "이번 노래에서는 얇게 들리는 인상과 직접 일치하는 "
                    "음향 패턴은 강하지 않았어요. 기본적으로는 비교적 선명한 쪽의 음색으로 보여요."
                    if axes
                    else "이번 분석에서 얇은 인상을 설명할 수 있는 근거가 충분하지 않았어요."
                ),
            )
        families = len(causes)
        if "HIGH_AIRINESS" in causes and "LOW_PRESENCE" in causes:
            hint = (
                "이번 노래에서는 숨 섞임이 많고 중역 존재감이 낮아지는 특징이 함께 나타나, "
                "소리가 얇게 느껴지는 데 영향을 주는 것으로 보여요."
            )
            el = "SONG_SUPPORTED"
        elif "LOW_PRESENCE" in causes and "HIGH_AIRINESS" not in causes:
            air_note = (
                "숨이 많이 섞여서 얇게 들리는 유형이라기보다, "
                if airiness is not None and airiness <= 0.4
                else ""
            )
            contact_note = "가벼운 음질과 " if "LIGHT_CONTACT" in causes else ""
            hint = (
                f"이번 노래에서는 {air_note}{contact_note}"
                "상대적으로 낮은 중역 존재감이 얇은 인상과 관련된 것으로 보여요."
            )
            el = "SONG_SUPPORTED" if families >= 2 else "SONG_INFERRED"
        elif "HIGH_AIRINESS" in causes:
            hint = (
                "이번 노래에서는 숨 섞임이 늘어나는 경향이 있어 "
                "얇게 느껴지는 인상과 관련될 가능성이 있어 보여요."
            )
            el = "SONG_INFERRED" if families < 2 else "SONG_SUPPORTED"
        else:
            hint = "이번 노래에서 확인된 음색·접촉 특징이 얇은 인상과 일부 관련된 것으로 보여요."
            el = "SONG_INFERRED"
        return _empty_eval(
            concern_id,
            "PARTIALLY_SUPPORTED",
            support=support,
            candidate_causes=causes,
            task_ids_used=used_tasks,
            song_evidence_used=["timbre_profile"] if song_timbre_ok else ["canonical_song_evidence"],
            evidence_level=el,
            answer_hint=hint,
        )

    if concern_id == "VOICE_TOO_BREATHY":
        vf = song_profile.get("vocal_function_profile") or {}
        leak = (vf.get("dimensions") or {}).get("air_leakage_breathiness") or {}
        st = str(leak.get("status") or "").upper()
        base_br = ((profiles.get("sustain_a") or {}).get("dimensions") or {}).get("breathiness") or {}
        if st in ("INCREASED", "HIGH", "ELEVATED") or str(base_br.get("status") or "").upper() == "HIGH":
            return _empty_eval(
                concern_id,
                "CONFIRMED",
                support=["breathiness_high"],
                candidate_causes=["HIGH_AIRINESS"],
                task_ids_used=used_tasks,
                song_evidence_used=["air_leakage_breathiness"],
                answer_hint="숨 섞임이 상대적으로 두드러지는 패턴이 확인됐어요.",
            )
        if st in ("STABLE", "LOW", "NORMAL") or str(base_br.get("status") or "").upper() == "LOW":
            return _empty_eval(
                concern_id,
                "NOT_SUPPORTED_IN_THIS_RECORDING",
                against=["breathiness_low"],
                answer_hint="이번 녹음에서는 숨 섞임이 크게 두드러지지 않았어요.",
            )
        return _empty_eval(concern_id, "UNRESOLVED", unresolved_reason="INSUFFICIENT_TIMBRE_FAMILIES")

    if concern_id == "VOICE_TOO_SHARP":
        if bright is not None and bright >= 0.6:
            return _empty_eval(
                concern_id,
                "PARTIALLY_SUPPORTED",
                support=[f"brightness={bright:.2f}"],
                song_evidence_used=["timbre_profile"],
                answer_hint="밝기가 높은 편이어서 날카롭게 들릴 수 있는 특징이 일부 확인됐어요.",
            )
        if bright is not None:
            return _empty_eval(
                concern_id,
                "NOT_SUPPORTED_IN_THIS_RECORDING",
                against=[f"brightness={bright:.2f}"],
                answer_hint="밝기가 과도하게 높은 패턴은 뚜렷하지 않았어요.",
            )
        return _empty_eval(concern_id, "UNRESOLVED", unresolved_reason="INSUFFICIENT_TIMBRE_FAMILIES")

    if concern_id == "VOICE_ROUGH":
        tex = texture
        stab = ((profiles.get("sustain_a") or {}).get("dimensions") or {}).get("stability") or {}
        if (tex is not None and tex >= 0.58) or str(stab.get("status") or "").upper() == "UNSTABLE":
            return _empty_eval(
                concern_id,
                "PARTIALLY_SUPPORTED",
                support=["texture_or_stability"],
                candidate_causes=["STABILITY_COST"],
                answer_hint="질감이 거칠거나 안정성이 떨어지는 구간이 일부 확인됐어요.",
            )
        return _empty_eval(
            concern_id,
            "NOT_SUPPORTED_IN_THIS_RECORDING" if tex is not None or stab else "UNRESOLVED",
            against=["rough_cues_weak"],
            unresolved_reason=None if (tex is not None or stab) else "INSUFFICIENT_TIMBRE_FAMILIES",
            answer_hint="거친 인상과 일치하는 패턴이 뚜렷하지 않았어요."
            if tex is not None or stab
            else "거친 인상 관련 지표가 부족했어요.",
        )

    if concern_id == "TIMBRE_CHANGES_HIGH":
        # Use high-note vs baseline resonance/breathiness as proxy when mid/high timbre shift absent
        hn_change = (song_profile.get("vocal_function_profile") or {}).get("timbre_profile") or {}
        change = hn_change.get("high_note_timbre_change") or {}
        if change:
            support = [f"{k}={v}" for k, v in change.items() if v is not None]
            if support:
                return _empty_eval(
                    concern_id,
                    "PARTIALLY_SUPPORTED",
                    support=support,
                    song_evidence_used=["high_note_timbre_change"],
                    answer_hint="고음에서 음색 축이 달라지는 변화가 일부 확인됐어요.",
                )
        breath = ((contrasts.get("baseline_vs_high") or {}).get("dimensions") or {}).get("breathiness") or {}
        if breath.get("direction") == "INCREASED":
            return _empty_eval(
                concern_id,
                "PARTIALLY_SUPPORTED",
                support=["high_breathiness_shift"],
                contrast_evidence=[breath],
                task_ids_used=used_tasks,
                answer_hint="고음 과제에서 숨 섞임·음색 쪽 변화가 일부 확인됐어요.",
            )
        return _empty_eval(
            concern_id,
            "UNRESOLVED",
            unresolved_reason="NO_RELEVANT_TASK_EVIDENCE",
            missing=["high_note_timbre_change"],
        )

    return _empty_eval(concern_id, "UNRESOLVED", unresolved_reason="NO_RELEVANT_TASK_EVIDENCE")


def infer_precision_bottleneck(
    *,
    song_profile: dict[str, Any],
    fused_profile: Optional[dict[str, Any]] = None,
    concern_evaluations: Optional[list[dict[str, Any]]] = None,
    controlled_contrasts: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Prefer strong controlled evidence over song-only primary."""
    from .concerns import _infer_bottleneck

    song_bn = _infer_bottleneck(song_profile)
    fused = fused_profile or {}
    contrasts = controlled_contrasts or fused.get("controlled_contrasts") or {}
    evals = concern_evaluations or []

    # 1) Confirmed concern with task-derived cause
    for ev in evals:
        if ev.get("status") not in ("CONFIRMED", "PARTIALLY_SUPPORTED"):
            continue
        causes = ev.get("candidate_causes") or []
        cid = ev.get("concern_id") or ev.get("concern")
        if "EFFORT_ESCALATION_WITH_HEIGHT" in causes:
            return {
                "bottleneck": "HIGH_NOTE_EFFORT",
                "source": "TASK" if ev.get("contrast_evidence") else "BOTH",
                "from_concern": cid,
            }
        if "REGISTER_TRANSITION_DISRUPTION" in causes:
            return {
                "bottleneck": "REGISTER_TRANSITION_DISRUPTION",
                "source": "TASK",
                "from_concern": cid,
            }
        if "LOW_PRESENCE" in causes or "LOW_BRIGHTNESS" in causes:
            return {
                "bottleneck": "LOW_PRESENCE",
                "source": "BOTH",
                "from_concern": cid,
            }
        if "HIGH_AIRINESS" in causes:
            return {
                "bottleneck": "AIR_LEAKAGE",
                "source": "BOTH",
                "from_concern": cid,
            }
        if "HIGH_NOTE_STABILITY_DROP" in causes:
            return {
                "bottleneck": "HIGH_NOTE_STABILITY_DROP",
                "source": "TASK",
                "from_concern": cid,
            }

    effort_c = ((contrasts.get("baseline_vs_high") or {}).get("dimensions") or {}).get("effort") or {}
    if effort_c.get("direction") == "INCREASED":
        return {"bottleneck": "HIGH_NOTE_EFFORT", "source": "TASK", "from_concern": None}

    if song_bn and song_bn != "UNRESOLVED":
        return {"bottleneck": song_bn, "source": "SONG", "from_concern": None}
    return {"bottleneck": "UNRESOLVED", "source": "NONE", "from_concern": None}
