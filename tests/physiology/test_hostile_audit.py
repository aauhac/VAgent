"""Hostile audit cases + evidence-family tests (physiology-inference-v1.1)."""

from __future__ import annotations

from audio_analyzer.physiology.config import (
    AUDIO_ONLY_GLOBAL_CONFIDENCE_CAP,
    INFERENCE_VERSION,
    MECHANISM_CONFIDENCE_CAPS,
)
from audio_analyzer.physiology.evidence import build_evidence_bundle, count_independent_families
from audio_analyzer.physiology.inference import infer_mechanisms
from audio_analyzer.physiology.validity import perturbation_allowed


def _obs(mid, value, task="sustain_a", valid=True):
    return {
        "metric_id": mid,
        "value": value,
        "valid": valid,
        "confidence": 0.8,
        "source_task": task,
    }


def _task(task_id, observations, attempt=1):
    return {"task_id": task_id, "attempt": attempt, "observations": observations}


def test_inference_version_bump():
    assert INFERENCE_VERSION == "physiology-inference-v1.3"


def test_case_a_periodicity_only_no_high_confidence_anatomy():
    """CPP+HNR low without spectral family → unknown or capped; never anatomy."""
    t = _task(
        "sustain_a",
        [
            _obs("cepstral_prominence_proxy_db", 8.0),
            _obs("hnr_ac_proxy_db", 7.0),
        ],
    )
    mechs = infer_mechanisms([t])
    g = next(m for m in mechs if m["mechanism_id"] == "phonation_contact_pattern")
    # Only one independent family (periodicity)
    assert g["independent_family_count"] <= 1 or g["status"] == "unknown"
    assert g["confidence"] < 0.75
    # User-facing fields must not assert anatomy (forbidden lists may mention banned phrases)
    assert "성문이 벌어" not in g["summary"]
    assert "LCA" not in g["summary"]
    assert g["status"] in ("unknown", "balanced", "possibly_light_contact", "possibly_firm_contact")
    if g["independent_family_count"] < 2:
        assert g["status"] == "unknown" or g["status"] == "balanced"


def test_case_b_contradictory_periodicity_reduces_confidence():
    t = _task(
        "sustain_a",
        [
            _obs("cepstral_prominence_proxy_db", 8.0),
            _obs("hnr_ac_proxy_db", 25.0),
            _obs("raw_h1_h2_proxy_db", 10.0),
        ],
    )
    mechs = infer_mechanisms([t])
    g = next(m for m in mechs if m["mechanism_id"] == "phonation_contact_pattern")
    assert g["status"] == "unknown" or g["confidence"] < 0.5
    assert any("contradiction" in c.lower() for c in (g.get("contradicting_evidence") or []) ) or g["status"] == "unknown"


def test_case_c_cross_vowel_inconsistency():
    t1 = _task(
        "sustain_a",
        [
            _obs("cepstral_prominence_proxy_db", 8.0, "sustain_a"),
            _obs("raw_h1_h2_proxy_db", 12.0, "sustain_a"),
        ],
    )
    t2 = _task(
        "sustain_i",
        [
            _obs("cepstral_prominence_proxy_db", 22.0, "sustain_i"),
            _obs("raw_h1_h2_proxy_db", 1.0, "sustain_i"),
        ],
    )
    bundle = build_evidence_bundle([t1, t2])
    assert bundle["cross_vowel"]["inconsistent_metrics"]
    mechs = infer_mechanisms([t1, t2])
    g = next(m for m in mechs if m["mechanism_id"] == "phonation_contact_pattern")
    # Should not be high confidence
    assert g["confidence"] <= MECHANISM_CONFIDENCE_CAPS["phonation_contact_pattern"]
    assert g["confidence"] < 0.7


def test_case_d_two_vowels_plus_spectral_can_raise_but_capped():
    obs_a = [
        _obs("cepstral_prominence_proxy_db", 9.0, "sustain_a"),
        _obs("hnr_ac_proxy_db", 8.0, "sustain_a"),
        _obs("raw_h1_h2_proxy_db", 11.0, "sustain_a"),
        _obs("onset_slope_db_per_sec", 20.0, "sustain_a"),
    ]
    obs_i = [
        _obs("cepstral_prominence_proxy_db", 9.5, "sustain_i"),
        _obs("hnr_ac_proxy_db", 8.5, "sustain_i"),
        _obs("raw_h1_h2_proxy_db", 10.5, "sustain_i"),
    ]
    mechs = infer_mechanisms([_task("sustain_a", obs_a), _task("sustain_i", obs_i)])
    g = next(m for m in mechs if m["mechanism_id"] == "phonation_contact_pattern")
    assert g["status"] == "possibly_light_contact"
    assert g["independent_family_count"] >= 2
    assert g["confidence"] <= g["confidence_cap"] <= AUDIO_ONLY_GLOBAL_CONFIDENCE_CAP
    assert g.get("rule_id") == "CONTACT_LIGHT_V2"


def test_case_e_cpp_hnr_count_as_one_family():
    t = _task(
        "sustain_a",
        [
            _obs("cepstral_prominence_proxy_db", 9.0),
            _obs("hnr_ac_proxy_db", 8.0),
        ],
    )
    bundle = build_evidence_bundle([t])
    assert count_independent_families(bundle, ["periodicity", "spectral_source"]) == 1
    assert "periodicity" in bundle["by_family"]
    assert len(bundle["by_family"]["periodicity"]["metrics"]) == 2


def test_case_f_vibrato_invalidates_perturbation():
    ok, notes = perturbation_allowed(
        10.0,
        True,
        {"ok": True, "voiced_sec": 3.0, "max_residual_std_for_perturbation": 25.0},
        task_id="sustain_a",
    )
    assert ok is False
    assert "vibrato" in "".join(notes)


def test_case_g_siren_not_used_for_perturbation():
    ok, notes = perturbation_allowed(
        5.0,
        False,
        {"ok": True, "voiced_sec": 3.0, "max_residual_std_for_perturbation": 25.0},
        task_id="siren",
    )
    assert ok is False


def test_case_h_raw_h1h2_alone_no_closure():
    t = _task("sustain_a", [_obs("raw_h1_h2_proxy_db", 12.0)])
    mechs = infer_mechanisms([t])
    g = next(m for m in mechs if m["mechanism_id"] == "phonation_contact_pattern")
    assert g["status"] == "unknown"


def test_case_i_smooth_swell_no_abdominal_pressure_claim():
    t = _task(
        "dynamic_swell",
        [
            _obs("envelope_smoothness_index", 0.9, "dynamic_swell"),
            _obs("release_drop_db", 5.0, "dynamic_swell"),
        ],
    )
    mechs = infer_mechanisms([t])
    b = next(m for m in mechs if m["mechanism_id"] == "intensity_phonation_coordination")
    blob = str(b)
    assert "복압 부족" not in blob
    assert "횡격막" not in blob or "알 수 없" in blob or "미측정" in blob or b["status"] == "balanced"


def test_case_j_abrupt_onset_alone_not_pressed_voice():
    t = _task("sustain_a", [_obs("onset_slope_db_per_sec", 200.0)])
    mechs = infer_mechanisms([t])
    o = next(m for m in mechs if m["mechanism_id"] == "onset_coordination")
    assert o["status"] == "unknown"
    assert "pressed" not in o["summary"].lower()


def test_phonatory_efficiency_weak_suppressed():
    t = _task(
        "sustain_a",
        [
            _obs("cepstral_prominence_proxy_db", 8.0),
            _obs("hnr_ac_proxy_db", 7.0),
            _obs("raw_h1_h2_proxy_db", 11.0),
        ],
    )
    mechs = infer_mechanisms([t])
    pe = next(m for m in mechs if m["mechanism_id"] == "phonatory_efficiency")
    assert pe["status"] == "unknown"
    assert pe["literature_strength"] == "WEAK"


def test_monotonicity_removing_spectral_does_not_increase_conf():
    full = [
        _task(
            "sustain_a",
            [
                _obs("cepstral_prominence_proxy_db", 9.0),
                _obs("raw_h1_h2_proxy_db", 11.0),
            ],
        )
    ]
    reduced = [
        _task(
            "sustain_a",
            [_obs("cepstral_prominence_proxy_db", 9.0)],
        )
    ]
    g_full = next(m for m in infer_mechanisms(full) if m["mechanism_id"] == "phonation_contact_pattern")
    g_red = next(m for m in infer_mechanisms(reduced) if m["mechanism_id"] == "phonation_contact_pattern")
    # reduced should not have higher confidence than full when full had a direction
    if g_full["status"] != "unknown":
        assert g_red["confidence"] <= g_full["confidence"] + 0.001


def test_contact_requires_cross_vowel_for_direction():
    obs = [
        _obs("cepstral_prominence_proxy_db", 9.0),
        _obs("hnr_ac_proxy_db", 8.0),
        _obs("raw_h1_h2_proxy_db", 11.0),
    ]
    mechs = infer_mechanisms([_task("sustain_a", obs)])
    g = next(m for m in mechs if m["mechanism_id"] == "phonation_contact_pattern")
    assert g["status"] == "unknown"
    assert "cross" in " ".join(g.get("contradicting_evidence") or []).lower() or "모음" in g["summary"]


def test_primary_ux_excludes_weak_from_reliable_section():
    from audio_analyzer.physiology.report import build_premium_report

    obs = [
        _obs("cepstral_prominence_proxy_db", 9.0, "sustain_a"),
        _obs("raw_h1_h2_proxy_db", 11.0, "sustain_a"),
        _obs("cepstral_prominence_proxy_db", 9.2, "sustain_i"),
        _obs("raw_h1_h2_proxy_db", 10.8, "sustain_i"),
        _obs("envelope_smoothness_index", 0.2, "dynamic_swell"),
        _obs("release_drop_db", 20.0, "dynamic_swell"),
        _obs("sustained_residual_f0_cents", 10.0, "sustain_a"),
        _obs("f0_continuity_ratio", 0.9, "siren"),
    ]
    report = build_premium_report(
        session_id="ux",
        task_results=[
            _task("sustain_a", [o for o in obs if o["source_task"] == "sustain_a"]),
            _task("sustain_i", [o for o in obs if o["source_task"] == "sustain_i"]),
            _task("dynamic_swell", [o for o in obs if o["source_task"] == "dynamic_swell"]),
            _task("siren", [o for o in obs if o["source_task"] == "siren"]),
        ],
    )
    reliable_ids = {i["mechanism_id"] for i in report["sections"]["B_reliable"]["items"]}
    needs_ids = {i["mechanism_id"] for i in report["sections"]["B_needs_more"]["items"]}
    assert "phonatory_efficiency" not in reliable_ids
    assert "phonatory_efficiency" in needs_ids
    assert "phonation_stability" in reliable_ids
    # public cards never expose raw numeric confidence
    assert all("confidence" not in i or "confidence_label" in i for i in report["sections"]["B_reliable"]["items"])
    for i in report["sections"]["B_reliable"]["items"]:
        assert "confidence_label" in i
        assert "confidence" not in i


def test_contact_confidence_never_high_label():
    obs_a = [
        _obs("cepstral_prominence_proxy_db", 9.0, "sustain_a"),
        _obs("hnr_ac_proxy_db", 8.0, "sustain_a"),
        _obs("raw_h1_h2_proxy_db", 11.0, "sustain_a"),
        _obs("onset_slope_db_per_sec", 20.0, "sustain_a"),
    ]
    obs_i = [
        _obs("cepstral_prominence_proxy_db", 9.5, "sustain_i"),
        _obs("hnr_ac_proxy_db", 8.5, "sustain_i"),
        _obs("raw_h1_h2_proxy_db", 10.5, "sustain_i"),
    ]
    mechs = infer_mechanisms([_task("sustain_a", obs_a), _task("sustain_i", obs_i)])
    g = next(m for m in mechs if m["mechanism_id"] == "phonation_contact_pattern")
    if g["status"] != "unknown":
        assert g["confidence_label"] in ("낮음", "중간")
        assert g["confidence_label"] != "높음"
        assert g["ux_tier"] == "conditional_primary"


def test_legacy_metric_ids_still_canonicalized():
    t = _task(
        "sustain_a",
        [
            _obs("cpp_db", 9.0),
            _obs("hnr_ac_db", 8.0),
            _obs("h1_h2_db", 11.0),
        ],
    )
    bundle = build_evidence_bundle([t])
    assert "cepstral_prominence_proxy_db" in bundle["by_metric"]
    assert "periodicity" in bundle["by_family"]
