# -*- coding: utf-8 -*-
"""Personal Vocal Baseline — separate from Singer Identity. Schema/artifact only (not production)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Axes that may be described as increase/decrease/change — never auto "improvement"
DESCRIPTIVE_AXES = frozenset(
    {
        "brightness",
        "source_balance",
        "timbre",
        "presence",
        "stability",
        "breathiness",
        "contact",
    }
)

# Functional axes that MAY be called improvement only with an explicit user goal
GOAL_AWARE_AXES = frozenset(
    {
        "register_connection",
        "effort",  # only with goal + functional context — never unconditional
    }
)


@dataclass
class PersonalVocalRecordingSnapshot:
    singer_id: str
    recording_id: str
    recorded_at: Optional[str] = None
    analyzer_version: Optional[str] = None
    canonical: dict[str, Any] = field(default_factory=dict)
    goal: Optional[Any] = None
    analysis_quality: Optional[str] = None
    experimental: bool = True
    note: str = "EXPERIMENTAL_NOT_PRODUCTION"


@dataclass
class PersonalVocalBaseline:
    singer_id: str
    recording_count: int
    period: dict[str, Any]
    axis_distributions: dict[str, Any]
    reliable_axes: list[str]
    baseline_version: str = "personal-vocal-baseline-v0-experimental"
    experimental: bool = True
    production_connected: bool = False
    identity_embedding_used_as_quality: bool = False
    note: str = (
        "Distribution over currently registered recordings only. "
        "Not a claim about the singer's average voice in general."
    )


def describe_axis_change(
    axis: str,
    before: Any,
    after: Any,
    *,
    user_goal: Optional[str] = None,
) -> dict[str, Any]:
    """
    Never call descriptive timbre/brightness/source_balance changes 'improvement'.
    Goal-aware axes may return improvement only with an explicit goal direction.
    """
    if before == after:
        kind = "unchanged"
    else:
        kind = "change"
    out: dict[str, Any] = {
        "axis": axis,
        "before": before,
        "after": after,
        "expression": kind,
        "called_improvement": False,
    }
    if axis in DESCRIPTIVE_AXES:
        out["expression"] = "increase_or_decrease_or_change"
        out["forbidden_labels"] = ["improvement", "worse", "better"]
        out["called_improvement"] = False
        return out
    if axis == "brightness" or axis == "source_balance":
        out["called_improvement"] = False
        return out
    if axis in GOAL_AWARE_AXES and user_goal:
        # Explicit goal required; this helper does not invent goals.
        out["expression"] = "goal_relative_possible"
        out["called_improvement"] = False  # still false unless caller sets with goal check
        out["requires_user_goal"] = True
        return out
    out["called_improvement"] = False
    return out


def brightness_change_is_improvement(before: Any, after: Any) -> bool:
    """Always False — brightness is descriptive."""
    return False


def source_balance_change_is_improvement(before: Any, after: Any) -> bool:
    """Always False — source_balance is descriptive."""
    return False


def identity_profile_is_vocal_baseline() -> bool:
    return False


def _axis_value(canonical: dict[str, Any], axis: str) -> Any:
    block = canonical.get(axis)
    if isinstance(block, dict):
        return block.get("label") or block.get("status") or block.get("value")
    return block


def build_experimental_baseline_preview(
    *,
    singer_id: str,
    recordings: list[Any],
    reviews_path: Path,
) -> dict[str, Any]:
    reviews_by_id: dict[str, dict[str, Any]] = {}
    if reviews_path.exists():
        data = json.loads(reviews_path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("audios") or data.get("reviews") or []
        for item in items:
            aid = item.get("audio_id")
            if aid:
                reviews_by_id[aid] = item
            sha = item.get("sha256")
            if sha:
                reviews_by_id[sha] = item

    snapshots: list[dict[str, Any]] = []
    axis_values: dict[str, list[Any]] = {}
    for r in recordings:
        aid = getattr(r, "audio_id", None) or r.get("audio_id")
        sha = getattr(r, "sha256", None) or r.get("sha256")
        fname = getattr(r, "filename", None) or r.get("filename")
        rev = reviews_by_id.get(aid) or reviews_by_id.get(sha) or {}
        canonical = rev.get("canonical") or {}
        # also accept flattened presentation fields
        if not canonical and rev.get("effort_status"):
            canonical = {
                "effort": rev.get("effort_status"),
                "register_connection": rev.get("register_connection"),
                "breathiness": rev.get("breathiness"),
                "brightness": rev.get("brightness"),
                "source_balance": rev.get("source_balance"),
                "contact": rev.get("contact"),
                "stability": rev.get("stability"),
                "presence": rev.get("presence"),
            }
        snap = PersonalVocalRecordingSnapshot(
            singer_id=singer_id,
            recording_id=aid,
            recorded_at=None,  # no date → no time-trend
            analyzer_version=rev.get("analyzer_version") or rev.get("pipeline_version"),
            canonical={
                k: _axis_value(canonical, k) if isinstance(canonical.get(k), dict) else canonical.get(k)
                for k in (
                    "effort",
                    "contact",
                    "breathiness",
                    "register_connection",
                    "source_balance",
                    "stability",
                    "brightness",
                    "presence",
                )
                if k in canonical or True
            },
            goal=None,
            analysis_quality=rev.get("analysis_quality") or rev.get("quality"),
        )
        # clean Nones
        snap.canonical = {k: v for k, v in snap.canonical.items() if v is not None}
        for axis, val in snap.canonical.items():
            axis_values.setdefault(axis, []).append(val)
        snapshots.append({**asdict(snap), "filename": fname})

    distributions: dict[str, Any] = {}
    reliable: list[str] = []
    for axis, vals in axis_values.items():
        counts: dict[str, int] = {}
        for v in vals:
            key = str(v)
            counts[key] = counts.get(key, 0) + 1
        distributions[axis] = {
            "counts": counts,
            "n": len(vals),
            "expression_rule": "descriptive_change_only"
            if axis in DESCRIPTIVE_AXES or axis in ("brightness", "source_balance")
            else "goal_aware_only",
        }
        if len(vals) >= 3:
            reliable.append(axis)

    baseline = PersonalVocalBaseline(
        singer_id=singer_id,
        recording_count=len(snapshots),
        period={"start": None, "end": None, "note": "No recording dates — time trend forbidden"},
        axis_distributions=distributions,
        reliable_axes=reliable,
    )

    return {
        "experimental": True,
        "production_connected": False,
        "uses_identity_embedding_as_vocal_quality": False,
        "uses_existing_canonical_analysis": True,
        "calls_descriptive_timbre_change_improvement": False,
        "identity_layer": "WHO — Singer Identity selects whose history",
        "vocal_layer": "HOW — VAgent analyzer describes how they sang",
        "layers_separate": True,
        "baseline": asdict(baseline),
        "snapshots": snapshots,
        "safety": {
            "brightness_change_is_improvement": False,
            "source_balance_change_is_improvement": False,
            "pain_as_performance_improvement_forbidden": True,
            "effort_decrease_not_always_improvement": True,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def write_baseline_preview_artifacts(output_dir: Path, preview: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "personal_vocal_baseline_preview.json").write_text(
        json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    dist = (preview.get("baseline") or {}).get("axis_distributions") or {}
    lines = [
        "# 개인 발성 기준선 — 실험용 (EXPERIMENTAL / NOT PRODUCTION)",
        "",
        "> 현재 등록된 녹음에서 나타난 분포입니다. "
        "평균적인 당신의 발성이라고 일반화하지 않습니다.",
        "",
        f"확정 음원: **{(preview.get('baseline') or {}).get('recording_count', 0)}**",
        "",
        "Singer Identity와 Personal Vocal Baseline은 **별개**입니다.",
        "",
        "## 축 분포 (registered recordings only)",
        "",
    ]
    labels_ko = {
        "effort": "힘 사용",
        "register_connection": "성구 연결",
        "breathiness": "숨 섞임",
        "brightness": "밝기",
        "source_balance": "소스 밸런스",
        "contact": "접촉",
        "stability": "안정성",
        "presence": "존재감",
    }
    for axis, ko in labels_ko.items():
        block = dist.get(axis) or {}
        counts = block.get("counts") or {}
        if not counts:
            lines.append(f"- {ko} (`{axis}`): _(no data)_")
            continue
        parts = ", ".join(f"{k}×{v}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))
        lines.append(f"- {ko} (`{axis}`): {parts}")
    lines += [
        "",
        "## 표현 규칙",
        "",
        "- brightness / source_balance / timbre: **증가·감소·변화**만 (개선/악화 금지)",
        "- 날짜 없음 → **이전→최근 개선** 계산 금지",
        "- production VAgent 연결: **NO**",
        "",
    ]
    (output_dir / "personal_vocal_baseline_preview.md").write_text("\n".join(lines), encoding="utf-8")
