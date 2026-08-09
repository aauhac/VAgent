"""
feedback/templates.py
---------------------
Deterministic fallback feedback when LLM is unavailable.
"""

from __future__ import annotations

from typing import Any

from .user_text import AREA_COPY


def build_template_feedback(analysis: dict[str, Any]) -> dict[str, Any]:
    score = analysis.get("score") or {}
    quality = analysis.get("quality") or {}

    if not score.get("available"):
        return {
            "confidence": "low",
            "overall_summary": quality.get("user_message")
            or "정확한 분석이 어려운 녹음이에요. 실력 점수는 제공하지 않아요.",
            "well_done": [],
            "needs_work": [],
            "segment_feedback": [],
            "practice_plan": [
                "조용한 곳에서 이어폰을 끼고 30초 이상 불러 보세요.",
                "마이크와 거리를 일정하게 유지해 보세요.",
            ],
            "weekly_goal": "분석 가능한 녹음 조건을 먼저 만들어 보세요.",
            "analysis_notes": analysis.get("analysis_notes") or [],
            "caution": "이 결과는 의료 진단이 아니며, 연습 참고용입니다.",
        }

    overall = score.get("overall")
    label = score.get("label") or ""
    well_done = []
    needs_work = []

    for s in score.get("strengths") or []:
        area_id = s.get("area_id")
        copy = AREA_COPY.get(area_id, {})
        well_done.append(
            {
                "title": copy.get("strength_title", s.get("display_name")),
                "feedback": copy.get("strength_feedback", ""),
                "keep_advice": copy.get("keep_advice", ""),
            }
        )

    for p in score.get("priority_issues") or []:
        area_id = p.get("area_id")
        copy = AREA_COPY.get(area_id, {})
        needs_work.append(
            {
                "title": copy.get("needs_title", p.get("display_name")),
                "what_user_hears": copy.get("what_user_hears", ""),
                "possible_reason": copy.get("possible_reason", ""),
                "how_to_sing": copy.get("how_to_sing", ""),
                "practice": copy.get("practice", ""),
                "check_next": copy.get("check_next", ""),
            }
        )

    # Never promote unknown areas into well_done/needs_work
    # (strengths/priority already filtered in scoring)

    segment_feedback = []
    for ev in (analysis.get("timeline") or [])[:5]:
        segment_feedback.append(
            {
                "start_sec": ev.get("start_sec"),
                "end_sec": ev.get("end_sec"),
                "feedback": ev.get("user_message"),
            }
        )

    practice_plan = [item["practice"] for item in needs_work if item.get("practice")]
    if not practice_plan:
        practice_plan = ["편한 음 하나를 골라 3초 유지 연습을 해보세요."]

    conf = "high"
    if quality.get("status") == "warn":
        conf = "medium"
    if any(a.get("status") == "unknown" for a in score.get("areas") or []):
        conf = "medium"

    return {
        "confidence": conf,
        "overall_summary": f"종합 {overall}점, {label}이에요. 점수는 아직 보정 전 잠정 기준입니다.",
        "well_done": well_done,
        "needs_work": needs_work,
        "segment_feedback": segment_feedback,
        "practice_plan": practice_plan[:4],
        "weekly_goal": (
            needs_work[0]["practice"]
            if needs_work
            else "지금 잘하는 느낌을 유지하며 편하게 불러 보세요."
        ),
        "analysis_notes": analysis.get("analysis_notes") or [],
        "caution": "이 결과는 의료 진단이 아니며, 발성 특성 분석과 연습 참고용입니다.",
    }
