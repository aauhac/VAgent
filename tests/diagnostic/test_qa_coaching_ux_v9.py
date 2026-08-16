# -*- coding: utf-8 -*-
"""VAgent Coaching UX Polish v9 — direct action, Korean, success dedup."""

from __future__ import annotations

from audio_analyzer.diagnostic.coaching_protocol import build_coaching_protocol
from audio_analyzer.diagnostic.goal_planner import STYLE_TARGET_LABELS, _goal_copy, _why_first
from audio_analyzer.diagnostic.qa_coaching_depth import (
    ABSTRACT_STANDALONE,
    attach_prescription_fields,
    build_perceptual_depth,
    dedupe_success_cues,
    is_abstract_only,
    koreanize_user_copy,
)
from audio_analyzer.diagnostic.report_versions import QA_GUIDANCE_VERSION, REPORT_LOGIC_VERSION


def _snap():
    return {
        "effort": {"level": "LOW", "available": True, "reliable": True},
        "breathiness": {"level": "LOW"},
        "register": {"status": "PARTIAL"},
        "stability": {"status": "STABLE"},
        "contact": {"status": "FIRM"},
        "timbre": {"presence": 0.72, "brightness": 0.35},
    }


def _user_blob(*parts: object) -> str:
    return " ".join(str(p) for p in parts)


def test_versions_v9():
    assert QA_GUIDANCE_VERSION == "precision-qa-coaching-ux-v9"
    assert REPORT_LOGIC_VERSION == "precision-report-v10"


def test_normal_global_protocol_has_no_ab_labels():
    proto = build_coaching_protocol(
        "STYLE",
        snap=_snap(),
        target_timbre={"id": "BRIGHT_CLEAR", "type": "TIMBRE", "label": "밝고 선명하게"},
    )
    entry = proto.get("entry_step") or proto["steps"][0]
    user = _user_blob(
        entry.get("title"),
        entry.get("instruction"),
        entry.get("repetitions"),
        proto.get("if_better"),
        proto.get("if_no_difference"),
        (proto.get("song_transfer") or {}).get("instruction"),
    )
    assert "짧은 비교" not in user
    assert "비교해보기" not in user
    assert "A · B" not in user
    assert "각 2~3회" not in user or "A" not in user
    assert "평소 방식과" not in user


def test_style_protocol_title_is_action_not_comparison():
    proto = build_coaching_protocol(
        "STYLE",
        snap=_snap(),
        target_timbre={"id": "BRIGHT_CLEAR", "type": "TIMBRE"},
    )
    title = (proto.get("entry_step") or proto["steps"][0]).get("title") or ""
    assert "발음으로 선명함 만들기" in title
    assert "짧은 비교" not in title
    assert "밝고 선명하게 ·" not in title


def test_style_protocol_instruction_is_direct_prescription():
    proto = build_coaching_protocol(
        "STYLE",
        snap=_snap(),
        target_timbre={"id": "BRIGHT_CLEAR", "type": "TIMBRE"},
    )
    inst = (proto.get("entry_step") or proto["steps"][0]).get("instruction") or ""
    assert "자음 시작" in inst
    assert "모음" in inst
    assert "비교하세요" not in inst


def test_thin_does_not_use_keep_center_as_standalone_action():
    d = attach_prescription_fields(
        build_perceptual_depth("VOICE_TOO_THIN", _snap()),
        qtype="PERCEPTUAL",
    )
    inst = (d.get("prescription") or {}).get("instruction") or d.get("what_to_change") or ""
    assert not is_abstract_only(inst)
    assert "소리 중심을 유지" not in inst
    assert "모음" in inst or "연결" in inst


def test_register_does_not_use_smooth_connection_without_how():
    from audio_analyzer.diagnostic.qa_coaching_depth import ladder_cue

    cue = ladder_cue("REGISTER", 0)
    inst = cue.get("instruction") or ""
    assert "립트릴" in inst or "빨대" in inst
    assert "연결을 매끄럽게" not in inst or "립트릴" in inst


def test_style_does_not_use_desired_feeling_without_how():
    proto = build_coaching_protocol(
        "STYLE",
        snap=_snap(),
        target_timbre={"id": "BRIGHT_CLEAR", "type": "TIMBRE"},
    )
    inst = (proto.get("entry_step") or proto["steps"][0]).get("instruction") or ""
    assert "원하는 느낌" not in inst
    assert not any(bad == inst for bad in ABSTRACT_STANDALONE)


def test_success_cues_are_semantically_unique():
    cues = dedupe_success_cues(
        ["얇은 인상 감소, 힘 증가 없음", "힘 증가 없음", "힘이 늘지 않음"],
        family="THIN",
    )
    keys = []
    from audio_analyzer.diagnostic.qa_coaching_depth import _success_cue_key

    for c in cues:
        k = _success_cue_key(c)
        assert k not in keys
        keys.append(k)


def test_effort_no_increase_not_repeated_twice():
    cues = dedupe_success_cues(
        ["힘 증가 없음", "힘이 더 들어가지 않음", "얇게 느껴지는 인상이 줄어듦"],
        family="THIN",
    )
    effortish = [c for c in cues if "힘" in c]
    assert len(effortish) <= 1


def test_user_copy_contains_no_pitch_token():
    assert "pitch" not in koreanize_user_copy("같은 pitch에서 연습").lower()


def test_user_copy_contains_no_phrase_token():
    assert "phrase" not in koreanize_user_copy("짧은 phrase에 적용").lower()


def test_user_copy_contains_no_glide_token():
    assert "glide" not in koreanize_user_copy("작은 강도 glide를 반복").lower()


def test_user_copy_contains_no_sustain_token():
    assert "sustain" not in koreanize_user_copy("짧은 sustain에서 유지").lower()


def test_bright_clear_goal_is_short_and_actionable():
    title, desc = _goal_copy(
        {"id": "BRIGHT_CLEAR", "label": "밝고 선명하게", "type": "TIMBRE"},
        "STYLE",
        _snap(),
        style=True,
        safety=False,
    )
    assert "탐색" not in title
    assert "원하는" not in title
    assert "선명" in title
    assert "발음" in desc or "모음" in desc


def test_style_primary_label_is_target_specific():
    assert STYLE_TARGET_LABELS["BRIGHT_CLEAR"] == "밝고 선명한 표현"
    assert STYLE_TARGET_LABELS["DENSE_SOLID"] == "밀도 있는 표현"


def test_why_first_explains_why_target_action_is_selected():
    why = _why_first("STYLE", _snap(), ["LOW_EFFORT", "LOW_BREATHINESS"])
    assert "발음" in why or "모음" in why
    assert "밝기" in why or "선명" in why


def test_current_thin_has_concrete_register_or_vowel_action():
    d = attach_prescription_fields(
        build_perceptual_depth("VOICE_TOO_THIN", _snap()),
        qtype="PERCEPTUAL",
    )
    p = d.get("prescription") or {}
    inst = p.get("instruction") or ""
    assert "우" in inst or "모음" in inst
    assert "음량" in inst
    assert "연결을 일정" not in inst
    assert "소리 중심" not in inst


def test_current_global_bright_protocol_has_direct_articulation_instruction():
    proto = build_coaching_protocol(
        "STYLE",
        snap=_snap(),
        target_timbre={"id": "BRIGHT_CLEAR", "type": "TIMBRE"},
    )
    entry = proto.get("entry_step") or proto["steps"][0]
    assert "발음으로 선명함 만들기" in (entry.get("title") or "")
    assert "자음" in (entry.get("instruction") or "")


def test_current_muffled_success_cues_not_duplicate():
    d = attach_prescription_fields(
        build_perceptual_depth("VOICE_TOO_DARK_MUFFLED", _snap()),
        qtype="PERCEPTUAL",
    )
    cues = (d.get("prescription") or {}).get("success_cues") or []
    from audio_analyzer.diagnostic.qa_coaching_depth import _success_cue_key

    keys = [_success_cue_key(c) for c in cues]
    assert len(keys) == len(set(keys))


def test_current_nasal_uses_korean_user_language():
    d = attach_prescription_fields(
        build_perceptual_depth("VOICE_TOO_NASAL_PERCEPT", _snap()),
        qtype="PERCEPTUAL",
    )
    p = d.get("prescription") or {}
    blob = _user_blob(
        p.get("instruction"),
        (p.get("alternate") or {}).get("instruction"),
        p.get("song_transfer"),
        * (p.get("success_cues") or []),
    ).lower()
    assert "pitch" not in blob
    assert "phrase" not in blob
    assert "덜 몰려" not in blob
    assert "음높이" in blob or "음절" in blob


def test_no_anatomical_diagnosis_regression():
    d = build_perceptual_depth("VOICE_TOO_THIN", _snap())
    blob = str(d)
    for bad in ("연구개", "성대를 붙", "후두를", "복압", "혀뿌리"):
        assert bad not in blob


def test_pain_no_active_prescription():
    from audio_analyzer.diagnostic.qa_coaching_depth import build_prescription

    assert build_prescription(instruction="쉬세요", qtype="SAFETY") is None
