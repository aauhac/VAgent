"""Preserve vs Modify — coach must not tell user to undo strengths."""

from __future__ import annotations

from typing import Any, Optional


def build_preserve_modify(
    profile: dict[str, Any],
    episodes: list[dict[str, Any]],
    primary: Optional[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dims = profile.get("dimensions") or {}
    plane = profile.get("contact_effort_plane") or {}
    preserve: list[dict[str, Any]] = []
    modify: list[dict[str, Any]] = []

    contact = dims.get("glottal_contact_profile") or {}
    effort = dims.get("vocal_effort_strain") or {}
    regularity = dims.get("phonation_regularity") or {}
    vibrato = dims.get("vibrato_control") or {}

    # Preserve firm contact when effort low
    if plane.get("firm_high_strain_low") or (
        contact.get("continuum_0_to_1") is not None
        and contact.get("continuum_0_to_1") > 0.55
        and effort.get("status") == "LOW"
    ):
        preserve.append(
            {
                "id": "contact_firmness",
                "label": "안정적인 성대 접촉 관련 패턴",
                "action": "PRESERVE",
                "why": "단단함이 effort 과다와 함께 나타나지 않았어요.",
            }
        )

    if regularity.get("status") == "STABLE":
        preserve.append(
            {
                "id": "periodicity",
                "label": "안정적인 주기성",
                "action": "PRESERVE",
                "why": "진동 규칙성이 비교적 유지됐어요.",
            }
        )

    if vibrato.get("status") == "OBSERVED":
        preserve.append(
            {
                "id": "vibrato",
                "label": "관찰된 비브라토 패턴",
                "action": "PRESERVE",
                "why": "규칙적 비브라토는 불안정성으로 보지 않아요.",
            }
        )

    if primary and primary.get("id") == "EXCESS_EFFORT_HIGH_NOTE":
        modify.append(
            {
                "id": "high_note_entry_effort",
                "label": "고음 진입 때 급격히 증가하는 힘",
                "action": "MODIFY",
                "why": (
                    "접촉을 약하게 만들기보다 고음 진입 시 "
                    "불필요하게 증가하는 effort를 먼저 줄여보세요."
                ),
            }
        )
        # coherent: if modifying effort, keep contact if firm-without-strain
        if plane.get("firm_high_strain_low") or plane.get("firm_high_strain_high"):
            if not any(p["id"] == "contact_firmness" for p in preserve):
                preserve.append(
                    {
                        "id": "contact_firmness",
                        "label": "성대 접촉 관련 패턴",
                        "action": "PRESERVE",
                        "why": "고음에서도 접촉 관련 패턴 자체는 유지되는 편이에요.",
                    }
                )

    if primary and primary.get("id") == "REGISTER_TRANSITION_DISRUPTION":
        modify.append(
            {
                "id": "register_transition",
                "label": "음역 전환 시 source·주기성 흔들림",
                "action": "MODIFY",
                "why": "전환 구간을 작은 범위의 사이렌으로 부드럽게 연결해보세요.",
            }
        )

    if primary and primary.get("id") == "AIR_LEAKAGE":
        modify.append(
            {
                "id": "air_leakage",
                "label": "기식성·누출 경향",
                "action": "MODIFY",
                "why": "부드러운 시작으로 소리가 모이는지 짧게 확인해보세요.",
            }
        )

    if primary and primary.get("id") in (
        "RESONANCE_MID_PRESENCE_LOSS",
        "RESONANCE_HIGH_NOTE_COLLAPSE",
    ):
        modify.append(
            {
                "id": "resonance_strategy",
                "label": "고음·중역 공명 전략",
                "action": "MODIFY",
                "why": "모음·공명 위치를 살짝 바꿔 중역 존재감을 탐색해보세요.",
            }
        )

    if primary and primary.get("id") == "ABRUPT_ONSET":
        modify.append(
            {
                "id": "onset",
                "label": "급격한 소리 시작",
                "action": "MODIFY",
                "why": "허밍으로 부드럽게 시작해 모음으로 열어보세요.",
            }
        )

    # Mutual coherence: don't modify contact weaker if preserve contact
    if any(p["id"] == "contact_firmness" for p in preserve):
        modify = [m for m in modify if m["id"] != "weaken_contact"]

    return preserve[:4], modify[:3]
