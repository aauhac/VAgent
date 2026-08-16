# -*- coding: utf-8 -*-
"""Canonical-only per-audio review (concern-independent)."""

from __future__ import annotations

from typing import Any, Optional

from scripts.vocal_behavioral_audit.diagnose import axes_from_snap, _bucket_float
from scripts.vocal_behavioral_audit.report_labels import (
    axis_explanation,
    display_axis_value,
    natural_one_line_summary,
)


UNKNOWN_STATES = {
    "",
    "UNKNOWN",
    "UNAVAILABLE",
    "UNRESOLVED",
    "NONE",
    "N/A",
}


def _timbre_consistency_status(timbre: dict[str, Any]) -> str:
    axes = timbre.get("axes") or {}
    raw = axes.get("timbre_consistency") or axes.get("consistency")
    if isinstance(raw, dict):
        if raw.get("continuum") is not None:
            return _bucket_float(raw.get("continuum"))
        return str(raw.get("status") or "UNKNOWN").upper()
    if raw is None:
        return "UNKNOWN"
    try:
        return _bucket_float(raw)
    except Exception:
        return str(raw or "UNKNOWN").upper()


def _is_unknown(v: Any) -> bool:
    return str(v or "").upper() in UNKNOWN_STATES


def _conf(obj: dict[str, Any], *keys: str) -> str:
    for k in keys:
        c = str(obj.get(k) or "").strip()
        if c:
            return c
    return ""


def build_canonical_review(
    *,
    audio_id: str,
    path: str,
    sha256: str,
    snap: dict[str, Any],
    axes: Optional[dict[str, Any]] = None,
    duration_sec: Optional[float] = None,
    sample_rate: Optional[int] = None,
    analysis_meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build structured review from canonical snapshot only — never from concerns."""
    axes = axes or axes_from_snap(snap)
    effort = snap.get("effort") or {}
    contact = snap.get("contact") or {}
    breath = snap.get("breathiness") or {}
    register = snap.get("register") or {}
    sb = snap.get("source_balance") or {}
    stability = snap.get("stability") or {}
    timbre = snap.get("timbre") or {}
    high = snap.get("high_note") or {}
    avail = snap.get("availability") or {}

    canonical = {
        "effort": {
            "status": axes.get("effort_status"),
            "confidence": axes.get("effort_confidence") or _conf(effort, "confidence_label"),
            "reliable": bool(axes.get("effort_reliable")),
            "description": axis_explanation("effort", axes.get("effort_status")),
            "display": display_axis_value("effort", axes.get("effort_status")),
        },
        "contact": {
            "status": axes.get("contact"),
            "confidence": _conf(contact, "confidence_label"),
            "description": axis_explanation("contact", axes.get("contact")),
            "display": display_axis_value("contact", axes.get("contact")),
        },
        "breathiness": {
            "status": axes.get("breathiness"),
            "confidence": _conf(breath, "confidence_label"),
            "description": axis_explanation("breathiness", axes.get("breathiness")),
            "display": display_axis_value("breathiness", axes.get("breathiness")),
        },
        "register_connection": {
            "status": axes.get("register_connection") or axes.get("register"),
            "confidence": _conf(register, "confidence_label"),
            "description": axis_explanation(
                "register_connection", axes.get("register_connection") or axes.get("register")
            ),
            "display": display_axis_value(
                "register_connection", axes.get("register_connection") or axes.get("register")
            ),
        },
        "source_balance": {
            "status": axes.get("source_balance"),
            "confidence": _conf(sb, "confidence_label"),
            "description": axis_explanation("source_balance", axes.get("source_balance")),
            "display": display_axis_value("source_balance", axes.get("source_balance")),
        },
        "stability": {
            "status": axes.get("stability"),
            "confidence": _conf(stability, "confidence_label"),
            "description": axis_explanation("stability", axes.get("stability")),
            "display": display_axis_value("stability", axes.get("stability")),
        },
        "presence": {
            "status": axes.get("presence"),
            "confidence": "",
            "raw": timbre.get("presence"),
            "description": axis_explanation("presence", axes.get("presence")),
            "display": display_axis_value("presence", axes.get("presence")),
        },
        "brightness": {
            "status": axes.get("brightness"),
            "confidence": "",
            "raw": timbre.get("brightness"),
            "description": axis_explanation("brightness", axes.get("brightness")),
            "display": display_axis_value("brightness", axes.get("brightness")),
        },
        "airiness": {
            "status": axes.get("airiness"),
            "confidence": "",
            "description": axis_explanation("airiness", axes.get("airiness")),
            "display": display_axis_value("airiness", axes.get("airiness")),
        },
        "texture": {
            "status": axes.get("texture"),
            "confidence": "",
            "description": _axis_desc("texture", axes.get("texture")),
        },
        "harmonic_concentration": {
            "status": axes.get("harmonic_concentration"),
            "confidence": "",
            "description": _axis_desc("harmonic", axes.get("harmonic_concentration")),
        },
        "timbre_consistency": {
            "status": _timbre_consistency_status(timbre),
            "confidence": "",
            "description": "",
        },
        "high_note": {
            "available": bool(axes.get("high_note_available") or high.get("available") or avail.get("high_note")),
            "status": "AVAILABLE" if axes.get("high_note_available") else "UNAVAILABLE",
            "description": "고음 구간 분석 가능" if axes.get("high_note_available") else "고음 직접 분석 지표가 제한적",
        },
    }

    salient = _rank_salient(canonical)
    maintained = _maintained_features(canonical)
    uncertain = [
        k
        for k, v in canonical.items()
        if k != "high_note" and _is_unknown((v or {}).get("status"))
    ]
    one_line = natural_one_line_summary(canonical)
    flags = _review_flags(canonical, uncertain)

    meta = analysis_meta or {}
    return {
        "audio_id": audio_id,
        "file": path,
        "sha256": sha256,
        "audio_info": {
            "duration_sec": duration_sec,
            "sample_rate": sample_rate,
            "analysis_status": "OK" if snap else "MISSING",
            "source": meta.get("source") or meta.get("hint_hit") and "hint" or meta.get("cache_hit") and "cache" or "fresh",
            "analysis_version": meta.get("analysis_version") or "",
            "cache_hit": bool(meta.get("cache_hit")),
            "original_filename": meta.get("original_filename"),
        },
        "canonical": canonical,
        "axes": axes,
        "salient_features": salient,
        "maintained_features": maintained,
        "uncertain_axes": uncertain,
        "one_line_summary": one_line,
        "review_flags": flags,
        # Explicit: no concern fields in audio truth
        "concern_independent": True,
    }


def build_one_line_summary(canonical: dict[str, Any]) -> str:
    """Backward-compatible wrapper — natural Korean, not axis-fragment concat."""
    return natural_one_line_summary(canonical)


def _axis_desc(kind: str, status: Any) -> str:
    return axis_explanation(kind, status)


def _rank_salient(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    order = [
        ("register_connection", {"DISRUPTED": 100, "PARTIAL": 80, "CONNECTED": 40}),
        ("stability", {"UNSTABLE": 90}),
        ("effort", {"HIGH": 85, "MODERATE": 70}),
        ("contact", {"FIRM": 60, "LIGHT": 50}),
        ("breathiness", {"HIGH": 75, "LOW": 35}),
        ("presence", {"LOW": 55, "HIGH": 50}),
        ("brightness", {"LOW": 45, "HIGH": 45}),
        ("source_balance", {"CHEST_DOMINANT": 40, "HEAD_DOMINANT": 40, "CONFLICTED": 50}),
    ]
    for key, weights in order:
        block = canonical.get(key) or {}
        st = str(block.get("status") or "").upper()
        if _is_unknown(st):
            continue
        if key == "effort" and not block.get("reliable"):
            # low-confidence effort should not dominate salience
            continue
        conf = str(block.get("confidence") or "").lower()
        if conf == "low" and st not in ("DISRUPTED", "UNSTABLE", "HIGH"):
            continue
        w = weights.get(st)
        if w:
            scored.append(
                (
                    w,
                    {
                        "axis": key,
                        "status": st,
                        "text": block.get("description") or st,
                    },
                )
            )
    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:5]]


def _maintained_features(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    effort = canonical.get("effort") or {}
    if effort.get("reliable") and str(effort.get("status") or "").upper() == "LOW":
        out.append({"axis": "effort", "text": "전반적인 힘 사용이 낮은 편으로 유지되는 특징"})
    stab = canonical.get("stability") or {}
    if str(stab.get("status") or "").upper() == "STABLE":
        out.append({"axis": "stability", "text": "발성 안정성이 유지되는 편"})
    breath = canonical.get("breathiness") or {}
    if str(breath.get("status") or "").upper() == "LOW":
        out.append({"axis": "breathiness", "text": "숨 섞임이 적은 편"})
    reg = canonical.get("register_connection") or {}
    if str(reg.get("status") or "").upper() == "CONNECTED":
        out.append({"axis": "register_connection", "text": "성구 연결이 비교적 이어지는 편"})
    return out


def _review_flags(canonical: dict[str, Any], uncertain: list[str]) -> list[str]:
    flags: list[str] = []
    reg = str((canonical.get("register_connection") or {}).get("status") or "").upper()
    if reg == "CONNECTED":
        flags.append("RARE_REGISTER_CONNECTED")
    if reg in ("DISRUPTED", "PARTIAL"):
        flags.append("REGISTER_LIMITATION_PRESENT")
    if len(uncertain) >= 4:
        flags.append("UNKNOWN_HEAVY")
    effort = canonical.get("effort") or {}
    if str(effort.get("status") or "").upper() in ("HIGH", "MODERATE") and effort.get("reliable"):
        flags.append("RELIABLE_ELEVATED_EFFORT")
    bright = str((canonical.get("brightness") or {}).get("status") or "").upper()
    if bright == "HIGH":
        flags.append("RARE_BRIGHTNESS_HIGH")
    return flags


def actionable_limitations(canonical: dict[str, Any]) -> list[dict[str, str]]:
    """Priority review sections from canonical evidence only."""
    out: list[dict[str, str]] = []
    reg = canonical.get("register_connection") or {}
    st = str(reg.get("status") or "").upper()
    if st == "DISRUPTED":
        out.append(
            {
                "title": "성구 연결",
                "body": "음역이 올라가는 과정에서 연결 변화가 급격한 구간이 보여요. 중음에서 위쪽으로 작은 강도로 이어 올리는 쪽을 우선 확인해보세요.",
            }
        )
    elif st == "PARTIAL":
        out.append(
            {
                "title": "성구 연결",
                "body": "성구 연결이 일부 구간에서만 안정적으로 이어져요. 전환 구간을 짧게 반복해보는 쪽이 도움이 될 수 있어요.",
            }
        )
    stab = canonical.get("stability") or {}
    if str(stab.get("status") or "").upper() in ("UNSTABLE", "UNSTABLE_LIKE"):
        out.append(
            {
                "title": "안정성",
                "body": "일부 구간에서 안정성이 떨어지는 패턴이 보여요. 길게 버티기보다 짧은 유지부터 확인해보세요.",
            }
        )
    effort = canonical.get("effort") or {}
    if effort.get("reliable") and str(effort.get("status") or "").upper() in ("HIGH", "MODERATE"):
        out.append(
            {
                "title": "힘 사용",
                "body": "힘 사용이 커지는 경향이 보여요. 음량을 키우지 않은 채 편한 강도를 먼저 찾는 쪽이 좋아요.",
            }
        )
    return out
