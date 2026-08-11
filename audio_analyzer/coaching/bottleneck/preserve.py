"""Preserve vs Modify — coach must not tell user to undo strengths."""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.audit.consistency import PRIMARY_MODIFY_FAMILY


def build_preserve_modify(
    profile: dict[str, Any],
    episodes: list[dict[str, Any]],
    primary: Optional[dict[str, Any]],
    target_episode: Optional[dict[str, Any]] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dims = profile.get("dimensions") or {}
    plane = profile.get("contact_effort_plane") or {}
    matrix = profile.get("criteria_matrix") or []
    preserve: list[dict[str, Any]] = []
    modify: list[dict[str, Any]] = []
    primary_modify: list[dict[str, Any]] = []
    secondary_modify: list[dict[str, Any]] = []

    contact = dims.get("glottal_contact_profile") or {}
    effort = dims.get("vocal_effort_strain") or {}
    regularity = dims.get("phonation_regularity") or {}
    vibrato = dims.get("vibrato_control") or {}

    fm = (target_episode or {}).get("feature_matrix") or {}
    target_effort = ((fm.get("effort") or {}).get("strain_like") or 0)
    target_firm = ((fm.get("source") or {}).get("contact_firmness") or 0)
    target_period = ((fm.get("regularity") or {}).get("periodicity"))
    target_rough = bool((fm.get("regularity") or {}).get("roughness"))

    vib_suf = None
    for row in matrix:
        if row.get("dimension_id") == "vibrato_control":
            vib_suf = (row.get("measurement_sufficiency") or "").upper()
            break

    # Target-episode evidence preferred over global "firm song" heuristics
    if target_episode:
        if target_firm >= 0.5 and target_effort < 0.4 and not target_rough:
            preserve.append(
                {
                    "id": "contact_firmness",
                    "label": "이 구간의 안정적인 성대 접촉 관련 패턴",
                    "action": "PRESERVE",
                    "why": "대상 episode에서 단단함이 effort 과다와 함께 나타나지 않았어요.",
                    "episode_id": target_episode.get("episode_id"),
                }
            )
        if target_period is not None and target_period >= 8 and not target_rough:
            preserve.append(
                {
                    "id": "periodicity",
                    "label": "이 구간의 안정적인 주기성",
                    "action": "PRESERVE",
                    "why": "대상 episode에서 진동 규칙성이 비교적 유지됐어요.",
                    "episode_id": target_episode.get("episode_id"),
                }
            )
        if target_effort >= 0.4:
            secondary_modify.append(
                {
                    "id": "high_note_entry_effort",
                    "label": "이 구간에서 급격히 증가하는 힘",
                    "action": "MODIFY",
                    "why": (
                        "접촉을 약하게 만들기보다 이 구간에서 "
                        "불필요하게 증가하는 effort를 먼저 줄여보세요."
                    ),
                    "episode_id": target_episode.get("episode_id"),
                    "triggered_by": "target_effort_secondary",
                }
            )
    else:
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

    # Vibrato preserve only when observed AND measurement sufficient
    vib_ok = vibrato.get("status") == "OBSERVED" and vib_suf not in (
        "INSUFFICIENT",
        "UNAVAILABLE",
    )
    if vib_suf is None:
        vib_ok = vibrato.get("status") == "OBSERVED" and vibrato.get("confidence_label") != "low"
    if vib_ok and not any(p["id"] == "vibrato" for p in preserve):
        preserve.append(
            {
                "id": "vibrato",
                "label": "관찰된 비브라토 패턴",
                "action": "PRESERVE",
                "why": "규칙적 비브라토는 불안정성으로 보지 않아요.",
            }
        )

    def _pm(item: dict[str, Any]) -> None:
        item = {**item, "triggered_by": (primary or {}).get("id")}
        primary_modify.append(item)

    if primary and primary.get("id") == "EXCESS_EFFORT_HIGH_NOTE":
        _pm(
            {
                "id": "high_note_entry_effort",
                "label": "고음 진입 때 급격히 증가하는 힘",
                "action": "MODIFY",
                "why": (
                    "접촉을 약하게 만들기보다 고음 진입 시 "
                    "불필요하게 증가하는 effort를 먼저 줄여보세요."
                ),
                "episode_id": (target_episode or {}).get("episode_id"),
            }
        )

    if primary and primary.get("id") == "GENERAL_EXCESS_EFFORT":
        _pm(
            {
                "id": "general_effort",
                "label": "여러 구간에서 반복되는 힘 과다",
                "action": "MODIFY",
                "why": "고음만이 아니라 전반적인 effort를 낮추는 방향으로 짧게 연습해보세요.",
            }
        )

    if primary and primary.get("id") == "REGISTER_TRANSITION_DISRUPTION":
        _pm(
            {
                "id": "register_transition",
                "label": "음역 전환 시 source·주기성 흔들림",
                "action": "MODIFY",
                "why": "전환 구간을 작은 범위의 사이렌으로 부드럽게 연결해보세요.",
                "episode_id": (target_episode or {}).get("episode_id"),
            }
        )

    if primary and primary.get("id") == "AIR_LEAKAGE":
        _pm(
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
        _pm(
            {
                "id": "resonance_strategy",
                "label": "고음·중역 공명 전략",
                "action": "MODIFY",
                "why": "모음·공명 위치를 살짝 바꿔 중역 존재감을 탐색해보세요.",
                "episode_id": (target_episode or {}).get("episode_id"),
            }
        )

    if primary and primary.get("id") == "ABRUPT_ONSET":
        _pm(
            {
                "id": "onset",
                "label": "급격한 소리 시작",
                "action": "MODIFY",
                "why": "허밍으로 부드럽게 시작해 모음으로 열어보세요.",
            }
        )

    if primary and primary.get("id") == "APERIODIC_ROUGHNESS":
        _pm(
            {
                "id": "roughness",
                "label": "불규칙·거친 음질 경향",
                "action": "MODIFY",
                "why": "부드러운 지속음으로 주기성이 유지되는지 짧게 확인해보세요.",
                "episode_id": (target_episode or {}).get("episode_id"),
            }
        )

    # Primary-linked modify must lead; drop secondary duplicates of primary ids
    primary_ids = {m["id"] for m in primary_modify}
    secondary_modify = [m for m in secondary_modify if m["id"] not in primary_ids]
    # If primary is AIR_LEAKAGE, effort secondary stays secondary (not first)
    modify = primary_modify + secondary_modify

    # Hard invariant: first modify matches primary family when primary exists
    if primary and primary.get("id") in PRIMARY_MODIFY_FAMILY and modify:
        want = PRIMARY_MODIFY_FAMILY[primary["id"]]
        if modify[0].get("id") not in want and modify[0].get("triggered_by") != primary.get("id"):
            matched = [m for m in modify if m.get("id") in want]
            rest = [m for m in modify if m not in matched]
            if matched:
                modify = matched + rest

    if target_episode and target_firm < 0.35 and target_rough:
        preserve = [p for p in preserve if p["id"] != "contact_firmness"]

    if any(p["id"] == "contact_firmness" for p in preserve):
        modify = [m for m in modify if m["id"] != "weaken_contact"]

    return preserve[:4], modify[:3]
