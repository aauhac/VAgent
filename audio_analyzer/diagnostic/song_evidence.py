"""Canonical song evidence snapshot for Precision Diagnostic v2.5.

Concern resolver and coaching MUST read the same snapshot so they cannot
contradict each other. Does not invent missing axes or lower thresholds.
"""

from __future__ import annotations

from typing import Any, Optional

EVIDENCE_LEVEL_CONTROLLED = "CONTROLLED_CONFIRMED"
EVIDENCE_LEVEL_SONG_SUPPORTED = "SONG_SUPPORTED"
EVIDENCE_LEVEL_SONG_INFERRED = "SONG_INFERRED"
EVIDENCE_LEVEL_INSUFFICIENT = "INSUFFICIENT"

# Korean descriptive labels from resonance_formant_strategy.profile → continuum
_KO_CONTINUUM: dict[str, float] = {
    "어두운 편": 0.32,
    "어두운": 0.30,
    "낮은 편": 0.32,
    "낮음": 0.28,
    "적은 편": 0.32,
    "적음": 0.28,
    "보통": 0.50,
    "중간": 0.50,
    "밝은 편": 0.68,
    "밝음": 0.72,
    "높은 편": 0.68,
    "높음": 0.72,
    "많은 편": 0.68,
    "많음": 0.72,
}


def extract_vocal_function_profile(
    song_payload: Optional[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    """Locate vocal_function_profile across payload versions.

    Returns (profile, source_path_used). Never invents fields.
    """
    if not song_payload:
        return {}, "none"
    if isinstance(song_payload.get("vocal_function_profile"), dict) and song_payload[
        "vocal_function_profile"
    ]:
        return song_payload["vocal_function_profile"], "vocal_function_profile"
    report = song_payload.get("report") or {}
    if isinstance(report, dict) and isinstance(report.get("vocal_function_profile"), dict):
        vf = report["vocal_function_profile"]
        if vf:
            return vf, "report.vocal_function_profile"
    # Already a VF-shaped object (analyze() may pass VF directly)
    if any(
        k in song_payload
        for k in (
            "effort_assessment",
            "timbre_profile",
            "dimensions",
            "vocal_type_profile",
            "high_note_function_profile",
        )
    ):
        return song_payload, "direct_vocal_function_profile"
    return {}, "missing"


def _ko_to_continuum(label: Any) -> Optional[float]:
    if label is None:
        return None
    s = str(label).strip()
    if not s:
        return None
    if s in _KO_CONTINUUM:
        return _KO_CONTINUUM[s]
    for key, val in _KO_CONTINUUM.items():
        if key in s:
            return val
    return None


def _axis_continuum(ax: Optional[dict[str, Any]]) -> Optional[float]:
    if not ax:
        return None
    for key in ("continuum", "continuum_0_to_1", "value", "score"):
        v = ax.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return _ko_to_continuum(ax.get("status") or ax.get("label") or ax.get("continuum_label"))


def _dim(vf: dict[str, Any], dim_id: str) -> dict[str, Any]:
    return (vf.get("dimensions") or {}).get(dim_id) or {}


def _pack_level_from_status(status: str) -> Optional[str]:
    st = (status or "").upper()
    if st in ("HIGH", "INCREASED", "ELEVATED", "EXCESS", "MODERATE"):
        return "HIGH" if st != "MODERATE" else "MODERATE"
    if st in ("LOW", "STABLE", "NORMAL", "NOT_PROMINENT", "OK_PROXY"):
        return "LOW"
    return None


def build_song_evidence_snapshot(
    song_payload: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Build one canonical snapshot used by resolver + coaching."""
    vf, source_path = extract_vocal_function_profile(song_payload)
    availability: dict[str, bool] = {}
    snap: dict[str, Any] = {
        "source_path": source_path,
        "availability": availability,
        "key_features": [],
    }
    if not vf:
        return snap

    # --- effort ---
    effort = vf.get("effort_assessment") or {}
    effort_dim = _dim(vf, "vocal_effort_strain")
    sev = (
        effort.get("severity")
        or effort.get("global_severity")
        or effort_dim.get("status")
        or ""
    ).upper()
    raw_status = str(effort.get("status") or effort_dim.get("status") or "").upper()
    if sev or effort or effort_dim:
        level = "UNKNOWN"
        # Raw UNKNOWN/AMBIGUOUS must not be presented as LOW strength
        if raw_status in ("UNKNOWN", "UNAVAILABLE", "AMBIGUOUS") or effort_dim.get("hidden"):
            level = "UNKNOWN"
        elif sev in ("UNKNOWN", "UNAVAILABLE", "AMBIGUOUS"):
            level = "UNKNOWN"
        elif sev in ("HIGH", "EXCESS"):
            level = "HIGH"
        elif sev == "MODERATE":
            level = "MODERATE"
        elif sev in ("MILD", "OCCASIONAL"):
            level = "MODERATE"
        elif sev in ("LOW", "STABLE", "NORMAL") and raw_status not in (
            "UNKNOWN",
            "UNAVAILABLE",
            "AMBIGUOUS",
        ):
            level = "LOW"
        conf = str(effort.get("confidence_label") or effort_dim.get("confidence_label") or "").lower()
        snap["effort"] = {
            "available": level not in ("UNKNOWN",),
            "level": level,
            "severity": sev or None,
            "status": raw_status or effort.get("status") or effort_dim.get("status"),
            "confidence_label": conf or None,
            "reliable_for_preserve": (
                level == "LOW" and conf in ("medium", "high") and not effort_dim.get("hidden")
            ),
        }
        availability["effort"] = bool(snap["effort"]["available"])

    # --- contact ---
    contact_dim = _dim(vf, "glottal_contact_profile")
    cont = contact_dim.get("continuum_0_to_1")
    cstat = str(contact_dim.get("status") or "").upper()
    contact_status = None
    if isinstance(cont, (int, float)):
        if cont >= 0.62:
            contact_status = "FIRM"
        elif cont <= 0.38:
            contact_status = "LIGHT"
        else:
            contact_status = "MID"
    elif "단단" in str(contact_dim.get("status_label") or "") or "FIRM" in cstat:
        contact_status = "FIRM"
        cont = 0.72
    elif "가벼" in str(contact_dim.get("status_label") or "") or "LIGHT" in cstat:
        contact_status = "LIGHT"
        cont = 0.28
    if contact_status or contact_dim:
        snap["contact"] = {
            "available": contact_status is not None or cstat in ("OBSERVED", "SUFFICIENT"),
            "status": contact_status or cstat or None,
            "continuum": float(cont) if isinstance(cont, (int, float)) else None,
            "status_label": contact_dim.get("status_label"),
        }
        availability["contact"] = bool(snap["contact"]["available"])

    # --- breathiness / airiness ---
    breath_dim = _dim(vf, "air_leakage_breathiness")
    bstat = str(breath_dim.get("status") or "").upper()
    blevel = _pack_level_from_status(bstat)
    airiness_c: Optional[float] = None
    if blevel == "HIGH":
        airiness_c = 0.68
    elif blevel == "LOW":
        airiness_c = 0.28
    elif blevel == "MODERATE":
        airiness_c = 0.52
    if breath_dim or blevel:
        snap["breathiness"] = {
            "available": blevel is not None or bstat not in ("", "UNKNOWN"),
            "level": blevel or "UNKNOWN",
            "status": breath_dim.get("status"),
            "status_label": breath_dim.get("status_label"),
            "airiness_continuum": airiness_c,
        }
        availability["breathiness"] = bool(snap["breathiness"]["available"])

    # --- stability ---
    stab_dim = _dim(vf, "phonation_regularity")
    sstat = str(stab_dim.get("status") or "").upper()
    if stab_dim:
        snap["stability"] = {
            "available": sstat not in ("", "UNKNOWN"),
            "status": stab_dim.get("status"),
            "status_label": stab_dim.get("status_label"),
        }
        availability["stability"] = bool(snap["stability"]["available"])

    # --- register connection (canonical) + source balance (separate) ---
    vt = vf.get("vocal_type_profile") or {}
    reg = vt.get("register_strategy") or {}
    reg_dim = _dim(vf, "register_configuration")
    canon = vt.get("canonical_register") if isinstance(vt.get("canonical_register"), dict) else {}
    if not canon and (reg or reg_dim):
        try:
            from audio_analyzer.vocal_style.register_canonical import (
                build_canonical_register_assessment,
            )

            dims = vf.get("dimensions") if isinstance(vf.get("dimensions"), dict) else None
            if not dims and reg_dim:
                dims = {"register_configuration": reg_dim}
            canon = build_canonical_register_assessment(
                register_strategy=reg or None,
                dimensions=dims,
            )
        except Exception:
            canon = {}
    raw_strategy = str(reg.get("status") or reg_dim.get("status") or "").upper()
    conn_status = str((canon or {}).get("status") or "").upper()
    if not conn_status or conn_status == "UNKNOWN":
        # Never expose source-tendency labels as connection status
        if raw_strategy in (
            "DISRUPTED",
            "PARTIAL",
            "CONNECTED",
            "UNRESOLVED",
            "CONFLICTED",
            "TRANSITION_EVENTS",
            "TRANSITION_UNSTABLE",
            "UNSTABLE",
        ):
            if raw_strategy in ("TRANSITION_EVENTS", "TRANSITION_UNSTABLE", "UNSTABLE"):
                conn_status = "DISRUPTED"
            else:
                conn_status = raw_strategy
        else:
            conn_status = "UNRESOLVED" if (vt or reg or reg_dim) else ""
    if vt or reg or reg_dim or canon:
        snap["register"] = {
            "available": bool(conn_status) and conn_status not in ("", "UNKNOWN"),
            "status": conn_status or "UNRESOLVED",
            "mix_evidence": reg.get("mix_evidence"),
            "description": (canon or {}).get("description")
            or reg.get("description")
            or reg_dim.get("status_label"),
            "modifiers": list(vt.get("modifiers") or []),
            "head_chest": vt.get("head_chest") or {},
            "raw_strategy_status": raw_strategy or None,
            "canonical": dict(canon) if canon else None,
        }
        availability["register"] = bool(snap["register"]["available"])

    # Source balance is NOT register connection
    sb = vt.get("source_balance") if isinstance(vt.get("source_balance"), dict) else {}
    sb_status = str(sb.get("balance_class") or sb.get("status") or "").upper()
    if not sb_status and raw_strategy in ("CHEST_DOMINANT", "HEAD_DOMINANT"):
        sb_status = raw_strategy
    if not sb_status:
        hc = vt.get("head_chest") if isinstance(vt.get("head_chest"), dict) else {}
        lean = str(hc.get("balance") or hc.get("lean") or "").upper()
        if lean:
            sb_status = lean
    if sb_status or sb:
        snap["source_balance"] = {
            "available": bool(sb_status),
            "status": sb_status or "UNKNOWN",
            "balance_class": sb_status or None,
            "profile": sb or None,
        }
        availability["source_balance"] = bool(snap["source_balance"]["available"])

    # --- timbre (prefer axes; fall back to resonance profile labels) ---
    tp = vf.get("timbre_profile") or {}
    axes = tp.get("axes") or {}
    timbre: dict[str, Any] = {
        "available": False,
        "source": None,
        "axes": {},
    }
    brightness = _axis_continuum(axes.get("brightness"))
    presence = _axis_continuum(axes.get("presence"))
    airiness = _axis_continuum(axes.get("airiness"))
    texture = _axis_continuum(axes.get("texture"))
    harmonic = _axis_continuum(axes.get("harmonic_concentration"))
    consistency = _axis_continuum(axes.get("timbre_consistency") or axes.get("consistency"))
    src = None
    if any(v is not None for v in (brightness, presence, airiness, texture)):
        src = "timbre_profile.axes"
    # Resonance descriptive profile (common when timbre_profile.available=false)
    res = _dim(vf, "resonance_formant_strategy")
    res_prof = res.get("profile") or {}
    if brightness is None:
        brightness = _ko_to_continuum(res_prof.get("brightness"))
        if brightness is not None:
            src = src or "resonance_formant_strategy.profile"
    if presence is None:
        presence = _ko_to_continuum(
            res_prof.get("mid_presence") or res_prof.get("presence")
        )
        if presence is not None:
            src = src or "resonance_formant_strategy.profile"
    if airiness is None and airiness_c is not None:
        airiness = airiness_c
        src = src or "air_leakage_breathiness"
    # Modifier-backed soft cue (not a numeric invention beyond known label)
    modifiers = set(vt.get("modifiers") or [])
    if presence is None and "LOW_RESONANCE_PRESENCE" in modifiers:
        presence = 0.32
        src = src or "vocal_type.modifiers"
    if brightness is not None:
        timbre["axes"]["brightness"] = brightness
    if presence is not None:
        timbre["axes"]["presence"] = presence
    if airiness is not None:
        timbre["axes"]["airiness"] = airiness
    if texture is not None:
        timbre["axes"]["texture"] = texture
    if harmonic is not None:
        timbre["axes"]["harmonic_concentration"] = harmonic
    if consistency is not None:
        timbre["axes"]["consistency"] = consistency
    timbre["available"] = bool(timbre["axes"])
    timbre["source"] = src
    timbre["brightness"] = brightness
    timbre["presence"] = presence
    timbre["airiness"] = airiness
    timbre["texture"] = texture
    timbre["harmonic_concentration"] = harmonic
    timbre["consistency"] = consistency
    snap["timbre"] = timbre
    availability["timbre"] = timbre["available"]

    # --- high note ---
    hn = vf.get("high_note_function_profile") or {}
    snap["high_note"] = {
        "available": bool(hn.get("available")),
        "reason": hn.get("reason"),
        "summary": hn.get("summary"),
        "axes": hn.get("axes") or {},
    }
    availability["high_note"] = bool(snap["high_note"]["available"])

    # --- resonance pack ---
    if res:
        snap["resonance"] = {
            "available": str(res.get("status") or "").upper() not in ("", "UNKNOWN"),
            "status": res.get("status"),
            "status_label": res.get("status_label"),
            "profile": res_prof,
        }
        availability["resonance"] = bool(snap["resonance"]["available"])

    snap["key_features"] = _derive_key_features(snap)
    snap["vocal_function_profile"] = vf  # reference for callers needing raw VF
    return snap


def snapshot_to_ui_acoustic_axes(snap: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Canonical-first axes payload for VocalProfile bars. Never invents brightness."""
    snap = snap or {}
    axes: dict[str, Any] = {}
    contact = snap.get("contact") or {}
    if contact.get("continuum") is not None:
        axes["contact"] = {
            "available": True,
            "continuum": float(contact["continuum"]),
            "status": contact.get("status"),
            "display": contact.get("status_label") or contact.get("status"),
        }
    effort = snap.get("effort") or {}
    level = str(effort.get("level") or "").upper()
    effort_cont = {"LOW": 0.22, "MODERATE": 0.55, "HIGH": 0.82}.get(level)
    if effort_cont is not None:
        axes["effort"] = {
            "available": True,
            "continuum": effort_cont,
            "status": level,
            "display": {"LOW": "낮은 편", "MODERATE": "중간", "HIGH": "높은 편"}.get(level, level),
        }
    breath = snap.get("breathiness") or {}
    if breath.get("airiness_continuum") is not None:
        packed = {
            "available": True,
            "continuum": float(breath["airiness_continuum"]),
            "status": breath.get("level"),
            "display": breath.get("status_label") or breath.get("level"),
        }
        axes["functional_breathiness"] = packed
        axes["breathiness"] = packed
    timbre = snap.get("timbre") or {}
    presence = timbre.get("presence")
    if presence is not None:
        try:
            pv = float(presence)
        except (TypeError, ValueError):
            pv = None
        if pv is not None:
            st = "LOW" if pv <= 0.42 else ("HIGH" if pv >= 0.58 else "MID")
            packed_p = {
                "available": True,
                "continuum": pv,
                "status": st,
                "display": {"LOW": "낮은 편", "HIGH": "높은 편", "MID": "중간"}.get(st, st),
            }
            axes["presence"] = packed_p
            axes["resonance"] = packed_p
    brightness = timbre.get("brightness")
    if brightness is not None:
        try:
            bv = float(brightness)
        except (TypeError, ValueError):
            bv = None
        if bv is not None:
            st = "LOW" if bv <= 0.42 else ("HIGH" if bv >= 0.58 else "MID")
            axes["brightness"] = {
                "available": True,
                "continuum": bv,
                "status": st,
                "display": {"LOW": "어두운 편", "HIGH": "밝은 편", "MID": "중간"}.get(st, st),
            }
    reg = snap.get("register") or {}
    rst = str(reg.get("status") or "").upper()
    if rst and rst not in ("UNKNOWN", "UNRESOLVED", ""):
        cont = {
            "CONNECTED": 0.78,
            "SMOOTH": 0.78,
            "STABLE": 0.78,
            "CONTINUOUS": 0.78,
            "STABLE_LIKE": 0.78,
            "PARTIAL": 0.55,
            "INSUFFICIENT": 0.55,
            "MIXED": 0.55,
            "DISRUPTED": 0.32,
            "UNSTABLE": 0.32,
            "TRANSITION_EVENTS": 0.32,
            "CONFLICTED": 0.5,
        }.get(rst, 0.5)
        axes["register"] = {
            "available": True,
            "continuum": cont,
            "status": rst,
            "display": reg.get("description") or rst,
        }
    return {"axes": axes}


def _derive_key_features(snap: dict[str, Any]) -> list[str]:
    """Salience-ranked key features — actionable bottlenecks beat maintained positives."""
    scored: list[tuple[int, str]] = []

    reg = snap.get("register") or {}
    rst = str(reg.get("status") or "").upper()
    if rst in ("DISRUPTED", "UNSTABLE", "TRANSITION_EVENTS", "BREAK", "FAIL", "ABRUPT"):
        scored.append((100, "성구 연결이 급격히 달라지는 편"))
    elif rst in ("PARTIAL", "INSUFFICIENT", "MIXED"):
        scored.append((90, "성구 연결이 일부 구간에서만 이어지는 편"))

    effort = snap.get("effort") or {}
    effort_level = str(effort.get("level") or "").upper()
    effort_conf = str(effort.get("confidence_label") or "").lower()
    effort_reliable = bool(effort.get("available")) and effort_level not in (
        "",
        "UNKNOWN",
        "UNAVAILABLE",
        "AMBIGUOUS",
    )
    if effort_level in ("HIGH", "MODERATE"):
        scored.append((95, "일부 구간에서 힘 사용이 증가하는 편"))
    elif effort_reliable and effort_level == "LOW" and effort_conf in ("medium", "high", ""):
        # Positive maintain trait — lower salience than bottlenecks
        scored.append((25, "힘 사용은 낮은 편"))

    stab = snap.get("stability") or {}
    sst = str(stab.get("status") or "").upper()
    if sst in ("UNSTABLE", "POOR", "LOW", "IRREGULAR"):
        scored.append((88, "발성 안정성이 떨어지는 구간이 있는 편"))
    elif sst in ("STABLE", "NORMAL", "OK_PROXY", "NOT_PROMINENT"):
        scored.append((20, "발성 안정성은 비교적 유지되는 편"))

    hn = snap.get("high_note") or {}
    if hn.get("available") and str(hn.get("severity") or "").upper() in ("HIGH", "MODERATE"):
        scored.append((85, "고음 구간에서 제한이 두드러지는 편"))

    breath = snap.get("breathiness") or {}
    if breath.get("available") and breath.get("level") == "HIGH":
        scored.append((70, "숨 섞임이 두드러지는 편"))
    elif breath.get("available") and breath.get("level") == "LOW":
        scored.append((22, "숨 섞임은 적은 편"))

    contact = snap.get("contact") or {}
    if contact.get("status") == "FIRM":
        scored.append((55, "접촉감은 단단한 쪽"))
    elif contact.get("status") == "LIGHT":
        scored.append((55, "접촉감은 가벼운 쪽"))

    timbre = snap.get("timbre") or {}
    if timbre.get("presence") is not None:
        if timbre["presence"] <= 0.42:
            scored.append((75, "중역 존재감이 다소 낮은 편"))
        elif timbre["presence"] >= 0.58:
            scored.append((30, "중역 존재감이 유지되는 편"))
    if timbre.get("brightness") is not None:
        if timbre["brightness"] <= 0.35 or timbre["brightness"] >= 0.65:
            side = "어두운" if timbre["brightness"] <= 0.35 else "밝은"
            scored.append((50, f"밝기는 {side} 쪽에 가까운 편"))

    scored.sort(key=lambda x: -x[0])
    out: list[str] = []
    for _score, text in scored:
        if text not in out:
            out.append(text)
        if len(out) >= 4:
            break
    return out


def wrap_song_profile_with_snapshot(
    song_payload: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Normalize any song payload into {vocal_function_profile, canonical_song_evidence}."""
    snap = build_song_evidence_snapshot(song_payload)
    vf = snap.get("vocal_function_profile") or extract_vocal_function_profile(song_payload)[0]
    return {
        "vocal_function_profile": vf,
        "canonical_song_evidence": snap,
    }


def get_canonical_snapshot(song_profile: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not song_profile:
        return build_song_evidence_snapshot(None)
    if isinstance(song_profile.get("canonical_song_evidence"), dict):
        return song_profile["canonical_song_evidence"]
    return build_song_evidence_snapshot(song_profile)
