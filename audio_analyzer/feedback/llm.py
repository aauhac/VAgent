"""
feedback/llm.py
---------------
Optional LLM narration layer. Never computes or modifies scores.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .formatter import format_for_llm
from .templates import build_template_feedback


_SYSTEM_PROMPT = """\
너는 보컬 코치 AI다. 주어진 점수와 이슈만 자연스러운 한국어로 설명한다.

절대 규칙:
1. JSON만 출력한다.
2. 점수를 계산·수정·재해석해 바꾸지 않는다. 입력 점수를 그대로 사용한다.
3. 음정 정확도, 박자 정확도, 원곡 비교를 말하지 않는다.
4. 성대 결절/질환 등 의학 진단을 하지 않는다.
5. 데이터에 없는 근육/원인 단정을 하지 않는다. 원인은 가능성으로만 말한다.
6. status가 unknown인 영역은 well_done/needs_work에 넣지 않는다.
7. 비브라토가 없다고 나쁘다고 말하지 않는다.
8. 사용자에게 LTAS, SPR, formant, spectral, pYIN, z-score 같은 용어를 쓰지 않는다.

출력 스키마:
{
  "confidence": "high|medium|low",
  "overall_summary": "...",
  "well_done": [{"title":"...","feedback":"...","keep_advice":"..."}],
  "needs_work": [{
    "title":"...","what_user_hears":"...","possible_reason":"...",
    "how_to_sing":"...","practice":"...","check_next":"..."
  }],
  "segment_feedback": [{"start_sec":0,"end_sec":1,"feedback":"..."}],
  "practice_plan": ["..."],
  "weekly_goal": "...",
  "analysis_notes": ["..."],
  "caution": "..."
}
"""


def generate_feedback(
    analysis: dict[str, Any],
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """
    Generate user feedback. Falls back to templates if LLM unavailable.
    """
    payload = format_for_llm(analysis)
    template = build_template_feedback(analysis)

    if not use_llm:
        return template

    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    model = model or os.environ.get("FEEDBACK_MODEL", "gpt-4o-mini")
    base_url = base_url if base_url is not None else os.environ.get("BASE_URL")

    if not api_key:
        out = dict(template)
        out["analysis_notes"] = list(out.get("analysis_notes") or []) + [
            "LLM API 키가 없어 템플릿 피드백을 사용했어요."
        ]
        return out

    try:
        from openai import OpenAI

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)

        resp = client.chat.completions.create(
            model=model,
            temperature=0.4,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
        )
        text = resp.choices[0].message.content or ""
        parsed = _extract_json(text)
        parsed.setdefault("analysis_notes", payload.get("analysis_notes") or [])
        parsed.setdefault(
            "caution",
            "이 결과는 의료 진단이 아니며, 발성 특성 분석과 연습 참고용입니다.",
        )
        parsed["model_used"] = model
        parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
        return parsed
    except Exception as exc:  # noqa: BLE001
        out = dict(template)
        out["analysis_notes"] = list(out.get("analysis_notes") or []) + [
            f"LLM 호출 실패로 템플릿 피드백을 사용했어요. ({exc})"
        ]
        return out


def generate_feedback_from_files(
    output_dir: str,
    recording_id: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict[str, Any]:
    path = Path(output_dir) / recording_id / "analysis.json"
    with open(path, encoding="utf-8") as f:
        analysis = json.load(f)
    feedback = generate_feedback(
        analysis, api_key=api_key, model=model, base_url=base_url
    )
    out_path = Path(output_dir) / recording_id / "feedback.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(feedback, f, indent=2, ensure_ascii=False)

    report = build_user_friendly_report(feedback)
    report_path = Path(output_dir) / recording_id / "feedback_report.txt"
    report_path.write_text(report, encoding="utf-8")
    feedback["user_friendly_report"] = report
    return feedback


def build_user_friendly_report(feedback: dict[str, Any]) -> str:
    lines = [
        f"[요약] {feedback.get('overall_summary', '')}",
        "",
        "== 잘하고 있는 점 ==",
    ]
    for item in feedback.get("well_done") or []:
        lines.append(f"- {item.get('title')}: {item.get('feedback')}")
        if item.get("keep_advice"):
            lines.append(f"  유지: {item['keep_advice']}")
    lines.append("")
    lines.append("== 개선하면 좋은 점 ==")
    for item in feedback.get("needs_work") or []:
        lines.append(f"- {item.get('title')}")
        lines.append(f"  느낌: {item.get('what_user_hears')}")
        lines.append(f"  연습: {item.get('practice')}")
    lines.append("")
    lines.append("== 오늘의 연습 ==")
    for p in feedback.get("practice_plan") or []:
        lines.append(f"- {p}")
    lines.append("")
    lines.append(f"주간 목표: {feedback.get('weekly_goal', '')}")
    lines.append(feedback.get("caution") or "")
    return "\n".join(lines)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        return json.loads(match.group(0))
