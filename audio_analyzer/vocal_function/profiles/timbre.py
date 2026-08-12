"""Derived Timbre Profile (v2.11) — characteristics, not good/bad quality."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.vocal_function.evidence.families import leakage_like
from audio_analyzer.vocal_evidence.phonation_quality import classify_rough_segment


def _obs(seg: dict[str, Any]) -> dict[str, Any]:
    return seg.get("observations") or {}


def _vocal_ok(seg: dict[str, Any]) -> bool:
    if not seg.get("valid"):
        return False
    ve = seg.get("vocal_evidence") or {}
    if not ve.get("vocal_specific", True):
        return False
    if float(ve.get("accompaniment_match") or 0) >= 0.55:
        return False
    return True


def _vals(segs: list[dict[str, Any]], key: str) -> list[float]:
    out = []
    for s in segs:
        v = _obs(s).get(key)
        if v is None:
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            pass
    return out


def _med(vals: list[float]) -> Optional[float]:
    if not vals:
        return None
    return float(np.median(np.asarray(vals, dtype=float)))


def _rank01(vals: list[float], value: Optional[float]) -> Optional[float]:
    """Within-recording percentile rank in [0,1]."""
    if value is None or len(vals) < 3:
        return None
    arr = np.asarray(vals, dtype=float)
    return float(np.mean(arr <= value))


def _axis_label(kind: str, pos: Optional[float]) -> str:
    if pos is None:
        return "판단 부족"
    if kind == "brightness":
        if pos < 0.35:
            return "어두운 편"
        if pos > 0.65:
            return "밝은 편"
        return "중간"
    if kind == "presence":
        if pos < 0.35:
            return "낮은 편"
        if pos > 0.65:
            return "높은 편"
        return "보통"
    if kind == "airiness":
        if pos < 0.35:
            return "적은 편"
        if pos > 0.65:
            return "많은 편"
        return "보통"
    if kind == "texture":
        if pos < 0.35:
            return "매끈한 편"
        if pos > 0.65:
            return "거친 질감"
        return "보통"
    if kind == "harmonic":
        if pos < 0.35:
            return "분산된 편"
        if pos > 0.65:
            return "집중된 편"
        return "보통"
    if kind == "consistency":
        if pos < 0.35:
            return "변화가 큰 편"
        if pos > 0.65:
            return "일관된 편"
        return "보통"
    return "보통"


def _brightness_score(segs: list[dict[str, Any]]) -> tuple[Optional[float], dict[str, Any]]:
    """Multi-family brightness; not single centroid."""
    cents = _vals(segs, "spectral_centroid_hz")
    tilts = _vals(segs, "spectral_tilt_db_per_oct")
    e48 = _vals(segs, "energy_4_8k")
    e24 = _vals(segs, "energy_2_4k")
    alpha = _vals(segs, "alpha_ratio_db")
    families = 0
    scores: list[float] = []
    # Use within-set z-like ranks via median comparisons across families
    if len(cents) >= 2:
        families += 1
        # map typical singing centroid 800–3500 → 0..1 soft
        c = _med(cents) or 1500.0
        scores.append(max(0.0, min(1.0, (c - 900.0) / 2000.0)))
    if len(tilts) >= 2:
        families += 1
        t = _med(tilts) or -12.0
        # less negative / higher tilt → brighter-ish
        scores.append(max(0.0, min(1.0, (t + 20.0) / 20.0)))
    if len(e48) >= 2 and len(e24) >= 2:
        families += 1
        ratio = float((_med(e48) or 0) / ((_med(e24) or 0) + 1e-6))
        scores.append(max(0.0, min(1.0, ratio / 1.2)))
    elif len(e48) >= 2:
        families += 1
        scores.append(max(0.0, min(1.0, (_med(e48) or 0) / 0.25)))
    if len(alpha) >= 2:
        families += 1
        a = _med(alpha) or 0.0
        scores.append(max(0.0, min(1.0, (a + 5.0) / 25.0)))
    if families < 2 or not scores:
        return None, {"families": families, "reason": "insufficient_multi_family"}
    return float(np.mean(scores)), {"families": families, "components": len(scores)}


def _presence_score(segs: list[dict[str, Any]]) -> tuple[Optional[float], dict[str, Any]]:
    e24 = _vals(segs, "energy_2_4k")
    e12 = _vals(segs, "energy_1_2k")
    if len(e24) < 2 and len(e12) < 2:
        return None, {"families": 0}
    parts = []
    fam = 0
    if e24:
        fam += 1
        parts.append(max(0.0, min(1.0, (_med(e24) or 0) / 0.28)))
    if e12:
        fam += 1
        parts.append(max(0.0, min(1.0, (_med(e12) or 0) / 0.32)))
    return float(np.mean(parts)), {"families": fam}


def _airiness_score(segs: list[dict[str, Any]]) -> tuple[Optional[float], dict[str, Any]]:
    if not segs:
        return None, {"source": "breathiness_engine"}
    hits = sum(1 for s in segs if leakage_like(s))
    rate = float(hits / len(segs))
    # also soft continuous cue from h1h2 if present
    h1h2 = _vals(segs, "raw_h1_h2_proxy_db")
    cont = rate
    if h1h2:
        h = _med(h1h2) or 0.0
        cont = 0.6 * rate + 0.4 * max(0.0, min(1.0, (h - 1.0) / 10.0))
    return cont, {"source": "breathiness_engine", "leakage_rate": rate}


def _texture_score(segs: list[dict[str, Any]]) -> tuple[Optional[float], dict[str, Any]]:
    if not segs:
        return None, {"source": "regularity_roughness"}
    hits = 0
    n = 0
    for s in segs:
        n += 1
        if classify_rough_segment(s).get("verdict") == "POSITIVE":
            hits += 1
    if n <= 0:
        return None, {"source": "regularity_roughness"}
    return float(hits / n), {"source": "regularity_roughness", "n": n}


def _harmonic_concentration(segs: list[dict[str, Any]]) -> tuple[Optional[float], dict[str, Any]]:
    """Concentration vs spread — NOT 'rich = good'."""
    e24 = _vals(segs, "energy_2_4k")
    e12 = _vals(segs, "energy_1_2k")
    e48 = _vals(segs, "energy_4_8k")
    cpp = _vals(segs, "cepstral_prominence_proxy_db") or _vals(segs, "periodicity_primary_db")
    if not e24 and not cpp:
        return None, {}
    # higher mid-band share + stronger periodicity → more concentrated
    parts = []
    if e24 and e12:
        share = float((_med(e24) or 0) / ((_med(e12) or 0) + (_med(e24) or 0) + (_med(e48) or 0) + 1e-6))
        parts.append(max(0.0, min(1.0, share / 0.55)))
    if cpp:
        parts.append(max(0.0, min(1.0, ((_med(cpp) or 0) - 4.0) / 12.0)))
    if not parts:
        return None, {}
    return float(np.mean(parts)), {"families": len(parts)}


def _consistency_score(segs: list[dict[str, Any]]) -> tuple[Optional[float], dict[str, Any]]:
    """
    Timbre consistency within comparable F0/intensity bands.
    Avoids raw whole-song spectral variance (vowel/pitch confounded).
    """
    usable = []
    for s in segs:
        f0 = _obs(s).get("f0_hz")
        rms = _obs(s).get("rms")
        if f0 is None or rms is None:
            continue
        usable.append(s)
    if len(usable) < 4:
        return None, {"reason": "insufficient_comparable_segments"}

    f0s = np.asarray([float(_obs(s)["f0_hz"]) for s in usable], dtype=float)
    rmss = np.asarray([float(_obs(s)["rms"]) for s in usable], dtype=float)
    f0_lo, f0_hi = np.percentile(f0s, [30, 70])
    r_lo, r_hi = np.percentile(rmss, [25, 75])
    comparable = [
        s
        for s in usable
        if f0_lo <= float(_obs(s)["f0_hz"]) <= f0_hi and r_lo <= float(_obs(s)["rms"]) <= r_hi
    ]
    if len(comparable) < 3:
        comparable = usable

    vectors = []
    for s in comparable:
        o = _obs(s)
        vec = [
            float(o.get("energy_1_2k") or 0),
            float(o.get("energy_2_4k") or 0),
            float(o.get("energy_4_8k") or 0),
            float(o.get("spectral_centroid_hz") or 0) / 4000.0,
            float(o.get("spectral_tilt_db_per_oct") or 0) / 20.0,
        ]
        vectors.append(vec)
    mat = np.asarray(vectors, dtype=float)
    # mean pairwise L1 distance (normalized) → invert to consistency
    if len(mat) < 2:
        return None, {}
    dists = []
    for i in range(len(mat)):
        for j in range(i + 1, len(mat)):
            dists.append(float(np.mean(np.abs(mat[i] - mat[j]))))
    mean_d = float(np.mean(dists)) if dists else 1.0
    # smaller distance → higher consistency
    score = max(0.0, min(1.0, 1.0 - mean_d / 0.35))
    return score, {"n_comparable": len(comparable), "mean_envelope_distance": round(mean_d, 4)}


def _region_feature_means(segs: list[dict[str, Any]]) -> dict[str, Optional[float]]:
    return {
        "brightness": _brightness_score(segs)[0],
        "presence": _presence_score(segs)[0],
        "airiness": _airiness_score(segs)[0],
        "texture": _texture_score(segs)[0],
    }


def build_timbre_profile_v211(
    *,
    segments: list[dict[str, Any]],
    mid_segments: Optional[list[dict[str, Any]]] = None,
    high_segments: Optional[list[dict[str, Any]]] = None,
    input_mode: str = "AUTO",
    functional_quality: str = "FULL",
) -> dict[str, Any]:
    segs = [s for s in segments if _vocal_ok(s)]
    mixed = (input_mode or "").upper() == "MIXED" or functional_quality == "LIMITED"
    limitations = [
        "음색은 스타일 목표가 달라 좋고 나쁨으로 평가하지 않아요.",
        "녹음 환경과 마이크 특성에 따라 음색 분석은 일부 달라질 수 있어요.",
    ]
    if mixed:
        limitations.append("반주 영향이 있을 수 있어 음색 신뢰도를 제한했어요.")

    # Contamination: many non-vocal-specific → unavailable
    total = len(segments) or 1
    vocal_n = len(segs)
    if vocal_n < 3:
        return {
            "available": False,
            "reason": "INSUFFICIENT_VOCAL_SEGMENTS",
            "axes": {},
            "summary": [],
            "confidence_label": "low",
            "limitations": limitations
            + ["보컬로 확인된 구간이 부족해 음색 프로필을 만들지 않았어요."],
            "descriptive_only": True,
            "what_it_is_not": "좋은 음색 / 음색 점수가 아닙니다.",
        }
    if mixed and (vocal_n / total) < 0.35:
        return {
            "available": False,
            "reason": "MIXED_CONTAMINATION",
            "axes": {},
            "summary": [],
            "confidence_label": "low",
            "limitations": limitations
            + ["반주 오염 가능성이 커 음색 프로필을 제공하지 않았어요."],
            "descriptive_only": True,
            "what_it_is_not": "좋은 음색 / 음색 점수가 아닙니다.",
        }

    bright, bright_meta = _brightness_score(segs)
    presence, presence_meta = _presence_score(segs)
    airiness, air_meta = _airiness_score(segs)
    texture, tex_meta = _texture_score(segs)
    harmonic, harm_meta = _harmonic_concentration(segs)
    consistency, cons_meta = _consistency_score(segs)

    conf = "medium"
    if mixed:
        conf = "low"
    elif bright_meta.get("families", 0) >= 3 and vocal_n >= 6:
        conf = "high"
    elif bright is None or presence is None:
        conf = "low"

    def pack(name: str, value: Optional[float], left: str, right: str, meta: dict) -> dict[str, Any]:
        return {
            "status": _axis_label(name, value) if value is not None else "UNCERTAIN",
            "continuum": None if value is None else round(float(value), 3),
            "left_label": left,
            "right_label": right,
            "confidence_label": conf if value is not None else "low",
            "provenance": meta,
        }

    axes = {
        "brightness": pack("brightness", bright, "어두움", "밝음", bright_meta),
        "presence": pack("presence", presence, "낮음", "높음", presence_meta),
        "airiness": pack("airiness", airiness, "적음", "많음", air_meta),
        "texture": pack("texture", texture, "매끈", "거침", tex_meta),
        "harmonic_concentration": pack("harmonic", harmonic, "분산", "집중", harm_meta),
        "timbre_consistency": pack("consistency", consistency, "변화 큼", "일관됨", cons_meta),
    }

    # mid → high timbre change
    high_note_timbre_change = None
    if mid_segments and high_segments and len(mid_segments) >= 1 and len(high_segments) >= 2:
        mid_m = _region_feature_means(mid_segments)
        high_m = _region_feature_means(high_segments)
        high_note_timbre_change = {
            "brightness_shift": _safe_delta(mid_m.get("brightness"), high_m.get("brightness")),
            "presence_shift": _safe_delta(mid_m.get("presence"), high_m.get("presence")),
            "airiness_shift": _safe_delta(mid_m.get("airiness"), high_m.get("airiness")),
            "texture_shift": _safe_delta(mid_m.get("texture"), high_m.get("texture")),
        }

    summary = []
    if bright is not None:
        summary.append(f"밝기: {_axis_label('brightness', bright)}")
    if presence is not None:
        summary.append(f"존재감: {_axis_label('presence', presence)}")
    if airiness is not None and airiness >= 0.55:
        summary.append("숨이 섞이는 편으로 보여요.")
    if high_note_timbre_change:
        b = high_note_timbre_change.get("brightness_shift")
        p = high_note_timbre_change.get("presence_shift")
        if b is not None and p is not None and b > 0.08 and p < -0.08:
            summary.append("고음에서 밝기는 증가하지만 중역 존재감은 다소 감소하는 경향이 있어요.")
        elif p is not None and p < -0.12:
            summary.append("고음에서 중역 존재감이 줄어드는 경향이 있어요.")

    return {
        "available": True,
        "axes": axes,
        "high_note_timbre_change": high_note_timbre_change,
        "summary": summary[:3],
        "confidence_label": conf,
        "limitations": limitations,
        "descriptive_only": True,
        "what_it_is_not": "좋은 음색 / 음색 점수 / 절대 품질 평가가 아닙니다.",
    }


def _safe_delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return round(float(b - a), 3)
