"""Coach Profile Engine — Vocal Type v1.2."""

from __future__ import annotations

from typing import Any, Optional

from . import config as cfg
from .bridge import compute_bridge
from .head_chest import (
    aggregate_family_summary,
    aggregate_range_profiles,
    detect_neutral_collapse,
    index_to_ratios,
    ratio_eligible,
    score_all_segments,
    song_evidence_stats,
    weighted_index,
)
from .modifiers import collect_modifiers
from .naming import (
    classify_base_type,
    coaching_link_sentence,
    compose_display_name,
    key_traits,
    one_line_description,
)
from .register_strategy import (
    classify_register_strategy,
    classify_source_balance,
    register_strategy_display,
)


def classify_vocal_type_resolution_state(
    *,
    base_type: str,
    confidence: str,
    ratios_available: bool,
    balance_class: str,
    neutral_collapse: bool,
) -> str:
    """Map engine branch flags to additive public resolution_state. Does not change type."""
    if str(base_type or "") != "UNRESOLVED":
        return "RESOLVED"
    bal = str(balance_class or "").upper()
    if bal == "CONFLICTED":
        return "CONFLICTED_EVIDENCE"
    if neutral_collapse:
        return "NEUTRAL_EVIDENCE"
    if confidence == "low" or not ratios_available:
        return "INSUFFICIENT_EVIDENCE"
    return "INSUFFICIENT_EVIDENCE"


def compute_vocal_type_profile(
    *,
    segments: list[dict[str, Any]],
    dimensions: dict[str, Any],
    episodes: Optional[list[dict[str, Any]]] = None,
    baseline: Optional[dict[str, Any]] = None,
    coaching_decision: Optional[dict[str, Any]] = None,
    criteria_matrix: Optional[list[dict[str, Any]]] = None,
    user_goal: str = "GENERAL_EASE_AND_CONTROL",
) -> dict[str, Any]:
    episodes = episodes or []
    coaching_decision = coaching_decision or {}
    baseline = baseline or {}

    hc_rows = score_all_segments(segments, baseline=baseline)
    stats = song_evidence_stats(hc_rows)
    usable = [r for r in hc_rows if r.get("head_chest_index") is not None]
    index = weighted_index(hc_rows) if ratio_eligible(stats) else None
    ratios = index_to_ratios(index)
    ranges = aggregate_range_profiles(hc_rows)
    family_summary = aggregate_family_summary(hc_rows)

    register = dimensions.get("register_configuration") or {}
    bridge = compute_bridge(
        segments=segments,
        hc_rows=hc_rows,
        register_dim=register,
        episodes=episodes,
        criteria_matrix=criteria_matrix,
        dimensions=dimensions,
    )
    local_events = bridge.get("local_register_events") or []
    modifiers = collect_modifiers(
        dimensions=dimensions, bridge=bridge, head_chest=ratios
    )

    warnings: list[str] = list(ranges.get("warnings") or [])
    neutral_collapse = detect_neutral_collapse(
        hc_rows, ranges, index=index, stats=stats
    )
    if neutral_collapse:
        warnings.append("HEAD_CHEST_NEUTRAL_COLLAPSE_WARNING")
        ratios = {
            "available": False,
            "chest_ratio": None,
            "head_ratio": None,
            "index": index,
            "broad_label": "발성 타입 판단 보류",
        }
        index_for_type = None
    else:
        index_for_type = index if ratios.get("available") else None

    n_ok = len(usable)
    n_fam_med = float(stats.get("mean_source_families") or 0)
    mass = float(stats.get("total_evidence_mass") or 0)
    agree = float(stats.get("mean_family_agreement") or 0)
    cov = ranges.get("coverage") or {}
    global_ratio_dir = float(stats.get("global_ratio_directionality") or 0)

    conf = "low"
    if (
        ratios.get("available")
        and n_ok >= cfg.MIN_SEGMENTS_FOR_HIGH_CONF
        and n_fam_med >= 1.5
        and mass >= cfg.MIN_SONG_EVIDENCE_MASS * 1.5
        and agree >= cfg.MIN_FAMILY_AGREEMENT_HIGH
    ):
        conf = "high"
    elif ratios.get("available") and n_ok >= cfg.MIN_SEGMENTS_FOR_RATIO and n_fam_med >= 1.0:
        conf = "medium"

    if conf == "high" and float(cov.get("high") or 0) < 0.05 and float(cov.get("mid") or 0) < 0.15:
        conf = "medium"
    if conf == "high" and agree < cfg.MIN_FAMILY_AGREEMENT_HIGH:
        conf = "medium"

    split_ok = bool((bridge.get("split_eligibility") or {}).get("eligible"))
    mix_coverage_ok = (
        float(cov.get("mid") or 0) + float(cov.get("high") or 0) >= 0.05
        or n_ok >= cfg.MIN_SEGMENTS_FOR_RATIO
    )
    source_balance = classify_source_balance(
        index_for_type,
        family_agreement=agree,
        directionality=global_ratio_dir,
    )
    pre_balance_class = str((source_balance or {}).get("balance_class") or "")
    pre_ratios_available = bool(ratios.get("available"))
    register_strategy = classify_register_strategy(
        index=index_for_type,
        bridge=bridge,
        confidence=conf,
        neutral_collapse=neutral_collapse,
        register_split_ok=split_ok,
        family_agreement=agree,
        mix_coverage_ok=mix_coverage_ok,
        modifiers=modifiers,
    )
    base_type = register_strategy.get("type_id") or classify_base_type(
        index=index_for_type,
        bridge=bridge,
        modifiers=modifiers,
        confidence=conf,
        neutral_collapse=neutral_collapse,
        register_split_ok=split_ok,
        family_agreement=agree,
        mix_coverage_ok=mix_coverage_ok,
    )
    # Normalize alias
    if base_type == "REGISTER_SPLIT":
        base_type = "REGISTER_SPLIT_GLOBAL"

    if conf == "low" or not ratios.get("available"):
        if base_type not in ("REGISTER_SPLIT_GLOBAL", "TRANSITION_UNSTABLE"):
            base_type = "UNRESOLVED"
            register_strategy = {
                **register_strategy,
                "status": "UNRESOLVED",
                "type_id": "UNRESOLVED",
                "confidence_label": "low",
            }
        ratios = {
            "available": False,
            "chest_ratio": None,
            "head_ratio": None,
            "index": index,
            "broad_label": _broad_label(index),
        }
        source_balance = {
            "balance_class": "UNKNOWN",
            "label": "발성 성향 판단 보류",
            "confidence_label": "low",
            "show_ratio": False,
        }

    show_ratio = bool(source_balance.get("show_ratio", True)) and bool(ratios.get("available"))
    if source_balance.get("balance_class") in ("CONFLICTED", "UNRESOLVED", "UNKNOWN"):
        show_ratio = False

    display_name = compose_display_name(
        base_type,
        modifiers,
        local_events=local_events,
        source_balance=source_balance,
        register_strategy=register_strategy,
    )
    description = one_line_description(
        base_type=base_type,
        display_name=display_name,
        head_chest=ratios,
        bridge=bridge,
        modifiers=modifiers,
        local_events=local_events,
        source_balance=source_balance,
        register_strategy=register_strategy,
    )
    reg_ui = register_strategy_display(register_strategy)
    primary = coaching_decision.get("primary_bottleneck")
    coach_line = coaching_link_sentence(
        base_type=base_type, primary=primary, modifiers=modifiers
    )
    traits = key_traits(
        modifiers=modifiers,
        bridge=bridge,
        dimensions=dimensions,
        local_events=local_events,
    )
    timeline = _timeline(hc_rows)

    # Consistency: global_ratio_directionality vs published ratio
    ratio_dir_note = None
    if ratios.get("available") and ratios.get("chest_ratio") is not None:
        c = float(ratios["chest_ratio"])
        h = float(ratios["head_ratio"])
        expected = abs(c - h) / 100.0
        # expected from ratio percentages; global_ratio_dir from raw mass
        ratio_dir_note = {
            "from_published_ratio": round(expected, 3),
            "from_raw_mass": round(global_ratio_dir, 3),
            "segment_directionality_mean": stats.get("segment_directionality_mean"),
            "note": (
                "from_published_ratio uses |C%-H%|/100; "
                "from_raw_mass uses aggregated chest_raw/head_raw; "
                "segment_* is mean of per-segment directionality (not the same quantity)."
            ),
        }

    # BALANCED_SOURCE keeps ratios visible even when Mix is unresolved
    available = bool(ratios.get("available")) or base_type in (
        "REGISTER_SPLIT_GLOBAL",
        "TRANSITION_UNSTABLE",
        "BALANCED_SOURCE",
        "CHEST_DOMINANT",
        "HEAD_DOMINANT",
        "BALANCED_MIX",
        "CHEST_DOMINANT_MIX",
        "HEAD_DOMINANT_MIX",
        "LIGHT_HEAD_FALSETTO_LIKE",
    )
    resolution_state = classify_vocal_type_resolution_state(
        base_type=base_type,
        confidence=conf,
        ratios_available=pre_ratios_available,
        balance_class=pre_balance_class,
        neutral_collapse=bool(neutral_collapse),
    )

    return {
        "available": available or bool(usable and ratios.get("available")),
        "engine_version": cfg.COACH_PROFILE_VERSION,
        "calibration_status": cfg.CALIBRATION_STATUS,
        "type_id": base_type,
        "base_type": base_type,
        "global_type": base_type,
        "resolution_state": resolution_state,
        "display_name": display_name,
        "confidence": conf,
        "confidence_label": {"high": "높음", "medium": "중간", "low": "낮음"}.get(conf, conf),
        "source_balance": {
            "chest_percent": ratios.get("chest_ratio") if show_ratio else None,
            "head_percent": ratios.get("head_ratio") if show_ratio else None,
            "balance_class": source_balance.get("balance_class"),
            "label": source_balance.get("label"),
            "confidence_label": source_balance.get("confidence_label") or conf,
            "index": ratios.get("index") if ratios.get("available") else index,
            "show_ratio": show_ratio,
            "family_agreement": source_balance.get("family_agreement", agree),
            "directionality": source_balance.get("directionality", global_ratio_dir),
        },
        "register_strategy": {
            "status": register_strategy.get("status"),
            "mix_evidence": register_strategy.get("mix_evidence"),
            "continuity": register_strategy.get("continuity"),
            "source_transition": register_strategy.get("source_transition"),
            "confidence_label": register_strategy.get("confidence_label"),
            "title": reg_ui.get("title"),
            "description": reg_ui.get("description"),
            "evidence": register_strategy.get("evidence"),
        },
        "head_chest": {
            "chest_ratio": ratios.get("chest_ratio") if show_ratio else None,
            "head_ratio": ratios.get("head_ratio") if show_ratio else None,
            "index": ratios.get("index") if ratios.get("available") else index,
            "available": bool(ratios.get("available")) and show_ratio,
            "show_ratio": show_ratio,
            "broad_label": ratios.get("broad_label") or source_balance.get("label"),
            "evidence_mass": stats.get("total_evidence_mass"),
            "global_ratio_directionality": stats.get("global_ratio_directionality"),
            "segment_directionality_mean": stats.get("segment_directionality_mean"),
            "segment_directionality_median": stats.get("segment_directionality_median"),
            "directionality": stats.get("global_ratio_directionality"),
            "family_agreement": stats.get("mean_family_agreement"),
        },
        "evidence": {
            "mass": stats.get("total_evidence_mass"),
            "chest_raw_sum": stats.get("chest_raw_sum"),
            "head_raw_sum": stats.get("head_raw_sum"),
            "global_ratio_directionality": stats.get("global_ratio_directionality"),
            "segment_directionality_mean": stats.get("segment_directionality_mean"),
            "segment_directionality_median": stats.get("segment_directionality_median"),
            "family_agreement": stats.get("mean_family_agreement"),
            "mean_signed_family_votes": stats.get("mean_signed_family_votes"),
            "n_usable_segments": stats.get("n_usable"),
            "mean_source_families": stats.get("mean_source_families"),
            "family_summary": family_summary,
            "ratio_eligible": ratio_eligible(stats),
            "ratio_directionality_note": ratio_dir_note,
            "weight_change_log": cfg.WEIGHT_CHANGE_LOG,
        },
        "bridge": {
            "type": bridge.get("type"),
            "score": bridge.get("score"),
            "passaggio_time": bridge.get("passaggio_time"),
            "core_span": bridge.get("core_span"),
            "available": bridge.get("available"),
            "register_sufficiency": bridge.get("register_sufficiency"),
            "split_eligibility": bridge.get("split_eligibility"),
            "n_transition_opportunities": bridge.get("n_transition_opportunities"),
            "break_prevalence": bridge.get("break_prevalence"),
            "transition_opportunities": bridge.get("transition_opportunities") or [],
            "global_vs_local": bridge.get("global_vs_local"),
        },
        "global_bridge": {
            "type": bridge.get("type"),
            "score": bridge.get("score"),
            "register_sufficiency": bridge.get("register_sufficiency"),
        },
        "local_register_events": local_events,
        "range_profiles": ranges.get("bands") or {},
        "range_coverage": ranges.get("coverage") or {},
        "modifiers": modifiers,
        "headline": display_name,
        "description": description,
        "coaching_link": coach_line,
        "key_traits": traits,
        "timeline": timeline,
        "segment_scores": hc_rows,
        "n_scored_segments": n_ok,
        "user_goal": user_goal,
        "warnings": warnings,
        "note_internal": "ratios are goal-invariant; no artist metadata used; mix != chest/head balance",
    }


def _broad_label(index: Optional[float]) -> Optional[str]:
    if index is None:
        return None
    if index <= 0.4:
        return "흉성 우세 가능성"
    if index >= 0.6:
        return "두성 우세 가능성"
    return "발성 타입 판단 보류"


def _timeline(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    starts = [float(r.get("start_sec") or 0) for r in rows]
    ends = [float(r.get("end_sec") or starts[i]) for i, r in enumerate(rows)]
    t0, t1 = min(starts), max(ends)
    if t1 <= t0:
        return []
    import numpy as np

    out = []
    for i in range(4):
        a = t0 + (t1 - t0) * i / 4
        b = t0 + (t1 - t0) * (i + 1) / 4
        bucket = [
            r
            for r in rows
            if r.get("head_chest_index") is not None
            and (
                a <= float(r.get("start_sec") or 0) < b
                or (i == 3 and float(r.get("start_sec") or 0) <= b)
            )
        ]
        if not bucket:
            out.append(
                {
                    "start_sec": round(a, 2),
                    "end_sec": round(b, 2),
                    "available": False,
                    "head_chest_index": None,
                    "chest_ratio": None,
                    "head_ratio": None,
                    "label": "측정 부족",
                }
            )
            continue
        mass = sum(float(r.get("evidence_mass") or 0) for r in bucket)
        mean_dir = float(
            np.mean([float(r["directionality"]) for r in bucket if r.get("directionality") is not None])
        ) if any(r.get("directionality") is not None for r in bucket) else 0.0
        if mass < cfg.MIN_EVIDENCE_MASS_SEGMENT:
            out.append(
                {
                    "start_sec": round(a, 2),
                    "end_sec": round(b, 2),
                    "available": False,
                    "head_chest_index": None,
                    "chest_ratio": None,
                    "head_ratio": None,
                    "label": "측정 부족",
                    "evidence_mass": round(mass, 3),
                }
            )
            continue
        idx = float(np.median([r["head_chest_index"] for r in bucket]))
        head = max(0, min(100, int(round(idx * 100))))
        # Weak ambiguous near-50 with low directionality → soft label option
        soft = abs(idx - 0.5) <= 0.04 and mean_dir < 0.12 and mass < cfg.MIN_EVIDENCE_MASS_SEGMENT * 4
        out.append(
            {
                "start_sec": round(a, 2),
                "end_sec": round(b, 2),
                "available": True,
                "head_chest_index": round(idx, 3),
                "chest_ratio": 100 - head,
                "head_ratio": head,
                "evidence_mass": round(mass, 3),
                "directionality": round(mean_dir, 3),
                "label": "균형에 가까움" if soft else None,
            }
        )
    return out


def build_vocal_type_public(profile: Optional[dict[str, Any]]) -> dict[str, Any]:
    resolution_state = (profile or {}).get("resolution_state") or "INSUFFICIENT_EVIDENCE"
    if not profile or not profile.get("available"):
        return {
            "available": False,
            "resolution_state": resolution_state,
            "display_name": "발성 성향 판단 보류",
            "description": "이번 녹음에서는 발성 성향을 충분히 구분하지 못했어요.",
            "head_chest": {"available": False},
            "source_balance": {"balance_class": "UNKNOWN"},
            "register_strategy": {
                "status": "UNRESOLVED",
                "title": "추가 확인 필요",
                "description": "이번 녹음만으로 성구 연결 방식을 충분히 확인하기 어려웠어요.",
            },
            "key_traits": [],
            "modifiers": [],
            "local_register_events": [],
            "timeline": (profile or {}).get("timeline") or [],
            "warnings": (profile or {}).get("warnings") or [],
        }
    hc = profile.get("head_chest") or {}
    sb = profile.get("source_balance") or {}
    rs = profile.get("register_strategy") or {}
    return {
        "available": True,
        "resolution_state": profile.get("resolution_state") or (
            "RESOLVED" if str(profile.get("base_type") or profile.get("type_id") or "") != "UNRESOLVED" else "INSUFFICIENT_EVIDENCE"
        ),
        "type_id": profile.get("type_id"),
        "base_type": profile.get("base_type"),
        "global_type": profile.get("global_type") or profile.get("type_id"),
        "display_name": profile.get("display_name"),
        "confidence": profile.get("confidence"),
        "confidence_label": profile.get("confidence_label"),
        "source_balance": {
            "chest_percent": sb.get("chest_percent", hc.get("chest_ratio")),
            "head_percent": sb.get("head_percent", hc.get("head_ratio")),
            "balance_class": sb.get("balance_class"),
            "label": sb.get("label"),
            "confidence_label": sb.get("confidence_label"),
            "show_ratio": sb.get("show_ratio", hc.get("show_ratio")),
        },
        "register_strategy": {
            "status": rs.get("status"),
            "canonical_status": rs.get("canonical_status"),
            "mix_evidence": rs.get("mix_evidence"),
            "continuity": rs.get("continuity"),
            "confidence_label": rs.get("confidence_label"),
            "title": rs.get("title"),
            "description": rs.get("description"),
            "profile_label": rs.get("profile_label"),
        },
        "head_chest": {
            "available": hc.get("available"),
            "chest_ratio": hc.get("chest_ratio"),
            "head_ratio": hc.get("head_ratio"),
            "index": hc.get("index"),
            "broad_label": hc.get("broad_label"),
            "show_ratio": hc.get("show_ratio", sb.get("show_ratio")),
        },
        "canonical_register": profile.get("canonical_register"),
        "vocal_style_profile": profile.get("vocal_style_profile"),
        "bridge": {
            "type": (profile.get("bridge") or {}).get("type"),
            "score": (profile.get("bridge") or {}).get("score"),
            "passaggio_time": (profile.get("bridge") or {}).get("passaggio_time"),
            "core_span": (profile.get("bridge") or {}).get("core_span"),
            "register_sufficiency": (profile.get("bridge") or {}).get("register_sufficiency"),
        },
        "local_register_events": [
            {
                "type": e.get("type"),
                "start_sec": e.get("start_sec"),
                "end_sec": e.get("end_sec"),
                "severity": e.get("severity"),
                "confidence": e.get("confidence"),
            }
            for e in (profile.get("local_register_events") or [])
        ],
        "range_profiles": profile.get("range_profiles") or {},
        "range_coverage": profile.get("range_coverage") or {},
        "modifiers": profile.get("modifiers") or [],
        "headline": profile.get("headline"),
        "description": profile.get("description"),
        "coaching_link": profile.get("coaching_link"),
        "key_traits": profile.get("key_traits") or [],
        "timeline": profile.get("timeline") or [],
        "engine_version": profile.get("engine_version"),
        "warnings": profile.get("warnings") or [],
    }
