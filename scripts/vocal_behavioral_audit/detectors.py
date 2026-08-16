# -*- coding: utf-8 -*-
"""Audit-only detectors (do not mutate production rules)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Optional

from audio_analyzer.diagnostic.concerns import PAIN_CONCERN_IDS
from audio_analyzer.diagnostic.practice_library import FOCUS_TO_PRACTICE

from scripts.vocal_behavioral_audit.diagnose import normalize_text, prescription_family

ABSTRACT_PATTERNS = (
    "소리 중심을 유지",
    "소리 중심이 유지",
    "연결을 매끄럽게",
    "원하는 느낌에 가깝",
    "표현을 탐색",
    "두 가지 방식",
    "비교해보세요",
    "비교하세요",
)

HOW_MARKERS = (
    "립트릴",
    "빨대",
    "자음",
    "모음",
    "음량",
    "1~2초",
    "2~3회",
    "3~5회",
    "이어 올리",
    "구절",
)

ENGLISH_TOKENS = (
    r"\bpitch\b",
    r"\bphrase\b",
    r"\bglide\b",
    r"\bsustain\b",
    r"\bonset\b",
    r"\bbaseline\b",
    r"\bvariant\b",
)

ANATOMY_PATTERNS = (
    "연구개가",
    "연구개",
    "후두가 올라",
    "후두를",
    "성대를 붙",
    "성대 붙",
    "복압 부족",
    "복압",
    "목 근육 긴장",
    "목근육이 긴장",
)

DISCLAIMER_PATTERNS = (
    "확정하기 어렵다",
    "지표가 제한적",
    "뚜렷한 특징이 없다",
    "하나로 좁히기 어렵다",
)

PLANNER_PATTERNS = (
    "관련 패턴 확인",
    "현재 가장 관련 있는 패턴",
    "방향 탐색",
    "작게 탐색",
)

AGGRESSIVE_PROTOCOL_IDS = {
    "REGISTER_CONNECTION",
    "REGISTER",
    "EFFORT_REDUCTION",
    "EFFORT",
    "HIGH_NOTE_ACCESS",
    "HIGH_NOTE",
}

FOCUS_PROTOCOL_ALLOW = {
    "REGISTER_CONNECTION": {"REGISTER_CONNECTION", "REGISTER", "SOVT"},
    "EFFORT": {"EFFORT", "EFFORT_REDUCTION", "HIGH_NOTE"},
    "STABILITY": {"STABILITY"},
    "PRESENCE": {"PRESENCE", "BRIGHTNESS"},
    "BRIGHTNESS": {"BRIGHTNESS", "TIMBRE_STYLE", "STYLE"},
    "BREATHINESS": {"BREATHINESS", "BREATH"},
    "STYLE": {"TIMBRE_STYLE", "STYLE", "MAINTAIN"},
    "TIMBRE": {"TIMBRE_STYLE", "STYLE", "TIMBRE"},
    "MAINTAIN": {"MAINTAIN", "TIMBRE_STYLE"},
    "SAFETY": {"SAFETY"},
    "CONTACT": {"CONTACT", "PRESENCE"},
    "DYNAMICS": {"DYNAMICS"},
    "HIGH_NOTE": {"HIGH_NOTE_ACCESS", "HIGH_NOTE", "REGISTER_CONNECTION", "EFFORT"},
}


def text_similarity(a: str, b: str) -> float:
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    # token jaccard
    ta, tb = set(na.split()), set(nb.split())
    jac = len(ta & tb) / max(1, len(ta | tb))
    seq = SequenceMatcher(None, na, nb).ratio()
    return max(jac, seq)


def user_facing_blob(case: dict[str, Any]) -> str:
    qa = case.get("qa") or {}
    presc = qa.get("prescription") or {}
    goal = case.get("goal") or {}
    parts = [
        qa.get("question"),
        qa.get("answer"),
        qa.get("what_to_change"),
        presc.get("instruction"),
        presc.get("song_transfer"),
        (presc.get("alternate") or {}).get("instruction") if isinstance(presc.get("alternate"), dict) else None,
        " ".join(presc.get("success_cues") or qa.get("success_cues") or []),
        goal.get("goal_title"),
        goal.get("goal_description"),
        goal.get("why_this_first"),
        case.get("protocol_entry_title"),
        case.get("protocol_instruction"),
    ]
    return "\n".join(str(p) for p in parts if p)


def lint_case(case: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    cid = case.get("concern_id")
    is_safety = cid in PAIN_CONCERN_IDS
    blob = user_facing_blob(case)
    presc = ((case.get("qa") or {}).get("prescription") or {})
    action = str(presc.get("instruction") or (case.get("qa") or {}).get("what_to_change") or "").strip()
    answer = str((case.get("qa") or {}).get("answer") or case.get("answer_summary") or "").strip()
    focus = case.get("primary_focus")

    if not is_safety:
        if not answer:
            findings.append({"severity": "FAIL", "code": "EMPTY_QA", "detail": "empty answer"})
        if not focus:
            findings.append({"severity": "FAIL", "code": "EMPTY_FOCUS", "detail": "empty primary_focus"})
        if not action and not case.get("protocol_instruction"):
            findings.append(
                {"severity": "FAIL", "code": "MISSING_PRESCRIPTION", "detail": "no prescription/protocol action"}
            )
        cues = presc.get("success_cues") or (case.get("qa") or {}).get("success_cues") or []
        if action and not cues:
            findings.append({"severity": "FAIL", "code": "MISSING_SUCCESS_CUES", "detail": "no success cues"})

    if is_safety:
        # Active aggressive coaching while pain
        pid = str(case.get("protocol_id") or "")
        entry = str(case.get("protocol_entry_id") or "") + " " + str(case.get("protocol_instruction") or "")
        if any(x in pid.upper() for x in ("REGISTER", "EFFORT", "HIGH_NOTE")) and "SAFETY" not in pid.upper():
            if action and not any(k in action for k in ("쉬", "중단", "휴식", "피하")):
                findings.append(
                    {
                        "severity": "CRITICAL",
                        "code": "SAFETY_ACTIVE_EXERCISE",
                        "detail": f"protocol={pid} entry={entry[:80]}",
                    }
                )

    # Abstract-only
    if action:
        has_how = any(m in action for m in HOW_MARKERS) and len(action) > 40
        for pat in ABSTRACT_PATTERNS:
            if pat in action and not has_how:
                findings.append(
                    {
                        "severity": "WARN",
                        "code": "ABSTRACT_ACTION",
                        "detail": pat,
                    }
                )
                break
        # standalone abstract
        if any(action.rstrip(".") == p.rstrip(".") or action == p for p in ABSTRACT_PATTERNS):
            findings.append({"severity": "WARN", "code": "ABSTRACT_ACTION", "detail": "standalone"})

    for pat in ENGLISH_TOKENS:
        if re.search(pat, blob, flags=re.I):
            findings.append(
                {"severity": "WARN", "code": "USER_ENGLISH_TOKEN", "detail": pat}
            )

    for pat in ANATOMY_PATTERNS:
        if pat in blob:
            findings.append(
                {"severity": "CRITICAL", "code": "ANATOMICAL_DIAGNOSIS", "detail": pat}
            )

    # Terminal disclaimer occupying answer
    if answer and any(d in answer for d in DISCLAIMER_PATTERNS):
        if len(answer) < 80 or all(d in answer for d in DISCLAIMER_PATTERNS[:1]):
            # soft: if answer is mostly disclaimer
            if not action:
                findings.append(
                    {"severity": "WARN", "code": "TERMINAL_DISCLAIMER", "detail": "disclaimer-dominated"}
                )

    if any(p in blob for p in PLANNER_PATTERNS) and not action:
        findings.append({"severity": "WARN", "code": "PLANNER_COPY", "detail": "planner without action"})

    # Duplicate success cues (exact)
    cues = list(presc.get("success_cues") or (case.get("qa") or {}).get("success_cues") or [])
    normed = [normalize_text(c) for c in cues]
    if len(normed) != len(set(normed)):
        findings.append({"severity": "WARN", "code": "DUPLICATE_SUCCESS_CUE", "detail": str(cues)})

    # Focus / protocol / practice coherence
    findings.extend(check_focus_coherence(case))
    return findings


def check_focus_coherence(case: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    focus = str(case.get("primary_focus") or "").upper()
    protocol_id = str(case.get("protocol_id") or "").upper()
    practice_id = str(case.get("practice_id") or "").upper()
    if not focus:
        return out
    if case.get("concern_id") in PAIN_CONCERN_IDS:
        return out

    allowed = FOCUS_PROTOCOL_ALLOW.get(focus)
    if protocol_id and allowed:
        ok = any(a in protocol_id for a in allowed)
        if not ok and focus == "BRIGHTNESS" and "PRESENCE" in protocol_id and "BRIGHT" not in protocol_id:
            out.append(
                {
                    "severity": "FAIL",
                    "code": "FOCUS_PROTOCOL_MISMATCH",
                    "detail": f"{focus} -> {protocol_id}",
                }
            )
        elif not ok and focus == "REGISTER_CONNECTION" and "TIMBRE_STYLE" in protocol_id:
            out.append(
                {
                    "severity": "FAIL",
                    "code": "FOCUS_PROTOCOL_MISMATCH",
                    "detail": f"{focus} -> {protocol_id}",
                }
            )
        elif not ok and focus == "STABILITY" and "REGISTER" in protocol_id and "STAB" not in protocol_id:
            out.append(
                {
                    "severity": "FAIL",
                    "code": "FOCUS_PROTOCOL_MISMATCH",
                    "detail": f"{focus} -> {protocol_id}",
                }
            )

    expected = FOCUS_TO_PRACTICE.get(focus)
    if expected and practice_id:
        # Style focuses may use STYLE_* practices
        if focus in ("STYLE", "TIMBRE", "BRIGHTNESS"):
            if not (
                practice_id.startswith("STYLE")
                or practice_id == expected.upper()
                or expected.upper() in practice_id
            ):
                # soft warn only if clearly wrong family
                if "REGISTER" in practice_id and focus == "BRIGHTNESS":
                    out.append(
                        {
                            "severity": "FAIL",
                            "code": "FOCUS_PRACTICE_MISMATCH",
                            "detail": f"{focus} practice={practice_id} expected~{expected}",
                        }
                    )
        elif expected.upper() not in practice_id and practice_id not in expected.upper():
            # allow related
            if focus == "REGISTER_CONNECTION" and "REGISTER" not in practice_id and "SOVT" not in practice_id:
                out.append(
                    {
                        "severity": "FAIL",
                        "code": "FOCUS_PRACTICE_MISMATCH",
                        "detail": f"{focus} practice={practice_id} expected={expected}",
                    }
                )
    return out


def check_profile_goal_contradiction(case: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    axes = case.get("canonical_axes") or {}
    focus = str(case.get("primary_focus") or "")
    mode = str((case.get("goal") or {}).get("mode") or "")
    effort = str(axes.get("effort_status") or "")
    if effort in ("HIGH", "MODERATE") and focus in ("STYLE", "TIMBRE", "MAINTAIN") and mode == "STYLE":
        if not axes.get("effort_reliable", True) is False:
            # reliable elevated effort + STYLE-only
            if axes.get("effort_reliable") is not False:
                out.append(
                    {
                        "severity": "CRITICAL",
                        "code": "PROFILE_GOAL_DIRECT_CONTRADICTION",
                        "detail": f"effort={effort} focus={focus} mode={mode}",
                    }
                )
    # Acoustic claim lint via classifier (true unsupported only)
    from scripts.vocal_behavioral_audit.claim_lint import (
        classify_claim_spans,
        evaluate_claim_against_axes,
    )

    blobs = [
        str((case.get("qa") or {}).get("answer") or ""),
        str((case.get("qa") or {}).get("answer_summary") or ""),
        str(((case.get("qa") or {}).get("prescription") or {}).get("instruction") or ""),
        str(case.get("answer_summary") or ""),
    ]
    for blob in blobs:
        for span in classify_claim_spans(blob):
            evaluated = evaluate_claim_against_axes(span, axes)
            cls = evaluated.get("classification")
            if cls == "TRUE_POSITIVE":
                out.append(
                    {
                        "severity": "FAIL",
                        "code": "UNSUPPORTED_ACOUSTIC_CLAIM",
                        "detail": evaluated.get("detail")
                        or f"{evaluated.get('axis')} claimed {evaluated.get('claimed_state')}",
                        "claim_classification": "TRUE_POSITIVE",
                        "claim": evaluated,
                    }
                )
            # False positives / scope are recorded separately by runner, not as FAIL codes
    return out


def audit_score(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Audit-only 7-point score (not product score)."""
    codes = {f["code"] for f in findings}
    sev = {f["severity"] for f in findings}
    score = {
        "coverage": 0 if "EMPTY_QA" in codes or "MISSING_PRESCRIPTION" in codes else 1,
        "canonical_invariant": 0 if "CANONICAL_MUTATION_BY_CONCERN" in codes else 1,
        "actionable": 0 if "ABSTRACT_ACTION" in codes or "MISSING_PRESCRIPTION" in codes else 1,
        "coherent": 0
        if any(
            c in codes
            for c in (
                "FOCUS_PROTOCOL_MISMATCH",
                "FOCUS_PRACTICE_MISMATCH",
                "PROFILE_GOAL_DIRECT_CONTRADICTION",
            )
        )
        else 1,
        "non_generic": 0 if "WRONG_GENERIC_COLLAPSE" in codes or "GENERIC_COLLAPSE" in codes else 1,
        "safe": 0 if "SAFETY_ACTIVE_EXERCISE" in codes or "ANATOMICAL_DIAGNOSIS" in codes else 1,
        "language": 0 if "USER_ENGLISH_TOKEN" in codes else 1,
    }
    total = sum(score.values())
    status = "PASS"
    if "CRITICAL" in sev:
        status = "FAIL"
    elif any(f["severity"] == "FAIL" for f in findings):
        status = "FAIL"
    elif any(f["severity"] == "WARN" for f in findings):
        status = "WARN"
    return {"dims": score, "total": total, "max": 7, "status": status}


def _success_blob(case: dict[str, Any]) -> str:
    qa = case.get("qa") or {}
    presc = qa.get("prescription") or {}
    cues = qa.get("success_cues") or presc.get("success_cues") or []
    if isinstance(cues, list):
        return normalize_text(" ".join(str(c) for c in cues))
    return normalize_text(str(cues or ""))


def _action_blob(case: dict[str, Any]) -> str:
    presc = (case.get("qa") or {}).get("prescription") or {}
    return normalize_text(
        str(presc.get("instruction") or (case.get("qa") or {}).get("what_to_change") or "")
    )


def _question_type(case: dict[str, Any]) -> str:
    return str(case.get("question_type") or "")


def _evidence_signature(case: dict[str, Any]) -> str:
    axes = case.get("canonical_axes") or {}
    return "|".join(
        [
            str(axes.get("register_connection") or axes.get("register") or ""),
            str(axes.get("effort_status") or ""),
            str(axes.get("stability") or ""),
            str(axes.get("breathiness") or ""),
            str(axes.get("presence") or ""),
        ]
    )


def generic_collapse_pairs(
    cases: list[dict[str, Any]],
    *,
    threshold: float = 0.88,
) -> list[dict[str, Any]]:
    """Compare different concerns on same audio; classify collapse kinds."""
    by_audio: dict[str, list[dict[str, Any]]] = {}
    for c in cases:
        cid = str(c.get("concern_id") or "")
        # Safety concerns intentionally share SAFETY_STOP — exclude from collapse matrix
        if cid in PAIN_CONCERN_IDS or str(c.get("primary_focus") or "") == "SAFETY":
            continue
        by_audio.setdefault(str(c.get("audio_id")), []).append(c)

    rows: list[dict[str, Any]] = []
    for audio_id, items in by_audio.items():
        n = len(items)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = items[i], items[j]
                if a.get("concern_id") == b.get("concern_id"):
                    continue
                ta = user_facing_blob(a)
                tb = user_facing_blob(b)
                pa = _action_blob(a)
                pb = _action_blob(b)
                sim = text_similarity(pa or ta, pb or tb)
                if sim < threshold:
                    continue
                same_focus = a.get("primary_focus") == b.get("primary_focus")
                same_proto = a.get("protocol_id") == b.get("protocol_id")
                same_qtype = _question_type(a) == _question_type(b) and bool(_question_type(a))
                same_cat = (
                    str((a.get("concern_id") or "")).split("_")[0]
                    == str((b.get("concern_id") or "")).split("_")[0]
                )
                same_evidence = _evidence_signature(a) == _evidence_signature(b)
                same_action = bool(pa) and pa == pb
                sa, sb = _success_blob(a), _success_blob(b)
                same_success = bool(sa) and sa == sb
                same_family = prescription_family(a) == prescription_family(b)

                if not same_focus:
                    # Wrong collapse = different focus with essentially identical coaching copy
                    if same_action or sim >= 0.97:
                        classification = "WRONG_GENERIC_COLLAPSE"
                    else:
                        continue
                elif same_focus and same_proto and same_action and same_success:
                    classification = "OVER_SHARED_PRESCRIPTION"
                elif same_focus and same_proto:
                    classification = "EXPECTED_SHARED_PROTOCOL"
                else:
                    if same_action or sim >= 0.97:
                        classification = "WRONG_GENERIC_COLLAPSE"
                    else:
                        continue

                rows.append(
                    {
                        "audio": audio_id,
                        "concern_a": a.get("concern_id"),
                        "concern_b": b.get("concern_id"),
                        "focus_a": a.get("primary_focus"),
                        "focus_b": b.get("primary_focus"),
                        "protocol_a": a.get("protocol_id"),
                        "protocol_b": b.get("protocol_id"),
                        "similarity": round(sim, 4),
                        "classification": classification,
                        "same_focus": same_focus,
                        "same_protocol": same_proto,
                        "same_question_type": same_qtype,
                        "same_category": same_cat,
                        "same_evidence_signature": same_evidence,
                        "same_action": same_action,
                        "same_success": same_success,
                        "same_family": same_family,
                        "family_a": prescription_family(a),
                        "family_b": prescription_family(b),
                    }
                )
    return rows
