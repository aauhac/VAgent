"""
song_detail/explain_v3.py
-------------------------
v3 evidence-aware axis / overall explanation (no score math changes).
"""

from __future__ import annotations

from typing import Any, Optional

from .copy import (
    CONF_HIDE_SCORE,
    CONF_MEDIUM,
    SUBMETRIC_STRENGTH_MIN,
    SUBMETRIC_WEAK_MAX,
    AREA_DISPLAY,
    confidence_label,
    confidence_state,
    coverage_state,
    join_summary,
    practice_for_submetric,
    subject_particle,
    submetric_display_name,
    topic_particle,
)

# Ratio / worst meta scores are shown in UI but excluded from capability contrast copy
_META_SUBMETRIC_SUFFIXES = (
    "_ratio",
    "_worst_region",
    "_worst_segment",
)


def _is_meta_submetric(submetric_id: str) -> bool:
    sid = submetric_id or ""
    return any(sid.endswith(sfx) for sfx in _META_SUBMETRIC_SUFFIXES)


def _reliable_subs(area: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for s in area.get("submetrics") or []:
        if s.get("score") is None:
            continue
        conf = float(s.get("confidence") or 0)
        if conf < CONF_HIDE_SCORE:
            continue
        out.append(s)
    return out


def _capability_subs(subs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cap = [s for s in subs if not _is_meta_submetric(str(s.get("submetric_id") or ""))]
    return cap or subs


def _sorted_subs(subs: list[dict[str, Any]], *, reverse: bool = False) -> list[dict[str, Any]]:
    return sorted(subs, key=lambda s: float(s["score"]), reverse=reverse)


def _named(s: dict[str, Any]) -> str:
    return submetric_display_name(s.get("submetric_id") or "", s.get("display_name"))


def explain_unknown(area: dict[str, Any]) -> dict[str, Any]:
    reasons = list(area.get("ceiling_reasons") or [])
    conf = area.get("confidence")
    cov = area.get("coverage")
    why = []
    if any("confidence" in str(r) for r in reasons) or (
        conf is not None and float(conf) < CONF_MEDIUM
    ):
        why.append("측정된 지표의 신뢰도가 전체 영역 점수를 확정하기엔 부족했어요.")
    if any("coverage" in str(r) for r in reasons) or (
        cov is not None and float(cov) < 0.5
    ):
        why.append("이번 녹음에서 사용 가능한 구간·지표 범위(coverage)가 충분하지 않았어요.")
    if any("submetric" in str(r) or "missing" in str(r) for r in reasons):
        why.append("필요한 세부 지표가 일부만 확보됐어요.")
    if not why:
        why.append(
            "전달력/공명 관련 일부 지표는 측정됐지만, "
            "전체 영역을 확정할 만큼 신뢰 가능한 정보가 충분하지 않았어요."
        )
    return {
        "headline": "이번 녹음에서는 전체 영역 점수를 확정하기 어려워요.",
        "interpretation": " ".join(why),
        "why_this_score": why,
        "limitations": [
            "전체 점수가 없다는 것은 실패가 아니라 보수적 판단이에요.",
            "아래 참고 가능한 세부 항목은 확정 점수가 아닐 수 있어요.",
        ],
    }


def explain_area(area: dict[str, Any]) -> dict[str, Any]:
    area_id = area.get("area_id") or ""
    display = area.get("display_name") or AREA_DISPLAY.get(area_id, area_id)
    status = area.get("status")
    score = area.get("score")
    temporal = area.get("temporal") or {}
    worst = temporal.get("worst")
    bad_ratio = temporal.get("bad_segment_ratio")
    subs = _reliable_subs(area)
    all_subs = [s for s in (area.get("submetrics") or []) if s.get("score") is not None]

    if status == "unknown" or score is None:
        unk = explain_unknown(area)
        strength_points = []
        improvement_points = []
        for s in _sorted_subs(_capability_subs(subs), reverse=True)[:2]:
            if float(s["score"]) >= SUBMETRIC_STRENGTH_MIN and float(s.get("confidence") or 0) >= CONF_MEDIUM:
                n = _named(s)
                strength_points.append(f"{n}{subject_particle(n)} 상대적으로 좋게 측정됐어요.")
        for s in _sorted_subs(_capability_subs(subs))[:2]:
            if float(s["score"]) < SUBMETRIC_WEAK_MAX:
                n = _named(s)
                improvement_points.append(
                    f"{n}{topic_particle(n)} 참고 수준에서 상대적으로 낮게 보였어요."
                )
        return {
            **unk,
            "strength_points": strength_points,
            "improvement_points": improvement_points,
            "practice": {
                "summary": "전체 점수를 확정하려면 조금 더 또렷한 녹음이 도움이 돼요.",
                "items": [],
            },
        }

    cap_subs = _capability_subs(subs)
    best = _sorted_subs(cap_subs, reverse=True)[0] if cap_subs else None
    weakest = _sorted_subs(cap_subs)[0] if cap_subs else None
    why: list[str] = []
    strength_points: list[str] = []
    improvement_points: list[str] = []

    # Axis-specific wording
    if area_id == "stability" and best and weakest:
        b_id, w_id = best["submetric_id"], weakest["submetric_id"]
        b_sc, w_sc = float(best["score"]), float(weakest["score"])
        b_name, w_name = _named(best), _named(weakest)
        if b_id == "sustain_pitch_stability" and b_sc >= 85 and w_sc < 60:
            headline = "음 중심 유지는 좋지만, 음량 유지·약한 구간이 점수를 낮췄어요."
            interpretation = (
                "지속음의 음높이 자체는 안정적인 편이었어요. "
                f"다만 {w_name}{subject_particle(w_name)} 상대적으로 약했고"
                + (
                    f", 가장 약한 구간 점수({round(float(worst))})가 전체 점수를 낮췄어요."
                    if worst is not None and float(worst) < 65
                    else " 전체 점수를 낮췄어요."
                )
            )
        elif w_id == "sustain_pitch_stability" and w_sc < 60:
            headline = "지속음의 음 중심 유지가 상대적으로 약했어요."
            interpretation = f"{w_name} 점수가 낮아 발성 안정성 전체가 내려갔어요."
        elif b_sc >= 85 and w_sc < 60:
            headline = (
                f"{b_name}{topic_particle(b_name)} 좋지만, "
                f"{w_name}{subject_particle(w_name)} 점수를 낮췄어요."
            )
            interpretation = (
                f"{b_name}{topic_particle(b_name)} 좋은 편이에요. "
                f"다만 {w_name}{subject_particle(w_name)} 상대적으로 약했고"
                + (
                    f", 가장 약한 구간({round(float(worst))}점)이 전체 점수를 낮췄어요."
                    if worst is not None and float(worst) < 65
                    else " 전체 점수를 낮췄어요."
                )
            )
        else:
            headline = f"{display} {round(float(score))}점 · 세부 항목 간 차이가 있어요."
            interpretation = (
                f"{b_name}{topic_particle(b_name)} 좋은 편이고, "
                f"{w_name}{subject_particle(w_name)} 상대적으로 점수를 낮췄어요."
            )
    elif area_id == "dynamic_control" and best and weakest:
        high_count = sum(1 for s in cap_subs if float(s["score"]) >= 70)
        if high_count >= max(3, len(cap_subs) - 1) and worst is not None and float(worst) < 55:
            headline = "전체 강약 흐름은 괜찮지만, 일부 구간이 크게 무너졌어요."
            interpretation = (
                "전체적인 강약 변화와 부드러움은 비교적 괜찮았지만, "
                f"일부 구간(최악 {round(float(worst))}점)에서 강약 조절이 크게 흔들리며 "
                "전체 점수가 낮아졌어요."
            )
            why.append("평균 세부 항목은 양호하나 worst segment가 축 점수를 제한했어요.")
        elif float(weakest["score"]) < 60:
            w_name = _named(weakest)
            headline = "강약 조절에서 약한 세부 항목이 있어요."
            interpretation = (
                f"{w_name}{subject_particle(w_name)} 상대적으로 낮아 "
                "전체 강약 점수를 끌어내렸어요."
            )
        else:
            if score is not None and float(score) >= 70:
                headline = f"{display}{topic_particle(display)} 비교적 좋게 측정됐어요."
                interpretation = "강약 표현이 전반적으로 양호하고, 더 분명한 대비를 만들 여지는 있어요."
            else:
                headline = f"{display}{topic_particle(display)} 중간 수준으로 측정됐어요."
                interpretation = "강약 표현이 전반적으로 무난하지만, 더 분명한 대비를 만들 여지는 있어요."
    else:
        if best and weakest and float(best["score"]) >= 85 and float(weakest["score"]) < 60:
            b_name, w_name = _named(best), _named(weakest)
            headline = (
                f"{b_name}{topic_particle(b_name)} 좋지만 "
                f"{w_name}{subject_particle(w_name)} 전체 점수를 낮췄어요."
            )
            interpretation = headline
        elif best and all(float(s["score"]) >= 78 for s in cap_subs):
            headline = f"{display}{topic_particle(display)} 대부분 좋게 측정됐어요."
            interpretation = (
                "대부분 세부 항목이 양호하고, 일부 구간에서만 차이가 있었어요."
                if worst is not None and float(worst) < 80
                else "세부 항목이 전반적으로 안정적으로 측정됐어요."
            )
        elif score is not None and float(score) < 55:
            headline = f"{display}에서 개선 여지가 분명해요."
            w_name = _named(weakest) if weakest else "일부 지표"
            interpretation = f"가장 약한 세부 항목은 {w_name}예요."
        elif score is not None and float(score) >= 70:
            # Never pair GOOD / 80+ scores with "중간 수준"
            headline = f"{display}{topic_particle(display)} 비교적 좋게 측정됐어요."
            interpretation = "세부 항목이 전반적으로 양호한 편이에요."
        else:
            headline = f"{display}{topic_particle(display)} 전반적으로 중간 수준이에요."
            interpretation = "세부 항목이 한쪽으로 극단적이지 않고 중간 구간에 모여 있어요."

    if best and float(best["score"]) >= SUBMETRIC_STRENGTH_MIN:
        name = _named(best)
        if float(best.get("confidence") or 0) >= CONF_MEDIUM:
            strength_points.append(f"{name}{subject_particle(name)} 특히 좋게 측정됐어요.")
        else:
            strength_points.append(f"{name}{topic_particle(name)} 참고 수준에서 좋게 보였어요.")

    if weakest and float(weakest["score"]) < SUBMETRIC_WEAK_MAX:
        improvement_points.append(f"핵심 개선: {_named(weakest)}")
    if worst is not None and float(worst) < 65:
        improvement_points.append(
            f"가장 약한 구간 점수 {round(float(worst))}점이 전체 점수를 제한했어요."
        )
        why.append(f"worst segment ≈ {round(float(worst))}")
    if bad_ratio is not None and float(bad_ratio) >= 0.2:
        why.append(f"낮은 점수 구간 비율 ≈ {round(float(bad_ratio) * 100)}%")
        improvement_points.append("낮은 점수 구간이 여러 곳에서 반복됐어요.")

    if best:
        why.insert(0, f"가장 높은 세부 항목: {_named(best)} {round(float(best['score']))}")
    if weakest and (not best or weakest["submetric_id"] != best["submetric_id"]):
        why.append(f"가장 낮은 세부 항목: {_named(weakest)} {round(float(weakest['score']))}")

    practice_items = []
    if weakest:
        practice_items.append(practice_for_submetric(weakest["submetric_id"]))
    if worst is not None and float(worst) < 65:
        practice_items.append(
            practice_for_submetric(
                {
                    "stability": "stability_worst_region",
                    "projection": "projection_worst_segment",
                    "resonance": "resonance_worst_segment",
                    "dynamic_control": "dynamic_worst_segment",
                }.get(area_id, weakest["submetric_id"] if weakest else "")
            )
        )
    # dedupe
    seen = set()
    uniq = []
    for p in practice_items:
        if p and p not in seen:
            seen.add(p)
            uniq.append(p)

    return {
        "headline": headline,
        "interpretation": interpretation,
        "why_this_score": why[:6],
        "strength_points": strength_points[:3],
        "improvement_points": improvement_points[:4],
        "practice": {
            "summary": uniq[0] if uniq else "가장 약한 세부 항목을 짧게 반복해 보세요.",
            "items": uniq[:3],
        },
        "limitations": [
            "이 영역 점수는 음향 특성 기반이며 해부학적 진단이 아닙니다.",
        ],
    }


def build_submetric_views(area: dict[str, Any]) -> list[dict[str, Any]]:
    views = []
    for s in area.get("submetrics") or []:
        conf = float(s.get("confidence") or 0)
        score = s.get("score")
        label = confidence_label(conf)
        show_score = score is not None and conf >= CONF_HIDE_SCORE
        views.append(
            {
                "submetric_id": s.get("submetric_id"),
                "display_name": submetric_display_name(
                    s.get("submetric_id") or "", s.get("display_name")
                ),
                "score": None if not show_score else round(float(score), 1),
                "status": s.get("status"),
                "confidence": round(conf, 3),
                "confidence_label": label,
                "coverage": s.get("coverage"),
                "raw_value": s.get("raw_value"),
                "unit": s.get("unit"),
                "display_note": (
                    "참고"
                    if show_score and conf < CONF_MEDIUM
                    else ("신뢰 낮음 — 숫자 숨김" if score is not None and not show_score else None)
                ),
                "perfect_claim_forbidden": bool(
                    show_score and float(score) >= 99.5 and conf < CONF_MEDIUM
                ),
            }
        )
    return views


def overall_display_state(score: dict[str, Any]) -> dict[str, Any]:
    areas = score.get("areas") or []
    reliable = [
        a
        for a in areas
        if a.get("score") is not None and a.get("status") != "unknown"
    ]
    n_rel = len(reliable)
    n_tot = max(1, len(areas))
    cov = score.get("overall_coverage")
    if n_rel <= 1:
        state = "UNAVAILABLE"
    elif n_rel == 2:
        state = "PARTIAL"
    else:
        # 3–4 reliable
        if cov is not None and float(cov) < 0.45:
            state = "PARTIAL"
        else:
            state = "FULL"
    return {
        "overall_display_state": state,
        "reliable_axis_count": n_rel,
        "total_axis_count": n_tot,
        "overall_coverage": cov,
        "overall_confidence": score.get("overall_confidence"),
    }


def build_overall_assessment(score: dict[str, Any]) -> dict[str, Any]:
    meta = overall_display_state(score)
    state = meta["overall_display_state"]
    overall = score.get("overall")
    label = score.get("label")
    # Public overall only when >=3 reliable axes (FULL). PARTIAL/UNAVAILABLE hide the number.
    if state == "UNAVAILABLE":
        text = "충분한 영역이 확보되지 않아 종합 점수를 확정하지 않았어요. 확인된 항목만 아래에 표시해요."
        display_overall = None
    elif state == "PARTIAL":
        text = (
            f"이번 녹음에서 확인된 항목만 표시해요. "
            f"{meta['total_axis_count']}개 영역 중 {meta['reliable_axis_count']}개 영역만 "
            f"신뢰도 있게 계산되어 종합 점수는 숨겼어요."
        )
        display_overall = None
    else:
        text = join_summary(overall, label, partial=False)
        display_overall = overall
    return {
        **meta,
        "display_overall": display_overall,
        "internal_overall": overall,
        "label": label,
        "text": text,
        "provisional": True,
    }


def collect_detail_strengths(areas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for area in areas:
        # UNKNOWN parent axis must never create user-facing strengths
        if area.get("status") == "unknown" or area.get("score") is None:
            continue
        for s in area.get("submetrics") or []:
            sid = str(s.get("submetric_id") or "")
            if _is_meta_submetric(sid):
                continue
            if s.get("score") is None:
                continue
            if float(s["score"]) < SUBMETRIC_STRENGTH_MIN:
                continue
            if float(s.get("confidence") or 0) < CONF_MEDIUM:
                continue
            if s.get("perfect_claim_forbidden"):
                note = "이 세부 항목에서는 매우 좋게 측정됐어요."
            else:
                note = "신뢰도 있게 측정된 세부 강점이에요."
            items.append(
                {
                    "area_id": area.get("area_id"),
                    "submetric_id": s.get("submetric_id"),
                    "display_name": s.get("display_name"),
                    "score": s.get("score"),
                    "note": note,
                    "kind": "submetric_strength",
                }
            )
    items.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    return items[:5]


def collect_detail_priorities(areas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for area in areas:
        if area.get("status") == "unknown":
            continue
        weak_subs = [
            s
            for s in (area.get("submetrics") or [])
            if s.get("score") is not None
            and float(s["score"]) < SUBMETRIC_WEAK_MAX
            and float(s.get("confidence") or 0) >= CONF_MEDIUM
            and not _is_meta_submetric(str(s.get("submetric_id") or ""))
        ]
        # Prefer capability weakness; fall back to any weak including worst meta
        if not weak_subs:
            weak_subs = [
                s
                for s in (area.get("submetrics") or [])
                if s.get("score") is not None
                and float(s["score"]) < SUBMETRIC_WEAK_MAX
                and float(s.get("confidence") or 0) >= CONF_MEDIUM
            ]
        weak_subs.sort(key=lambda s: float(s["score"]))
        if not weak_subs:
            if area.get("score") is not None and float(area["score"]) < 55:
                items.append(
                    {
                        "area_id": area.get("area_id"),
                        "display_name": area.get("display_name"),
                        "score": area.get("score"),
                        "what_user_hears": (area.get("improvement_points") or ["개선 여지가 있어요."])[0],
                        "practice": (area.get("practice") or {}).get("summary"),
                        "kind": "axis_priority",
                    }
                )
            continue
        w = weak_subs[0]
        w_name = w.get("display_name")
        if _is_meta_submetric(str(w.get("submetric_id") or "")):
            hear = (
                f"{area.get('display_name')} 개선 핵심: "
                f"일부 약한 구간(최악 {round(float(w['score']))}점)"
            )
        else:
            hear = (
                f"{area.get('display_name')} 개선 핵심: "
                f"{w_name} ({round(float(w['score']))}점)"
            )
        items.append(
            {
                "area_id": area.get("area_id"),
                "display_name": area.get("display_name"),
                "submetric_id": w.get("submetric_id"),
                "score": area.get("score"),
                "what_user_hears": hear,
                "practice": practice_for_submetric(w.get("submetric_id") or ""),
                "kind": "submetric_priority",
            }
        )
    items.sort(
        key=lambda x: (
            0 if x.get("kind") == "submetric_priority" else 1,
            float(x.get("score") or 100),
        )
    )
    return items[:5]
