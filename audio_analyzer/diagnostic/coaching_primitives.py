"""Reusable coaching primitives + comparison families for Precision Coaching v6.

Concern semantics select evidence → focus → primitive + comparison family.
Does NOT hard-code concern × acoustic × target matrices.
"""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.diagnostic.practice_library import FOCUS_TO_PRACTICE, get_practice
from audio_analyzer.diagnostic.question_semantics import (
    FACTOR_BREATHINESS,
    FACTOR_BRIGHTNESS,
    FACTOR_CONTACT,
    FACTOR_DYNAMICS,
    FACTOR_EFFORT,
    FACTOR_HIGH_NOTE,
    FACTOR_MAINTAIN,
    FACTOR_PRESENCE,
    FACTOR_REGISTER,
    FACTOR_SAFETY,
    FACTOR_STABILITY,
    FACTOR_TEXTURE,
    FACTOR_TIMBRE,
    semantics_for,
)

# ---------------------------------------------------------------------------
# Coaching primitives (focus-keyed)
# ---------------------------------------------------------------------------

COACHING_PRIMITIVES: dict[str, dict[str, Any]] = {
    "REGISTER_CONNECTION": {
        "id": "REGISTER_CONNECTION",
        "goal": "음역 전환을 끊김 없이 연결하기",
        "base_instruction": "작은 강도로 중음에서 위쪽까지 glide하며 전환 직전 음량을 키우지 않기",
        "success_cues": ["끊김 감소", "갑작스러운 음색 변화 감소", "힘 증가 없음"],
        "avoid": ["끊기는 음을 세게 밀어 통과하기", "음량부터 키워 넘어가기"],
        "practice_ids": ["REGISTER_GLIDE_LIGHT", "SOVT_GLIDE"],
        "allowed_for": ["high_note", "control", "timbre", "effort"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "HIGH_NOTE_ACCESS": {
        "id": "HIGH_NOTE_ACCESS",
        "goal": "높은 음에 세게 밀지 않고 접근하기",
        "base_instruction": "목표 음높이 직전 짧은 구간을 작은 강도로 연결",
        "success_cues": ["도달이 더 편함", "힘 증가 없음"],
        "avoid": ["높은 음을 세게 밀어 통과하기"],
        "practice_ids": ["REGISTER_GLIDE_LIGHT"],
        "allowed_for": ["high_note"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "EFFORT": {
        "id": "EFFORT",
        "goal": "힘 사용이 급격히 커지지 않게 하기",
        "base_instruction": "같은 음높이를 작은~중간 강도로만 유지",
        "success_cues": ["같은 음높이인데 힘 사용이 덜 느껴짐", "불편감 없음"],
        "avoid": ["음량부터 키우기", "통증 상태 반복"],
        "practice_ids": ["REDUCE_HIGH_NOTE_EFFORT", "MAINTAIN_LOW_EFFORT"],
        "allowed_for": ["effort", "high_note"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "STABILITY": {
        "id": "STABILITY",
        "goal": "짧은 구간에서 음정·소리 흔들림 줄이기",
        "base_instruction": "같은 음을 1~2초만 짧게 유지하며 비교",
        "success_cues": ["흔들림 감소", "힘 증가 없음"],
        "avoid": ["길게 버텨 흔들림을 키우기", "불안정한 음을 세게 고정하기"],
        "practice_ids": ["STABILITY_SHORT_HOLD"],
        "allowed_for": ["high_note", "control", "timbre"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "PITCH_STABILITY": {
        "id": "PITCH_STABILITY",
        "goal": "짧은 안정 구간에서 음정 유지",
        "base_instruction": "긴 음보다 짧은 안정 구간부터 비교",
        "success_cues": ["짧은 구간 음정 유지", "힘 증가 없음"],
        "avoid": ["긴 음으로 억지로 버티기"],
        "practice_ids": ["STABILITY_SHORT_HOLD"],
        "allowed_for": ["control"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "BREATHINESS": {
        "id": "BREATHINESS",
        "goal": "숨이 과하게 새지 않는 짧은 패턴 찾기",
        "base_instruction": "작은 강도에서 짧게 유지하며 숨이 먼저 과하게 새지 않게",
        "success_cues": ["숨 섞임 감소", "힘 증가 없음"],
        "avoid": ["숨을 갑자기 막아 세게 붙이기"],
        "practice_ids": ["BREATHINESS_CONTROL"],
        "allowed_for": ["timbre", "high_note"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "CONTACT": {
        "id": "CONTACT",
        "goal": "접촉 느낌을 세게 바꾸지 않고 짧은 구간에서 비교",
        "base_instruction": "음량을 키우지 않고 짧은 지속에서 접촉 느낌만 비교",
        "success_cues": ["원하는 접촉 느낌이 유지되고 힘 증가 없음"],
        "avoid": ["접촉을 세게 붙여 밀기"],
        "practice_ids": ["MAINTAIN_LOW_EFFORT"],
        "allowed_for": ["timbre"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "PRESENCE": {
        "id": "PRESENCE",
        "goal": "밀지 않고 중역 존재감 유지",
        "base_instruction": "편안한 강도에서 짧은 모음으로 중역 존재감이 사라지지 않게",
        "success_cues": ["중역 존재감 유지", "음량을 과하게 키우지 않음"],
        "avoid": ["얇음을 가리려고 과하게 밀기"],
        "practice_ids": ["PRESENCE_WITHOUT_PUSHING"],
        "allowed_for": ["timbre", "high_note"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "BRIGHTNESS": {
        "id": "BRIGHTNESS",
        "goal": "밝기 느낌을 세게 바꾸지 않고 짧은 표현으로 비교",
        "base_instruction": "같은 음량에서 밝기만 조금 다르게 짧게 비교",
        "success_cues": ["원하는 밝기 쪽에 가깝고 불편 없음"],
        "avoid": ["밝기를 위해 세게 밀기"],
        "practice_ids": ["PRESENCE_WITHOUT_PUSHING"],
        "allowed_for": ["timbre"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "TIMBRE_STYLE": {
        "id": "TIMBRE_STYLE",
        "goal": "원하는 음색 표현을 작은 강도로 탐색",
        "base_instruction": "짧은 구절에서 원하는 느낌에 가깝게, 과하게 밀지 않고 비교",
        "success_cues": ["원하는 느낌에 더 가깝고 불편 없음"],
        "avoid": ["음색을 바꾸려고 세게 밀기"],
        "practice_ids": ["TIMBRE_PRESERVE"],
        "allowed_for": ["timbre"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "TEXTURE": {
        "id": "TEXTURE",
        "goal": "거친 인상이 줄어드는 짧은 안정 패턴 찾기",
        "base_instruction": "짧은 지속에서 안정이 유지되는 쪽을 비교",
        "success_cues": ["거친 인상 감소", "힘 증가 없음"],
        "avoid": ["거칠음을 가리려고 세게 밀기", "병변을 추정하기"],
        "practice_ids": ["STABILITY_SHORT_HOLD"],
        "allowed_for": ["timbre"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "DYNAMICS": {
        "id": "DYNAMICS",
        "goal": "작은 강약 변화에서도 안정·편안함 유지",
        "base_instruction": "편한 강도 유지 후 같은 구절에 작은 강약만 추가",
        "success_cues": ["강약 변화 중 pitch/stability/effort 유지"],
        "avoid": ["처음부터 큰 소리로 연습하기"],
        "practice_ids": ["MAINTAIN_LOW_EFFORT"],
        "allowed_for": ["control", "effort"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "PHRASE_ENDURANCE": {
        "id": "PHRASE_ENDURANCE",
        "goal": "프레이즈 끝까지 소리 중심이 급격히 약해지지 않게",
        "base_instruction": "조금 짧은 프레이즈부터 끝까지 같은 편안함 유지",
        "success_cues": ["끝음에서 소리 중심이 급격히 약해지지 않음"],
        "avoid": ["긴 프레이즈를 세게 버텨 끝내기"],
        "practice_ids": ["MAINTAIN_LOW_EFFORT"],
        "allowed_for": ["control"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "VIBRATO_CONTROL": {
        "id": "VIBRATO_CONTROL",
        "goal": "짧은 지속음에서 자연스러운 흔들림이 생기는지 비교",
        "base_instruction": "억지로 크게 만들지 말고 짧은 지속에서만 비교",
        "success_cues": ["자연스러운 흔들림이 유지되고 불편 없음"],
        "avoid": ["비브라토를 억지로 크게 만들기"],
        "practice_ids": ["STABILITY_SHORT_HOLD"],
        "allowed_for": ["control"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "MAINTAIN": {
        "id": "MAINTAIN",
        "goal": "현재 편안한 패턴을 유지하며 짧은 비교",
        "base_instruction": "평소 방식과 조금 작은 강도만 짧게 비교",
        "success_cues": ["더 편하고 안정적이며 힘 증가 없음"],
        "avoid": ["원인을 가정하고 세게 바꾸기"],
        "practice_ids": ["MAINTAIN_LOW_EFFORT"],
        "allowed_for": ["other", "timbre", "effort", "control", "high_note"],
        "blocked_when": ["PAIN_LIMITED"],
    },
    "SAFETY": {
        "id": "SAFETY",
        "goal": "통증·불편이 있을 때는 실험을 중단하고 쉬기",
        "base_instruction": "강한 고음·큰 소리·반복 phonation·style experiment 하지 않기",
        "success_cues": ["통증/불편이 늘지 않음"],
        "avoid": ["통증 상태에서의 반복", "강한 고음 밀어붙이기"],
        "practice_ids": ["SAFETY_STOP"],
        "allowed_for": ["safety"],
        "blocked_when": [],
    },
}

FOCUS_TO_PRIMITIVE: dict[str, str] = {
    FACTOR_REGISTER: "REGISTER_CONNECTION",
    FACTOR_HIGH_NOTE: "HIGH_NOTE_ACCESS",
    FACTOR_EFFORT: "EFFORT",
    FACTOR_STABILITY: "STABILITY",
    FACTOR_BREATHINESS: "BREATHINESS",
    FACTOR_CONTACT: "CONTACT",
    FACTOR_PRESENCE: "PRESENCE",
    FACTOR_BRIGHTNESS: "BRIGHTNESS",
    FACTOR_TIMBRE: "TIMBRE_STYLE",
    FACTOR_TEXTURE: "TEXTURE",
    FACTOR_DYNAMICS: "DYNAMICS",
    FACTOR_MAINTAIN: "MAINTAIN",
    FACTOR_SAFETY: "SAFETY",
    "PITCH_STABILITY": "PITCH_STABILITY",
    "PHRASE_ENDURANCE": "PHRASE_ENDURANCE",
    "VIBRATO_CONTROL": "VIBRATO_CONTROL",
    "AIRINESS": "BREATHINESS",
}

# ---------------------------------------------------------------------------
# Comparison families (protocol templates)
# ---------------------------------------------------------------------------

COMPARISON_FAMILIES: dict[str, dict[str, str]] = {
    "REGISTER_BRIDGE_COMPARE": {
        "working_direction": "전환 구간을 작은 강도로 일정하게 연결",
        "what_to_change": "전환 구간을 더 일정하게 연결하기",
        "baseline_label": "평소 연결",
        "baseline_instruction": "평소대로 중음→위쪽 음역 이동을 한 번",
        "variant_label": "비교 연결",
        "variant_instruction": (
            "작은 강도로 glide하며 전환 지점에서 음량을 키우지 않고 연결한 한 번"
        ),
        "success_condition": "끊김 감소, 갑작스러운 음색 변화 감소, 힘 증가 없음",
        "if_better": "그 방식으로 반복하면 됩니다.",
        "if_not_better": "차이가 거의 없다면, 전환이 느껴지는 짧은 구간만 따로 비교해보세요.",
        "lead": (
            "음역이 바뀔 때 연결이 끊기는 느낌을 줄이려면, "
            "세게 밀기보다 작은 강도로 전환 구간을 이어서 비교해보세요."
        ),
        "avoid": "끊기는 음을 세게 밀어 통과하기;음량을 먼저 키워 넘어가기",
    },
    "HIGH_NOTE_ACCESS_COMPARE": {
        "working_direction": "세게 밀기보다 작은 강도로 중음에서 위쪽까지 연결",
        "what_to_change": "고음을 더 세게 내기보다 연결을 다듬기",
        "baseline_label": "평소 방식",
        "baseline_instruction": "평소대로 중음에서 위쪽으로 한 번",
        "variant_label": "비교 방식",
        "variant_instruction": "조금 작은 강도로 시작해 음량을 먼저 키우지 않고 천천히 연결한 한 번",
        "success_condition": "도달이 더 편하고 힘이 늘지 않음",
        "if_better": "그 방향을 유지하세요.",
        "if_not_better": "차이가 거의 없다면, 목표 음높이 직전 짧은 구간만 따로 비교해보세요.",
        "lead": "높은 음에 닿으려면 세게 밀기보다, 작은 강도로 연결하는 쪽을 먼저 비교해보세요.",
        "avoid": "높은 음을 세게 밀어 통과하기",
    },
    "HIGH_NOTE_EFFORT_COMPARE": {
        "working_direction": "고음에서 음량을 먼저 키우지 않고 편안한 강도로 접근",
        "what_to_change": "힘 사용이 갑자기 커지지 않게 하기",
        "baseline_label": "평소 방식",
        "baseline_instruction": "평소대로 고음 구절을 한 번",
        "variant_label": "비교 방식",
        "variant_instruction": "같은 구절을 작은~중간 강도로만 유지한 채 한 번",
        "success_condition": "같은 음높이인데 힘 사용이 덜 느껴짐",
        "if_better": "그 방향을 유지하세요.",
        "if_not_better": "차이가 거의 없다면, 힘이 커지는 짧은 구간만 따로 비교해보세요.",
        "lead": "고음에서 힘이 드는 느낌을 줄이려면, 같은 구절을 작은 강도로 한 번 더 비교해보세요.",
        "avoid": "높은 음에 도달하려고 음량부터 키우기",
    },
    "HIGH_NOTE_STABILITY_COMPARE": {
        "working_direction": "긴 음보다 짧은 안정 구간에서 흔들림 비교",
        "what_to_change": "고음에서 짧게 유지되는 안정 구간부터 만들기",
        "baseline_label": "평소 유지",
        "baseline_instruction": "평소 방식으로 해당 높은 음을 짧게 유지",
        "variant_label": "짧은 안정",
        "variant_instruction": "같은 음을 조금 작은 강도로 1~2초만 짧게 유지",
        "success_condition": "음정/소리 흔들림 감소, 힘 증가 없음",
        "if_better": "짧은 안정 구간부터 조금씩 길이·범위를 확장하세요.",
        "if_not_better": "차이가 거의 없다면, 흔들림이 큰 짧은 구간만 따로 비교해보세요.",
        "lead": (
            "고음에서 음정이나 소리가 흔들릴 때는 길게 버티기보다, "
            "같은 음을 짧은 안정 구간으로 비교해보세요."
        ),
        "avoid": "불안정한 음을 세게 고정하기;길게 버텨 흔들림을 키우기",
    },
    "PITCH_STABILITY_COMPARE": {
        "working_direction": "긴 음보다 짧은 안정 구간에서 음정 비교",
        "what_to_change": "짧은 구간에서 음정이 유지되는 쪽 찾기",
        "baseline_label": "평소 유지",
        "baseline_instruction": "평소대로 음을 유지한 한 번",
        "variant_label": "짧은 안정",
        "variant_instruction": "같은 음을 조금 작은 강도로 2~3초만 짧게 유지한 한 번",
        "success_condition": "짧은 구간에서 음정 흔들림이 줄고 힘 증가 없음",
        "if_better": "짧은 안정부터 조금씩 길이를 늘려보세요.",
        "if_not_better": "차이가 거의 없다면, 흔들림이 큰 짧은 구간만 따로 비교해보세요.",
        "lead": "음정이 흔들릴 때는 긴 음보다 짧은 안정 구간부터 비교해보세요.",
        "avoid": "긴 음으로 억지로 버티기",
    },
    "BREATHINESS_COMPARE": {
        "working_direction": "숨을 갑자기 막기보다 짧은 구간에서 숨이 과하게 새지 않는 패턴 비교",
        "what_to_change": "짧은 지속에서 숨이 과하게 새지 않는 패턴을 찾기",
        "baseline_label": "평소 방식",
        "baseline_instruction": "평소대로 한 번",
        "variant_label": "비교 방식",
        "variant_instruction": "작은 강도에서 짧게 유지하며 숨이 먼저 과하게 새지 않게 한 번",
        "success_condition": "숨 섞임은 줄고 힘은 증가하지 않음",
        "if_better": "그 방향을 유지하세요.",
        "if_not_better": "차이가 거의 없다면, 숨이 섞여 들리는 짧은 구간만 따로 비교해보세요.",
        "lead": "숨이 섞이는 구간에서는 숨을 갑자기 막기보다, 짧은 지속으로 비교해보세요.",
        "avoid": "숨을 갑자기 막아 세게 붙이기",
    },
    "PRESENCE_COMPARE": {
        "working_direction": "음량을 키우지 않고 중역 존재감이 유지되는 방식 비교",
        "what_to_change": "중역 존재감이 갑자기 사라지지 않게 하기",
        "baseline_label": "평소 방식",
        "baseline_instruction": "평소대로 한 번",
        "variant_label": "비교 방식",
        "variant_instruction": "같은 음량을 유지하며 중역 존재감이 흐려지지 않게 한 번",
        "success_condition": "존재감은 유지되고 힘 증가 없음",
        "if_better": "그 방향을 유지하세요.",
        "if_not_better": "차이가 거의 없다면, 존재감이 떨어지는 짧은 구간만 따로 비교해보세요.",
        "lead": "존재감이 약해지는 구간에서는 더 세게 밀기보다, 같은 음량에서 중심이 유지되는지 비교해보세요.",
        "avoid": "존재감을 가리려고 세게 밀기",
    },
    "CONTACT_COMPARE": {
        "working_direction": "접촉 느낌을 세게 바꾸지 않고 짧은 구간에서 비교",
        "what_to_change": "짧은 지속에서 접촉 느낌이 유지되는 쪽 찾기",
        "baseline_label": "평소 방식",
        "baseline_instruction": "평소대로 한 번",
        "variant_label": "비교 방식",
        "variant_instruction": "음량을 키우지 않고 짧은 지속에서 접촉 느낌만 유지한 한 번",
        "success_condition": "원하는 접촉 느낌이 유지되고 힘 증가 없음",
        "if_better": "그 방향을 유지하세요.",
        "if_not_better": "차이가 거의 없다면, 해당 짧은 구간만 따로 비교해보세요.",
        "lead": "접촉 느낌이 달라지는 구간에서는 세게 붙이기보다, 짧은 지속으로 비교해보세요.",
        "avoid": "접촉을 세게 붙여 밀기",
    },
    "TIMBRE_STYLE_COMPARE": {
        "working_direction": "짧은 구절에서 원하는 느낌에 가까운 표현을 작은 강도로 비교",
        "what_to_change": "짧은 구절에서 원하는 느낌에 가까운 표현을 비교해보세요.",
        "baseline_label": "평소 표현",
        "baseline_instruction": "평소 부르는 방식으로 한 번",
        "variant_label": "비교 표현",
        "variant_instruction": "같은 음량에서 원하는 느낌에 가깝게, 과하게 밀지 않고 한 번",
        "success_condition": "원하는 느낌에 더 가깝고 불편이 없음",
        "if_better": "그 표현을 유지하세요.",
        "if_not_better": "차이가 거의 없다면, 원하는 느낌이 필요한 짧은 구절만 따로 비교해보세요.",
        "lead": "원하는 음색에 가까워지려면 같은 짧은 구절을 표현 방식만 바꿔 비교해보세요.",
        "avoid": "음색을 바꾸려고 세게 밀기",
    },
    "MUFFLED_COMPARE": {
        "working_direction": "세게 바꾸기보다 작은 강도에서 소리 중심과 연결을 유지하며 비교",
        "what_to_change": "짧은 구절에서 답답함이 줄면서 중심이 유지되는 쪽을 찾기",
        "baseline_label": "평소 방식",
        "baseline_instruction": "평소대로 한 번",
        "variant_label": "비교 방식",
        "variant_instruction": "같은 구절을 조금 더 작은 강도로 소리 중심과 연결을 유지하며 한 번",
        "success_condition": "답답한 느낌은 줄고 소리 중심·안정성은 유지됨",
        "if_better": "그 방향을 유지하세요.",
        "if_not_better": "차이가 거의 없다면, 답답함이 큰 짧은 구간만 따로 비교해보세요.",
        "lead": "답답하게 느껴지는 구간에서는 세게 바꾸기보다, 작은 강도에서 중심이 유지되는지 비교해보세요.",
        "avoid": "답답함을 가리려고 세게 밀기",
    },
    "THIN_COMPARE": {
        "working_direction": "숨을 더 막는 것보다 소리 중심이 유지되는 방식 탐색",
        "what_to_change": "음역이 변해도 소리 중심이 갑자기 가벼워지지 않게 하기",
        "baseline_label": "평소 방식",
        "baseline_instruction": "평소대로 한 번",
        "variant_label": "비교 방식",
        "variant_instruction": (
            "같은 음량을 유지하면서 숨을 더 섞지 않고, "
            "음이 올라가도 더 크게 만들지 않은 채 연결을 일정하게 유지한 한 번"
        ),
        "success_condition": "얇게 느껴지는 인상이 줄고 힘 사용은 늘지 않음",
        "if_better": "그 방향이 현재 발성에 더 잘 맞습니다.",
        "if_not_better": "차이가 거의 없다면, 얇게 느껴지는 음역·구간만 따로 비교해보세요.",
        "lead": (
            "지금은 숨을 더 막거나 소리를 더 세게 만드는 것보다, "
            "얇게 느껴지는 구간에서 소리 중심이 유지되는 방식을 찾는 게 좋아요."
        ),
        "avoid": "얇음을 가리려고 소리를 세게 밀기",
    },
    "NASAL_PERCEPT_COMPARE": {
        "working_direction": "특정 모음·구간에서 소리가 몰려 들리는 느낌을 작은 강도에서 표현 방식으로 비교",
        "what_to_change": "특정 모음에서 소리가 몰리지 않게 연결하기",
        "baseline_label": "평소 방식",
        "baseline_instruction": "평소 부르는 방식으로 한 번",
        "variant_label": "비교 방식",
        "variant_instruction": (
            "같은 음량을 유지하면서 문제가 느껴지는 모음·구절을 "
            "더 또렷하고 매끄럽게 이어서 한 번"
        ),
        "success_condition": "콧소리처럼 느껴지는 인상 감소, 불편감·힘 증가 없음",
        "if_better": "두 번째 표현을 유지하는 방향이 좋아요.",
        "if_not_better": "차이가 거의 없다면, 다음 녹음에서 해당 모음·구간만 따로 짧게 비교해보세요.",
        "lead": (
            "콧소리처럼 느껴지는 구간에서는 소리를 더 세게 바꾸기보다, "
            "같은 음량에서 모음을 더 또렷하고 매끄럽게 이어보세요."
        ),
        "avoid": "소리를 크게 밀기;코소리를 없애려고 과하게 힘주기",
    },
    "ROUGHNESS_COMPARE": {
        "working_direction": "짧은 안정 구간에서 거친 인상이 줄어드는지 비교",
        "what_to_change": "짧은 구간에서 안정이 유지되는 쪽 찾기",
        "baseline_label": "평소 방식",
        "baseline_instruction": "평소대로 한 번",
        "variant_label": "비교 방식",
        "variant_instruction": "조금 작은 강도로 2~3초만 짧게 유지한 한 번",
        "success_condition": "거친 인상은 줄고 힘·불편 증가 없음",
        "if_better": "그 방향을 유지하세요.",
        "if_not_better": "차이가 거의 없다면, 거칠게 느껴지는 짧은 구간만 따로 비교해보세요.",
        "lead": "거칠게 느껴지는 구간에서는 세게 밀기보다, 짧은 안정 구간으로 비교해보세요.",
        "avoid": "거칠음을 가리려고 세게 밀기;병변을 추정하기",
    },
    "VIBRATO_COMPARE": {
        "working_direction": "짧은 지속음에서 자연스러운 흔들림이 생기는지 비교",
        "what_to_change": "억지로 크게 만들지 말고 짧은 지속에서만 비교",
        "baseline_label": "평소 유지",
        "baseline_instruction": "평소대로 짧게 유지한 한 번",
        "variant_label": "자연 유지",
        "variant_instruction": "같은 음을 조금 작은 강도로 짧게 유지하며 흔들림을 억지로 키우지 않은 한 번",
        "success_condition": "자연스러운 흔들림이 유지되고 불편 없음",
        "if_better": "그 방향을 유지하세요.",
        "if_not_better": "차이가 거의 없다면, 해당 짧은 구간만 따로 비교해보세요.",
        "lead": "비브라토가 불안정할 때는 억지로 크게 만들기보다, 짧은 지속에서만 비교해보세요.",
        "avoid": "비브라토를 억지로 크게 만들기",
    },
    "DYNAMICS_COMPARE": {
        "working_direction": "편한 강도 유지 후 작은 강약만 추가해 비교",
        "what_to_change": "같은 구절에서 작은 강약 변화만 추가하기",
        "baseline_label": "편한 강도",
        "baseline_instruction": "편한 강도로 유지한 한 번",
        "variant_label": "작은 강약",
        "variant_instruction": "같은 구절에서 작은 강약 변화만 추가한 한 번",
        "success_condition": "강약 변화 중 pitch·stability·effort가 유지됨",
        "if_better": "그 범위를 조금씩 넓혀보세요.",
        "if_not_better": "차이가 거의 없다면, 강약이 필요한 짧은 구간만 따로 비교해보세요.",
        "lead": "강약 조절은 처음부터 크게 바꾸기보다, 편한 강도에서 작은 변화만 추가해 비교해보세요.",
        "avoid": "처음부터 큰 소리로 연습하기",
    },
    "PHRASE_END_COMPARE": {
        "working_direction": "조금 짧은 프레이즈부터 끝까지 같은 편안함 유지",
        "what_to_change": "끝음에서 소리 중심이 급격히 약해지지 않게 하기",
        "baseline_label": "평소 프레이즈",
        "baseline_instruction": "평소 프레이즈로 한 번",
        "variant_label": "짧은 프레이즈",
        "variant_instruction": "조금 짧은 프레이즈부터 끝까지 같은 편안함을 유지한 한 번",
        "success_condition": "끝음에서 소리 중심이 급격히 약해지지 않음",
        "if_better": "그 길이를 조금씩 늘려보세요.",
        "if_not_better": "차이가 거의 없다면, 끝이 약해지는 짧은 구간만 따로 비교해보세요.",
        "lead": "프레이즈 끝이 약해질 때는 긴 문장을 세게 버티기보다, 짧은 프레이즈부터 끝까지 유지해보세요.",
        "avoid": "긴 프레이즈를 세게 버텨 끝내기",
    },
    "HIGH_TIMBRE_COMPARE": {
        "working_direction": "높은 음을 더 세게 만들지 않고 전환·표현을 일정하게 비교",
        "what_to_change": "고음에서 음색이 갑자기 달라지지 않게 연결하기",
        "baseline_label": "평소 연결",
        "baseline_instruction": "평소대로 중음→위쪽 음역 구절을 한 번",
        "variant_label": "비교 연결",
        "variant_instruction": (
            "조금 작은 강도로 시작해, 전환 직전부터 음량을 키우지 않고 "
            "위쪽 음역까지 부드럽게 이어서 한 번"
        ),
        "success_condition": "음색 변화가 덜 갑작스럽고 힘 증가 없음",
        "if_better": "그 방식으로 반복하면 됩니다.",
        "if_not_better": "차이가 거의 않다면, 전환이 느껴지는 짧은 구간만 따로 비교해보세요.",
        "lead": (
            "고음에서 음색이 갑자기 달라지는 느낌을 줄이려면, "
            "높은 음을 더 세게 만드는 것보다 전환 구간을 더 일정하게 연결하는 것을 먼저 해보는 게 좋아요."
        ),
        "avoid": "고음을 세게 밀어 통과하기;음량을 먼저 키워 넘어가기",
    },
    "GENERAL_COMPARE": {
        "working_direction": "같은 짧은 구절을 평소 방식과 작은 강도 방식으로 비교",
        "what_to_change": "같은 구절을 작은 강도로 짧게 비교해보세요.",
        "baseline_label": "평소 방식",
        "baseline_instruction": "평소 부르는 방식으로 한 번",
        "variant_label": "비교 방식",
        "variant_instruction": "같은 음량에서 조금 작은 강도로, 과하게 밀지 않고 한 번",
        "success_condition": "더 편하고 안정적이며 힘 증가 없음",
        "if_better": "그 방향을 유지하세요.",
        "if_not_better": "차이가 거의 없다면, 해당 구절의 짧은 구간만 따로 비교해보세요.",
        "lead": "같은 짧은 구절을 평소 방식과 작은 강도로 한 번씩 비교해보세요.",
        "avoid": "원인을 가정하고 세게 바꾸기",
    },
    "SAFETY_STOP": {
        "working_direction": "통증·불편이 있을 때는 실험을 하지 않고 쉬기",
        "what_to_change": "강한 고음·큰 소리·반복 발성 실험을 중단하기",
        "baseline_label": "중단",
        "baseline_instruction": "통증이 있으면 연습을 멈춥니다",
        "variant_label": "휴식",
        "variant_instruction": "충분한 휴식을 취하고 증상이 늘면 전문의와 상담하세요",
        "success_condition": "통증·불편이 늘지 않음",
        "if_better": "증상이 가라앉을 때까지 쉬세요.",
        "if_not_better": "증상이 계속되면 의료 상담을 권합니다.",
        "lead": "통증이나 지속되는 불편이 있으면 실험을 하지 말고 쉬세요.",
        "avoid": "통증 상태에서의 반복;강한 고음 밀어붙이기",
    },
}

# Default family per concern (semantic overlay). Evidence/focus may override.
CONCERN_DEFAULT_FAMILY: dict[str, str] = {
    "HIGH_NOTE_CANNOT_REACH": "HIGH_NOTE_ACCESS_COMPARE",
    "HIGH_NOTE_TOO_EFFORTFUL": "HIGH_NOTE_EFFORT_COMPARE",
    "HIGH_NOTE_FLIPS": "REGISTER_BRIDGE_COMPARE",
    "HIGH_NOTE_THINS": "THIN_COMPARE",
    "HIGH_NOTE_UNSTABLE": "HIGH_NOTE_STABILITY_COMPARE",
    "THROAT_EFFORT": "HIGH_NOTE_EFFORT_COMPARE",
    "LOUD_VOICE_DIFFICULT": "DYNAMICS_COMPARE",
    "VOCAL_FATIGUE": "HIGH_NOTE_EFFORT_COMPARE",
    "AFTER_SINGING_FATIGUE": "HIGH_NOTE_EFFORT_COMPARE",
    "TIMBRE_DISSATISFIED": "TIMBRE_STYLE_COMPARE",
    "VOICE_TOO_THIN": "THIN_COMPARE",
    "VOICE_TOO_DARK_MUFFLED": "MUFFLED_COMPARE",
    "VOICE_TOO_NASAL_PERCEPT": "NASAL_PERCEPT_COMPARE",
    "VOICE_TOO_BREATHY": "BREATHINESS_COMPARE",
    "VOICE_TOO_SHARP": "TIMBRE_STYLE_COMPARE",
    "VOICE_ROUGH": "ROUGHNESS_COMPARE",
    "TIMBRE_CHANGES_HIGH": "HIGH_TIMBRE_COMPARE",
    "PITCH_UNSTABLE": "PITCH_STABILITY_COMPARE",
    "REGISTER_CONNECTION_DIFFICULT": "REGISTER_BRIDGE_COMPARE",
    "VIBRATO_UNSTABLE": "VIBRATO_COMPARE",
    "DYNAMICS_DIFFICULT": "DYNAMICS_COMPARE",
    "PHRASE_END_WEAK": "PHRASE_END_COMPARE",
    "PAIN_WHILE_SINGING": "SAFETY_STOP",
    "PAIN_AFTER_SINGING": "SAFETY_STOP",
    "SPEAKING_DISCOMFORT": "SAFETY_STOP",
    "PERSISTENT_HOARSENESS": "SAFETY_STOP",
    "OTHER_CONCERN": "GENERAL_COMPARE",
}

FOCUS_TO_FAMILY: dict[str, str] = {
    FACTOR_REGISTER: "REGISTER_BRIDGE_COMPARE",
    FACTOR_HIGH_NOTE: "HIGH_NOTE_ACCESS_COMPARE",
    FACTOR_EFFORT: "HIGH_NOTE_EFFORT_COMPARE",
    FACTOR_STABILITY: "HIGH_NOTE_STABILITY_COMPARE",
    FACTOR_BREATHINESS: "BREATHINESS_COMPARE",
    FACTOR_PRESENCE: "PRESENCE_COMPARE",
    FACTOR_CONTACT: "CONTACT_COMPARE",
    FACTOR_BRIGHTNESS: "TIMBRE_STYLE_COMPARE",
    FACTOR_TIMBRE: "TIMBRE_STYLE_COMPARE",
    FACTOR_TEXTURE: "ROUGHNESS_COMPARE",
    FACTOR_DYNAMICS: "DYNAMICS_COMPARE",
    FACTOR_MAINTAIN: "GENERAL_COMPARE",
    FACTOR_SAFETY: "SAFETY_STOP",
    "PITCH_STABILITY": "PITCH_STABILITY_COMPARE",
    "PHRASE_ENDURANCE": "PHRASE_END_COMPARE",
    "VIBRATO_CONTROL": "VIBRATO_COMPARE",
}

# Concern-specific family locks (question meaning wins over generic focus remap)
CONCERN_FAMILY_LOCK: dict[str, str] = {
    "HIGH_NOTE_UNSTABLE": "HIGH_NOTE_STABILITY_COMPARE",
    "HIGH_NOTE_FLIPS": "REGISTER_BRIDGE_COMPARE",
    "REGISTER_CONNECTION_DIFFICULT": "REGISTER_BRIDGE_COMPARE",
    "PITCH_UNSTABLE": "PITCH_STABILITY_COMPARE",
    "VIBRATO_UNSTABLE": "VIBRATO_COMPARE",
    "DYNAMICS_DIFFICULT": "DYNAMICS_COMPARE",
    "PHRASE_END_WEAK": "PHRASE_END_COMPARE",
    "VOICE_TOO_NASAL_PERCEPT": "NASAL_PERCEPT_COMPARE",
}

GENERIC_FALLBACK_FAMILIES = frozenset({"GENERAL_COMPARE", "MAINTAIN"})


def primitive_for_focus(primary_focus: Optional[str]) -> dict[str, Any]:
    focus = str(primary_focus or FACTOR_MAINTAIN).upper()
    pid = FOCUS_TO_PRIMITIVE.get(focus, "MAINTAIN")
    base = dict(COACHING_PRIMITIVES.get(pid) or COACHING_PRIMITIVES["MAINTAIN"])
    practice_id = FOCUS_TO_PRACTICE.get(focus) or (base.get("practice_ids") or [None])[0]
    practice = get_practice(str(practice_id)) if practice_id else None
    base["resolved_practice_id"] = practice_id
    base["practice"] = practice
    return base


def resolve_comparison_family(
    concern_id: Optional[str],
    *,
    primary_focus: Optional[str] = None,
) -> str:
    cid = str(concern_id or "").upper()
    focus = str(primary_focus or "").upper()
    if cid in CONCERN_FAMILY_LOCK:
        return CONCERN_FAMILY_LOCK[cid]
    # Prefer concern default when focus is maintain/empty; else focus map with concern overlay
    if focus and focus not in ("", "MAINTAIN", "UNKNOWN") and focus in FOCUS_TO_FAMILY:
        # Keep question-specific locks already handled; for thin/nasal etc. allow focus remap
        if cid in (
            "VOICE_TOO_THIN",
            "VOICE_TOO_DARK_MUFFLED",
            "VOICE_TOO_BREATHY",
            "VOICE_TOO_SHARP",
            "VOICE_ROUGH",
            "HIGH_NOTE_CANNOT_REACH",
            "HIGH_NOTE_TOO_EFFORTFUL",
            "HIGH_NOTE_THINS",
            "TIMBRE_CHANGES_HIGH",
            "THROAT_EFFORT",
            "TIMBRE_DISSATISFIED",
        ):
            return FOCUS_TO_FAMILY[focus]
    if cid in CONCERN_DEFAULT_FAMILY:
        return CONCERN_DEFAULT_FAMILY[cid]
    if focus in FOCUS_TO_FAMILY:
        return FOCUS_TO_FAMILY[focus]
    return "GENERAL_COMPARE"


def concern_policy(concern_id: str) -> dict[str, Any]:
    """Coverage contract for one catalog concern."""
    sem = semantics_for(concern_id)
    family = CONCERN_DEFAULT_FAMILY.get(concern_id) or resolve_comparison_family(
        concern_id, primary_focus=str(sem.get("fallback_focus") or "")
    )
    prim_id = FOCUS_TO_PRIMITIVE.get(str(sem.get("fallback_focus") or ""), "MAINTAIN")
    prim = COACHING_PRIMITIVES.get(prim_id) or COACHING_PRIMITIVES["MAINTAIN"]
    qtype = str(sem.get("type") or "")
    safety = qtype == "SAFETY" or concern_id.startswith("PAIN") or concern_id in (
        "SPEAKING_DISCOMFORT",
        "PERSISTENT_HOARSENESS",
    )
    return {
        "concern_id": concern_id,
        "semantic_type": qtype,
        "candidate_factors": list(sem.get("candidate_factors") or []),
        "fallback_focus": sem.get("fallback_focus"),
        "response_policy": "SAFETY_STOP" if safety else "GUIDED_EXPERIMENT",
        "comparison_family": family,
        "success_policy": list(prim.get("success_cues") or []),
        "safety_policy": "BLOCK_EXPERIMENT" if safety else "ALLOW_LOW_RISK",
        "what_to_change": (COMPARISON_FAMILIES.get(family) or {}).get("what_to_change"),
        "action_or_comparison": family,
        "primitive_id": prim_id,
    }


def route_other_concern_text(text: str) -> str:
    """Deterministic keyword routing for OTHER_CONCERN free text."""
    t = str(text or "").lower()
    if any(k in t for k in ("통증", "아픔", "쉼", "쉬어야", "아파")):
        return "safety"
    if any(k in t for k in ("고음", "높은 음", "높은음", "하이")):
        return "high_note"
    if any(k in t for k in ("힘", "목 힘", "지침", "피곤", "피로")):
        return "effort"
    if any(k in t for k in ("얇", "답답", "콧소", "숨", "거칠", "음색", "밝", "어두")):
        return "timbre"
    if any(k in t for k in ("음정", "흔들", "비브라", "강약", "연결", "성구")):
        return "control"
    return "other"
