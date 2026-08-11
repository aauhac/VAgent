"""Shared breathiness / roughness evidence families (VQ + Functional).

Interpretation (aggregation) stays in each engine; evidence routing is shared.
Vocal Function Engine v2.9 — roughness persistence / artifact hardening.
"""

from __future__ import annotations

from typing import Any, Optional


# Soft directional cues — uncalibrated; not clinical thresholds
BREATHY_PERIOD_DB = 8.0
BREATHY_H1H2_DB = 7.0
BREATHY_TILT = -16.0
BREATHY_OQ = 0.58

ROUGH_PERIOD_DB = 5.5
ROUGH_PERTURB = 3.0
ROUGH_DROPOUT = 0.2
# Strong clean phonation: high periodicity makes dropout+perturb unlikely "true rough"
ROUGH_CLEAN_PERIOD_DB = 10.0
ROUGH_MIN_VOICED_FRAMES = 6
ROUGH_EVENT_MERGE_GAP_SEC = 1.5
ROUGH_MIN_EVENT_SEGMENTS = 2


def _obs(seg: dict[str, Any]) -> dict[str, Any]:
    return seg.get("observations") or {}


def _src(seg: dict[str, Any]) -> dict[str, Any]:
    return ((seg.get("level2_proxies") or {}).get("glottal_source") or {})


def vocal_presence_ok(seg: dict[str, Any]) -> bool:
    """Phonatory / vocal energy present — not silence or pure noise.

    Presence ≠ periodic voicing: breathy phonation may have weak F0/periodicity.
    """
    obs = _obs(seg)
    rms = obs.get("rms")
    if rms is None:
        rms = seg.get("rms")
    if rms is not None and float(rms) <= 1e-5:
        return False
    ve = seg.get("vocal_evidence") or {}
    if ve.get("vocal_energy") is not None and float(ve["vocal_energy"]) <= 0:
        return False
    if (ve.get("accompaniment_match") or 0) >= 0.85 and (ve.get("vocal_dominance") or 0) < 0.35:
        return False
    period = obs.get("periodicity_primary_db")
    has_proxy = (
        period is not None
        or obs.get("raw_h1_h2_proxy_db") is not None
        or obs.get("spectral_tilt_db_per_oct") is not None
        or obs.get("spectral_centroid_hz") is not None
    )
    if rms is None and not has_proxy:
        return False
    voiced = seg.get("voiced_ratio")
    if voiced is not None and float(voiced) < 0.08 and not has_proxy:
        return False
    return True


def breathy_family_flags(seg: dict[str, Any]) -> dict[str, Any]:
    obs = _obs(seg)
    src = _src(seg)
    per = obs.get("periodicity_primary_db")
    h1h2 = obs.get("raw_h1_h2_proxy_db")
    tilt = obs.get("spectral_tilt_db_per_oct")

    periodicity_noise = per is not None and float(per) <= BREATHY_PERIOD_DB
    harmonic_spectral = False
    if h1h2 is not None and float(h1h2) >= BREATHY_H1H2_DB:
        harmonic_spectral = True
    if tilt is not None and float(tilt) <= BREATHY_TILT:
        harmonic_spectral = True

    glottal_source = False
    if src.get("valid"):
        oq = src.get("estimated_oq_proxy")
        naq = src.get("estimated_naq")
        if oq is not None and float(oq) >= BREATHY_OQ:
            glottal_source = True
        if naq is not None and float(naq) >= 0.15:
            glottal_source = True

    available = []
    if per is not None:
        available.append("periodicity_noise")
    if h1h2 is not None or tilt is not None:
        available.append("harmonic_spectral")
    if src.get("valid"):
        available.append("glottal_source")

    return {
        "periodicity_noise": periodicity_noise,
        "harmonic_spectral": harmonic_spectral,
        "glottal_source": glottal_source,
        "available_families": available,
        "n_positive": sum(
            [periodicity_noise, harmonic_spectral, glottal_source]
        ),
    }


def breathy_negative_flags(seg: dict[str, Any]) -> dict[str, Any]:
    obs = _obs(seg)
    per = obs.get("periodicity_primary_db")
    h1h2 = obs.get("raw_h1_h2_proxy_db")
    tilt = obs.get("spectral_tilt_db_per_oct")
    neg = 0
    details = []
    if per is not None and float(per) >= 10.0:
        neg += 1
        details.append("periodicity_preserved")
    if h1h2 is not None and float(h1h2) <= 3.0:
        neg += 1
        details.append("h1h2_not_breathy")
    if tilt is not None and float(tilt) >= -12.0:
        neg += 1
        details.append("tilt_not_breathy")
    return {"n_negative": neg, "details": details, "strong": neg >= 2}


def classify_breathy_segment(seg: dict[str, Any]) -> dict[str, Any]:
    if not vocal_presence_ok(seg):
        return {
            "verdict": "INSUFFICIENT",
            "reason": "no_vocal_presence",
            "families": {},
            "negative": {},
        }
    fam = breathy_family_flags(seg)
    neg = breathy_negative_flags(seg)
    n_avail = len(fam.get("available_families") or [])
    if n_avail < 1:
        return {
            "verdict": "INSUFFICIENT",
            "reason": "no_breathy_families_computable",
            "families": fam,
            "negative": neg,
        }
    if fam["n_positive"] >= 2:
        return {
            "verdict": "POSITIVE",
            "reason": "multi_family_breathy",
            "families": fam,
            "negative": neg,
        }
    if fam["n_positive"] == 1 and n_avail >= 2 and not neg.get("strong"):
        return {
            "verdict": "INSUFFICIENT",
            "reason": "single_family_only",
            "families": fam,
            "negative": neg,
        }
    if fam["n_positive"] == 0 and neg.get("strong"):
        return {
            "verdict": "NEGATIVE",
            "reason": "explicit_anti_breathy",
            "families": fam,
            "negative": neg,
        }
    if fam["n_positive"] == 0 and n_avail >= 2:
        return {
            "verdict": "NEGATIVE",
            "reason": "evaluable_no_positive",
            "families": fam,
            "negative": neg,
        }
    return {
        "verdict": "INSUFFICIENT",
        "reason": "weak_or_partial",
        "families": fam,
        "negative": neg,
    }


def rough_family_flags(seg: dict[str, Any]) -> dict[str, Any]:
    """
    Roughness needs irregularity-specific evidence — CPP drop alone is NOT enough.
    A. PERIODICITY_LOSS
    B. IRREGULARITY (perturbation)
    C. DROPOUT / discontinuity
    """
    obs = _obs(seg)
    per = obs.get("periodicity_primary_db")
    perturb = obs.get("f0_frame_period_perturbation_proxy_percent")
    dropout = obs.get("f0_dropout_ratio")
    art = obs.get("f0_tracker_artifact") or {}
    octave_jump = obs.get("f0_octave_jump_ratio")
    n_voiced = int(art.get("n_voiced") or 0)
    n_frames = int(art.get("n_frames") or 0)
    octave_jumps = int(art.get("octave_jumps") or 0)

    periodicity_loss = per is not None and float(per) <= ROUGH_PERIOD_DB
    irregularity = perturb is not None and float(perturb) >= ROUGH_PERTURB
    dropout_flag = dropout is not None and float(dropout) >= ROUGH_DROPOUT

    # OCTAVE_TRACKER_ARTIFACT candidates
    octave_artifact = bool(
        (octave_jump is not None and float(octave_jump) >= 0.12)
        or (octave_jumps >= 1 and n_voiced > 0 and n_voiced < 12)
        or (octave_jumps >= 2)
    )
    sparse_track = bool(n_frames > 0 and n_voiced < ROUGH_MIN_VOICED_FRAMES)
    tracker_suspect = bool(
        art.get("suspect")
        or octave_artifact
        or (sparse_track and (irregularity or dropout_flag))
    )

    return {
        "periodicity_loss": periodicity_loss,
        "irregularity": irregularity,
        "dropout": dropout_flag,
        "tracker_artifact_suspect": tracker_suspect,
        "octave_tracker_artifact": octave_artifact,
        "n_positive": sum([periodicity_loss, irregularity, dropout_flag]),
        "has_irregularity_specific": bool(irregularity or dropout_flag),
        "octave_jump_ratio": None if octave_jump is None else float(octave_jump),
        "n_voiced": n_voiced,
        "n_frames": n_frames,
        "periodicity_db": None if per is None else float(per),
        "perturb": None if perturb is None else float(perturb),
        "dropout_ratio": None if dropout is None else float(dropout),
    }


def classify_rough_segment(seg: dict[str, Any]) -> dict[str, Any]:
    """
    Roughness verdict (v2.9).

    Hard rules:
    - periodicity loss alone ≠ rough
    - perturbation spike alone ≠ strong rough
    - tracker artifact ≠ rough
    - breathiness-only weak periodicity ≠ rough
    - high-periodicity clean phonation + dropout/perturb ≠ rough
    """
    if not vocal_presence_ok(seg):
        return {
            "verdict": "INSUFFICIENT",
            "reason": "no_vocal_presence",
            "families": {},
            "roughness_score": 0.0,
            "roughness_confidence": "low",
        }
    fam = rough_family_flags(seg)

    if fam["periodicity_loss"] and not fam["has_irregularity_specific"]:
        return {
            "verdict": "REJECTED",
            "reason": "periodicity_loss_without_irregularity",
            "families": fam,
            "roughness_score": 0.0,
            "roughness_confidence": "low",
        }

    if fam.get("tracker_artifact_suspect"):
        return {
            "verdict": "REJECTED",
            "reason": "tracker_artifact",
            "families": fam,
            "roughness_score": 0.0,
            "roughness_confidence": "low",
            "persistence": {"isolated": True},
        }

    if fam["irregularity"] and not fam["periodicity_loss"] and not fam["dropout"]:
        return {
            "verdict": "INSUFFICIENT",
            "reason": "irregularity_without_cooccurrence",
            "families": fam,
            "roughness_score": 0.2,
            "roughness_confidence": "low",
        }

    # Clean / loud phonation contamination: strong periodicity + dropout/perturb
    per_db = fam.get("periodicity_db")
    if (
        per_db is not None
        and float(per_db) >= ROUGH_CLEAN_PERIOD_DB
        and fam["irregularity"]
        and fam["dropout"]
        and not fam["periodicity_loss"]
    ):
        return {
            "verdict": "REJECTED",
            "reason": "clean_phonation_tracker_noise",
            "families": fam,
            "roughness_score": 0.0,
            "roughness_confidence": "low",
        }

    # Breathiness contamination
    if fam["periodicity_loss"] and fam["dropout"] and not fam["irregularity"]:
        breathy = classify_breathy_segment(seg)
        if breathy.get("verdict") == "POSITIVE":
            return {
                "verdict": "REJECTED",
                "reason": "breathy_contamination",
                "families": fam,
                "roughness_score": 0.0,
                "roughness_confidence": "low",
            }
        return {
            "verdict": "INSUFFICIENT",
            "reason": "periodicity_dropout_without_irregularity",
            "families": fam,
            "roughness_score": 0.25,
            "roughness_confidence": "low",
        }

    # Minimum tracker support for strong positive — only when F0 track was computed
    n_frames = int(fam.get("n_frames") or 0)
    n_voiced = int(fam.get("n_voiced") or 0)
    if (
        n_frames > 0
        and n_voiced < ROUGH_MIN_VOICED_FRAMES
        and fam["irregularity"]
        and (fam["periodicity_loss"] or fam["dropout"])
    ):
        return {
            "verdict": "REJECTED",
            "reason": "insufficient_voiced_frames",
            "families": fam,
            "roughness_score": 0.0,
            "roughness_confidence": "low",
        }

    if fam["irregularity"] and fam["periodicity_loss"]:
        return {
            "verdict": "POSITIVE",
            "reason": "irregularity_and_periodicity",
            "families": fam,
            "roughness_score": 0.8,
            "roughness_confidence": "medium",
        }
    if fam["irregularity"] and fam["dropout"]:
        return {
            "verdict": "POSITIVE",
            "reason": "irregularity_and_dropout",
            "families": fam,
            "roughness_score": 0.65,
            "roughness_confidence": "medium",
        }

    return {
        "verdict": "NEGATIVE" if fam["n_positive"] == 0 else "INSUFFICIENT",
        "reason": "no_rough_hit",
        "families": fam,
        "roughness_score": 0.0,
        "roughness_confidence": "medium" if fam["n_positive"] == 0 else "low",
    }


def disambiguate_breathy_vs_rough(seg: dict[str, Any]) -> dict[str, Any]:
    b = classify_breathy_segment(seg)
    r = classify_rough_segment(seg)
    label = "NEITHER"
    if b["verdict"] == "POSITIVE" and r["verdict"] == "POSITIVE":
        label = "MIXED"
    elif b["verdict"] == "POSITIVE":
        label = "BREATHY"
    elif r["verdict"] == "POSITIVE":
        label = "ROUGH"
    return {"label": label, "breathy": b, "rough": r}


def merge_rough_events(
    positive_segs: list[dict[str, Any]],
    *,
    gap_sec: float = ROUGH_EVENT_MERGE_GAP_SEC,
) -> list[dict[str, Any]]:
    """Merge adjacent POSITIVE segments into roughness events."""
    if not positive_segs:
        return []
    ordered = sorted(positive_segs, key=lambda s: float(s.get("start_sec") or 0))
    events: list[dict[str, Any]] = []
    cur: list[dict[str, Any]] = [ordered[0]]
    for s in ordered[1:]:
        prev_end = float(cur[-1].get("end_sec") or 0)
        start = float(s.get("start_sec") or 0)
        if start - prev_end <= gap_sec:
            cur.append(s)
        else:
            events.append(_event_from_members(cur))
            cur = [s]
    events.append(_event_from_members(cur))
    return events


def _event_from_members(members: list[dict[str, Any]]) -> dict[str, Any]:
    start = float(members[0].get("start_sec") or 0)
    end = float(members[-1].get("end_sec") or start)
    return {
        "start_sec": start,
        "end_sec": end,
        "duration_sec": max(0.0, end - start),
        "n_segments": len(members),
        "persistent": len(members) >= ROUGH_MIN_EVENT_SEGMENTS,
        "member_starts": [m.get("start_sec") for m in members],
    }


def roughness_persistence_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        return {
            "n_events": 0,
            "n_persistent_events": 0,
            "total_duration_sec": 0.0,
            "max_run_segments": 0,
            "prevalence_proxy": 0.0,
        }
    return {
        "n_events": len(events),
        "n_persistent_events": sum(1 for e in events if e.get("persistent")),
        "total_duration_sec": round(sum(float(e.get("duration_sec") or 0) for e in events), 3),
        "max_run_segments": max(int(e.get("n_segments") or 0) for e in events),
        "prevalence_proxy": round(
            sum(float(e.get("duration_sec") or 0) for e in events), 3
        ),
    }
