"""Public report slices + banned-claim validator."""

from __future__ import annotations

from typing import Any

from audio_analyzer.vocal_function import config as cfg


_AFFIRMATIVE = (
    "summary",
    "status_label",
    "what_it_may_mean",
    "user_message",
    "headline",
    "conclusion",
    "why",
    "label",
)


def affirmative_blob(obj: Any) -> str:
    chunks: list[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k in _AFFIRMATIVE or k == "headline":
                    chunks.append(str(v))
                elif k in (
                    "what_we_cannot_know",
                    "limitation",
                    "disclaimer",
                    "scientific_debug",
                    "feature_matrix",
                ):
                    continue
                else:
                    walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(obj)
    return " ".join(chunks)


def assert_no_banned_claims(blob: str) -> None:
    for banned in cfg.BANNED_CLAIM_SUBSTRINGS:
        if banned in blob:
            raise AssertionError(f"banned anatomical/medical claim: {banned}")


def public_dimensions(profile: dict[str, Any]) -> list[dict[str, Any]]:
    order = [
        "glottal_contact_profile",
        "air_leakage_breathiness",
        "vocal_effort_strain",
        "phonation_regularity",
        "register_configuration",
        "onset_offset_coordination",
        "vibrato_control",
        "resonance_formant_strategy",
        "respiratory_phonatory_coordination",
        "phonatory_economy_proxy",
    ]
    dims = profile.get("dimensions") or {}
    out = []
    for key in order:
        d = dims.get(key)
        if not d or d.get("hidden") or d.get("status") in ("UNKNOWN", "AMBIGUOUS"):
            continue
        if (d.get("confidence_label") or "low") == "low":
            continue
        if key == "phonatory_economy_proxy":
            continue  # never main card
        pub = {
            k: v
            for k, v in d.items()
            if k
            not in (
                "observations",
                "evidence_graph",
                "what_we_cannot_know",
            )
        }
        out.append(pub)
    return out


def excluded_dimensions(profile: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for d in (profile.get("dimensions") or {}).values():
        if d.get("hidden") or d.get("status") in ("UNKNOWN", "AMBIGUOUS") or (
            d.get("confidence_label") or "low"
        ) == "low":
            out.append(
                {
                    "dimension_id": d.get("dimension_id"),
                    "display_name": d.get("display_name"),
                    "reason": "신뢰도 부족",
                }
            )
    return out


def build_vocal_function_public(profile: dict[str, Any]) -> dict[str, Any]:
    if not profile or not profile.get("available"):
        return {
            "available": False,
            "headline": ["기능적 발성 상태 분석을 제공하지 못했어요."],
            "dimensions": [],
            "excluded": [],
            "focus_segments": [],
            "coaching": {},
            "coaching_decision": {},
            "high_note_events": [],
        }
    pub_dims = public_dimensions(profile)
    excl = excluded_dimensions(profile)
    decision = profile.get("coaching_decision") or {}
    focus_eps = profile.get("focus_episodes") or {}

    focus = []
    target = decision.get("target_episode")
    if target and target.get("start_sec") is not None:
        focus.append(
            {
                "start_sec": target.get("start_sec"),
                "end_sec": target.get("end_sec"),
                "local_start_sec": target.get("local_start_sec", target.get("start_sec")),
                "local_end_sec": target.get("local_end_sec", target.get("end_sec")),
                "original_start_sec": target.get("original_start_sec"),
                "original_end_sec": target.get("original_end_sec"),
                "time_origin_sec": target.get("time_origin_sec"),
                "headline": "가장 먼저 바꿔볼 구간",
                "user_message": (decision.get("modify") or [{}])[0].get("why")
                if decision.get("modify")
                else target.get("label"),
                "state": "primary_bottleneck",
                "role": "MODIFY",
            }
        )
    best = decision.get("best_self_reference") or focus_eps.get("best_self_reference")
    if best and best.get("start_sec") is not None:
        focus.append(
            {
                "start_sec": best.get("start_sec"),
                "end_sec": best.get("end_sec"),
                "local_start_sec": best.get("local_start_sec", best.get("start_sec")),
                "local_end_sec": best.get("local_end_sec", best.get("end_sec")),
                "original_start_sec": best.get("original_start_sec"),
                "original_end_sec": best.get("original_end_sec"),
                "time_origin_sec": best.get("time_origin_sec"),
                "headline": "비교해서 들어볼 좋은 구간",
                "user_message": best.get("coaching_hint")
                or "비슷한 높이에서 더 적은 effort로 유지된 구간이에요.",
                "state": "best_self",
                "role": "PRESERVE_EXAMPLE",
            }
        )
    for ev in profile.get("high_note_events") or []:
        if len(focus) >= 4:
            break
        key = (round(float(ev.get("start_sec") or 0), 1), round(float(ev.get("end_sec") or 0), 1))
        if any(
            (round(float(f.get("start_sec") or 0), 1), round(float(f.get("end_sec") or 0), 1))
            == key
            for f in focus
        ):
            continue
        focus.append(
            {
                "start_sec": ev.get("start_sec"),
                "end_sec": ev.get("end_sec"),
                "local_start_sec": ev.get("local_start_sec", ev.get("start_sec")),
                "local_end_sec": ev.get("local_end_sec", ev.get("end_sec")),
                "original_start_sec": ev.get("original_start_sec"),
                "original_end_sec": ev.get("original_end_sec"),
                "time_origin_sec": ev.get("time_origin_sec"),
                "headline": "고음 episode",
                "user_message": ev.get("conclusion"),
                "state": "high_note",
            }
        )

    exercises = decision.get("exercise_plan") or []
    training = [ex.get("instructions") for ex in exercises if ex.get("instructions")]

    public_decision = {
        "headline": decision.get("headline"),
        "primary_bottleneck": _public_bottleneck(decision.get("primary_bottleneck")),
        "secondary_bottlenecks": [
            _public_bottleneck(b) for b in (decision.get("secondary_bottlenecks") or [])
        ],
        "preserve": decision.get("preserve") or [],
        "modify": decision.get("modify") or [],
        "why": decision.get("why") or [],
        "target_episode": decision.get("target_episode"),
        "best_self_reference": {
            "start_sec": (best or {}).get("start_sec"),
            "end_sec": (best or {}).get("end_sec"),
            "coaching_hint": (best or {}).get("coaching_hint"),
        }
        if best
        else None,
        "exercise_plan": exercises,
        "success_criteria": decision.get("success_criteria") or [],
        "user_goal": decision.get("user_goal"),
        "note": decision.get("note"),
    }

    excl_names = [x.get("display_name") for x in excl if x.get("display_name")]
    unknown_footer = None
    if excl_names:
        unknown_footer = (
            "이번 녹음에서는 "
            + "·".join(excl_names[:6])
            + " 등 일부 항목은 신뢰도 있게 판단하지 못했어요."
        )

    out = {
        "available": True,
        "engine_version": profile.get("engine_version"),
        "report_version": profile.get("report_version"),
        "functional_quality": profile.get("functional_quality") or "FULL",
        "quality_badge": profile.get("quality_badge") or "충분",
        "headline": profile.get("headline") or ([public_decision["headline"]] if public_decision.get("headline") else []),
        "dimensions": pub_dims,
        "excluded": excl,
        "unknown_footer": unknown_footer,
        "focus_segments": focus[:4],
        "high_note_events": profile.get("high_note_events") or [],
        "coaching_decision": public_decision,
        "coaching": {
            "exercises": exercises,
            "problems": [
                public_decision.get("primary_bottleneck"),
                *(public_decision.get("secondary_bottlenecks") or []),
            ],
            "additional_measurement_suggestions": _adaptive_tasks(profile),
        },
        "training_plan": training,
        "disclaimer": profile.get("disclaimer")
        or "이 분석은 음향 기반 기능 추정이며 해부학적/의학적 진단이 아닙니다.",
        "valid_segment_count": profile.get("valid_segment_count"),
        "contact_effort_plane": profile.get("contact_effort_plane"),
        "analysis_time_origin_sec": profile.get("analysis_time_origin_sec"),
    }
    assert_no_banned_claims(affirmative_blob(out))
    return out


def _public_bottleneck(b: Any) -> Any:
    if not b:
        return None
    return {
        "id": b.get("id"),
        "user_title": b.get("user_title") or b.get("id"),
        "cause_family": b.get("cause_family"),
        "impact": b.get("impact"),
        "confidence_label": b.get("confidence_label"),
        "why": b.get("why") or b.get("summary"),
        "supporting_evidence": b.get("supporting_evidence"),
        "supporting_episode_ids": b.get("supporting_episode_ids") or [],
        "contradicting_evidence": b.get("contradicting_evidence"),
        "alternative_explanations": b.get("alternative_explanations"),
    }


def _adaptive_tasks(profile: dict[str, Any]) -> list[dict[str, Any]]:
    dims = profile.get("dimensions") or {}
    suggestions = []
    if (dims.get("vocal_effort_strain") or {}).get("status") in (
        "OCCASIONAL",
        "UNKNOWN",
        "MODERATE",
        "REPEATED",
    ):
        suggestions.append(
            {"reason": "high-note strain uncertainty", "tasks": ["siren_high", "sustain_strong_a"]}
        )
    if (dims.get("air_leakage_breathiness") or {}).get("status") in (
        "OCCASIONAL",
        "UNKNOWN",
        "MODERATE",
    ):
        suggestions.append(
            {
                "reason": "breathiness uncertainty",
                "tasks": ["sustain_a_soft", "sustain_a_comfortable"],
            }
        )
    if (dims.get("register_configuration") or {}).get("status") == "UNKNOWN":
        suggestions.append({"reason": "register uncertainty", "tasks": ["siren", "five_tone"]})
    return suggestions[:3]


def free_function_teaser(profile: dict[str, Any]) -> list[str]:
    if not profile or not profile.get("available"):
        return []
    decision = profile.get("coaching_decision") or {}
    bullets = []
    primary = decision.get("primary_bottleneck")
    if primary and primary.get("user_title"):
        bullets.append(f"먼저 살펴볼 후보: {primary.get('user_title')}.")
    elif primary and primary.get("id"):
        bullets.append("고음·effort 관련 기능 병목 후보가 있어요.")
    preserve = decision.get("preserve") or []
    if preserve:
        bullets.append(f"유지하면 좋은 점: {preserve[0].get('label')}.")
    if not bullets:
        dims = profile.get("dimensions") or {}
        e = dims.get("vocal_effort_strain") or {}
        if e.get("status") in ("OCCASIONAL", "MODERATE", "REPEATED"):
            bullets.append("일부 구간에서 힘이 과하게 들어간 소리 가능성이 있어요.")
        if not bullets:
            bullets.append("뚜렷한 기능 병목 후보는 제한적으로 관찰됐어요.")
    return bullets[:3]
