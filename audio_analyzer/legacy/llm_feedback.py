"""
llm_feedback.py
---------------
analysis.json(또는 llm_input.json)을 LLM에 보내어 보컬 피드백 JSON을 생성한다.

OpenAI API 또는 vLLM(OpenAI-compatible)을 모두 지원한다.
  - OpenAI: base_url=None, api_key=실제키
  - vLLM:   base_url="http://localhost:8000/v1", api_key="EMPTY"

출력 스키마 (feedback.json)
{
  "recording_id": "...",
  "model_used": "...",
  "generated_at": "ISO8601",
  "confidence": "high|medium|low",
  "overall_summary": "...",
  "main_issues": [
    {
      "issue": "low_mid_heavy",
      "evidence": "...",
      "possible_cause": "...",
      "vocal_advice": "...",
      "practice": "..."
    }
  ],
  "segment_feedback": [
    {"start_sec": 12.3, "end_sec": 18.7, "feedback": "..."}
  ],
  "next_practice_plan": ["...", "..."]
}
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# 시스템 프롬프트
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
너는 실제 보컬 코치 AI다.
분석 결과를 나열하지 않고, 실제 보컬 코치가 직접 설명하듯 작성한다.

─── 입력 구조 ───────────────────────────────────────────────────────────────
- vocal_score : 코드에서 계산된 영역별 점수/종합점수 (최우선 근거)
- vocal_assessment.user_facing_issues : 실제 발성 개선이 필요한 이슈 (피드백 대상)
- vocal_assessment.user_facing_strengths : 잘 되고 있는 부분
- artifact_warnings : 전처리 artifact 가능성이 있는 항목 (발성 문제로 단정 금지)
- artifact_notes    : 분석 참고사항 문장 (그대로 사용 가능)
- demucs_hf_loss_detected : Demucs 고역 손실 감지 여부 (true이면 고역 관련 판단 주의)

─── 절대 규칙 ───────────────────────────────────────────────────────────────
1. 출력은 반드시 JSON 형식만이다. 앞뒤 설명 없이 JSON만 출력한다.
2. 한국어로 작성한다.
3. voiced_ratio < 0.6이면 confidence를 "low"로 낮추고 단정을 피한다.
4. recording_quality.echo_level이 "high"이면 confidence를 "low" 또는 "medium"으로 낮춘다.
5. demucs_hf_loss_detected가 true이면 고역(presence, airiness) 관련 판단에 주의한다.
6. artifact_warnings에 있는 이슈는 needs_work에 넣지 않는다.
7. artifact_notes에 있는 문장은 analysis_notes 배열에 그대로 포함시킨다.
8. 의학적 진단 표현을 쓰지 않는다. ("성대 결절 의심" 금지)
9. 점수 계산은 절대 수행하지 않는다. vocal_score를 그대로 사용한다.

─── 점수 해석 규칙 ───────────────────────────────────────────────────────────
1. vocal_score.area_scores를 기준으로 설명한다.
2. 각 개선 항목에는 현재 점수/지표값/목표 기준의 차이를 짧게 반영한다.
3. confidence < 0.35 영역은 강한 단정 대신 참고용으로 설명한다.
4. priority_areas를 개선 우선순위로 반영한다.

─── 사용자 언어 규칙 ────────────────────────────────────────────────────────
아래 표현은 사용자 피드백 본문에 직접 쓰지 않는다.
금지 표현: 박스감, 둔탁함, 두께, 저중역, 고역대, presence, airiness,
           포먼트, 공명, 스펙트럼, centroid, z-score,
           저중음 과다, 고음 부족, 음량 감소 패턴, 음정 흔들림 반복,
           끝음 처리 약점, 저중음, 고음 부족

표현 변환 기준:
- 소리가 아래쪽에 무겁게 잡히는 느낌 (× 저중음 과다)
- 소리가 입 안에 머무는 느낌 (× 박스감)
- 가사와 음의 시작이 덜 또렷하게 들릴 수 있는 느낌 (× 고음 부족, presence 약함)
- 소리 끝이 조금 빨리 닫히거나 여유가 적게 들릴 수 있는 느낌 (× 끝음 처리 약점)
- 피치 추적이 불안정하게 측정됨, 전처리 영향 가능성 있음 (× 음정 흔들림)

단정 대신 가능성으로 말한다:
  가능: "가능성이 있습니다", "그렇게 들릴 수 있습니다", "측정됩니다"
  금지: "목을 누르고 있습니다", "혀가 뒤로 빠졌습니다", "음정이 흔들립니다"

─── needs_work 작성 기준 ────────────────────────────────────────────────────
각 항목은 반드시 다음 5개 필드를 최소 5~7문장으로 작성한다.
짧은 한 줄 피드백은 금지다.

  what_user_hears  : 사용자가 들었을 때의 느낌 (2~3문장 이상)
  possible_reason  : 가능한 원인 (단정하지 않고, 2~3문장)
  how_to_sing      : 바로 해볼 발성 방법 (구체적인 행동, 2~3문장)
  practice         : 구체적인 연습법 (짧고 따라할 수 있는 루틴, 2~3문장)
  check_next       : 다음 녹음에서 확인할 기준 (1~2문장)

─── 출력 JSON 스키마 ────────────────────────────────────────────────────────
{
  "confidence": "high|medium|low",
  "overall_summary": "전체 인상 2~3문장 (전문용어 없이, 코치 말투로)",
  "well_done": [
    {
      "title": "<강점 제목>",
      "feedback": "<잘 되고 있는 점 2~3문장>",
      "keep_advice": "<유지 방법 1~2문장>"
    }
  ],
  "needs_work": [
    {
      "title": "<개선 제목>",
      "what_user_hears": "<2~3문장>",
      "possible_reason": "<2~3문장>",
      "how_to_sing": "<2~3문장>",
      "practice": "<2~3문장>",
      "check_next": "<1~2문장>"
    }
  ],
  "analysis_notes": [
    "<전처리 영향 가능성 참고 문장>"
  ],
  "segment_feedback": [
    {"start_sec": 0, "end_sec": 0, "feedback": "..."}
  ],
  "practice_plan": ["<오늘 할 연습 1>", "<연습 2>", "<연습 3>"],
  "weekly_goal": "1주 목표를 한 문장으로",
  "caution": "무리하지 않기 위한 주의사항 1~2문장"
}

needs_work에 들어가는 이슈는 vocal_assessment.user_facing_issues에 있는 항목만이다.
artifact_warnings 이슈는 analysis_notes에만 간단히 언급한다.
segment_feedback은 issue_events 기반으로 중요한 구간 최대 5개만 채운다.
모든 문자열 값은 반드시 닫혀야 한다. 응답이 잘릴 수 있으므로 간결하게 작성한다.
"""


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------

def generate_feedback(
    llm_input: dict,
    recording_id: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    base_url: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> dict:
    """
    Parameters
    ----------
    llm_input      : format_for_llm() 반환값 (llm_input.json 내용)
    recording_id   : 결과에 포함할 녹음 ID
    api_key        : OpenAI 또는 vLLM API 키
    model          : 모델명 (예: "gpt-4o-mini", "Qwen/Qwen2.5-7B-Instruct")
    base_url       : vLLM 등 로컬 서버 URL. None이면 OpenAI 공식 endpoint 사용
    temperature    : 생성 온도 (낮을수록 일관성 높음)
    max_tokens     : 최대 출력 토큰
    """
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError(
            "openai 패키지가 필요합니다. pip install openai"
        ) from exc

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)

    user_content = json.dumps(llm_input, ensure_ascii=False, indent=2)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    raw = response.choices[0].message.content or ""
    feedback_data = _parse_json_response(raw)
    feedback_data = _normalize_schema(feedback_data)

    # 점수 기반 우선: vocal_score를 기준으로 needs_work / well_done를 결정한다.
    vocal_score = llm_input.get("vocal_score", {})
    score_needs_work = _build_needs_work_from_vocal_score(vocal_score)
    score_well_done = _build_well_done_from_vocal_score(vocal_score)
    if score_needs_work:
        feedback_data["needs_work"] = score_needs_work
    if score_well_done:
        feedback_data["well_done"] = score_well_done

    # 보조 폴백: vocal_score가 없거나 비어 있으면 사전 계산된 vocal_assessment 사용
    assessment = llm_input.get("vocal_assessment", {})
    if not feedback_data.get("needs_work"):
        user_issues = assessment.get("user_facing_issues", [])
        feedback_data["needs_work"] = [
            {
                "title": item.get("display_title", ""),
                "what_user_hears": item.get("user_symptom", ""),
                "possible_reason": item.get("possible_cause", ""),
                "how_to_sing": item.get("vocal_advice", ""),
                "practice": item.get("practice", ""),
                "check_next": "",
            }
            for item in user_issues
        ]
    else:
        # check_next 키 보장
        for item in feedback_data["needs_work"]:
            item.setdefault("check_next", "")

    if not feedback_data.get("well_done"):
        user_strengths = assessment.get("user_facing_strengths", [])
        feedback_data["well_done"] = [
            {
                "title": item.get("display_title", ""),
                "feedback": item.get("message", ""),
                "keep_advice": item.get("keep_advice", ""),
            }
            for item in user_strengths
        ]

    # analysis_notes 폴백: artifact_notes가 있으면 그대로 사용
    if not feedback_data.get("analysis_notes"):
        feedback_data["analysis_notes"] = llm_input.get("artifact_notes", [])

    feedback_data["recording_id"] = recording_id
    feedback_data["model_used"] = model
    feedback_data["generated_at"] = datetime.now(timezone.utc).isoformat()

    # 필수 키 보장 (새 스키마)
    list_keys = ("well_done", "needs_work", "segment_feedback", "practice_plan", "analysis_notes")
    str_keys  = ("confidence", "overall_summary", "weekly_goal", "caution")
    for key in list_keys:
        feedback_data.setdefault(key, [])
    for key in str_keys:
        feedback_data.setdefault(key, "")
    if not feedback_data.get("confidence"):
        feedback_data["confidence"] = "medium"

    if not feedback_data.get("overall_summary"):
        feedback_data["overall_summary"] = _fallback_overall_summary(llm_input, feedback_data)

    if not feedback_data.get("practice_plan"):
        feedback_data["practice_plan"] = _fallback_practice_plan_from_vocal_score(llm_input)

    return feedback_data


def generate_feedback_from_files(
    output_dir: str,
    recording_id: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    base_url: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> dict:
    """
    저장된 llm_input.json을 읽어 피드백을 생성하고 feedback.json으로 저장한다.

    Parameters
    ----------
    output_dir   : 분석 결과 루트 폴더 (예: "outputs")
    recording_id : 대상 녹음 ID
    """
    rec_dir = Path(output_dir) / recording_id
    llm_input_path = rec_dir / "llm_input.json"
    analysis_path = rec_dir / "analysis.json"

    if not llm_input_path.exists():
        raise FileNotFoundError(f"llm_input.json을 찾을 수 없음: {llm_input_path}")

    with open(llm_input_path, encoding="utf-8") as f:
        llm_input = json.load(f)

    source_filename = None
    if analysis_path.exists():
        with open(analysis_path, encoding="utf-8") as f:
            analysis_result = json.load(f)
        source_filename = (
            analysis_result.get("audio_meta", {}).get("source_filename")
            or Path(analysis_result.get("audio_meta", {}).get("original_path", "")).name
            or None
        )

    llm_payload = dict(llm_input)
    if source_filename:
        llm_payload["source_filename"] = source_filename

    try:
        feedback = generate_feedback(
            llm_input=llm_payload,
            recording_id=recording_id,
            api_key=api_key,
            model=model,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        feedback = _build_local_fallback_feedback(
            llm_input=llm_payload,
            recording_id=recording_id,
            model=model,
            error_message=str(exc),
        )
    if source_filename:
        feedback["source_filename"] = source_filename
    feedback["vocal_score"] = llm_input.get("vocal_score")

    # 일반 사용자용 상세 리포트 텍스트를 생성한다.
    feedback_report = build_user_friendly_report(feedback)
    feedback["user_friendly_report"] = feedback_report

    feedback_path = rec_dir / "feedback.json"
    with open(feedback_path, "w", encoding="utf-8") as f:
        json.dump(feedback, f, ensure_ascii=False, indent=2)

    report_path = rec_dir / "feedback_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(feedback_report)

    return feedback


# ---------------------------------------------------------------------------
# 내부 함수
# ---------------------------------------------------------------------------

def _normalize_schema(data: dict) -> dict:
    """
    LLM이 자체 키명으로 응답했을 때 표준 스키마로 정규화한다.

    표준 스키마:
        well_done      ← strengths / current_strengths / positives
        needs_work     ← main_issues / needs_improvement / improvement_suggestions
        segment_feedback ← segment_analysis / segment_comments
        practice_plan  ← next_practice_plan / practice / exercises
    """
    # well_done 정규화
    if not data.get("well_done"):
        for alt in ("strengths", "current_strengths", "positives", "strong_points"):
            src = data.get(alt)
            if src:
                # 문자열 목록이면 dict로 감싸기
                normalized = []
                for item in src:
                    if isinstance(item, str):
                        normalized.append({"title": item, "feedback": "", "keep_advice": ""})
                    elif isinstance(item, dict):
                        normalized.append({
                            "title": item.get("description") or item.get("title") or item.get("type", ""),
                            "feedback": item.get("feedback") or item.get("message", ""),
                            "keep_advice": item.get("keep_advice") or item.get("suggestion", ""),
                        })
                data["well_done"] = normalized
                break

    # needs_work 정규화
    if not data.get("needs_work"):
        for alt in ("main_issues", "needs_improvement", "improvement_suggestions", "issues"):
            src = data.get(alt)
            if src:
                normalized = []
                for item in src:
                    if isinstance(item, str):
                        normalized.append({"title": item, "what_user_hears": "", "possible_reason": "", "how_to_sing": "", "practice": ""})
                    elif isinstance(item, dict):
                        normalized.append({
                            "title": item.get("display_title") or item.get("title") or item.get("issue") or item.get("type", ""),
                            "what_user_hears": item.get("what_user_hears") or item.get("user_symptom") or item.get("description", ""),
                            "possible_reason": item.get("possible_reason") or item.get("possible_cause") or item.get("cause", ""),
                            "how_to_sing": item.get("how_to_sing") or item.get("vocal_advice") or item.get("suggestion", ""),
                            "practice": item.get("practice") or item.get("exercise", ""),
                        })
                data["needs_work"] = normalized
                break

    # segment_feedback 정규화
    if not data.get("segment_feedback"):
        for alt in ("segment_analysis", "segment_comments", "segments"):
            src = data.get(alt)
            if src:
                normalized = []
                for item in src:
                    if isinstance(item, dict):
                        normalized.append({
                            "start_sec": item.get("start_sec") or item.get("start", 0),
                            "end_sec": item.get("end_sec") or item.get("end", 0),
                            "feedback": item.get("feedback") or item.get("detail") or item.get("description", ""),
                        })
                data["segment_feedback"] = normalized
                break

    # practice_plan 정규화
    if not data.get("practice_plan"):
        for alt in ("next_practice_plan", "practice", "exercises", "practice_routine"):
            src = data.get(alt)
            if src:
                if isinstance(src, list):
                    data["practice_plan"] = [str(x) for x in src]
                break

    return data


def _build_local_fallback_feedback(
    llm_input: dict,
    recording_id: str,
    model: str,
    error_message: str,
) -> dict:
    """
    LLM 호출이 실패했을 때 vocal_score 기반으로 deterministic feedback을 만든다.
    """
    vocal_score = llm_input.get("vocal_score", {})
    needs_work = _build_needs_work_from_vocal_score(vocal_score)
    well_done = _build_well_done_from_vocal_score(vocal_score)
    analysis_notes = list(llm_input.get("artifact_notes", []))
    analysis_notes.insert(0, "LLM 서버 연결에 실패하여 로컬 점수 기반 리포트로 대체했습니다.")

    feedback = {
        "recording_id": recording_id,
        "model_used": f"{model} (local fallback)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "confidence": _fallback_confidence(llm_input),
        "overall_summary": _fallback_overall_summary(llm_input, {"needs_work": needs_work}),
        "well_done": well_done,
        "needs_work": needs_work,
        "analysis_notes": analysis_notes[:3],
        "segment_feedback": [],
        "practice_plan": _fallback_practice_plan_from_vocal_score(llm_input),
        "weekly_goal": _fallback_weekly_goal(vocal_score),
        "caution": (
            "현재 리포트는 외부 LLM 없이 로컬 점수 기반으로 생성되었습니다. "
            f"연결 오류가 해결되면 더 자연스러운 코칭 문장으로 재생성할 수 있습니다. ({error_message[:120]})"
        ),
        "generation_mode": "local_fallback",
    }
    return feedback


def _fallback_confidence(llm_input: dict) -> str:
    recording_quality = llm_input.get("recording_quality", {})
    voiced_ratio = (llm_input.get("summary_features", {}) or {}).get("voiced_ratio")
    if recording_quality.get("echo_level") == "high":
        return "low"
    if voiced_ratio is not None and float(voiced_ratio) < 0.6:
        return "low"
    return "medium"


def _fallback_weekly_goal(vocal_score: dict) -> str:
    priority = vocal_score.get("priority_areas", []) or []
    area_scores = vocal_score.get("area_scores", []) or []
    by_id = {
        item.get("area_id"): item.get("display_name", item.get("area_id"))
        for item in area_scores if isinstance(item, dict)
    }
    if not priority:
        return "현재 안정적인 영역을 유지하면서 짧은 재녹음 루틴을 꾸준히 이어가세요."
    top = by_id.get(priority[0], priority[0])
    return f"이번 주에는 {top} 영역을 가장 먼저 끌어올리는 데 집중하세요."


def _fallback_overall_summary(llm_input: dict, feedback: dict) -> str:
    vocal_score = llm_input.get("vocal_score", {})
    overall = vocal_score.get("overall_score")
    label = vocal_score.get("score_label")
    priority = vocal_score.get("priority_areas", [])
    area_scores = vocal_score.get("area_scores", [])

    id_to_name = {
        item.get("area_id"): item.get("display_name")
        for item in area_scores if isinstance(item, dict)
    }
    top_names = [id_to_name.get(a, a) for a in priority[:2]]

    if overall is None:
        if feedback.get("needs_work"):
            return "전체적으로 개선할 포인트가 보이며, 작은 볼륨에서 발성 중심을 다시 정리해보는 것이 좋습니다."
        return "현재 발성 방향은 비교적 안정적이며, 현재 감각을 유지하면서 기본기 루틴을 이어가면 좋습니다."

    if top_names:
        return (
            f"현재 보컬 음색 완성도는 {round(float(overall))}점({label})입니다. "
            f"특히 {', '.join(top_names)} 영역에서 먼저 개선하면 체감 변화가 빠르게 나타날 수 있습니다."
        )

    return f"현재 보컬 음색 완성도는 {round(float(overall))}점({label})이며, 전반적인 균형은 비교적 안정적인 편입니다."


def _fallback_practice_plan_from_vocal_score(llm_input: dict) -> list[str]:
    vocal_score = llm_input.get("vocal_score", {})
    area_scores = vocal_score.get("area_scores", [])
    priority = vocal_score.get("priority_areas", [])
    by_id = {
        item.get("area_id"): item
        for item in area_scores if isinstance(item, dict)
    }

    plan: list[str] = []
    for area_id in priority:
        item = by_id.get(area_id, {})
        for p in item.get("practice", [])[:1]:
            if isinstance(p, str) and p not in plan:
                plan.append(p)
        if len(plan) >= 3:
            break

    if not plan:
        plan = [
            "가사를 먼저 말하듯 읽고 첫 자음을 분명하게 시작하기",
            "작은 볼륨 롱톤으로 음의 시작과 끝을 안정적으로 유지하기",
            "문제 구간 5초 단위로 재녹음 후 비교하기",
        ]

    return plan[:3]


def _build_needs_work_from_vocal_score(vocal_score: dict) -> list[dict]:
    area_scores = vocal_score.get("area_scores", []) or []
    priority = vocal_score.get("priority_areas", []) or []
    if not area_scores:
        return []

    by_id = {
        item.get("area_id"): item
        for item in area_scores if isinstance(item, dict)
    }

    result = []
    for area_id in priority[:3]:
        item = by_id.get(area_id)
        if not item:
            continue
        score = item.get("score")
        conf = float(item.get("confidence", 1.0))
        if score is None or conf < 0.35:
            continue

        title = item.get("display_name", area_id)
        current = item.get("feedback_hint", "")
        value = item.get("value")
        target = item.get("target", "")

        result.append({
            "title": title,
            "what_user_hears": (
                f"현재 {title} 영역 점수는 {round(float(score))}점이며, "
                f"지표값은 {value}로 측정되었습니다. {current}"
            ),
            "possible_reason": (
                "현재 수치가 목표 기준과 차이가 있어 해당 영역이 상대적으로 약하게 들릴 수 있습니다. "
                f"목표 기준은 {target}이며, 녹음 조건과 전처리 영향도 함께 확인하는 것이 좋습니다."
            ),
            "how_to_sing": (
                "소리를 크게 밀기보다 작은 볼륨에서 시작점을 분명하게 만들고, "
                "문장 끝을 급하게 닫지 않도록 안정적으로 연결해보세요."
            ),
            "practice": " / ".join(item.get("practice", [])[:3]) if item.get("practice") else "문제 구간 5초 단위로 나눠 반복 녹음 후 비교하세요.",
            "check_next": (
                f"다음 녹음에서 {title} 점수가 현재보다 상승했는지, "
                "그리고 같은 구간에서 지표값이 목표 기준에 가까워졌는지 확인하세요."
            ),
        })

    return result


def _build_well_done_from_vocal_score(vocal_score: dict) -> list[dict]:
    area_scores = vocal_score.get("area_scores", []) or []
    strength_ids = set(vocal_score.get("strength_areas", []) or [])
    if not area_scores:
        return []

    result = []
    for item in area_scores:
        if item.get("area_id") not in strength_ids:
            continue
        score = item.get("score")
        if score is None:
            continue
        title = item.get("display_name", item.get("area_id", "강점 영역"))
        metric = item.get("metric_name", "")
        value = item.get("value")
        target = item.get("target", "")
        result.append({
            "title": title,
            "feedback": f"현재 점수는 {round(float(score))}점이며, {metric}={value}로 측정되었습니다.",
            "keep_advice": f"현재 수준을 유지하되, 다음 녹음에서도 {target} 기준을 꾸준히 충족하는지 확인하세요.",
        })
        if len(result) >= 3:
            break

    return result


def _parse_json_response(raw: str) -> dict:
    """
    LLM 응답에서 JSON 블록을 추출한다.
    응답이 중간에 잘린 경우에도 가능한 필드를 최대한 복구한다.
    """
    # 마크다운 코드 블록 제거
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1:
            return {"raw_response": raw}
        # 완전한 JSON이 있으면 그대로 사용
        if end != -1 and end > start:
            json_str = raw[start : end + 1]
        else:
            json_str = raw[start:]

    # 1차 시도: 완전한 파싱
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # 2차 시도: 잘린 JSON 부분 복구
    # segment_feedback 배열이 잘린 경우가 많으므로 해당 위치까지만 추출
    result = {"raw_response": raw}
    for field in ("confidence", "overall_summary", "well_done", "needs_work",
                  "segment_feedback", "practice_plan", "weekly_goal", "caution"):
        pattern = rf'"{re.escape(field)}"\s*:\s*'
        m = re.search(pattern, json_str)
        if not m:
            continue
        val_start = m.end()
        val_char = json_str[val_start:val_start+1]
        if val_char == '"':
            # 문자열 값
            inner = re.search(r'"((?:[^"\\]|\\.)*)"', json_str[val_start:])
            if inner:
                result[field] = inner.group(1)
        elif val_char == '[':
            # 배열: 닫히지 않아도 지금까지 완성된 요소만 추출
            arr_str = json_str[val_start:]
            # 완전한 요소가 끝나는 위치 찾기 (단순 휴리스틱)
            depth = 0
            end_idx = 0
            for i, ch in enumerate(arr_str):
                if ch in ('{', '['):
                    depth += 1
                elif ch in ('}', ']'):
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break
            if end_idx > 0:
                try:
                    result[field] = json.loads(arr_str[:end_idx+1])
                except json.JSONDecodeError:
                    pass
            elif depth > 0:
                # 잘린 배열: 닫히지 않은 요소 제거 후 시도
                truncated = arr_str.rstrip().rstrip(',')
                # 마지막으로 완성된 객체까지만
                last_close = truncated.rfind('}')
                if last_close != -1:
                    repaired = truncated[:last_close+1] + ']'
                    try:
                        result[field] = json.loads(repaired)
                    except json.JSONDecodeError:
                        pass
    return result


def build_user_friendly_report(feedback: dict) -> str:
    """
    feedback dict를 일반 사용자가 읽기 쉬운 상세 리포트 문자열로 변환한다.
    """
    confidence_map = {"high": "높음", "medium": "보통", "low": "낮음"}
    conf = str(feedback.get("confidence", "medium")).lower()
    confidence_text = confidence_map.get(conf, "보통")

    lines = []
    lines.append("[보컬 음색 완성도 리포트]")
    source_name = feedback.get("source_filename")
    if source_name:
        lines.append(f"- 음원 파일: {source_name}")
    lines.append(f"- 신뢰도: {confidence_text}")
    vocal_score = feedback.get("vocal_score") or {}
    overall_score = vocal_score.get("overall_score")
    overall_label = vocal_score.get("score_label")
    if overall_score is not None:
        lines.append(f"- 종합 점수: {round(float(overall_score))} / 100")
    if overall_label:
        lines.append(f"- 평가: {overall_label}")
    lines.append(f"- 핵심 요약: {feedback.get('overall_summary', '요약 정보 없음')}")

    area_scores = vocal_score.get("area_scores") or []
    if area_scores:
        lines.append("")
        lines.append("[영역별 점수]")
        for idx, item in enumerate(area_scores, start=1):
            area_name = item.get("display_name", item.get("area_id", "영역"))
            score = item.get("score")
            metric = item.get("metric_name", "")
            value = item.get("value")
            target = item.get("target", "")
            confv = item.get("confidence", 1.0)
            hint = item.get("feedback_hint", "")
            lines.append(f"{idx}. {area_name}: {'분석 제외' if score is None else f'{round(float(score))}점'}")
            if metric:
                lines.append(f"   - 현재 지표: {metric} = {value}")
            if target:
                lines.append(f"   - 목표 기준: {target}")
            if hint:
                lines.append(f"   - 현재 상태: {hint}")
            lines.append(f"   - 신뢰도: {round(float(confv), 2)}")
            if confv < 0.35:
                lines.append("   - 해석 주의: 전처리/녹음 영향이 커 참고용으로 보는 것이 좋습니다.")

    priority_areas = vocal_score.get("priority_areas") or []
    if priority_areas:
        id_to_name = {i.get("area_id"): i.get("display_name", i.get("area_id")) for i in area_scores if isinstance(i, dict)}
        lines.append("")
        lines.append("[우선 개선 영역 TOP 3]")
        for rank, area_id in enumerate(priority_areas[:3], start=1):
            lines.append(f"{rank}. {id_to_name.get(area_id, area_id)}")

    # ── 잘하고 있는 점 ────────────────────────────────────────────────────
    well_done = feedback.get("well_done") or []
    well_done = well_done[:3]
    if well_done:
        lines.append("")
        lines.append("[잘하고 있는 점]")
        for i, item in enumerate(well_done, start=1):
            title = item.get("title", "") if isinstance(item, dict) else str(item)
            fb    = item.get("feedback", "") if isinstance(item, dict) else ""
            keep  = item.get("keep_advice", "") if isinstance(item, dict) else ""
            lines.append(f"{i}. {title}")
            if fb:
                lines.append(f"   {fb}")
            if keep:
                lines.append(f"   → {keep}")

    # ── 우선 개선 포인트 (feedback_eligible만) ───────────────────────────
    needs_work = feedback.get("needs_work") or []
    lines.append("")
    lines.append("[우선 개선 포인트]")
    if not needs_work:
        lines.append("- 지금 발성 방향은 비교적 안정적입니다. 현재 감각을 유지하며 기본기 루틴을 이어가세요.")
    else:
        for i, issue in enumerate(needs_work, start=1):
            title   = issue.get("title", "개선 항목") if isinstance(issue, dict) else str(issue)
            symptom = issue.get("what_user_hears", "") if isinstance(issue, dict) else ""
            cause   = issue.get("possible_reason", "") if isinstance(issue, dict) else ""
            advice  = issue.get("how_to_sing", "") if isinstance(issue, dict) else ""
            practice= issue.get("practice", "") if isinstance(issue, dict) else ""
            check   = issue.get("check_next", "") if isinstance(issue, dict) else ""

            lines.append(f"")
            lines.append(f"{'='*50}")
            lines.append(f"{i}. {title}")
            lines.append(f"{'='*50}")
            if symptom:
                lines.append(f"[들리는 느낌]")
                lines.append(f"  {symptom}")
            if cause:
                lines.append(f"[가능한 원인]")
                lines.append(f"  {cause}")
            if advice:
                lines.append(f"[바로 해볼 발성 방법]")
                lines.append(f"  {advice}")
            if practice:
                lines.append(f"[구체적인 연습법]")
                lines.append(f"  {practice}")
            if check:
                lines.append(f"[다음 녹음에서 확인할 기준]")
                lines.append(f"  {check}")

    # ── 구간별 코멘트 ─────────────────────────────────────────────────────
    segs = feedback.get("segment_feedback") or []
    if segs:
        lines.append("")
        lines.append("[구간별 코멘트]")
        for i, seg in enumerate(segs, start=1):
            start = seg.get("start_sec", 0)
            end   = seg.get("end_sec", 0)
            msg   = seg.get("feedback", "")
            lines.append(f"{i}. {start:.1f}s ~ {end:.1f}s: {msg}")

    # ── 분석 참고사항 (artifact_warnings) ────────────────────────────────
    notes = (feedback.get("analysis_notes") or [])[:2]
    if notes:
        lines.append("")
        lines.append("[분석 참고사항]")
        lines.append("※ 아래 항목은 보컬 분리 전처리 과정의 영향으로 발성 문제로 단정하기 어렵습니다.")
        for note in notes:
            lines.append(f"- {note}")

    # ── 다음 연습 루틴 ────────────────────────────────────────────────────
    plan = feedback.get("practice_plan") or []
    lines.append("")
    lines.append("[다음 연습 루틴]")
    if not plan:
        lines.append("1. 10분 스트레칭 및 호흡 준비")
        lines.append("2. 10분 롱톤 — 작은 볼륨에서 음정을 안정적으로 유지하는 연습")
        lines.append("3. 10분 문제 구간 집중 재녹음")
    else:
        for i, item in enumerate(plan, start=1):
            lines.append(f"{i}. {item}")

    # ── 이번 주 목표 ──────────────────────────────────────────────────────
    weekly_goal = feedback.get("weekly_goal")
    if weekly_goal:
        lines.append("")
        lines.append("[이번 주 목표]")
        lines.append(f"- {weekly_goal}")

    # ── 주의사항 ──────────────────────────────────────────────────────────
    caution = feedback.get("caution")
    lines.append("")
    lines.append("[주의사항]")
    if caution:
        lines.append(f"- {caution}")
    else:
        lines.append("- 목에 통증이 느껴지면 강도를 낮추고, 충분히 쉰 뒤 다시 연습하세요.")
        lines.append("- 높은 음을 억지로 밀기보다, 편한 음역에서 정확도를 먼저 올리세요.")

    return "\n".join(lines)

