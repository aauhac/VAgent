"""Precision Diagnostic v2.3 — Actionable coaching layer.

DIAGNOSIS is immutable input. This module only converts concern evaluations +
controlled contrasts into strengths, focus areas, and practice directions.

USER_REPORTED ≠ AUDIO_OBSERVED ≠ CONTROLLED_TASK_CONFIRMED
"""

from __future__ import annotations

from typing import Any, Optional

COACHING_VERSION = "precision-coaching-v1.2"

# Canonical coaching modes
MODE_CORRECT = "CORRECT"
MODE_REFINE = "REFINE"
MODE_MAINTAIN = "MAINTAIN"
MODE_TRANSFER = "TRANSFER"
MODE_PRESERVE_ONLY = "PRESERVE_ONLY"
MODE_GUIDE = "GUIDE"
MODE_SAFETY = "SAFETY"

_MODE_LABEL = {
    MODE_CORRECT: "교정",
    MODE_REFINE: "보완",
    MODE_MAINTAIN: "유지",
    MODE_TRANSFER: "전이",
    MODE_PRESERVE_ONLY: "유지",
    MODE_GUIDE: "안내",
    MODE_SAFETY: "안전",
}

# Known internal evidence tokens → user-facing Korean (unknown → hide)
_EVIDENCE_TOKEN_MAP: dict[str, str] = {
    "baseline_and_high_both_low": "편한 음과 높은 음 모두 힘 증가가 낮게 나타남",
    "high_note_stability_maintained": "고음에서도 안정성이 유지됨",
    "breathiness_increase_not_primary": "숨 섞임 증가는 크지 않음",
    "song_effort_high_but_controlled_low": "노래에서는 힘 증가가 보였지만 표준 과제에서는 낮음",
    "song_effort_low": "노래 분석에서 과도한 힘 증가가 뚜렷하지 않음",
    "song_effort_high": "노래 분석에서 힘 증가 패턴이 확인됨",
    "song_and_tasks_low_effort": "노래·표준 과제 모두 힘 증가가 낮음",
    "thin_cues_absent": "얇은 인상과 일치하는 패턴이 뚜렷하지 않음",
    "light_contact": "접촉감이 가벼운 편",
    "task_resonance": "표준 과제의 공명·스펙트럼 특성",
    "task_breathiness": "표준 과제의 숨 섞임 특성",
    "task_contact": "표준 과제의 접촉감 특성",
    "task_timbre_proxy": "표준 과제에서 확인된 음색 특성",
}


def user_facing_evidence_token(token: Any) -> Optional[str]:
    """Map known provenance tokens; hide unknown internal codes."""
    if token is None:
        return None
    s = str(token).strip()
    if not s:
        return None
    if s in _EVIDENCE_TOKEN_MAP:
        return _EVIDENCE_TOKEN_MAP[s]
    # Structured known prefixes
    if s.startswith("brightness="):
        try:
            v = float(s.split("=", 1)[1])
        except ValueError:
            return "밝기 특성"
        if v >= 0.58:
            return "밝은 음색 경향"
        if v <= 0.42:
            return "어두운 음색 경향"
        return "밝기는 보통"
    if s.startswith("presence="):
        try:
            v = float(s.split("=", 1)[1])
        except ValueError:
            return "중역 존재감"
        if v >= 0.58:
            return "중역 존재감이 유지됨"
        if v <= 0.42:
            return "중역 존재감이 낮은 편"
        return "중역 존재감은 보통"
    if s.startswith("airiness="):
        try:
            v = float(s.split("=", 1)[1])
        except ValueError:
            return "숨 섞임 특성"
        if v <= 0.4:
            return "숨 섞임이 적은 편"
        if v >= 0.55:
            return "숨 섞임이 있는 편"
        return "숨 섞임은 보통"
    if s.startswith("texture="):
        return "음색 질감 특성"
    if s.startswith("consistency="):
        return "구간별 음색 일관성"
    if s.startswith("low_presence="):
        return "중역 존재감이 낮은 편"
    if s.startswith("low_brightness="):
        return "밝기가 낮은 편"
    if s.startswith("low_airiness="):
        return "숨 섞임이 적은 편"
    if s.startswith("presence_ok="):
        return "중역 존재감이 유지됨"
    if s.startswith("brightness_ok="):
        return "밝은 음색 경향이 유지됨"
    if s.startswith("low_airiness_alone="):
        return "숨 섞임이 적다는 것만으로는 답답함과 단정하기 어려움"
    if s.startswith("high_airiness="):
        return "숨 섞임이 높은 편"
    if s.startswith("effort_delta_"):
        return "편한 음 대비 고음에서 힘 관련 패턴 변화"
    if s.startswith("baseline_") and "_to_high_" in s:
        return "편한 음과 고음의 힘 패턴 비교"
    if s.startswith("high_effort_"):
        return "높은 음 과제에서 힘 관련 패턴"
    if s.startswith("song_effort_"):
        return "노래 분석의 힘 관련 패턴"
    # Hide unknown snake_case / internal ids
    if "_" in s and s.replace("_", "").replace("=", "").replace(".", "").isalnum():
        if any(ch.isalpha() for ch in s) and s == s.lower() or s.isupper() or "=" in s:
            # likely internal code
            if not any(ord(c) > 127 for c in s):  # no hangul → hide
                return None
    return s if any(ord(c) > 127 for c in s) else None


def map_evidence_list(tokens: list[Any] | None) -> list[str]:
    out: list[str] = []
    for t in tokens or []:
        u = user_facing_evidence_token(t)
        if u and u not in out:
            out.append(u)
    return out


def coaching_mode_for_status(
    status: str,
    *,
    evaluation: Optional[dict[str, Any]] = None,
) -> str:
    ev = evaluation or {}
    st = str(status or "").upper()
    gl = str(ev.get("guidance_level") or "").upper()
    if st == "SAFETY_ONLY" or gl == "SAFETY_ONLY":
        return MODE_SAFETY
    if st == "CONFIRMED":
        return MODE_CORRECT
    if st == "PARTIALLY_SUPPORTED":
        return MODE_REFINE if gl != "SONG_DIRECT" else MODE_GUIDE
    if st == "CONTEXT_DEPENDENT":
        return MODE_TRANSFER
    if st in ("NOT_SUPPORTED_IN_THIS_RECORDING", "NOT_SUPPORTED"):
        against = ev.get("against") or []
        contrast = ev.get("contrast_evidence") or []
        support = ev.get("support") or []
        if against or contrast or support:
            return MODE_MAINTAIN
        if ev.get("practice") or gl == "SAFE_GENERAL_GUIDANCE":
            return MODE_GUIDE
        return MODE_PRESERVE_ONLY
    if gl in ("SONG_DIRECT", "SONG_COMPOSITE", "SAFE_GENERAL_GUIDANCE") or ev.get("practice"):
        return MODE_GUIDE
    return MODE_GUIDE  # never silence non-safety concerns


def _profiles(fused: dict[str, Any]) -> dict[str, Any]:
    return fused.get("task_profiles") or {}


def _contrasts(fused: dict[str, Any]) -> dict[str, Any]:
    return fused.get("controlled_contrasts") or {}


def _effort_contrast(fused: dict[str, Any]) -> dict[str, Any]:
    return ((_contrasts(fused).get("baseline_vs_high") or {}).get("dimensions") or {}).get(
        "effort"
    ) or {}


def _dim_status(profiles: dict[str, Any], task_id: str, dim: str) -> str:
    return str(
        (((profiles.get(task_id) or {}).get("dimensions") or {}).get(dim) or {}).get("status")
        or ""
    ).upper()


def _siren_connected(profiles: dict[str, Any]) -> bool:
    return _dim_status(profiles, "siren", "register") == "CONNECTED"


def _follow_up_for(concerns: list[dict[str, Any]], concern_id: str) -> Optional[str]:
    for c in concerns or []:
        if str(c.get("id")) == concern_id:
            return c.get("follow_up")
    return None


def derive_precision_strengths(
    *,
    concern_evaluations: list[dict[str, Any]],
    fused_profile: dict[str, Any],
    song_profile: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Positive-evidence strengths only — never invent from UNRESOLVED / skipped tasks."""
    fused = fused_profile or {}
    profiles = _profiles(fused)
    skipped = set(
        (fused.get("task_evidence") or {}).get("user_skipped_tasks")
        or fused.get("user_skipped_tasks")
        or []
    )
    strengths: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(sid: str, title: str, description: str, why: str, evidence: list[str]) -> None:
        if sid in seen:
            return
        seen.add(sid)
        strengths.append(
            {
                "id": sid,
                "title": title,
                "description": description,
                "why_keep": why,
                "evidence_source": evidence,
            }
        )

    effort_c = _effort_contrast(fused)
    high_ok = (
        "high_note_sustain_a" not in skipped
        and (profiles.get("high_note_sustain_a") or {}).get("valid")
    )
    if (
        high_ok
        and effort_c.get("available")
        and effort_c.get("direction") == "SIMILAR"
        and str(effort_c.get("baseline") or "").upper() in ("LOW", "STABLE", "")
        and str(effort_c.get("high") or "").upper() in ("LOW", "STABLE", "")
    ):
        add(
            "LOW_EFFORT_HIGH_NOTE_MAINTAINED",
            "고음에서도 힘을 크게 늘리지 않는 패턴",
            "편한 음과 높은 음 모두에서 힘 관련 패턴이 낮게 유지됐어요.",
            "높은 음에 도달할 때 음량까지 함께 키우지 않는 습관을 이어가면 좋아요.",
            ["baseline_vs_high.effort"],
        )

    stab_c = ((_contrasts(fused).get("baseline_vs_high") or {}).get("dimensions") or {}).get(
        "stability"
    ) or {}
    if high_ok and stab_c.get("available") and stab_c.get("direction") == "SIMILAR":
        high_st = str(stab_c.get("high") or "").upper()
        if high_st in ("STEADY", "STABLE", "LOW"):
            add(
                "HIGH_NOTE_STABILITY_MAINTAINED",
                "고음에서도 발성 안정성 유지",
                "높은 음 과제에서도 안정성이 크게 흔들리지 않았어요.",
                "안정적인 구간을 유지한 채 범위를 천천히 확장하는 방향이 좋아요.",
                ["baseline_vs_high.stability"],
            )

    siren_ok = "siren" not in skipped and (profiles.get("siren") or {}).get("valid")
    if siren_ok and _siren_connected(profiles):
        add(
            "REGISTER_CONNECTION_MAINTAINED",
            "중음→고음 연결의 연속성",
            "사이렌 과제에서 큰 단절 없이 이어지는 패턴이 확인됐어요.",
            "연결이 끊기지 않도록 음량을 급격히 키우지 않는 것이 좋아요.",
            ["siren.register"],
        )

    # Timbre clarity from NOT_SUPPORTED muffled / timbre partial with bright/presence
    for ev in concern_evaluations or []:
        cid = ev.get("concern_id") or ev.get("concern")
        st = str(ev.get("status") or "")
        against = " ".join(str(x) for x in (ev.get("against") or []))
        support = " ".join(str(x) for x in (ev.get("support") or []))
        if cid == "VOICE_TOO_DARK_MUFFLED" and st in (
            "NOT_SUPPORTED_IN_THIS_RECORDING",
            "NOT_SUPPORTED",
        ):
            if "brightness_ok" in against or "presence_ok" in against:
                add(
                    "TIMBRE_CLARITY_MAINTAINED",
                    "밝기와 중역 존재감 유지",
                    "표준 발성에서 밝기와 중역 존재감이 유지되는 특성이 확인됐어요.",
                    "더 선명하게 만들려고 소리를 밀기보다 현재의 선명함을 유지하세요.",
                    ["timbre.brightness", "timbre.presence"],
                )
        if cid == "TIMBRE_DISSATISFIED" and st == "PARTIALLY_SUPPORTED":
            if "brightness=" in support or "presence=" in support:
                add(
                    "TIMBRE_CLARITY_MAINTAINED",
                    "밝기와 중역 존재감 유지",
                    "표준 발성에서 밝고 중역 존재감이 있는 특성이 확인됐어요.",
                    "현재 확인된 선명한 기반을 유지하는 방향이 좋아요.",
                    ["timbre.axes"],
                )
            if "airiness=" in support and "적은" not in support:
                # low airiness encoded as airiness=0.xx <= 0.4 in support string
                pass
            for tok in ev.get("support") or []:
                if str(tok).startswith("airiness="):
                    try:
                        if float(str(tok).split("=", 1)[1]) <= 0.4:
                            add(
                                "LOW_AIRINESS_PATTERN",
                                "숨 섞임이 적은 패턴",
                                "기본 발성에서 숨 섞임이 많지 않은 특성이 나타났어요.",
                                "숨이 먼저 빠져나가도록 의도적으로 키우지 않는 것이 좋아요.",
                                ["timbre.airiness"],
                            )
                    except ValueError:
                        pass

        if cid == "VOICE_TOO_BREATHY" and st in (
            "NOT_SUPPORTED_IN_THIS_RECORDING",
            "NOT_SUPPORTED",
        ):
            add(
                "LOW_AIRINESS_PATTERN",
                "숨 섞임이 적은 패턴",
                "이번 녹음에서는 과도한 숨 섞임 패턴이 뚜렷하지 않았어요.",
                "현재의 깨끗한 발성 경향을 유지하세요.",
                ["breathiness"],
            )

        if cid == "HIGH_NOTE_TOO_EFFORTFUL" and st in (
            "NOT_SUPPORTED_IN_THIS_RECORDING",
            "NOT_SUPPORTED",
        ):
            if high_ok and effort_c.get("available") and effort_c.get("direction") == "SIMILAR":
                add(
                    "LOW_EFFORT_HIGH_NOTE_MAINTAINED",
                    "고음에서도 힘을 크게 늘리지 않는 패턴",
                    "편한 음과 높은 음 모두에서 힘 관련 패턴이 낮게 유지됐어요.",
                    "높은 음에서도 음량을 갑자기 키우지 않는 습관을 이어가면 좋아요.",
                    ["baseline_vs_high.effort"],
                )

        if cid == "HIGH_NOTE_UNSTABLE" and st in (
            "NOT_SUPPORTED_IN_THIS_RECORDING",
            "NOT_SUPPORTED",
        ):
            if high_ok:
                add(
                    "HIGH_NOTE_STABILITY_MAINTAINED",
                    "고음에서도 발성 안정성 유지",
                    "높은 음에서도 안정성이 잘 유지되는 편이에요.",
                    "현재의 안정 패턴을 유지한 채 범위를 확장하세요.",
                    ["baseline_vs_high.stability"],
                )

        if cid == "REGISTER_CONNECTION_DIFFICULT" and st in (
            "NOT_SUPPORTED_IN_THIS_RECORDING",
            "NOT_SUPPORTED",
        ):
            if siren_ok and _siren_connected(profiles):
                add(
                    "REGISTER_CONNECTION_MAINTAINED",
                    "중음→고음 연결의 연속성",
                    "중음에서 높은 음으로 이동할 때 큰 단절 없이 연결되는 패턴이 확인됐어요.",
                    "현재의 연속적인 연결을 유지하면서 음량을 급격히 키우지 마세요.",
                    ["siren.register"],
                )

    # Contact MID + low effort as soft strength (not firm=strain)
    contact = _dim_status(profiles, "sustain_a", "contact")
    base_eff = _dim_status(profiles, "sustain_a", "effort")
    if contact in ("MID", "LIGHT", "LIGHT_LEANING") and base_eff == "LOW":
        add(
            "BALANCED_CONTACT_LOW_EFFORT",
            "무리하지 않는 접촉감",
            "기본 지속음에서 접촉감이 지나치게 단단해지는 패턴은 두드러지지 않았어요.",
            "편안한 강도를 유지한 채 발성하세요.",
            ["sustain_a.contact", "sustain_a.effort"],
        )

    return strengths[:3]


def _practice(
    *,
    practice_id: str,
    mode: str,
    title: str,
    goal: str,
    instruction: str,
    success_cues: list[str],
    avoid: list[str],
    related: list[str],
    evidence: list[str],
    safety_note: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "practice_id": practice_id,
        "mode": mode,
        "mode_label": _MODE_LABEL.get(mode, mode),
        "title": title,
        "goal": goal,
        "instruction": instruction,
        "success_cues": success_cues[:3],
        "avoid": avoid[:2],
        "related_concerns": related,
        "evidence_basis": evidence,
        "safety_note": safety_note,
    }


def build_concern_coaching(
    evaluation: dict[str, Any],
    *,
    user_concerns: Optional[list[dict[str, Any]]] = None,
    fused_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Per-concern coaching payload — does not alter diagnosis status/answer."""
    cid = str(evaluation.get("concern_id") or evaluation.get("concern") or "")
    status = str(evaluation.get("status") or "UNRESOLVED")
    mode = coaching_mode_for_status(status, evaluation=evaluation)
    fused = fused_profile or {}
    follow = _follow_up_for(user_concerns or [], cid)

    takeaway = ""
    what_working = ""
    what_improve = ""
    practice: Optional[dict[str, Any]] = None

    # Prefer practice already attached by functional hypothesis
    hyp_practice = evaluation.get("practice")
    if isinstance(hyp_practice, dict) and hyp_practice.get("instruction"):
        practice = {
            "practice_id": hyp_practice.get("practice_id"),
            "mode": mode,
            "mode_label": _MODE_LABEL.get(mode, mode),
            "title": hyp_practice.get("title"),
            "goal": hyp_practice.get("goal"),
            "instruction": hyp_practice.get("instruction"),
            "success_cues": list(hyp_practice.get("success_cues") or [])[:3],
            "avoid": list(hyp_practice.get("avoid") or [])[:2],
            "related_concerns": [cid],
            "evidence_basis": list(evaluation.get("song_evidence_used") or ["song_evidence"]),
            "safety_note": None,
        }

    if mode == MODE_SAFETY:
        takeaway = "불편한 상태에서는 강한 고음·큰 소리 반복보다 휴식이 우선이에요."
        practice = _practice(
            practice_id="SAFETY_FIRST",
            mode=MODE_SAFETY,
            title="불편할 때는 강한 고음·큰 소리 피하기",
            goal="통증·지속 불편이 있을 때 무리한 연습 중단",
            instruction="불편감이 있으면 강한 고음과 큰 소리 반복을 멈추고 짧게 쉬세요.",
            success_cues=["불편감이 늘지 않음", "무리한 고음 시도를 하지 않음"],
            avoid=["통증 상태에서의 강한 고음 반복"],
            related=[cid],
            evidence=["safety"],
            safety_note="통증·쉰 느낌이 반복되면 전문 진료를 권장합니다.",
        )
    elif cid == "HIGH_NOTE_TOO_EFFORTFUL":
        if mode == MODE_MAINTAIN:
            takeaway = (
                "높은 음에서도 힘을 크게 늘리지 않는 패턴이 잘 유지되고 있어요. "
                "현재 과제에서 나타난 이 발성 방식은 유지해도 좋은 방향입니다."
            )
            what_working = "편한 음과 높은 음 모두 힘 관련 패턴이 낮게 나타났어요."
            practice = _practice(
                practice_id="MAINTAIN_HIGH_NOTE_EASE",
                mode=MODE_MAINTAIN,
                title="고음에서도 편안한 힘 유지하기",
                goal="높은 음에서도 힘을 크게 늘리지 않는 패턴 유지",
                instruction=(
                    "편안한 강도의 높은 '아—'를 짧게 유지하면서 "
                    "음이 올라가도 음량을 더 키우지 않는 패턴을 반복하세요."
                ),
                success_cues=[
                    "음이 올라가도 음량이 갑자기 커지지 않음",
                    "소리가 끝까지 비슷한 강도로 유지됨",
                    "불편감이 없음",
                ],
                avoid=["높은 음이라는 이유로 음량까지 같이 키우기"],
                related=[cid],
                evidence=["baseline_vs_high.effort"],
            )
        elif mode == MODE_CORRECT:
            takeaway = (
                "높은 음에 도달하는 것보다, "
                "높은 음에서 힘 사용이 커지는 변화가 더 두드러집니다."
            )
            what_improve = "고음에서 힘 관련 패턴이 증가하는 변화"
            practice = _practice(
                practice_id="REDUCE_HIGH_NOTE_EFFORT",
                mode=MODE_CORRECT,
                title="고음에서 힘 증가 줄이기",
                goal="높은 음에서 힘 사용이 급격히 커지지 않도록 하기",
                instruction=(
                    "현재 가능한 음보다 약간 낮은 편안한 높은 음에서 "
                    "작은~중간 강도를 유지한 상태로 짧게 발성하고, "
                    "그 편안함을 유지한 채 범위를 확장하세요."
                ),
                success_cues=[
                    "높은 음에서도 음량을 먼저 키우지 않음",
                    "짧은 구간에서 불편감 없이 유지",
                ],
                avoid=["높은 음에 도달하기 위해 음량부터 키우기"],
                related=[cid],
                evidence=["baseline_vs_high.effort"],
            )
        elif mode == MODE_TRANSFER:
            takeaway = (
                "표준 과제에서는 편안한 고음 패턴이 유지되지만, "
                "노래 상황에서는 같은 패턴이 반복되지 않았어요."
            )
            what_working = "표준 과제에서 확인된 편안한 고음 패턴"
            what_improve = "노래 상황에서 같은 편안함을 유지하기"
            practice = _practice(
                practice_id="TRANSFER_HIGH_NOTE_EASE",
                mode=MODE_TRANSFER,
                title="표준 과제의 편안한 고음을 노래에 옮기기",
                goal="과제에서 확인된 낮은 힘 패턴을 곡의 고음에 연결",
                instruction=(
                    "어려운 고음 구절을 처음부터 원래 강도로 부르지 말고, "
                    "편안한 강도로 먼저 연결한 뒤 "
                    "낮은 힘을 유지하면서 곡의 표현 강도에 접근하세요."
                ),
                success_cues=[
                    "연습 강도에서 고음 연결이 끊기지 않음",
                    "강도만 올리며 힘을 급격히 키우지 않음",
                ],
                avoid=["곡 강도부터 바로 밀어붙이기"],
                related=[cid],
                evidence=["song_vs_controlled.effort"],
            )
        elif mode == MODE_REFINE:
            takeaway = "고음에서 힘 증가가 일부 보이지만, 근거가 제한적이에요."
            what_improve = "고음에서 힘을 더 키우지 않도록 다듬기"
            practice = _practice(
                practice_id="REFINE_HIGH_NOTE_EFFORT",
                mode=MODE_REFINE,
                title="고음에서 힘 증가 줄이기",
                goal="고음에서 힘 사용을 완만하게 유지",
                instruction=(
                    "편안한 높은 음에서 작은 강도를 유지한 채 짧게 반복하고, "
                    "음이 올라갈수록 음량을 함께 키우지 마세요."
                ),
                success_cues=["높은 음에서도 음량이 급격히 커지지 않음"],
                avoid=["높은 음에서 음량부터 키우기"],
                related=[cid],
                evidence=["baseline_vs_high.effort"],
            )
        else:
            takeaway = (
                "원인을 하나로 좁히기는 어렵지만, "
                "지금은 작은 강도로 고음을 연결하는 연습부터 시도하는 것이 좋아요."
            )

    elif cid in ("THROAT_EFFORT", "LOUD_VOICE_DIFFICULT", "VOCAL_FATIGUE", "AFTER_SINGING_FATIGUE"):
        if mode == MODE_MAINTAIN:
            takeaway = (
                "체감상 힘을 느끼셨을 수 있지만, "
                "이번 녹음에서는 과도한 힘 증가 패턴이 뚜렷하지 않았어요."
            )
            what_working = "과도한 힘 증가가 뚜렷하지 않은 패턴"
            practice = _practice(
                practice_id="MAINTAIN_LOW_EFFORT",
                mode=MODE_MAINTAIN,
                title="현재의 편안한 힘 사용 유지하기",
                goal="불필요하게 힘을 키우지 않는 패턴 유지",
                instruction="편안한 강도로 짧은 지속음을 유지하며, 소리를 과하게 밀지 마세요.",
                success_cues=["불편감 없이 짧은 구간 유지", "음량을 갑자기 키우지 않음"],
                avoid=["힘을 더 주며 밀어붙이기"],
                related=[cid],
                evidence=["effort"],
            )
        elif mode in (MODE_CORRECT, MODE_REFINE):
            takeaway = "노래·표준 과제에서 확인된 힘 증가 패턴이 현재 더 두드러진 제한으로 보입니다."
            what_improve = "힘 사용이 급격히 커지지 않도록 하기"
            practice = _practice(
                practice_id="REDUCE_HIGH_NOTE_EFFORT",
                mode=mode if mode == MODE_CORRECT else MODE_REFINE,
                title="고음에서 힘 증가 줄이기",
                goal="높은 음·강한 구간에서 힘 사용이 급격히 커지지 않도록",
                instruction=(
                    "작은~중간 강도를 유지한 상태로 짧게 발성하고, "
                    "그 편안함을 유지한 채 범위를 확장하세요."
                ),
                success_cues=["음량을 먼저 키우지 않음", "짧은 구간에서 불편감 없이 유지"],
                avoid=["높은 음·큰 소리에 도달하기 위해 음량부터 키우기"],
                related=[cid],
                evidence=["effort"],
            )
        elif mode == MODE_TRANSFER:
            takeaway = (
                "표준 과제에서는 편안한 패턴이 보이지만, "
                "노래 상황에서는 힘 사용이 다르게 나타났어요."
            )
            practice = _practice(
                practice_id="TRANSFER_LOW_EFFORT",
                mode=MODE_TRANSFER,
                title="과제의 편안한 힘을 노래에 옮기기",
                goal="과제에서 확인된 낮은 힘 패턴을 곡에 연결",
                instruction="편안한 강도로 먼저 연결한 뒤, 힘을 유지하면서 곡의 표현 강도에 접근하세요.",
                success_cues=["연습 강도에서 연결이 끊기지 않음"],
                avoid=["곡 강도부터 바로 밀어붙이기"],
                related=[cid],
                evidence=["song_vs_controlled.effort"],
            )

    elif cid == "HIGH_NOTE_UNSTABLE":
        if mode == MODE_MAINTAIN:
            takeaway = "고음에서도 안정성이 잘 유지되고 있어요."
            what_working = "높은 음 과제에서도 안정성 유지"
            practice = _practice(
                practice_id="MAINTAIN_HIGH_NOTE_STABILITY",
                mode=MODE_MAINTAIN,
                title="고음 안정 패턴 유지하기",
                goal="높은 음에서도 흔들림이 커지지 않도록 유지",
                instruction="안정적으로 유지되는 높은 음을 짧게 반복하며 범위를 천천히 확장하세요.",
                success_cues=["높은 음에서도 소리가 급격히 흔들리지 않음"],
                avoid=["불안정한 높은 음까지 무리해서 늘리기"],
                related=[cid],
                evidence=["baseline_vs_high.stability"],
            )
        elif mode in (MODE_CORRECT, MODE_REFINE):
            takeaway = "고음에서 안정성이 떨어지는 변화가 더 두드러져요."
            what_improve = "고음 안정성 유지"
            practice = _practice(
                practice_id="CORRECT_HIGH_NOTE_STABILITY",
                mode=mode,
                title="고음 안정성 유지하기",
                goal="높은 음에서 흔들림이 커지지 않도록",
                instruction="안정 구간을 먼저 짧게 유지하고, 그 느낌을 유지한 채 범위를 확장하세요.",
                success_cues=["짧은 고음에서 흔들림이 크지 않음"],
                avoid=["불안정한 음역을 길게 버티기"],
                related=[cid],
                evidence=["baseline_vs_high.stability"],
            )

    elif cid == "REGISTER_CONNECTION_DIFFICULT":
        if mode == MODE_MAINTAIN:
            takeaway = (
                "중음에서 높은 음으로 이동할 때 "
                "큰 단절 없이 연결되는 패턴이 확인됐어요."
            )
            what_working = "사이렌 연결의 연속성"
            practice = _practice(
                practice_id="MAINTAIN_REGISTER_CONNECTION",
                mode=MODE_MAINTAIN,
                title="중음→고음 연결 유지하기",
                goal="연속적인 연결을 유지",
                instruction="현재의 연속적인 연결을 유지하면서 음량을 급격히 키우지 마세요.",
                success_cues=["중간에서 높은 음으로 넘어갈 때 갑자기 끊기지 않음"],
                avoid=["연결 구간에서 강도를 갑자기 키우기"],
                related=[cid],
                evidence=["siren.register"],
            )
        elif mode in (MODE_CORRECT, MODE_REFINE):
            takeaway = "전환 구간에서 연결이 끊기거나 급격히 달라지는 패턴이 보여요."
            what_improve = "전환 구간을 작은 강도로 연속 연결"
            practice = _practice(
                practice_id="CORRECT_REGISTER_CONNECTION",
                mode=mode,
                title="중음→고음 연결 안정화",
                goal="전환 구간을 연속적으로 연결",
                instruction="작은 강도로 부드러운 사이렌을 반복하며 끊기지 않게 이으세요.",
                success_cues=["전환에서 갑자기 끊기지 않음", "강도를 갑자기 키우지 않음"],
                avoid=["전환 구간에서 밀어붙이기"],
                related=[cid],
                evidence=["siren.register"],
            )

    elif cid == "TIMBRE_DISSATISFIED":
        # Descriptive — never good/bad
        el = str(evaluation.get("evidence_level") or "")
        song_only = el in ("SONG_SUPPORTED", "SONG_INFERRED") or not evaluation.get("task_ids_used")
        scope = "이번 노래에서 확인된" if song_only else "표준 발성에서 확인된"
        takeaway = (
            f"{scope} 기본 음색 특성을 기준으로, "
            "현재의 선명한 기반을 유지하는 방향이 좋아요."
        )
        what_working = f"밝기·중역 존재감·숨 섞임 등 {scope} 특성"
        if follow == "MUFFLED" and mode in (MODE_REFINE, MODE_MAINTAIN, MODE_PRESERVE_ONLY):
            # Personalize coaching only — do not invent muffled diagnosis
            against = " ".join(str(x) for x in (evaluation.get("against") or []))
            support = " ".join(str(x) for x in (evaluation.get("support") or []))
            if "brightness" in support or "presence" in support or "brightness_ok" in against:
                takeaway = (
                    f"원하시는 방향과 달리 {scope} 이미 선명한 특성이 있으므로 "
                    "더 밝게 밀기보다 이 선명함을 유지하는 방향이 좋아요."
                )
        practice = _practice(
            practice_id="MAINTAIN_TIMBRE_CLARITY",
            mode=MODE_MAINTAIN if mode != MODE_REFINE else MODE_REFINE,
            title="현재의 선명한 음색 기반 유지하기",
            goal=f"{scope} 밝기·존재감 기반 유지",
            instruction=(
                "편안한 강도로 짧은 '아—'를 유지할 때 "
                "음이 올라가도 음량을 갑자기 키우지 않고 "
                "현재의 선명한 소리를 유지하세요."
            ),
            success_cues=[
                "소리가 지나치게 어두워지지 않음",
                "중역 존재감이 갑자기 사라지지 않음",
            ],
            avoid=["더 선명하게 만들기 위해 소리를 세게 밀어붙이기"],
            related=[cid],
            evidence=["timbre.axes"],
        )

    elif cid == "VOICE_TOO_DARK_MUFFLED":
        if mode == MODE_MAINTAIN:
            takeaway = "표준 발성에서는 밝기와 중역 존재감이 잘 유지되고 있어요."
            what_working = "소리가 지나치게 어두워지거나 중역 존재감이 크게 줄어드는 패턴은 보이지 않았어요."
            practice = _practice(
                practice_id="MAINTAIN_TIMBRE_CLARITY",
                mode=MODE_MAINTAIN,
                title="현재의 선명함 유지하기",
                goal="밝기·중역 존재감을 유지",
                instruction="현재의 선명함을 유지한 채 중음에서 높은 음으로 연결하세요.",
                success_cues=["중역 존재감이 유지됨", "소리를 과하게 밀지 않음"],
                avoid=["더 선명하게 만들기 위해 소리를 세게 밀어붙이기"],
                related=[cid],
                evidence=["timbre.brightness", "timbre.presence"],
            )
        elif mode in (MODE_CORRECT, MODE_REFINE):
            takeaway = "밝기나 중역 존재감이 낮아 답답하게 느껴질 수 있는 패턴이 일부 확인됐어요."
            what_improve = "중역 존재감이 사라지지 않는 방향"
            practice = _practice(
                practice_id="REFINE_PRESENCE",
                mode=mode,
                title="중역 존재감 유지하기",
                goal="편안한 강도에서 선명한 모음 발성 유지",
                instruction=(
                    "편안한 강도에서 선명한 모음 발성을 유지하면서 "
                    "중역 존재감이 사라지지 않는 방향을 짧게 반복하세요."
                ),
                success_cues=["중역 존재감이 갑자기 사라지지 않음"],
                avoid=["선명함을 위해 과하게 밀기"],
                related=[cid],
                evidence=["timbre.presence"],
            )

    elif cid == "VOICE_TOO_BREATHY":
        if mode == MODE_MAINTAIN:
            takeaway = "이번 녹음에서는 과도한 숨 섞임 패턴이 뚜렷하지 않았어요."
            what_working = "숨 섞임이 적은 패턴"
            practice = _practice(
                practice_id="MAINTAIN_LOW_AIRINESS",
                mode=MODE_MAINTAIN,
                title="현재의 낮은 숨 섞임 유지하기",
                goal="숨 섞임이 갑자기 커지지 않도록 유지",
                instruction="편안한 강도의 짧은 지속음에서 숨이 먼저 빠져나가도록 키우지 마세요.",
                success_cues=["숨이 먼저 빠져나가는 느낌을 의도적으로 키우지 않음"],
                avoid=["숨 섞임을 일부러 키운 발성"],
                related=[cid],
                evidence=["breathiness"],
            )
        elif mode in (MODE_CORRECT, MODE_REFINE):
            takeaway = "숨 섞임과 일치하는 패턴이 더 두드러져요."
            what_improve = "숨 섞임 조절"
            practice = _practice(
                practice_id="CORRECT_AIRINESS",
                mode=mode,
                title="숨 섞임 조절하기",
                goal="숨이 과하게 섞이지 않는 안정적인 발성 유지",
                instruction="낮은 강도에서 짧은 지속음을 유지하며 숨이 먼저 새지 않게 하세요.",
                success_cues=["숨이 먼저 빠져나가는 느낌이 과하지 않음"],
                avoid=["숨만 흘리는 긴 발성"],
                related=[cid],
                evidence=["breathiness"],
            )

    elif cid == "VOICE_TOO_THIN":
        if mode in (MODE_CORRECT, MODE_REFINE):
            takeaway = "얇은 인상과 관련된 음색 특성이 일부 확인됐어요."
            what_improve = "중역 존재감·숨 섞임 균형"
            practice = _practice(
                practice_id="REFINE_THIN",
                mode=mode,
                title="중역 존재감 유지하기",
                goal="얇게 들릴 때 중역 존재감이 사라지지 않게",
                instruction="편안한 강도에서 짧은 모음을 유지하며 중역 존재감이 사라지지 않게 하세요.",
                success_cues=["중역 존재감이 유지됨"],
                avoid=["더 크게 밀어 얇음을 가리기"],
                related=[cid],
                evidence=["timbre.presence"],
            )
        elif mode == MODE_MAINTAIN:
            takeaway = "얇은 인상과 일치하는 패턴이 이번 조건에서는 뚜렷하지 않았어요."
            what_working = "중역 존재감·숨 섞임 균형"
            practice = _practice(
                practice_id="MAINTAIN_PRESENCE",
                mode=MODE_MAINTAIN,
                title="현재의 중역 존재감 유지하기",
                goal="중역 존재감 유지",
                instruction="편안한 강도로 짧은 지속음을 유지하며 소리를 과하게 밀지 마세요.",
                success_cues=["중역 존재감이 유지됨"],
                avoid=["얇음을 가리기 위해 과하게 밀기"],
                related=[cid],
                evidence=["timbre.presence"],
            )

    elif mode in (MODE_PRESERVE_ONLY, MODE_GUIDE) and practice is None:
        # Always-actionable: use hypothesis answer / safe practice — never end on silence
        takeaway = str(
            evaluation.get("answer_hint")
            or evaluation.get("interpretation")
            or "원인을 하나로 확정할 수는 없지만, 지금은 작은 강도로 연결을 만드는 연습부터 시도하는 것이 좋아요."
        )
        if "좁히기 어려워요" in takeaway and "→" not in takeaway:
            takeaway = (
                "원인을 하나로 확정할 수는 없지만, "
                "현재는 작은 강도로 연결을 만드는 연습부터 시도하는 것이 좋아요."
            )
        from audio_analyzer.diagnostic.practice_library import practice_for_focus

        focus = str(evaluation.get("primary_focus") or "REGISTER_CONNECTION")
        hp = practice_for_focus(focus)
        practice = _practice(
            practice_id=str(hp.get("practice_id") or "REGISTER_GLIDE_LIGHT"),
            mode=MODE_GUIDE,
            title=str(hp.get("title") or "작은 강도로 연결하기"),
            goal=str(hp.get("goal") or ""),
            instruction=str(hp.get("instruction") or ""),
            success_cues=list(hp.get("success_cues") or []),
            avoid=list(hp.get("avoid") or []),
            related=[cid],
            evidence=["song_evidence_guidance"],
        )
        mode = MODE_GUIDE
    elif mode == MODE_PRESERVE_ONLY:
        takeaway = str(
            evaluation.get("answer_hint")
            or "원인을 하나로 확정할 수는 없지만, 지금은 작은 강도로 연결을 만드는 연습부터 시도하는 것이 좋아요."
        )

    # If we already have hyp practice + answer, set takeaway from answer_hint
    if not takeaway and evaluation.get("answer_hint"):
        takeaway = str(evaluation.get("answer_hint"))
    if practice is None and mode == MODE_CORRECT:
        takeaway = takeaway or "이번 검사에서 확인된 제한을 중심으로 보완하는 방향이 좋아요."
        what_improve = what_improve or "확인된 발성 제한"
        practice = _practice(
            practice_id=f"CORRECT_{cid}",
            mode=MODE_CORRECT,
            title="확인된 제한 중심으로 보완하기",
            goal="확인된 패턴을 완화",
            instruction="편안한 강도에서 짧게 반복하며, 확인된 제한이 커지지 않게 유지하세요.",
            success_cues=["불편감 없이 짧은 구간 유지"],
            avoid=["확인된 제한이 커지는 방향으로 밀어붙이기"],
            related=[cid],
            evidence=["concern_evaluation"],
        )

    return {
        "coaching_mode": mode,
        "takeaway": takeaway,
        "what_is_working": what_working or None,
        "what_to_improve": what_improve or None,
        "practice_direction": practice,
        "user_facing_support": map_evidence_list(evaluation.get("support")),
        "user_facing_against": map_evidence_list(evaluation.get("against")),
        "user_facing_missing": map_evidence_list(evaluation.get("missing")),
    }


def _dedupe_practices(practices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    for p in practices:
        pid = str(p.get("practice_id") or "")
        title = str(p.get("title") or "")
        # Semantic merge: MAINTAIN_TIMBRE_CLARITY duplicates
        if pid in seen_ids:
            continue
        if title in seen_titles:
            continue
        # Collapse near-duplicates of high-note ease
        if pid.startswith("MAINTAIN_HIGH_NOTE") and any(
            x.get("practice_id", "").startswith("MAINTAIN_HIGH_NOTE") for x in out
        ):
            continue
        if pid.startswith("MAINTAIN_TIMBRE") and any(
            x.get("practice_id", "").startswith("MAINTAIN_TIMBRE") for x in out
        ):
            continue
        seen_ids.add(pid)
        seen_titles.add(title)
        out.append(p)
        if len(out) >= 3:
            break
    return out


def _priority_rank(mode: str) -> int:
    return {
        MODE_SAFETY: 0,
        MODE_CORRECT: 1,
        MODE_REFINE: 2,
        MODE_TRANSFER: 3,
        MODE_MAINTAIN: 4,
        MODE_PRESERVE_ONLY: 5,
    }.get(mode, 9)


def build_precision_coaching_plan(
    *,
    user_concerns: Optional[list[dict[str, Any]]] = None,
    concern_evaluations: Optional[list[dict[str, Any]]] = None,
    song_profile: Optional[dict[str, Any]] = None,
    fused_profile: Optional[dict[str, Any]] = None,
    task_results: Optional[list[dict[str, Any]]] = None,
    diagnostic_mode: Optional[str] = None,
) -> dict[str, Any]:
    """Build actionable coaching plan. Does not modify diagnosis."""
    evaluations = list(concern_evaluations or [])
    concerns = list(user_concerns or [])
    fused = fused_profile or {}

    per_concern: list[dict[str, Any]] = []
    practices: list[dict[str, Any]] = []
    focus: list[dict[str, Any]] = []

    for ev in evaluations:
        coach = build_concern_coaching(
            ev, user_concerns=concerns, fused_profile=fused
        )
        cid = ev.get("concern_id") or ev.get("concern")
        per_concern.append({"concern_id": cid, **coach})
        mode = coach.get("coaching_mode")
        pd = coach.get("practice_direction")
        if pd:
            practices.append(pd)
        if mode in (MODE_CORRECT, MODE_REFINE, MODE_TRANSFER) and pd:
            focus.append(
                {
                    "id": pd.get("practice_id"),
                    "title": pd.get("title"),
                    "description": coach.get("takeaway") or pd.get("goal"),
                    "reason": coach.get("what_to_improve") or pd.get("goal"),
                    "severity": "high" if mode == MODE_CORRECT else "medium",
                    "evidence_source": pd.get("evidence_basis") or [],
                }
            )

    strengths = derive_precision_strengths(
        concern_evaluations=evaluations,
        fused_profile=fused,
        song_profile=song_profile,
    )

    # Priority order: SAFETY → CORRECT → REFINE → TRANSFER → MAINTAIN
    practices.sort(key=lambda p: _priority_rank(str(p.get("mode"))))
    practices = _dedupe_practices(practices)

    # If only strengths and no practices, promote strength-based maintain practices
    if not practices and strengths:
        for s in strengths[:2]:
            practices.append(
                _practice(
                    practice_id=f"STRENGTH_{s['id']}",
                    mode=MODE_MAINTAIN,
                    title=s["title"] + " 유지하기",
                    goal=s["why_keep"],
                    instruction=s["why_keep"],
                    success_cues=["불편감 없이 현재 패턴 유지"],
                    avoid=["확인된 좋은 패턴을 깨는 방향으로 과하게 밀기"],
                    related=[],
                    evidence=s.get("evidence_source") or [],
                )
            )
        practices = _dedupe_practices(practices)

    # Headline / summary
    if any(p.get("mode") == MODE_SAFETY for p in practices):
        headline = "지금은 무리한 연습보다 안전이 우선이에요."
    elif any(p.get("mode") == MODE_CORRECT for p in practices):
        headline = "확인된 제한을 줄이는 연습 방향이 우선이에요."
    elif any(p.get("mode") == MODE_TRANSFER for p in practices):
        headline = "표준 과제에서 잘 되는 패턴을 노래로 옮기는 것이 우선이에요."
    elif strengths:
        headline = "현재 잘 유지되고 있는 발성 패턴을 이어가는 방향이에요."
    else:
        headline = "이번 검사에서 확인된 범위 안에서 안정적인 발성을 유지하세요."

    summary_bits = [s["description"] for s in strengths[:2]]
    if focus:
        summary_bits.append(focus[0]["description"])
    summary = " ".join(summary_bits) if summary_bits else headline

    # User-facing evidence families used in judgments
    evidence_families: list[str] = []
    effort_c = _effort_contrast(fused)
    if effort_c.get("available"):
        evidence_families.append("편한 음과 높은 음의 힘 차이")
    stab = ((_contrasts(fused).get("baseline_vs_high") or {}).get("dimensions") or {}).get(
        "stability"
    ) or {}
    if stab.get("available"):
        evidence_families.append("높은 음의 안정성")
    if any(
        (ev.get("concern_id") or ev.get("concern"))
        in ("TIMBRE_DISSATISFIED", "VOICE_TOO_DARK_MUFFLED", "VOICE_TOO_THIN")
        for ev in evaluations
    ):
        evidence_families.append("기본 음색의 밝기와 중역 존재감")
    if _siren_connected(_profiles(fused)):
        evidence_families.append("중음→고음 연결의 연속성")

    # Legacy improvement_priorities bridge (actionable, no generic observation)
    legacy_priorities: list[dict[str, Any]] = []
    for p in practices[:3]:
        legacy_priorities.append(
            {
                "goal_id": p.get("practice_id"),
                "title": p.get("title"),
                "principle": p.get("instruction"),
                "suggested_focus": list(p.get("success_cues") or [])[:2],
                "safety_note": p.get("safety_note"),
                "mode": p.get("mode"),
                "mode_label": p.get("mode_label"),
                "avoid": p.get("avoid") or [],
                "evidence_source": "COACHING",
            }
        )

    return {
        "coaching_version": COACHING_VERSION,
        "headline": headline,
        "summary": summary,
        "strengths": strengths,
        "focus_areas": focus[:3],
        "practice_directions": practices[:3],
        "per_concern": per_concern,
        "evidence_families": evidence_families[:5],
        "improvement_priorities": legacy_priorities,
        "diagnostic_mode": diagnostic_mode,
    }


def attach_coaching_to_questions(
    questions: list[dict[str, Any]],
    coaching_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    """Attach one-line takeaways only — detailed practice lives in practice_directions."""
    by_id = {
        str(p.get("concern_id")): p for p in (coaching_plan.get("per_concern") or [])
    }
    out = []
    for q in questions:
        cid = str(q.get("concern_id") or "")
        coach = by_id.get(cid) or {}
        nq = dict(q)
        nq["coaching_mode"] = coach.get("coaching_mode")
        takeaway = coach.get("takeaway")
        if takeaway:
            t = str(takeaway)
            nq["takeaway"] = t if t.startswith("→") else f"→ {t}"
        nq["what_is_working"] = coach.get("what_is_working")
        nq["what_to_improve"] = coach.get("what_to_improve")
        # Avoid duplicating detailed practice cards under each Q
        nq.pop("practice_direction", None)
        nq["user_facing_support"] = coach.get("user_facing_support") or []
        nq["user_facing_against"] = coach.get("user_facing_against") or []
        nq["user_facing_missing"] = coach.get("user_facing_missing") or []
        out.append(nq)
    return out


def banned_observation_fallback(text: str) -> bool:
    """True if text is the forbidden generic observation fallback."""
    t = text or ""
    return any(
        bad in t
        for bad in (
            "현재 발성 패턴 관찰하기",
            "같은 조건으로 다시 녹음",
            "반복 녹음으로 변화 추적",
            "비교해서 확인",
        )
    )
