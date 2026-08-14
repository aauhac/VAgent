"""Song-evidence functional hypothesis + always-actionable guidance (Precision Guidance v2).

CONTROLLED TASK SKIPPED ≠ NO ANSWER
USER_REPORTED ≠ AUDIO_OBSERVED
No anatomical / 복압 / CT-TA claims.
"""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.diagnostic.practice_library import practice_for_focus
from audio_analyzer.diagnostic.song_evidence import get_canonical_snapshot

GUIDANCE_CONTROLLED = "CONTROLLED_CONFIRMED"
GUIDANCE_SONG_DIRECT = "SONG_DIRECT"
GUIDANCE_SONG_COMPOSITE = "SONG_COMPOSITE"
GUIDANCE_SAFE_GENERAL = "SAFE_GENERAL_GUIDANCE"
GUIDANCE_SAFETY = "SAFETY_ONLY"

CONCERN_GUIDANCE_VERSION = "precision-concern-guidance-v1.0"

_BAD_FINAL_SUBSTRINGS = (
    "연습 방향을 충분히 좁히기 어려워요",
    "고음 힘 패턴을 충분히 확정하기 어려워요",
    "현재 노래에서 확인된 범위까지만 안내해요",
)

_BANNED_USER_SUBSTRINGS = (
    "복압이 부족",
    "횡격막이 약",
    "목 근육",
    "후두가 올라",
    "성대가 너무 붙",
    "성대가 벌어",
    "중음역이 약",
    "중음역대가 약",
    "TA",
    "CT",
    "LCA",
)


def _reg_bucket(snap: dict[str, Any]) -> str:
    reg = snap.get("register") or {}
    st = str(reg.get("status") or "").upper()
    if st in ("DISRUPTED", "UNSTABLE", "TRANSITION_EVENTS"):
        return "DISRUPTED"
    if st in ("PARTIAL", "INSUFFICIENT", "MIXED"):
        return "PARTIAL"
    if st in ("CONNECTED", "SMOOTH", "STABLE", "CONTINUOUS", "STABLE_LIKE"):
        return "CONNECTED"
    # canonical_register on vocal style / type
    return "UNKNOWN"


def _effort_bucket(snap: dict[str, Any]) -> str:
    return str((snap.get("effort") or {}).get("level") or "UNKNOWN").upper()


def _contact_bucket(snap: dict[str, Any]) -> str:
    return str((snap.get("contact") or {}).get("status") or "UNKNOWN").upper()


def _presence_low(snap: dict[str, Any]) -> bool:
    timbre = snap.get("timbre") or {}
    p = timbre.get("presence")
    if p is None:
        return False
    try:
        return float(p) <= 0.42
    except (TypeError, ValueError):
        return False


def _stability_ok(snap: dict[str, Any]) -> Optional[bool]:
    st = str((snap.get("stability") or {}).get("status") or "").upper()
    if not st or st == "UNKNOWN":
        return None
    if st in ("STABLE", "LOW", "NORMAL", "OK_PROXY"):
        return True
    if st in ("UNSTABLE", "HIGH", "IRREGULAR"):
        return False
    return None


def _scope_note_for_skip(skipped: set[str], concern_id: str) -> Optional[str]:
    if "siren" in skipped and concern_id in (
        "HIGH_NOTE_CANNOT_REACH",
        "HIGH_NOTE_FLIPS",
        "REGISTER_CONNECTION_DIFFICULT",
    ):
        return "추가 성구 과제를 진행하지 않아 이 해석은 현재 노래 기준입니다."
    if "high_note_sustain_a" in skipped and concern_id in (
        "HIGH_NOTE_TOO_EFFORTFUL",
        "HIGH_NOTE_CANNOT_REACH",
        "HIGH_NOTE_UNSTABLE",
        "HIGH_NOTE_THINS",
    ):
        return "추가 고음 과제를 진행하지 않아 이 해석은 현재 노래 기준입니다."
    return None


def _attach_practice(hyp: dict[str, Any]) -> dict[str, Any]:
    focus = str(hyp.get("primary_focus") or "REGISTER_CONNECTION")
    practice = practice_for_focus(focus)
    hyp["practice"] = practice
    hyp["practice_id"] = practice.get("practice_id")
    return hyp


def build_functional_hypothesis(
    concern_id: str,
    *,
    song_profile: dict[str, Any],
    evaluation: Optional[dict[str, Any]] = None,
    user_skipped_tasks: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Build actionable guidance from canonical song evidence (never invent anatomy)."""
    snap = get_canonical_snapshot(song_profile)
    skipped = set(user_skipped_tasks or [])
    ev = evaluation or {}
    effort = _effort_bucket(snap)
    contact = _contact_bucket(snap)
    register = _reg_bucket(snap)
    presence_low = _presence_low(snap)
    stab = _stability_ok(snap)
    breath = str((snap.get("breathiness") or {}).get("level") or "UNKNOWN").upper()

    secondary: list[str] = []
    evidence: list[str] = []
    contra: list[str] = []
    scope = _scope_note_for_skip(skipped, concern_id)

    # --- SAFETY ---
    if str(ev.get("status") or "").upper() == "SAFETY_ONLY" or concern_id.startswith("PAIN"):
        hyp = {
            "concern_id": concern_id,
            "guidance_level": GUIDANCE_SAFETY,
            "primary_focus": "SAFETY",
            "secondary_factors": [],
            "interpretation": (
                "통증이나 지속적인 불편감은 음향 분석만으로 원인을 판단할 수 없어요. "
                "지금은 강한 고음·큰 소리 반복보다 휴식이 우선이에요."
            ),
            "evidence": ["safety"],
            "contra_evidence": [],
            "confidence_label": "high",
            "causal_certainty": "SAFETY_GATE",
            "scope_note": None,
        }
        return _attach_practice(hyp)

    # Controlled already confirmed — keep tone, still ensure practice
    st = str(ev.get("status") or "").upper()
    if st == "CONFIRMED" and ev.get("answer_hint") and not skipped:
        hyp = {
            "concern_id": concern_id,
            "guidance_level": GUIDANCE_CONTROLLED,
            "primary_focus": (ev.get("candidate_causes") or ["EFFORT"])[0]
            if "EFFORT" in str(ev.get("candidate_causes"))
            else "REGISTER_CONNECTION"
            if "REGISTER" in str(ev.get("candidate_causes"))
            else "EFFORT",
            "secondary_factors": [],
            "interpretation": str(ev.get("answer_hint")),
            "evidence": list(ev.get("support") or []),
            "contra_evidence": list(ev.get("against") or []),
            "confidence_label": ev.get("confidence_label") or "medium",
            "causal_certainty": "CONTROLLED_CONFIRMED",
            "scope_note": None,
        }
        # Map cause ids to focus
        causes = ev.get("candidate_causes") or []
        if any("REGISTER" in str(c) for c in causes):
            hyp["primary_focus"] = "REGISTER_CONNECTION"
        elif any("EFFORT" in str(c) for c in causes):
            hyp["primary_focus"] = "EFFORT"
        elif any("STABILITY" in str(c) for c in causes):
            hyp["primary_focus"] = "STABILITY"
        return _attach_practice(hyp)

    # ========== High-note cannot reach ==========
    if concern_id == "HIGH_NOTE_CANNOT_REACH":
        if register == "DISRUPTED":
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_DIRECT,
                "primary_focus": "REGISTER_CONNECTION",
                "secondary_factors": [],
                "interpretation": (
                    "이번 노래에서는 음역이 올라갈 때 발성 연결이 급격하게 달라지는 구간이 보여요. "
                    "그래서 높은 음 자체의 부족이라기보다, 중간 음역에서 높은 음으로 넘어가는 과정이 "
                    "현재 고음 접근을 어렵게 만드는 쪽으로 보입니다."
                ),
                "evidence": ["song_register_disrupted"],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            if effort in ("HIGH", "MODERATE"):
                hyp["secondary_factors"] = ["EFFORT"]
            return _attach_practice(hyp)

        if register == "PARTIAL" and (effort in ("HIGH", "MODERATE") or contact == "FIRM"):
            bits = ["음역이 올라갈 때 연결이 충분히 이어지지 않는 구간이 있고"]
            if effort in ("HIGH", "MODERATE"):
                bits.append("힘 사용")
                evidence.append("song_effort_elevated")
                secondary.append("EFFORT")
            if contact == "FIRM":
                bits.append("단단한 접촉 특성")
                evidence.append("song_contact_firm")
                secondary.append("CONTACT")
            mid = "과 ".join(bits) if len(bits) > 1 else bits[0]
            # Fix awkward join
            if len(secondary) >= 1:
                factors = []
                if "EFFORT" in secondary:
                    factors.append("힘 사용")
                if "CONTACT" in secondary:
                    factors.append("단단한 접촉 특성")
                factor_txt = "과 ".join(factors) if factors else "관련 특성"
                interpretation = (
                    f"이번 노래에서는 높은 음으로 이동할 때 연결이 충분히 이어지지 않는 구간이 있고, "
                    f"{factor_txt}도 함께 나타나요. "
                    "높은 음을 같은 무게와 힘으로 유지하려는 방식이 "
                    "고음 접근을 어렵게 만드는 쪽으로 보여요."
                )
            else:
                interpretation = (
                    "이번 노래에서는 높은 음으로 이동할 때 연결이 충분히 이어지지 않는 구간이 보여요."
                )
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_COMPOSITE,
                "primary_focus": "REGISTER_CONNECTION",
                "secondary_factors": secondary[:2],
                "interpretation": interpretation,
                "evidence": ["song_register_partial", *evidence],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            return _attach_practice(hyp)

        if register == "PARTIAL":
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_DIRECT,
                "primary_focus": "REGISTER_CONNECTION",
                "secondary_factors": [],
                "interpretation": (
                    "이번 노래에서는 중음에서 높은 음으로 넘어가는 연결이 "
                    "일부 구간에서만 안정적으로 이어져요. "
                    "고음 접근이 어려운 느낌은 이 전환 구간의 연결과 관련될 가능성이 있어 보여요."
                ),
                "evidence": ["song_register_partial"],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            return _attach_practice(hyp)

        if effort in ("HIGH", "MODERATE"):
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_DIRECT,
                "primary_focus": "EFFORT",
                "secondary_factors": ["CONTACT"] if contact == "FIRM" else [],
                "interpretation": (
                    "이번 노래에서는 성구 전환을 단정하기는 어렵지만, "
                    "일부 구간에서 힘 사용이 커지는 경향이 보여요. "
                    "높은 음에 도달하려 할 때 강도를 먼저 키우는 방식이 "
                    "접근을 어렵게 만드는 쪽으로 보일 수 있어요."
                ),
                "evidence": ["song_effort_elevated"],
                "contra_evidence": [],
                "confidence_label": "low",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            return _attach_practice(hyp)

        hyp = {
            "concern_id": concern_id,
            "guidance_level": GUIDANCE_SAFE_GENERAL,
            "primary_focus": "REGISTER_CONNECTION",
            "secondary_factors": [],
            "interpretation": (
                "이번 노래만으로 고음이 어려운 원인을 하나로 좁히기는 어려워요. "
                "다만 고음을 연습할 때는 음량을 먼저 키우지 않고, "
                "편안한 중음에서 높은 음까지 작은 강도로 연결하는 연습부터 시작하는 것이 좋아요."
            ),
            "evidence": [],
            "contra_evidence": [],
            "confidence_label": "low",
            "causal_certainty": "GUIDANCE_ONLY",
            "scope_note": scope,
        }
        return _attach_practice(hyp)

    # ========== High-note too effortful ==========
    if concern_id == "HIGH_NOTE_TOO_EFFORTFUL":
        if effort in ("HIGH", "MODERATE"):
            contact_bit = ""
            secondary = []
            if contact == "FIRM":
                contact_bit = "단단한 접촉 특성도 함께 보여요. "
                secondary = ["CONTACT"]
                evidence.append("song_contact_firm")
            interpretation = (
                "추가 고음 과제를 하지 않아 고음에서 힘이 얼마나 더 증가하는지는 비교하지 못했어요. "
                if "high_note_sustain_a" in skipped
                else ""
            )
            interpretation += (
                f"다만 이번 노래 자체에서는 힘 사용이 큰 구간이 나타나고, {contact_bit}"
                if contact_bit
                else "다만 이번 노래 자체에서는 힘 사용이 큰 구간이 나타나요. "
            )
            interpretation += (
                "높은 음을 낼 때 소리를 더 강하게 유지하는 방식이 부담을 키우는 쪽으로 보입니다."
            )
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_COMPOSITE if secondary else GUIDANCE_SONG_DIRECT,
                "primary_focus": "EFFORT",
                "secondary_factors": secondary,
                "interpretation": interpretation,
                "evidence": ["song_effort_elevated", *evidence],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            return _attach_practice(hyp)

        if effort == "LOW":
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SAFE_GENERAL
                if register not in ("DISRUPTED", "PARTIAL")
                else GUIDANCE_SONG_COMPOSITE,
                "primary_focus": "REGISTER_CONNECTION"
                if register in ("DISRUPTED", "PARTIAL")
                else "MAINTAIN",
                "secondary_factors": [],
                "interpretation": (
                    "이번 노래에서는 과도한 힘 증가가 주된 제한으로 강하게 보이지는 않았어요. "
                    "따라서 고음을 더 편하게 만들 때 힘을 빼는 것만 반복하기보다, "
                    "작은 강도로 성구 연결이 유지되는지부터 확인하는 방향이 더 적합해 보여요."
                ),
                "evidence": ["song_effort_low"],
                "contra_evidence": ["song_effort_low"],
                "confidence_label": "medium",
                "causal_certainty": "CONTRA_TO_CONCERN",
                "scope_note": scope,
            }
            return _attach_practice(hyp)

        hyp = {
            "concern_id": concern_id,
            "guidance_level": GUIDANCE_SAFE_GENERAL,
            "primary_focus": "EFFORT",
            "secondary_factors": [],
            "interpretation": (
                "이번 노래만으로 고음에서 힘이 얼마나 더 커지는지 하나로 좁히기는 어려워요. "
                "다만 연습할 때는 음량을 먼저 키우지 않고, "
                "조금 높은 음을 작은 강도로 짧게 유지하는 것부터 시작하는 것이 좋아요."
            ),
            "evidence": [],
            "contra_evidence": [],
            "confidence_label": "low",
            "causal_certainty": "GUIDANCE_ONLY",
            "scope_note": scope,
        }
        return _attach_practice(hyp)

    # ========== Flips / register ==========
    if concern_id in ("HIGH_NOTE_FLIPS", "REGISTER_CONNECTION_DIFFICULT"):
        if register == "DISRUPTED":
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_DIRECT,
                "primary_focus": "REGISTER_CONNECTION",
                "secondary_factors": ["PRESENCE"] if presence_low else [],
                "interpretation": (
                    "이번 노래에서는 음역이 올라가는 구간에서 발성 연결이 갑자기 달라지는 패턴이 보여요. "
                    "느끼신 '뒤집힘'은 현재 분석에서 확인된 성구 연결 변화와 어느 정도 일치합니다."
                ),
                "evidence": ["song_register_disrupted"],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            if presence_low:
                hyp["interpretation"] += (
                    " 중역 존재감도 낮아지는 편이라, 전환 구간에서 음색이나 소리 존재감이 "
                    "함께 달라질 수 있어 보여요."
                )
            return _attach_practice(hyp)

        if register == "PARTIAL":
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_DIRECT,
                "primary_focus": "REGISTER_CONNECTION",
                "secondary_factors": ["PRESENCE"] if presence_low else [],
                "interpretation": (
                    "이번 노래에서는 중음에서 높은 음으로 넘어가는 연결이 "
                    "일부 구간에서만 안정적으로 이어져요. "
                    "따라서 뒤집힘은 전환 구간의 연결이 아직 일정하지 않은 점과 "
                    "관련되어 있을 가능성이 있어 보여요."
                ),
                "evidence": ["song_register_partial"],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            if presence_low:
                hyp["interpretation"] += (
                    " 중역 존재감도 낮은 편이라 전환에서 소리 존재감이 함께 달라질 수 있어 보여요."
                )
            return _attach_practice(hyp)

        # Presence alone must NOT be primary cause
        hyp = {
            "concern_id": concern_id,
            "guidance_level": GUIDANCE_SAFE_GENERAL,
            "primary_focus": "REGISTER_CONNECTION",
            "secondary_factors": [],
            "interpretation": (
                "이번 노래만으로 뒤집힘의 원인을 하나로 좁히기는 어려워요. "
                "다만 지금은 작은 강도의 립트릴이나 빨대 발성으로 "
                "중음에서 높은 음까지 끊기지 않게 연결하는 연습부터 시작하는 것이 좋아요."
            ),
            "evidence": ["presence_supporting_only"] if presence_low else [],
            "contra_evidence": [],
            "confidence_label": "low",
            "causal_certainty": "GUIDANCE_ONLY",
            "scope_note": scope,
        }
        return _attach_practice(hyp)

    # ========== Unstable ==========
    if concern_id == "HIGH_NOTE_UNSTABLE":
        if stab is False:
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_DIRECT,
                "primary_focus": "STABILITY",
                "secondary_factors": [],
                "interpretation": (
                    "이번 노래에서는 발성 안정성이 떨어지는 구간이 관찰됐어요. "
                    "짧은 구간을 안정적으로 유지한 뒤 범위를 넓히는 방향이 좋아요."
                ),
                "evidence": ["song_stability_reduced"],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            return _attach_practice(hyp)
        hyp = {
            "concern_id": concern_id,
            "guidance_level": GUIDANCE_SAFE_GENERAL,
            "primary_focus": "STABILITY",
            "secondary_factors": [],
            "interpretation": (
                "이번 노래만으로 고음 흔들림의 원인을 확정하기는 어려워요. "
                "다만 짧은 안정 구간을 유지한 뒤 한 음씩 위로 옮기는 연습부터 시작하는 것이 좋아요."
            ),
            "evidence": [],
            "contra_evidence": ["song_stability_ok"] if stab else [],
            "confidence_label": "low",
            "causal_certainty": "GUIDANCE_ONLY",
            "scope_note": scope,
        }
        return _attach_practice(hyp)

    # ========== Throat / fatigue effort ==========
    if concern_id in ("THROAT_EFFORT", "LOUD_VOICE_DIFFICULT", "VOCAL_FATIGUE", "AFTER_SINGING_FATIGUE"):
        if effort in ("HIGH", "MODERATE") or contact == "FIRM":
            parts = []
            if effort in ("HIGH", "MODERATE"):
                parts.append("힘 사용")
            if contact == "FIRM":
                parts.append("단단한 접촉 특성")
            joined = "과 ".join(parts) if parts else "힘 관련 특성"
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_COMPOSITE if len(parts) >= 2 else GUIDANCE_SONG_DIRECT,
                "primary_focus": "EFFORT",
                "secondary_factors": ["CONTACT"] if contact == "FIRM" and "힘" in joined else [],
                "interpretation": (
                    f"이번 노래에서는 {joined}이 함께 나타나는 구간이 보여요. "
                    "작은 강도로 짧게 유지하며 음량을 고정하는 연습부터 시작하는 것이 좋아요."
                ),
                "evidence": [f"song_effort_{effort}", f"song_contact_{contact}"],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            return _attach_practice(hyp)
        hyp = {
            "concern_id": concern_id,
            "guidance_level": GUIDANCE_SAFE_GENERAL,
            "primary_focus": "MAINTAIN" if effort == "LOW" else "EFFORT",
            "secondary_factors": [],
            "interpretation": (
                "체감상 힘을 느끼셨지만, 이번 노래에서는 과도한 힘 증가가 "
                "주된 제한으로 강하게 보이지는 않았어요. "
                "현재 편안한 패턴을 유지하며 범위를 천천히 넓히는 것이 좋아요."
                if effort == "LOW"
                else (
                    "이번 노래만으로 힘 관련 원인을 하나로 좁히기는 어려워요. "
                    "다만 작은 강도로 짧게 유지하는 연습부터 시작하는 것이 좋아요."
                )
            ),
            "evidence": ["song_effort_low"] if effort == "LOW" else [],
            "contra_evidence": ["song_effort_low"] if effort == "LOW" else [],
            "confidence_label": "medium" if effort == "LOW" else "low",
            "causal_certainty": "CONTRA_TO_CONCERN" if effort == "LOW" else "GUIDANCE_ONLY",
            "scope_note": scope,
        }
        return _attach_practice(hyp)

    # ========== Thin / muffled / breathy / timbre ==========
    if concern_id in (
        "VOICE_TOO_THIN",
        "HIGH_NOTE_THINS",
        "VOICE_TOO_DARK_MUFFLED",
        "VOICE_TOO_BREATHY",
        "VOICE_TOO_SHARP",
        "TIMBRE_DISSATISFIED",
        "VOICE_ROUGH",
        "TIMBRE_CHANGES_HIGH",
        "VOICE_TOO_NASAL_PERCEPT",
    ):
        timbre = snap.get("timbre") or {}
        if concern_id in ("VOICE_TOO_THIN", "HIGH_NOTE_THINS"):
            if presence_low or contact == "LIGHT" or breath == "HIGH":
                bits = []
                if breath == "HIGH":
                    bits.append("숨 섞임")
                if presence_low:
                    bits.append("낮은 중역 존재감")
                if contact == "LIGHT":
                    bits.append("가벼운 접촉감")
                if presence_low and contact == "LIGHT" and breath != "HIGH":
                    interpretation = (
                        "숨이 많이 섞여서라기보다 가벼운 음질과 낮은 중역 존재감이 "
                        "얇은 인상에 더 관련된 것으로 보여요."
                    )
                else:
                    interpretation = (
                        "이번 노래에서는 "
                        + "·".join(bits)
                        + " 특성이 함께 보여, 얇게 들리는 인상과 관련될 가능성이 있어 보여요."
                    )
                hyp = {
                    "concern_id": concern_id,
                    "guidance_level": GUIDANCE_SONG_COMPOSITE,
                    "primary_focus": "PRESENCE",
                    "secondary_factors": ["BREATHINESS"] if breath == "HIGH" else [],
                    "interpretation": interpretation,
                    "evidence": ["song_timbre"],
                    "contra_evidence": [],
                    "confidence_label": "medium",
                    "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                    "scope_note": scope,
                }
                return _attach_practice(hyp)
        if concern_id == "VOICE_TOO_DARK_MUFFLED" and timbre.get("available"):
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_DIRECT,
                "primary_focus": "TIMBRE",
                "secondary_factors": [],
                "interpretation": (
                    "이번 노래에서는 밝기·중역 존재감 쪽에서 "
                    "다소 어두운·낮은 존재감 경향이 관찰됐어요. "
                    "음색은 좋고 나쁨이 아니라 관찰된 특징으로 설명합니다."
                ),
                "evidence": ["song_timbre"],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "DESCRIPTIVE",
                "scope_note": scope,
            }
            return _attach_practice(hyp)
        if concern_id == "TIMBRE_DISSATISFIED":
            feats = list(snap.get("key_features") or [])[:3]
            feat_txt = ", ".join(feats) if feats else "확인된 음색 특징"
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_DIRECT if feats else GUIDANCE_SAFE_GENERAL,
                "primary_focus": "TIMBRE",
                "secondary_factors": [],
                "interpretation": (
                    f"이번 노래에서 관찰된 음색 쪽 특징은 다음과 같아요: {feat_txt}. "
                    "음색은 스타일 목표가 달라 좋고 나쁨으로 평가하지 않아요."
                ),
                "evidence": ["song_timbre_descriptive"],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "DESCRIPTIVE",
                "scope_note": scope,
            }
            return _attach_practice(hyp)

        hyp = {
            "concern_id": concern_id,
            "guidance_level": GUIDANCE_SAFE_GENERAL,
            "primary_focus": "TIMBRE",
            "secondary_factors": [],
            "interpretation": (
                "이번 노래만으로 음색 관련 원인을 하나로 좁히기는 어려워요. "
                "다만 편안한 강도에서 짧은 지속음을 유지하며 "
                "소리를 과하게 밀지 않는 연습부터 시작하는 것이 좋아요."
            ),
            "evidence": [],
            "contra_evidence": [],
            "confidence_label": "low",
            "causal_certainty": "GUIDANCE_ONLY",
            "scope_note": scope,
        }
        return _attach_practice(hyp)

    # ========== Default ==========
    hyp = {
        "concern_id": concern_id,
        "guidance_level": GUIDANCE_SAFE_GENERAL,
        "primary_focus": "REGISTER_CONNECTION",
        "secondary_factors": [],
        "interpretation": (
            "이번 노래만으로 원인을 하나로 좁히기는 어려워요. "
            "다만 지금은 작은 강도로 짧게 유지하며 "
            "불편감 없이 연결을 만드는 연습부터 시작하는 것이 좋아요."
        ),
        "evidence": [],
        "contra_evidence": [],
        "confidence_label": "low",
        "causal_certainty": "GUIDANCE_ONLY",
        "scope_note": scope,
    }
    return _attach_practice(hyp)


def compose_user_answer(hyp: dict[str, Any]) -> str:
    """Primary answer: interpretation (+ optional practice cue). Never end on bad fallback alone."""
    text = str(hyp.get("interpretation") or "").strip()
    practice = hyp.get("practice") or {}
    if practice.get("instruction") and hyp.get("guidance_level") != GUIDANCE_SAFETY:
        # Append actionable direction (second beat)
        title = practice.get("title") or "연습"
        tip = practice.get("instruction")
        text = f"{text}\n\n→ 지금은 {title}: {tip}"
        avoid = practice.get("avoid") or []
        if avoid:
            first = str(avoid[0]).rstrip(".。")
            particle = "는" if first.endswith(("기", "다", "음")) else "은"
            text += f" {first}{particle} 피하세요."
    scope = hyp.get("scope_note")
    if scope:
        text = f"{text}\n\n({scope})"
    # Scrub banned
    for bad in _BANNED_USER_SUBSTRINGS:
        if bad in text:
            text = text.replace(bad, "")
    return text.strip()


def ensure_actionable_guidance(
    evaluation: dict[str, Any],
    *,
    song_profile: dict[str, Any],
    user_skipped_tasks: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Enrich concern evaluation so skip never leaves a useless final answer."""
    out = dict(evaluation or {})
    cid = str(out.get("concern_id") or out.get("concern") or "")
    if not cid:
        return out

    status = str(out.get("status") or "").upper()
    if status == "SAFETY_ONLY":
        hyp = build_functional_hypothesis(
            cid, song_profile=song_profile, evaluation=out, user_skipped_tasks=user_skipped_tasks
        )
        out["guidance_level"] = GUIDANCE_SAFETY
        out["primary_focus"] = "SAFETY"
        out["functional_hypothesis"] = hyp
        out["answer_hint"] = compose_user_answer(hyp)
        out["practice"] = hyp.get("practice")
        return out

    skipped = set(user_skipped_tasks or [])
    # Preserve skip provenance without terminating reasoning
    if out.get("unresolved_reason") == "USER_SKIPPED_RELEVANT_TASK":
        out["controlled_confirmation"] = "NOT_AVAILABLE_USER_SKIPPED"
        # Do not keep skip-only answer as primary
        hint = str(out.get("answer_hint") or "")
        if any(b in hint for b in _BAD_FINAL_SUBSTRINGS) or "건너뛰어" in hint:
            out["answer_hint"] = None

    hyp = build_functional_hypothesis(
        cid,
        song_profile=song_profile,
        evaluation=out,
        user_skipped_tasks=skipped,
    )

    # If controlled CONFIRMED already had a strong answer, prefer it but attach practice
    if status == "CONFIRMED" and out.get("answer_hint") and not skipped:
        out["guidance_level"] = GUIDANCE_CONTROLLED
        out["primary_focus"] = hyp.get("primary_focus")
        out["practice"] = hyp.get("practice")
        out["functional_hypothesis"] = hyp
        # Ensure practice appended if takeaway-only
        if "→" not in str(out.get("answer_hint")):
            out["answer_hint"] = compose_user_answer(
                {**hyp, "interpretation": out["answer_hint"]}
            )
        return out

    out["guidance_level"] = hyp["guidance_level"]
    out["primary_focus"] = hyp.get("primary_focus")
    out["secondary_factors"] = hyp.get("secondary_factors") or []
    out["functional_hypothesis"] = hyp
    out["practice"] = hyp.get("practice")
    out["answer_hint"] = compose_user_answer(hyp)
    out["interpretation"] = hyp.get("interpretation")
    out["song_evidence_used"] = list(
        dict.fromkeys([*(out.get("song_evidence_used") or []), *(hyp.get("evidence") or [])])
    )
    # Soften status for song guidance paths without claiming controlled confirmation
    if status in ("UNRESOLVED", "") and hyp["guidance_level"] in (
        GUIDANCE_SONG_DIRECT,
        GUIDANCE_SONG_COMPOSITE,
    ):
        out["status"] = "PARTIALLY_SUPPORTED"
        out["evidence_level"] = "SONG_SUPPORTED"
    elif status in ("UNRESOLVED", "") and hyp["guidance_level"] == GUIDANCE_SAFE_GENERAL:
        out["status"] = "UNRESOLVED"
        out["evidence_level"] = "INSUFFICIENT"
    if skipped:
        out["controlled_confirmation"] = out.get("controlled_confirmation") or (
            "NOT_AVAILABLE_USER_SKIPPED"
        )
    return out


def assert_no_banned_claims(text: str) -> bool:
    return not any(b in (text or "") for b in _BANNED_USER_SUBSTRINGS)
