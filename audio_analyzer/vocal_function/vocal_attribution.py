"""Vocal attribution + claim-specific measurement suitability (v2.10).

Separates three questions that used to collapse into vocal_specific:

1. Is this a vocal source? (attribution)
2. Is F0 / pitch tracking sufficient? (tracking)
3. Is this claim measurable with available evidence? (claim suitability)

States:
  VOCAL_CONFIRMED | VOCAL_UNCERTAIN | NON_VOCAL_REJECTED
"""

from __future__ import annotations

from typing import Any, Optional

STATE_CONFIRMED = "VOCAL_CONFIRMED"
STATE_UNCERTAIN = "VOCAL_UNCERTAIN"
STATE_REJECTED = "NON_VOCAL_REJECTED"

# Primary / episode type → claim family
PRIMARY_CLAIM_FAMILY: dict[str, str] = {
    "GENERAL_EXCESS_EFFORT": "effort",
    "EXCESS_EFFORT_HIGH_NOTE": "effort",
    "EXCESS_FIRMNESS_WITH_STRAIN": "effort",
    "INTENSITY_OVERSHOOT": "effort",
    "AIR_LEAKAGE": "breathiness",
    "APERIODIC_ROUGHNESS": "roughness",
    "REGISTER_TRANSITION_DISRUPTION": "register",
    "ABRUPT_ONSET": "onset",
    "UNSTABLE_RELEASE": "onset",
    "RESONANCE_HIGH_NOTE_COLLAPSE": "resonance",
    "RESONANCE_MID_PRESENCE_LOSS": "resonance",
    "PHRASE_END_SUPPORT_LOSS": "respiratory",
    "VIBRATO_IRREGULARITY": "stability",
    "FIRM_PHONATION": "contact",
}

EPISODE_CLAIM_FAMILY: dict[str, str] = {
    "GENERAL_EFFORT": "effort",
    "HIGH_NOTE": "effort",
    "AIR_LEAKAGE": "breathiness",
    "ROUGHNESS": "roughness",
    "REGISTER_TRANSITION": "register",
    "ABRUPT_ONSET": "onset",
}

# Claims that require usable F0 / continuity for target validity
CLAIM_REQUIRES_F0: dict[str, bool] = {
    "effort": False,
    "contact": False,
    "breathiness": False,
    "roughness": False,
    "onset": False,
    "resonance": False,
    "respiratory": False,
    "stability": False,
    "register": True,
}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def classify_segment_vocal_attribution(
    *,
    vocal_dominance: float,
    vocal_vs_instrumental_ratio: Optional[float],
    vocal_energy: float,
    f0_confidence: float,
    voicing_confidence: float,
    periodicity_confidence: float,
    accompaniment_match: float,
    separation_artifact_risk: str = "low",
    stem_present: bool = False,
    voiced_ratio: Optional[float] = None,
) -> dict[str, Any]:
    """Classify one segment window into attribution state + family packets."""
    positive: list[str] = []
    negative: list[str] = []
    reason_codes: list[str] = []

    # --- STEM / ENERGY families (attribution) ---
    if stem_present:
        if vocal_dominance >= 0.55:
            positive.append("stem_attribution")
        if vocal_vs_instrumental_ratio is not None and vocal_vs_instrumental_ratio >= 1.0:
            positive.append("vocal_vs_instrumental")
        if vocal_dominance < 0.35:
            negative.append("low_vocal_dominance")
            reason_codes.append("low_vocal_dominance")
        if (
            vocal_vs_instrumental_ratio is not None
            and vocal_vs_instrumental_ratio < 0.8
            and vocal_dominance < 0.6
        ):
            negative.append("vocal_vs_instrumental_weak")
            reason_codes.append("vocal_vs_instrumental_weak")
    else:
        # No-stem: never reject on voiced_ratio alone; presence is soft positive
        vr = _f(voiced_ratio, 0.0)
        if vocal_energy >= 1e-3 and vr >= 0.25:
            positive.append("vocal_energy_presence")
        elif vocal_energy >= 1e-3:
            positive.append("vocal_energy_weak")

    if vocal_energy >= 5e-4:
        if "vocal_energy_presence" not in positive and "vocal_energy_weak" not in positive:
            positive.append("vocal_energy")

    # Pitch / periodicity = TRACKING families (not universal anti-vocal)
    tracking_weak = f0_confidence < 0.35 or voicing_confidence < 0.25
    if f0_confidence >= 0.35:
        positive.append("pitch_tracking")
    if periodicity_confidence >= 0.35:
        positive.append("periodicity")

    # --- CONTAMINATION (true non-vocal evidence) ---
    sep_high = str(separation_artifact_risk or "low").lower() == "high"
    if accompaniment_match >= 0.75:
        negative.append("accompaniment_spectral_match")
        reason_codes.append("accompaniment_spectral_match")
    if sep_high and accompaniment_match >= 0.5:
        negative.append("separation_artifact_with_accomp_match")
        reason_codes.append("separation_artifact_with_accomp_match")

    explicit_non_vocal = False
    if accompaniment_match >= 0.75 and vocal_dominance < 0.5:
        explicit_non_vocal = True
    if sep_high and accompaniment_match >= 0.5 and vocal_dominance < 0.55:
        explicit_non_vocal = True
    if stem_present and vocal_dominance < 0.35 and (vocal_vs_instrumental_ratio or 0) < 0.5:
        explicit_non_vocal = True
    if (
        stem_present
        and accompaniment_match >= 0.7
        and vocal_dominance < 0.55
        and "stem_attribution" not in positive
    ):
        explicit_non_vocal = True

    # Attribution confidence: do NOT fold F0 in as equal weight
    anti_contam = 1.0 - min(1.0, accompaniment_match)
    if stem_present:
        attribution_confidence = float(
            0.45 * vocal_dominance + 0.25 * anti_contam + 0.20 * min(1.0, vocal_energy * 40.0)
            + 0.10 * (1.0 if "vocal_vs_instrumental" in positive else 0.0)
        )
    else:
        # No-stem: capped
        attribution_confidence = float(
            min(
                0.72,
                0.35 * min(1.0, vocal_energy * 50.0)
                + 0.25 * _f(voiced_ratio, 0.0)
                + 0.25 * anti_contam
                + 0.15 * periodicity_confidence,
            )
        )

    tracking_confidence = float(
        0.5 * f0_confidence + 0.3 * voicing_confidence + 0.2 * periodicity_confidence
    )

    # State decision
    if explicit_non_vocal and "stem_attribution" not in positive:
        state = STATE_REJECTED
        reason_codes.append("explicit_contamination")
    elif stem_present and vocal_dominance >= 0.55 and accompaniment_match < 0.55:
        # F0 weakness alone cannot block CONFIRMED
        state = STATE_CONFIRMED
        if tracking_weak:
            reason_codes.append("tracking_weak_but_vocal_confirmed")
    elif stem_present and vocal_dominance >= 0.55 and accompaniment_match < 0.7:
        state = STATE_CONFIRMED if attribution_confidence >= 0.55 else STATE_UNCERTAIN
        if tracking_weak:
            reason_codes.append("tracking_weak")
    elif not stem_present:
        # No accompaniment stem: never REJECT on low voiced_ratio / F0 alone.
        # Clear acoustic energy in the analysis window → CONFIRMED (confidence capped).
        if vocal_energy >= 1e-3 and accompaniment_match < 0.5:
            if vocal_energy >= 0.005 or _f(voiced_ratio, 0.0) >= 0.25 or attribution_confidence >= 0.4:
                state = STATE_CONFIRMED
                reason_codes.append("no_stem_energy_confirmed_capped")
                if tracking_weak:
                    reason_codes.append("tracking_weak_but_vocal_confirmed")
            else:
                state = STATE_UNCERTAIN
                reason_codes.append("no_stem_uncertain")
        else:
            state = STATE_UNCERTAIN
            if _f(voiced_ratio, 0.0) < 0.2:
                reason_codes.append("no_stem_low_voiced_not_rejected")
            else:
                reason_codes.append("no_stem_uncertain")
        # Cap confidence for no-stem confirmed
        if state == STATE_CONFIRMED:
            attribution_confidence = min(attribution_confidence, 0.72)
    elif explicit_non_vocal:
        state = STATE_REJECTED
    else:
        state = STATE_UNCERTAIN
        if tracking_weak:
            reason_codes.append("tracking_weak_uncertain")
        if vocal_dominance < 0.55:
            reason_codes.append("borderline_dominance")

    # low F0 / voicing alone must never be the sole cause of REJECTED
    if state == STATE_REJECTED and set(reason_codes) <= {
        "low_f0_confidence",
        "low_voicing_confidence",
    }:
        state = STATE_UNCERTAIN

    return {
        "state": state,
        "confidence_score": round(max(0.0, min(1.0, attribution_confidence)), 3),
        "positive_families": positive,
        "negative_families": negative,
        "vocal_dominance": round(vocal_dominance, 3),
        "vocal_vs_instrumental_ratio": (
            None if vocal_vs_instrumental_ratio is None else round(float(vocal_vs_instrumental_ratio), 3)
        ),
        "f0_confidence": round(f0_confidence, 3),
        "voicing_confidence": round(voicing_confidence, 3),
        "periodicity_confidence": round(periodicity_confidence, 3),
        "accompaniment_match": round(accompaniment_match, 3),
        "separation_artifact_risk": separation_artifact_risk,
        "reason_codes": reason_codes,
        "tracking": {
            "f0_confidence": round(f0_confidence, 3),
            "voicing_confidence": round(voicing_confidence, 3),
            "periodicity_confidence": round(periodicity_confidence, 3),
            "tracking_confidence": round(tracking_confidence, 3),
            "weak": bool(tracking_weak),
        },
        "contamination": {
            "accompaniment_match": round(accompaniment_match, 3),
            "explicit_non_vocal": bool(explicit_non_vocal and state == STATE_REJECTED),
            "separation_artifact_risk": separation_artifact_risk,
        },
        "stem_present": bool(stem_present),
    }


def claim_vocal_suitability(
    claim_family: str,
    attribution: dict[str, Any],
    *,
    tracking: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Whether this claim can be measured given attribution + tracking."""
    state = (attribution or {}).get("state") or STATE_UNCERTAIN
    tracking = tracking or (attribution or {}).get("tracking") or {}
    f0c = _f(tracking.get("f0_confidence"), _f((attribution or {}).get("f0_confidence")))

    if state == STATE_REJECTED:
        return {
            "eligible": False,
            "claim_family": claim_family,
            "reason": "target_non_vocal_contamination",
        }
    if state == STATE_UNCERTAIN:
        return {
            "eligible": False,
            "claim_family": claim_family,
            "reason": "target_vocal_attribution_uncertain",
        }
    # CONFIRMED
    if CLAIM_REQUIRES_F0.get(claim_family, False) and f0c < 0.35:
        return {
            "eligible": False,
            "claim_family": claim_family,
            "reason": "target_register_f0_insufficient"
            if claim_family == "register"
            else "target_claim_measurement_insufficient",
        }
    return {
        "eligible": True,
        "claim_family": claim_family,
        "reason": f"vocal_confirmed_{claim_family}_families_sufficient",
    }


def _member_attribution(member: dict[str, Any]) -> dict[str, Any]:
    """Extract attribution packet from episode member / segment."""
    ve = member.get("vocal_evidence") or member.get("validity") or {}
    if isinstance(ve, dict) and isinstance(ve.get("vocal_attribution"), dict):
        return ve["vocal_attribution"]
    if isinstance(ve, dict) and ve.get("state") in (STATE_CONFIRMED, STATE_UNCERTAIN, STATE_REJECTED):
        return ve
    # Rebuild from legacy fields if needed
    return classify_segment_vocal_attribution(
        vocal_dominance=_f(ve.get("vocal_dominance"), 0.5),
        vocal_vs_instrumental_ratio=ve.get("vocal_vs_instrumental_ratio"),
        vocal_energy=_f(ve.get("vocal_energy"), 0.01),
        f0_confidence=_f(ve.get("f0_confidence")),
        voicing_confidence=_f(ve.get("voicing_confidence")),
        periodicity_confidence=_f(ve.get("periodicity_confidence")),
        accompaniment_match=_f(ve.get("accompaniment_match")),
        separation_artifact_risk=str(ve.get("separation_artifact_risk") or ve.get("artifact_risk") or "low"),
        stem_present=ve.get("vocal_vs_instrumental_ratio") is not None,
        voiced_ratio=member.get("voiced_ratio"),
    )


def aggregate_episode_vocal_attribution(
    members: list[dict[str, Any]],
    *,
    claim_family: str = "effort",
    core_members: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Aggregate member attributions — not raw majority on legacy vocal_specific."""
    attrs = [_member_attribution(m) for m in (members or [])]
    n = len(attrs)
    if n == 0:
        empty_suit = claim_vocal_suitability(claim_family, {"state": STATE_UNCERTAIN, "tracking": {}})
        return {
            "state": STATE_UNCERTAIN,
            "n_members": 0,
            "n_confirmed": 0,
            "n_uncertain": 0,
            "n_rejected": 0,
            "confirmed_ratio": 0.0,
            "vocal_dominance_median": None,
            "vocal_confidence_median": None,
            "accompaniment_match_median": None,
            "accompaniment_match_max": 0.0,
            "explicit_contamination_count": 0,
            "positive_family_coverage": [],
            "claim_suitability": {claim_family: empty_suit},
            "reason_codes": ["no_members"],
            "member_states": [],
            "core_attribution": None,
        }

    states = [a.get("state") or STATE_UNCERTAIN for a in attrs]
    n_c = sum(1 for s in states if s == STATE_CONFIRMED)
    n_u = sum(1 for s in states if s == STATE_UNCERTAIN)
    n_r = sum(1 for s in states if s == STATE_REJECTED)
    doms = [_f(a.get("vocal_dominance")) for a in attrs]
    confs = [_f(a.get("confidence_score")) for a in attrs]
    accs = [_f(a.get("accompaniment_match")) for a in attrs]
    acc_max = max(accs) if accs else 0.0
    pos_cov = sorted({f for a in attrs for f in (a.get("positive_families") or [])})

    reason_codes: list[str] = []
    # Explicit contamination outweighs weak majority
    if n_r >= 2 and n_c == 0:
        state = STATE_REJECTED
        reason_codes.append("majority_explicit_contamination")
    elif n_r >= 1 and acc_max >= 0.7 and n_c < n_r:
        state = STATE_REJECTED
        reason_codes.append("contamination_overrides_weak_confirm")
    elif n_c >= 1 and n_r == 0 and (n_c / n) >= 0.5:
        state = STATE_CONFIRMED
        reason_codes.append("confirmed_majority_no_reject")
    elif n_c >= 2 and n_r == 0:
        # confirmed + uncertain + confirmed
        state = STATE_CONFIRMED
        reason_codes.append("multi_confirmed_with_uncertain")
    elif n_u == n:
        state = STATE_UNCERTAIN
        reason_codes.append("all_uncertain")
    elif n_c == 1 and n_r == 1:
        state = STATE_UNCERTAIN
        reason_codes.append("mixed_confirm_reject")
    elif n_c >= 1 and n_r == 0:
        state = STATE_CONFIRMED if (n_c / n) >= 0.34 else STATE_UNCERTAIN
        reason_codes.append("partial_confirmed")
    else:
        state = STATE_UNCERTAIN
        reason_codes.append("mixed_uncertain")

    # Core span check
    core_attr = None
    if core_members:
        core_attr = aggregate_episode_vocal_attribution(
            core_members, claim_family=claim_family, core_members=None
        )
        if core_attr.get("state") == STATE_REJECTED:
            state = STATE_REJECTED
            reason_codes.append("core_span_contaminated")

    # Representative tracking from best-confirmed member or median
    track_src = next((a for a in attrs if a.get("state") == STATE_CONFIRMED), attrs[0])
    suit = claim_vocal_suitability(
        claim_family,
        {"state": state, "tracking": track_src.get("tracking"), "f0_confidence": track_src.get("f0_confidence")},
        tracking=track_src.get("tracking"),
    )

    import numpy as np

    return {
        "state": state,
        "n_members": n,
        "n_confirmed": n_c,
        "n_uncertain": n_u,
        "n_rejected": n_r,
        "confirmed_ratio": round(n_c / max(n, 1), 3),
        "vocal_dominance_median": round(float(np.median(doms)), 3) if doms else None,
        "vocal_confidence_median": round(float(np.median(confs)), 3) if confs else None,
        "accompaniment_match_median": round(float(np.median(accs)), 3) if accs else None,
        "accompaniment_match_max": round(acc_max, 3),
        "explicit_contamination_count": n_r,
        "positive_family_coverage": pos_cov,
        "claim_suitability": {claim_family: suit},
        "reason_codes": reason_codes,
        "member_states": states,
        "core_attribution": core_attr,
        "tracking": track_src.get("tracking"),
        "confidence_score": round(float(np.median(confs)), 3) if confs else 0.0,
    }


def evaluate_target_vocal_eligibility(
    primary: Optional[dict[str, Any]],
    target: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """
    Replace legacy: if vocal_specific is False → drop Primary.

    Returns status: ELIGIBLE | UNCERTAIN | REJECTED
    """
    if not primary or not target:
        return {
            "status": "REJECTED",
            "reason": "no_playable_target_episode",
            "claim_family": None,
            "episode_vocal_attribution": None,
        }

    pid = primary.get("id") or ""
    claim = PRIMARY_CLAIM_FAMILY.get(pid) or EPISODE_CLAIM_FAMILY.get(target.get("type") or "", "effort")
    members = target.get("members") or []
    # Core members: those overlapping core_evidence_span
    core = (target.get("core_evidence_span") or {})
    core_members = None
    if core.get("start_sec") is not None and members:
        cs, ce = float(core["start_sec"]), float(core.get("end_sec") or core["start_sec"])
        core_members = [
            m
            for m in members
            if float(m.get("end_sec") or 0) > cs and float(m.get("start_sec") or 0) < ce
        ] or None

    # Prefer precomputed episode attribution on feature_matrix
    fm = target.get("feature_matrix") or {}
    validity = fm.get("validity") or target.get("validity") or {}
    ep_attr = validity.get("episode_vocal_attribution")
    if not isinstance(ep_attr, dict) or not ep_attr.get("state"):
        if members:
            ep_attr = aggregate_episode_vocal_attribution(
                members, claim_family=claim, core_members=core_members
            )
        elif validity.get("vocal_specific") is True:
            # Legacy fixtures: vocal_specific alone on target (no member packets)
            synth = {
                "state": STATE_CONFIRMED,
                "tracking": {"f0_confidence": 0.6, "voicing_confidence": 0.6},
                "f0_confidence": 0.6,
                "confidence_score": 0.7,
                "reason_codes": ["legacy_vocal_specific_true"],
            }
            suit_legacy = claim_vocal_suitability(claim, synth, tracking=synth["tracking"])
            ep_attr = {
                **synth,
                "n_members": 0,
                "claim_suitability": {claim: suit_legacy},
                "member_states": [],
            }
        elif validity.get("vocal_specific") is False:
            # Legacy False alone ≠ contamination; treat as uncertain until new packets exist
            synth = {
                "state": STATE_UNCERTAIN,
                "tracking": {},
                "confidence_score": 0.3,
                "reason_codes": ["legacy_vocal_specific_false"],
            }
            suit_legacy = claim_vocal_suitability(claim, synth)
            ep_attr = {
                **synth,
                "n_members": 0,
                "claim_suitability": {claim: suit_legacy},
                "member_states": [],
            }
        else:
            # Legacy: missing vocal_specific did not reject (only explicit False did)
            synth = {
                "state": STATE_CONFIRMED,
                "tracking": {"f0_confidence": 0.6, "voicing_confidence": 0.6},
                "f0_confidence": 0.6,
                "confidence_score": 0.65,
                "reason_codes": ["legacy_validity_unspecified"],
            }
            suit_legacy = claim_vocal_suitability(claim, synth, tracking=synth["tracking"])
            ep_attr = {
                **synth,
                "n_members": 0,
                "claim_suitability": {claim: suit_legacy},
                "member_states": [],
            }

    suit = (ep_attr.get("claim_suitability") or {}).get(claim)
    if not isinstance(suit, dict):
        suit = claim_vocal_suitability(claim, ep_attr, tracking=ep_attr.get("tracking"))

    state = ep_attr.get("state")
    if state == STATE_REJECTED:
        return {
            "status": "REJECTED",
            "reason": "target_non_vocal_contamination",
            "claim_family": claim,
            "episode_vocal_attribution": ep_attr,
            "claim_suitability": suit,
        }
    if state == STATE_UNCERTAIN:
        return {
            "status": "UNCERTAIN",
            "reason": "target_vocal_attribution_uncertain",
            "claim_family": claim,
            "episode_vocal_attribution": ep_attr,
            "claim_suitability": suit,
        }
    if not suit.get("eligible"):
        return {
            "status": "REJECTED",
            "reason": suit.get("reason") or "target_claim_measurement_insufficient",
            "claim_family": claim,
            "episode_vocal_attribution": ep_attr,
            "claim_suitability": suit,
        }
    return {
        "status": "ELIGIBLE",
        "reason": suit.get("reason") or "target_vocal_eligible",
        "claim_family": claim,
        "episode_vocal_attribution": ep_attr,
        "claim_suitability": suit,
    }


def attribution_allows_context(seg: dict[str, Any], *, claim_family: str = "effort") -> bool:
    """Context windows for effort-like claims: reject only explicit non-vocal."""
    ve = seg.get("vocal_evidence") or {}
    attr = ve.get("vocal_attribution") if isinstance(ve.get("vocal_attribution"), dict) else None
    if attr is None:
        attr = classify_segment_vocal_attribution(
            vocal_dominance=_f(ve.get("vocal_dominance"), 0.5),
            vocal_vs_instrumental_ratio=ve.get("vocal_vs_instrumental_ratio"),
            vocal_energy=_f(ve.get("vocal_energy"), 0.01),
            f0_confidence=_f(ve.get("f0_confidence")),
            voicing_confidence=_f(ve.get("voicing_confidence")),
            periodicity_confidence=_f(ve.get("periodicity_confidence")),
            accompaniment_match=_f(ve.get("accompaniment_match")),
            separation_artifact_risk=str(ve.get("separation_artifact_risk") or "low"),
            stem_present=ve.get("vocal_vs_instrumental_ratio") is not None,
            voiced_ratio=seg.get("voiced_ratio"),
        )
    if claim_family == "register":
        suit = claim_vocal_suitability("register", attr)
        return bool(suit.get("eligible"))
    return attr.get("state") != STATE_REJECTED
