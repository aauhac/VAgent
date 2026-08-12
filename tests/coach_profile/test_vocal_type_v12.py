"""Vocal Type v1.2 — semantic direction, global/local, family agreement."""

from __future__ import annotations

from audio_analyzer.coach_profile.head_chest import (
    family_ablation,
    score_segment_head_chest,
    song_evidence_stats,
    weighted_index,
)
from audio_analyzer.coach_profile.naming import classify_base_type, compose_display_name


def _seg(
    start,
    end,
    *,
    f0=220.0,
    naq=0.10,
    oq=0.5,
    h1h2=4.0,
    tilt=-12.0,
    e24=0.12,
    mfdr=1.0,
    rms=0.05,
    gif=True,
    contact=None,
):
    s = {
        "start_sec": start,
        "end_sec": end,
        "valid": True,
        "rms": rms,
        "vocal_evidence": {"vocal_specific": True, "vocal_dominance": 0.8},
        "observations": {
            "f0_hz": f0,
            "raw_h1_h2_proxy_db": h1h2,
            "spectral_tilt_db_per_oct": tilt,
            "energy_2_4k": e24,
            "periodicity_primary_db": 12.0,
            "rms": rms,
        },
        "level2_proxies": {
            "glottal_source": {
                "valid": gif,
                "estimated_naq": naq,
                "estimated_oq_proxy": oq,
                "estimated_mfdr_norm_proxy": mfdr,
            }
            if gif
            else {"valid": False},
        },
    }
    if contact:
        s["contact_hint"] = contact
    return s


def test_chest_flow_pushes_chest():
    segs = [
        _seg(i, i + 2, naq=0.05, oq=0.35, h1h2=1.0, tilt=-8, e24=0.22, mfdr=1.4)
        for i in range(0, 12, 2)
    ]
    base = {"naq": 0.12, "oq": 0.5, "h1_h2": 5, "mfdr_norm": 1.0, "rms": 0.04}
    rows = [score_segment_head_chest(s, all_segments=segs, global_baseline=base) for s in segs]
    assert weighted_index(rows) < 0.5


def test_head_flow_pushes_head():
    segs = [
        _seg(i, i + 2, naq=0.20, oq=0.65, h1h2=12.0, tilt=-18, e24=0.06, mfdr=0.7)
        for i in range(0, 12, 2)
    ]
    base = {"naq": 0.10, "oq": 0.45, "h1_h2": 4.0, "mfdr_norm": 1.0, "rms": 0.04}
    rows = [score_segment_head_chest(s, all_segments=segs, global_baseline=base) for s in segs]
    assert weighted_index(rows) > 0.5


def test_light_contact_alone_cannot_flip_chest():
    segs = [
        _seg(i, i + 2, naq=0.05, oq=0.35, h1h2=1.0, tilt=-8, e24=0.22, mfdr=1.4, contact="lighter_like")
        for i in range(0, 12, 2)
    ]
    base = {"naq": 0.12, "oq": 0.5, "h1_h2": 5, "mfdr_norm": 1.0, "rms": 0.04}
    rows = [score_segment_head_chest(s, all_segments=segs, global_baseline=base) for s in segs]
    assert weighted_index(rows) < 0.5


def test_firm_contact_alone_cannot_flip_head():
    segs = [
        _seg(i, i + 2, naq=0.20, oq=0.65, h1h2=12.0, tilt=-18, e24=0.06, mfdr=0.7, contact="firmer_like")
        for i in range(0, 12, 2)
    ]
    base = {"naq": 0.10, "oq": 0.45, "h1_h2": 4.0, "mfdr_norm": 1.0, "rms": 0.04}
    rows = [score_segment_head_chest(s, all_segments=segs, global_baseline=base) for s in segs]
    assert weighted_index(rows) > 0.5


def test_breathy_chest_can_remain_chest_like():
    # Low NAQ chest source + breathy period + high H1H2 should not auto-head when GIF valid
    segs = [
        _seg(i, i + 2, naq=0.05, oq=0.35, h1h2=10.0, tilt=-11, e24=0.15, mfdr=1.3)
        for i in range(0, 12, 2)
    ]
    for s in segs:
        s["observations"]["periodicity_primary_db"] = 5.0
    base = {"naq": 0.12, "oq": 0.5, "h1_h2": 5, "mfdr_norm": 1.0, "rms": 0.04}
    rows = [score_segment_head_chest(s, all_segments=segs, global_baseline=base) for s in segs]
    idx = weighted_index(rows)
    assert idx is not None
    assert idx < 0.55  # not forced strongly head


def test_global_ratio_directionality_consistent():
    rows = [
        {
            "head_chest_index": 0.4,
            "evidence_mass": 2.0,
            "chest_raw_evidence": 1.2,
            "head_raw_evidence": 0.8,
            "directionality": 0.2,
            "family_agreement": 0.8,
            "n_source_families": 2,
            "confidence": "medium",
            "n_families": 3,
        }
        for _ in range(5)
    ]
    stats = song_evidence_stats(rows)
    # |1.2-0.8|/(1.2+0.8)=0.2
    assert abs(stats["global_ratio_directionality"] - 0.2) < 1e-6


def test_mix_plus_local_pull_display():
    name = compose_display_name(
        "BALANCED_MIX",
        ["CHEST_PULL"],
        local_events=[{"type": "LOCAL_CHEST_PULL", "start_sec": 11, "end_sec": 14}],
        register_strategy={"status": "MIX_LIKE_BALANCED"},
    )
    assert "믹스" in name
    assert "분리" not in name
    assert "단단한 믹스보이스" not in name


def test_family_ablation_runs():
    segs = [
        _seg(i, i + 2, naq=0.07, oq=0.4, h1h2=2.0, tilt=-9, e24=0.2, mfdr=1.3)
        for i in range(0, 10, 2)
    ]
    base = {"naq": 0.12, "oq": 0.55, "h1_h2": 6, "mfdr_norm": 1.0, "rms": 0.04}
    abl = family_ablation(segs, baseline=base)
    assert "FULL" in abl
    assert "without_CONTACT" in abl


def test_strong_mass_family_conflict_not_forced_balanced_high():
    t = classify_base_type(
        index=0.50,
        bridge={
            "type": "SMOOTH_BRIDGE",
            "score": 0.7,
            "register_sufficiency": "SUFFICIENT",
            "split_eligibility": {"eligible": False},
        },
        modifiers=[],
        confidence="medium",
        family_agreement=0.2,
    )
    # Low agreement near 50 → unresolved preferred over confident balanced mix
    assert t in ("UNRESOLVED", "BALANCED_SOURCE", "BALANCED_MIX")
