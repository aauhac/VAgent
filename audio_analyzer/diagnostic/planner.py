"""Adaptive Precision Diagnostic planner (deterministic, no LLM).

Selects the minimum set of standardized tasks that cover song-level
dimension uncertainty. Uncertainty ≠ abnormality.
"""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.diagnostic.task_registry import (
    DIMENSION_ALIASES,
    DIMENSION_PRIORITY,
    DIMENSION_USER_LABELS,
    DIAGNOSTIC_MODE_CONCERN,
    DIAGNOSTIC_MODE_GENERAL,
    DIAGNOSTIC_STATUS_NORMAL,
    DIAGNOSTIC_STATUS_SAFETY_LIMITED,
    PLANNER_VERSION,
    PRECISION_CORE_FALLBACK,
    PRECISION_CORE_GENERAL,
    PROTOCOL_VERSION,
    TASK_REGISTRY,
    normalize_recommended_task,
    user_labels_for_dimensions,
)

# Song engine dimension_id → planner key
_ENGINE_TO_PLANNER = {v: k for k, v in DIMENSION_ALIASES.items() if k != "roughness"}
_ENGINE_TO_PLANNER["phonation_regularity"] = "stability"

# Issue ids from measurement_candidates → planner dimension
_ISSUE_TO_DIM = {
    "EXCESS_EFFORT_HIGH_NOTE": "effort",
    "effort": "effort",
    "AIR_LEAK_BREATHINESS": "breathiness",
    "breathiness": "breathiness",
    "CONTACT_LIGHT": "contact",
    "CONTACT_FIRM": "contact",
    "contact": "contact",
    "REGISTER_TRANSITION_DISRUPTION": "register",
    "register": "register",
    "ROUGHNESS": "stability",
    "roughness": "stability",
    "stability": "stability",
    "RESONANCE_HIGH_NOTE_COLLAPSE": "resonance",
    "resonance": "resonance",
    "onset": "onset",
    "ABRUPT_ONSET": "onset",
}


def _confidence_rank(label: Optional[str]) -> int:
    m = {"high": 3, "medium": 2, "low": 1, "unknown": 0, None: 0}
    return m.get((label or "").lower(), 0)


def _resolve_state(row: dict[str, Any]) -> str:
    """Map criteria-matrix row → RESOLVED | PARTIALLY_RESOLVED | UNRESOLVED | UNAVAILABLE."""
    suf = (row.get("measurement_sufficiency") or "").upper()
    finding = (row.get("finding") or "").upper()
    elig = (row.get("coaching_eligibility") or "").upper()
    conf = _confidence_rank(row.get("confidence_label"))
    req_t = int(row.get("required_total") or 0)
    req_s = int(row.get("required_satisfied") or 0)

    if suf == "UNAVAILABLE":
        return "UNAVAILABLE"
    if suf in ("INSUFFICIENT",) or finding == "UNDETERMINED":
        return "UNRESOLVED"
    if elig in ("NEEDS_MEASUREMENT", "BLOCKED_INSUFFICIENT"):
        return "UNRESOLVED"
    if conf <= 1 and suf != "SUFFICIENT":
        return "UNRESOLVED"
    if conf <= 1:
        return "PARTIALLY_RESOLVED"
    if req_t and req_s < req_t:
        return "PARTIALLY_RESOLVED"
    if suf == "SUFFICIENT" and conf >= 2 and finding not in ("UNDETERMINED",):
        return "RESOLVED"
    if suf == "PARTIAL":
        return "PARTIALLY_RESOLVED"
    return "PARTIALLY_RESOLVED"


def build_uncertainty_profile(
    *,
    criteria_matrix: Optional[list[dict[str, Any]]] = None,
    dimensions: Optional[dict[str, Any]] = None,
    measurement_candidates: Optional[list[dict[str, Any]]] = None,
    song_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build planner-readable uncertainty profile from song analysis."""
    criteria_matrix = criteria_matrix or []
    dimensions = dimensions or {}
    measurement_candidates = measurement_candidates or []
    song_context = song_context or {}

    by_engine = {r.get("dimension_id"): r for r in criteria_matrix if r.get("dimension_id")}
    entries: list[dict[str, Any]] = []

    for planner_key in DIMENSION_PRIORITY:
        engine_id = DIMENSION_ALIASES.get(planner_key, planner_key)
        row = by_engine.get(engine_id) or {}
        dim = dimensions.get(engine_id) or {}
        if not row and dim:
            # Fallback from dimension alone
            conf = dim.get("confidence_label") or "low"
            status = (dim.get("status") or "UNKNOWN").upper()
            state = (
                "UNRESOLVED"
                if status in ("UNKNOWN",) or _confidence_rank(conf) <= 1
                else "RESOLVED"
                if _confidence_rank(conf) >= 2 and status not in ("UNKNOWN",)
                else "PARTIALLY_RESOLVED"
            )
            miss = []
            req_s = req_t = 0
            suf = "INSUFFICIENT" if state == "UNRESOLVED" else "SUFFICIENT"
            estimate = dim.get("summary") or dim.get("status")
            conf_label = conf
        elif row:
            state = _resolve_state(row)
            miss = [
                c.get("criterion_id")
                for c in (row.get("criteria") or [])
                if c.get("required") and c.get("availability") in ("INSUFFICIENT", "NOT_AVAILABLE")
            ]
            req_s = int(row.get("required_satisfied") or 0)
            req_t = int(row.get("required_total") or 0)
            suf = row.get("measurement_sufficiency")
            estimate = row.get("finding") or dim.get("status")
            conf_label = row.get("confidence_label") or dim.get("confidence_label")
        else:
            continue

        entries.append(
            {
                "dimension_id": planner_key,
                "engine_dimension_id": engine_id,
                "state": state,
                "estimate": estimate,
                "confidence": conf_label,
                "measurement_sufficiency": suf,
                "required_satisfied": req_s,
                "required_total": req_t,
                "missing_criteria": miss,
                "song_context": song_context,
            }
        )

    # measurement_candidates can force UNRESOLVED / add candidate tasks
    cand_by_dim: dict[str, list[dict[str, Any]]] = {}
    unsupported: list[dict[str, Any]] = []
    for m in measurement_candidates:
        issue = m.get("issue") or m.get("id")
        dim_key = _ISSUE_TO_DIM.get(str(issue or ""), None)
        norm = normalize_recommended_task(m.get("recommended_task"))
        if not norm.get("supported"):
            unsupported.append({**m, "normalize": norm})
        if dim_key:
            cand_by_dim.setdefault(dim_key, []).append({**m, "normalize": norm})
            for e in entries:
                if e["dimension_id"] == dim_key and e["state"] == "RESOLVED":
                    # needs_confirmation soft-demotes only when eligibility says so
                    if (m.get("eligibility") or "").upper() in (
                        "NEEDS_MEASUREMENT",
                        "LOW_CONFIDENCE",
                    ):
                        e["state"] = "PARTIALLY_RESOLVED"
                elif e["dimension_id"] == dim_key and e["state"] != "UNAVAILABLE":
                    if (m.get("eligibility") or "").upper() == "NEEDS_MEASUREMENT":
                        e["state"] = "UNRESOLVED"

    for e in entries:
        e["measurement_candidates"] = cand_by_dim.get(e["dimension_id"]) or []

    unresolved = [e for e in entries if e["state"] in ("UNRESOLVED", "PARTIALLY_RESOLVED")]
    # Planner targets UNRESOLVED first; PARTIALLY only if still needs confirmation
    target = [e for e in entries if e["state"] == "UNRESOLVED"]
    # Include PARTIALLY when confidence low
    for e in entries:
        if e["state"] == "PARTIALLY_RESOLVED" and _confidence_rank(e.get("confidence")) <= 1:
            if e not in target:
                target.append(e)

    return {
        "planner_version": PLANNER_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "dimensions": entries,
        "unresolved_dimensions": [e["dimension_id"] for e in target],
        "resolved_dimensions": [e["dimension_id"] for e in entries if e["state"] == "RESOLVED"],
        "partial_dimensions": [
            e["dimension_id"] for e in entries if e["state"] == "PARTIALLY_RESOLVED"
        ],
        "unsupported_recommendations": unsupported,
        "song_context": song_context,
    }


def _task_gain(
    task_id: str,
    remaining: set[str],
    *,
    concern_boost: Optional[dict[str, float]] = None,
) -> float:
    meta = TASK_REGISTRY.get(task_id) or {}
    gains = meta.get("expected_gain") or {}
    primary = set(meta.get("covers") or [])
    score = 0.0
    boost = concern_boost or {}
    for d in remaining:
        g = float(gains.get(d) or 0.0)
        if d in primary:
            score += g
        elif g > 0:
            score += g * 0.5
        score += float(boost.get(d) or 0.0) * 0.35
    # Priority bonus
    for i, d in enumerate(DIMENSION_PRIORITY):
        if d in remaining and d in primary:
            score += 0.15 * (len(DIMENSION_PRIORITY) - i) / len(DIMENSION_PRIORITY)
            score += float(boost.get(d) or 0.0) * 0.2
    return score


def select_diagnostic_tasks(
    uncertainty_profile: dict[str, Any],
    *,
    fallback_all_if_empty_song: bool = False,
    force_tasks: Optional[list[str]] = None,
    user_concerns: Optional[list[dict[str, Any]]] = None,
    pain_safety_flag: bool = False,
) -> dict[str, Any]:
    """Greedy set-cover: minimize recordings while maximizing unresolved coverage."""
    if force_tasks is not None:
        selected = [t for t in force_tasks if t in TASK_REGISTRY]
        return {
            "planner_version": PLANNER_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "resolved_dimensions": uncertainty_profile.get("resolved_dimensions") or [],
            "unresolved_dimensions": uncertainty_profile.get("unresolved_dimensions") or [],
            "selected_tasks": selected,
            "expected_coverage": {t: task_covers_primary(t) for t in selected},
            "rationale": {"mode": "forced", "tasks": selected},
        }

    from .concerns import concern_dimension_boost, filter_tasks_for_safety, normalize_user_concerns

    concerns = normalize_user_concerns(user_concerns)
    concern_boost = concern_dimension_boost(concerns) if concerns else {}

    remaining = set(uncertainty_profile.get("unresolved_dimensions") or [])
    # Concern relevance: boost dimensions in hypothesis space without forcing re-measure of RESOLVED
    if concern_boost:
        dim_states = {
            e["dimension_id"]: e.get("state")
            for e in (uncertainty_profile.get("dimensions") or [])
        }
        for dim, _b in sorted(concern_boost.items(), key=lambda kv: -kv[1]):
            if dim_states.get(dim) in ("UNRESOLVED", "PARTIALLY_RESOLVED"):
                remaining.add(dim)
            elif dim_states.get(dim) is None and dim in DIMENSION_PRIORITY:
                remaining.add(dim)

    if not remaining and fallback_all_if_empty_song:
        # Optional high-note task is song-context driven — not part of default battery
        selected = [t for t in TASK_REGISTRY.keys() if not (TASK_REGISTRY[t].get("optional_high_note"))]
        return {
            "planner_version": PLANNER_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "resolved_dimensions": [],
            "unresolved_dimensions": [],
            "selected_tasks": selected,
            "expected_coverage": {t: task_covers_primary(t) for t in selected},
            "rationale": {"mode": "standalone_full_battery"},
        }

    selected: list[str] = []
    coverage: dict[str, list[str]] = {}
    rationale_steps: list[dict[str, Any]] = []
    song_ctx = uncertainty_profile.get("song_context") or {}
    high_note_needed = bool(
        song_ctx.get("high_note_profile_unavailable")
        or song_ctx.get("high_note_uncertain")
    )
    available = [
        tid
        for tid in TASK_REGISTRY.keys()
        if (not TASK_REGISTRY[tid].get("optional_high_note")) or high_note_needed
    ]

    while remaining:
        best_id = None
        best_score = 0.0
        for tid in available:
            if tid in selected:
                continue
            # Must cover at least one primary remaining dim
            primary = set((TASK_REGISTRY[tid].get("covers") or []))
            if not (primary & remaining):
                # allow secondary-only only if nothing else can cover
                gains = TASK_REGISTRY[tid].get("expected_gain") or {}
                if not any(d in remaining and float(gains.get(d) or 0) >= 0.5 for d in remaining):
                    continue
            score = _task_gain(tid, remaining, concern_boost=concern_boost) / float(
                TASK_REGISTRY[tid].get("cost") or 1.0
            )
            if score > best_score:
                best_score = score
                best_id = tid
        if best_id is None or best_score <= 0:
            break
        selected.append(best_id)
        covered = set(TASK_REGISTRY[best_id].get("covers") or [])
        # Also remove dims with high secondary gain when selected for them
        gains = TASK_REGISTRY[best_id].get("expected_gain") or {}
        for d in list(remaining):
            if d in covered or float(gains.get(d) or 0) >= 0.7:
                remaining.discard(d)
        coverage[best_id] = sorted(covered)
        rationale_steps.append(
            {
                "selected": best_id,
                "gain": round(best_score, 3),
                "covers": sorted(covered),
                "remaining_after": sorted(remaining),
            }
        )

    # Stable order: registry order
    order = list(TASK_REGISTRY.keys())
    selected = sorted(selected, key=lambda t: order.index(t) if t in order else 99)
    selected = filter_tasks_for_safety(
        selected,
        pain_flag=pain_safety_flag or bool(concerns and any(
            c.get("id") in {"PAIN_WHILE_SINGING", "PAIN_AFTER_SINGING", "SPEAKING_DISCOMFORT", "PERSISTENT_HOARSENESS"}
            for c in concerns
        )),
    )

    return {
        "planner_version": PLANNER_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "resolved_dimensions": uncertainty_profile.get("resolved_dimensions") or [],
        "unresolved_dimensions": uncertainty_profile.get("unresolved_dimensions") or [],
        "selected_tasks": selected,
        "provisional_task_count": len(selected),
        "planned_task_count": len(selected),
        "expected_coverage": coverage,
        "rationale": {
            "mode": "set_cover_provisional",
            "steps": rationale_steps,
            "concern_boost": concern_boost if concern_boost else None,
            "user_concern_ids": [c.get("id") for c in concerns],
            "note": "song-only provisional; precision protocol may add core tasks",
        },
        "debug": {
            "dimension_states": [
                {"dimension": e["dimension_id"], "state": e["state"], "confidence": e.get("confidence")}
                for e in (uncertainty_profile.get("dimensions") or [])
            ],
            "unsupported": uncertainty_profile.get("unsupported_recommendations") or [],
        },
    }


def _concern_wants_register(concerns: list[dict[str, Any]]) -> bool:
    ids = {str(c.get("id")) for c in concerns}
    return bool(
        ids
        & {
            "HIGH_NOTE_CANNOT_REACH",
            "HIGH_NOTE_FLIPS",
            "HIGH_NOTE_UNSTABLE",
            "REGISTER_CONNECTION_DIFFICULT",
            "TIMBRE_CHANGES_HIGH",
        }
    )


def _concern_wants_high_note(concerns: list[dict[str, Any]]) -> bool:
    ids = {str(c.get("id")) for c in concerns}
    return bool(
        ids
        & {
            "HIGH_NOTE_CANNOT_REACH",
            "HIGH_NOTE_TOO_EFFORTFUL",
            "HIGH_NOTE_FLIPS",
            "HIGH_NOTE_THINS",
            "HIGH_NOTE_UNSTABLE",
            "TIMBRE_CHANGES_HIGH",
        }
    )


def plan_precision_protocol(
    uncertainty_profile: dict[str, Any],
    *,
    diagnostic_mode: str = DIAGNOSTIC_MODE_GENERAL,
    user_concerns: Optional[list[dict[str, Any]]] = None,
    pain_safety_flag: bool = False,
    safety_flags: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Precision protocol: CORE + ADAPTIVE. Normal flow always has >= 1 controlled task."""
    from .concerns import concern_dimension_boost, filter_tasks_for_safety, normalize_user_concerns

    concerns = normalize_user_concerns(user_concerns)
    raw_mode = (diagnostic_mode or "").upper().strip()
    if raw_mode in (DIAGNOSTIC_MODE_GENERAL, "GENERAL"):
        mode = DIAGNOSTIC_MODE_GENERAL
        concerns = []
    elif raw_mode in (DIAGNOSTIC_MODE_CONCERN, "CONCERN") or concerns:
        mode = DIAGNOSTIC_MODE_CONCERN
    else:
        mode = DIAGNOSTIC_MODE_GENERAL
        concerns = []

    pain = bool(pain_safety_flag) or any(
        c.get("id") in {"PAIN_WHILE_SINGING", "PAIN_AFTER_SINGING", "SPEAKING_DISCOMFORT", "PERSISTENT_HOARSENESS"}
        for c in concerns
    )
    safety_flags = list(safety_flags or [])

    # --- CORE ---
    if mode == DIAGNOSTIC_MODE_GENERAL:
        core = list(PRECISION_CORE_GENERAL)
    else:
        core = ["sustain_a"]
        if _concern_wants_register(concerns):
            core.append("siren")
        # High-note concern → prefer high_note_sustain_a in adaptive, keep sustain baseline

    # --- ADAPTIVE set-cover on remaining unresolved ---
    provisional = select_diagnostic_tasks(
        uncertainty_profile,
        user_concerns=concerns if mode == DIAGNOSTIC_MODE_CONCERN else None,
        pain_safety_flag=False,  # apply safety once at the end
    )
    adaptive = [t for t in (provisional.get("selected_tasks") or []) if t not in core]

    if mode == DIAGNOSTIC_MODE_CONCERN and _concern_wants_high_note(concerns):
        song_ctx = uncertainty_profile.get("song_context") or {}
        # Prefer controlled high-note evidence when concern mentions high notes
        if "high_note_sustain_a" not in adaptive and "high_note_sustain_a" not in core:
            adaptive.append("high_note_sustain_a")
        # Allow high_note even if song didn't flag uncertain
        _ = song_ctx

    # Merge unique, registry order
    order = list(TASK_REGISTRY.keys())
    merged = list(dict.fromkeys([*core, *adaptive]))
    merged = sorted(merged, key=lambda t: order.index(t) if t in order else 99)

    # Safety filter
    filtered = filter_tasks_for_safety(merged, pain_flag=pain, safety_flags=safety_flags)
    status = DIAGNOSTIC_STATUS_NORMAL

    # Acute phonation pain / breathing difficulty → do not force any controlled recording
    severe_safety = {"pain_on_phonation", "breathing_difficulty"}
    if any(f in severe_safety for f in safety_flags) or (
        pain and not filtered and pain_safety_flag
    ):
        if any(f in severe_safety for f in safety_flags):
            filtered = []
            status = DIAGNOSTIC_STATUS_SAFETY_LIMITED
        elif pain and not filtered:
            status = DIAGNOSTIC_STATUS_SAFETY_LIMITED

    if pain and not filtered:
        status = DIAGNOSTIC_STATUS_SAFETY_LIMITED
    elif not filtered:
        # Normal invariant: never finish with zero controlled tasks
        filtered = list(PRECISION_CORE_FALLBACK)
        core = list(PRECISION_CORE_FALLBACK)
        adaptive = []

    core_final = [t for t in filtered if t in core]
    adaptive_final = [t for t in filtered if t not in core_final]
    if not core_final and filtered:
        core_final = [filtered[0]]
        adaptive_final = filtered[1:]

    coverage = {t: task_covers_primary(t) for t in filtered}
    return {
        "planner_version": PLANNER_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "diagnostic_mode": mode,
        "diagnostic_status": status,
        "resolved_dimensions": uncertainty_profile.get("resolved_dimensions") or [],
        "unresolved_dimensions": uncertainty_profile.get("unresolved_dimensions") or [],
        "core_tasks": core_final,
        "adaptive_tasks": adaptive_final,
        "selected_tasks": filtered,
        "provisional_task_count": int(provisional.get("provisional_task_count") or 0),
        "planned_task_count": len(filtered),
        "expected_coverage": coverage,
        "rationale": {
            "mode": "precision_core_adaptive",
            "diagnostic_mode": mode,
            "diagnostic_status": status,
            "core": core_final,
            "adaptive": adaptive_final,
            "pain_safety": pain,
            "user_concern_ids": [c.get("id") for c in concerns],
            "provisional_set_cover": provisional.get("rationale"),
        },
        "debug": provisional.get("debug") or {},
    }


def task_covers_primary(task_id: str) -> list[str]:
    return list((TASK_REGISTRY.get(task_id) or {}).get("covers") or [])


def explain_task_selection(plan: dict[str, Any]) -> dict[str, Any]:
    """User-safe explanation (no criterion ids).

    Song-only provisional counts are NOT used to claim 'no recording needed'.
    Precision product always expects controlled recordings in normal flow.
    """
    unresolved = plan.get("unresolved_dimensions") or []
    selected = plan.get("selected_tasks") or []
    planned = int(plan.get("planned_task_count") if plan.get("planned_task_count") is not None else len(selected))
    provisional = int(plan.get("provisional_task_count") if plan.get("provisional_task_count") is not None else planned)
    labels = user_labels_for_dimensions(unresolved)
    purposes = []
    for tid in selected:
        meta = TASK_REGISTRY.get(tid) or {}
        purposes.append(
            {
                "task_id": tid,
                "purpose_labels": meta.get("purpose_labels") or [],
            }
        )
    mode = plan.get("diagnostic_mode")
    status = plan.get("diagnostic_status") or DIAGNOSTIC_STATUS_NORMAL

    if status == DIAGNOSTIC_STATUS_SAFETY_LIMITED and planned == 0:
        cta = "현재 불편감이 있어 추가 고음·강한 소리 검사는 진행하지 않아요."
        lead = "안전을 위해 추가 녹음을 제한했어요."
        est = "추가 녹음 없음"
    elif planned > 0:
        if mode == DIAGNOSTIC_MODE_CONCERN:
            cta = (
                f"선택한 고민을 더 정확히 확인하기 위해 "
                f"짧은 추가 녹음 {planned}개를 진행해요."
            )
            lead = f"추가 녹음 {planned}개"
        elif mode == DIAGNOSTIC_MODE_GENERAL:
            cta = "전체 발성 특성을 더 정확히 확인하기 위해 짧은 추가 녹음을 진행해요."
            lead = f"추가 녹음 {planned}개"
        else:
            # Provisional / pre-concern offer — never claim zero recordings skip precision
            cta = (
                "현재 노래와 짧은 추가 녹음을 함께 분석해 "
                "발성 특성을 더 정밀하게 확인해요."
            )
            lead = "몇 가지 짧은 추가 녹음"
        est = f"약 {max(1, int(round(planned * 0.75)))}분"
    else:
        # Provisional song-only zero — still advertise precision as controlled recording product
        cta = (
            "현재 노래와 짧은 추가 녹음을 함께 분석해 "
            "발성 특성을 더 정밀하게 확인해요."
        )
        lead = "몇 가지 짧은 추가 녹음"
        est = "짧은 추가 녹음"

    return {
        "lead": lead,
        "cta_text": cta,
        "unresolved_labels": labels,
        "task_purposes": purposes,
        "selected_task_count": planned,
        "provisional_task_count": provisional,
        "planned_task_count": planned,
        "estimated_duration_text": est,
        "diagnostic_offer": {
            "unresolved_count": len(unresolved),
            "unresolved_labels": labels,
            # Provisional only — UI must not treat this as final planned count
            "selected_task_count": None,
            "provisional_task_count": provisional,
            "planned_task_count": planned if mode else None,
            "estimated_duration_text": est,
            "required": True,
            "required_tasks": True,
            "precision_requires_recording": True,
        },
    }


def plan_from_song_analysis(
    song: dict[str, Any],
    *,
    user_concerns: Optional[list[dict[str, Any]]] = None,
    pain_safety_flag: bool = False,
    diagnostic_mode: Optional[str] = None,
    safety_flags: Optional[list[str]] = None,
    precision: bool = False,
) -> dict[str, Any]:
    """Song analysis → plan.

    precision=False: provisional song-only set-cover (CTA offer).
    precision=True: CORE+ADAPTIVE protocol with controlled recording invariant.
    """
    vf = song.get("vocal_function_profile") or song.get("vocal_function") or {}
    if not vf and isinstance(song.get("report"), dict):
        vf = (song["report"].get("vocal_function_profile") or {})
    criteria = vf.get("criteria_matrix") or song.get("criteria_matrix") or []
    dims = vf.get("dimensions") or {}
    coach = vf.get("coaching_decision") or {}
    cands = coach.get("measurement_candidates") or vf.get("measurement_candidates") or []
    hn = vf.get("high_note_function_profile") or {}
    high_note_unavailable = isinstance(hn, dict) and hn.get("available") is False
    high_note_uncertain = False
    if isinstance(hn, dict) and hn.get("available"):
        axes = hn.get("axes") or {}
        uncertain_n = sum(
            1
            for ax in axes.values()
            if isinstance(ax, dict) and str(ax.get("status") or "").upper() == "UNCERTAIN"
        )
        high_note_uncertain = uncertain_n >= 2 or (hn.get("confidence_label") == "low")
    profile = build_uncertainty_profile(
        criteria_matrix=criteria,
        dimensions=dims,
        measurement_candidates=cands,
        song_context={
            "has_song": True,
            "high_note_profile_unavailable": high_note_unavailable,
            "high_note_uncertain": high_note_uncertain,
        },
    )
    if precision or diagnostic_mode:
        mode = diagnostic_mode or (
            DIAGNOSTIC_MODE_CONCERN if user_concerns else DIAGNOSTIC_MODE_GENERAL
        )
        plan = plan_precision_protocol(
            profile,
            diagnostic_mode=mode,
            user_concerns=user_concerns,
            pain_safety_flag=pain_safety_flag,
            safety_flags=safety_flags,
        )
    else:
        plan = select_diagnostic_tasks(
            profile,
            user_concerns=user_concerns,
            pain_safety_flag=pain_safety_flag,
        )
    explain = explain_task_selection(plan)
    return {**plan, **explain, "uncertainty_profile": profile}
