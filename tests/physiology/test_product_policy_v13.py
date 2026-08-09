"""Product visibility / eligibility / wording tests (physiology-inference-v1.3)."""

from __future__ import annotations

from audio_analyzer.physiology.config import (
    INFERENCE_VERSION,
    PRODUCT_VISIBILITY,
    RESEARCH_ONLY_MECHANISMS,
)
from audio_analyzer.physiology.eligibility import evaluate_eligibility
from audio_analyzer.physiology.evidence import build_evidence_bundle
from audio_analyzer.physiology.inference import infer_mechanisms
from audio_analyzer.physiology.report import build_premium_report, public_premium_report


def _obs(mid, value, task="sustain_a", valid=True):
    return {
        "metric_id": mid,
        "value": value,
        "valid": valid,
        "confidence": 0.8,
        "source_task": task,
    }


def _task(task_id, observations, attempt=1, quality="pass"):
    return {
        "task_id": task_id,
        "attempt": attempt,
        "observations": observations,
        "quality": {"status": quality},
    }


def test_inference_version_v13():
    assert INFERENCE_VERSION == "physiology-inference-v1.3"


def test_a_weak_mechanism_user_visible_false():
    t = _task(
        "sustain_a",
        [
            _obs("cepstral_prominence_proxy_db", 9.0),
            _obs("raw_h1_h2_proxy_db", 11.0),
            _obs("sustained_residual_f0_cents", 10.0),
        ],
    )
    report = build_premium_report(session_id="a", task_results=[t])
    by = {m["mechanism_id"]: m for m in report["physiology_assessments"]}
    for mid in RESEARCH_ONLY_MECHANISMS:
        assert by[mid]["user_visible"] is False
        assert PRODUCT_VISIBILITY[mid] == "RESEARCH_ONLY"
    reliable = {i["mechanism_id"] for i in report["reliable_findings"]}
    assert "phonatory_efficiency" not in reliable
    assert "release_coordination" not in reliable
    assert "vocal_tract_resonance_balance" not in reliable


def test_b_single_family_conditional_primary_not_reliable():
    t = _task("sustain_a", [_obs("cepstral_prominence_proxy_db", 8.0), _obs("hnr_ac_proxy_db", 7.0)])
    report = build_premium_report(session_id="b", task_results=[t])
    reliable = {i["mechanism_id"] for i in report["reliable_findings"]}
    assert "phonation_contact_pattern" not in reliable
    uncertain = {i["mechanism_id"] for i in report["uncertain_findings"]}
    assert "phonation_contact_pattern" in uncertain


def test_c_two_independent_families_cross_vowel_eligible():
    obs_a = [
        _obs("cepstral_prominence_proxy_db", 9.0, "sustain_a"),
        _obs("hnr_ac_proxy_db", 8.0, "sustain_a"),
        _obs("raw_h1_h2_proxy_db", 11.0, "sustain_a"),
        _obs("sustained_residual_f0_cents", 12.0, "sustain_a"),
    ]
    obs_i = [
        _obs("cepstral_prominence_proxy_db", 9.5, "sustain_i"),
        _obs("hnr_ac_proxy_db", 8.5, "sustain_i"),
        _obs("raw_h1_h2_proxy_db", 10.5, "sustain_i"),
    ]
    report = build_premium_report(
        session_id="c",
        task_results=[_task("sustain_a", obs_a), _task("sustain_i", obs_i)],
    )
    reliable = {i["mechanism_id"]: i for i in report["reliable_findings"]}
    assert "phonation_contact_pattern" in reliable
    assert reliable["phonation_contact_pattern"]["status"] == "possibly_light_contact"


def test_d_cross_vowel_contradiction_confidence_down():
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
    mechs = infer_mechanisms([t1, t2])
    g = next(m for m in mechs if m["mechanism_id"] == "phonation_contact_pattern")
    assert g["status"] == "unknown" or g["confidence"] < 0.5


def test_e_cross_vowel_replication_allows_direction():
    obs_a = [
        _obs("cepstral_prominence_proxy_db", 9.0, "sustain_a"),
        _obs("raw_h1_h2_proxy_db", 11.0, "sustain_a"),
    ]
    obs_i = [
        _obs("cepstral_prominence_proxy_db", 9.2, "sustain_i"),
        _obs("raw_h1_h2_proxy_db", 10.8, "sustain_i"),
    ]
    g = next(
        m
        for m in infer_mechanisms([_task("sustain_a", obs_a), _task("sustain_i", obs_i)])
        if m["mechanism_id"] == "phonation_contact_pattern"
    )
    assert g["status"] == "possibly_light_contact"
    assert g["confidence"] > 0.4


def test_f_quality_degradation_blocks_eligibility():
    t = _task(
        "siren",
        [_obs("f0_continuity_ratio", 0.9, "siren"), _obs("voiced_dropout_count", 1, "siren")],
        quality="fail",
    )
    mechs = infer_mechanisms([t])
    m = next(x for x in mechs if x["mechanism_id"] == "register_transition_coordination")
    bundle = build_evidence_bundle([t])
    elig = evaluate_eligibility(m["mechanism_id"], m, [t], bundle)
    assert elig["eligible"] is False
    assert any(r["code"] == "quality" for r in elig["reasons"])


def test_g_unknown_not_auto_converted_to_strength():
    t = _task("sustain_a", [_obs("cepstral_prominence_proxy_db", 9.0)])
    report = build_premium_report(session_id="g", task_results=[t])
    for u in report["uncertain_findings"]:
        assert u["status"] == "unknown"
        assert u.get("status_label", "판단 어려움")
        # no fake directional strength
        assert u["status"] not in ("possibly_light_contact", "possibly_firm_contact", "needs_attention")


def test_h_glottal_wording_no_anatomy_assertion():
    obs_a = [
        _obs("cepstral_prominence_proxy_db", 9.0, "sustain_a"),
        _obs("raw_h1_h2_proxy_db", 11.0, "sustain_a"),
    ]
    obs_i = [
        _obs("cepstral_prominence_proxy_db", 9.2, "sustain_i"),
        _obs("raw_h1_h2_proxy_db", 10.8, "sustain_i"),
    ]
    report = build_premium_report(
        session_id="h",
        task_results=[_task("sustain_a", obs_a), _task("sustain_i", obs_i)],
    )
    blob = str(report["reliable_findings"]) + str(report["uncertain_findings"])
    for bad in ("성대가 안 붙", "성대가 벌", "성문 폐쇄 부전", "성대 폐쇄 부족"):
        assert bad not in blob


def test_i_breath_wording_no_abdominal_claim():
    t = _task(
        "dynamic_swell",
        [
            _obs("envelope_smoothness_index", 0.2, "dynamic_swell"),
            _obs("release_drop_db", 20.0, "dynamic_swell"),
            _obs("rms_variation_db", 6.0, "dynamic_swell"),
        ],
    )
    report = build_premium_report(session_id="i", task_results=[t])
    user_blob = str(report.get("reliable_findings")) + str(report.get("uncertain_findings")) + str(
        report.get("supporting_observations")
    ) + str(report.get("summary")) + str(report.get("training_plan"))
    assert "복압 부족" not in user_blob
    assert "횡격막 사용 부족" not in user_blob
    # coaching may mention that abdominal pressure was NOT measured — that is allowed
    for card in report["reliable_findings"]:
        assert "복압이 부족" not in (card.get("summary") or "")
        assert "복압이 부족" not in (card.get("motor_cue") or "")


def test_j_onset_slope_only_no_user_facing_conclusion():
    t = _task("sustain_a", [_obs("onset_slope_db_per_sec", 200.0)])
    report = build_premium_report(session_id="j", task_results=[t])
    reliable = {i["mechanism_id"] for i in report["reliable_findings"]}
    supporting = {i["mechanism_id"] for i in report["supporting_observations"]}
    assert "onset_coordination" not in reliable
    assert "onset_coordination" not in supporting
    o = next(m for m in report["physiology_assessments"] if m["mechanism_id"] == "onset_coordination")
    assert o["status"] == "unknown"
    assert o.get("user_visible") is False


def test_k_scientific_debug_default_hidden():
    t = _task("sustain_a", [_obs("sustained_residual_f0_cents", 10.0)])
    report = build_premium_report(session_id="k", task_results=[t], include_scientific_debug=False)
    assert "scientific_debug" not in report
    pub = public_premium_report(
        build_premium_report(session_id="k2", task_results=[t], include_scientific_debug=True)
    )
    assert "scientific_debug" not in pub


def test_l_premium_report_reliable_uncertain_split():
    tasks = [
        _task("sustain_a", [_obs("sustained_residual_f0_cents", 10.0, "sustain_a")]),
        _task("siren", [_obs("f0_continuity_ratio", 0.95, "siren")]),
    ]
    report = build_premium_report(session_id="l", task_results=tasks)
    assert "reliable_findings" in report
    assert "uncertain_findings" in report
    assert report["sections"]["B_reliable"]["items"] == report["reliable_findings"]
    assert report["sections"]["B_uncertain"]["items"] == report["uncertain_findings"]


def test_m_weak_not_in_main_card_count():
    report = build_premium_report(
        session_id="m",
        task_results=[
            _task("sustain_a", [_obs("sustained_residual_f0_cents", 10.0)]),
            _task("siren", [_obs("f0_continuity_ratio", 0.9, "siren")]),
        ],
    )
    main_ids = {i["mechanism_id"] for i in report["reliable_findings"]} | {
        i["mechanism_id"] for i in report["uncertain_findings"]
    }
    for mid in RESEARCH_ONLY_MECHANISMS:
        assert mid not in main_ids


def test_n_low_coverage_retry_or_note():
    report = build_premium_report(
        session_id="n",
        task_results=[_task("sustain_a", [_obs("onset_slope_db_per_sec", 50.0)])],
    )
    assert report["mechanism_coverage"]["eligible_mechanisms"] < report["mechanism_coverage"][
        "attempted_primary_mechanisms"
    ]
    assert report["summary"].get("coverage_note") or report["retry_recommendation"].get("message")


def test_numeric_confidence_hidden_on_public_cards():
    obs_a = [
        _obs("cepstral_prominence_proxy_db", 9.0, "sustain_a"),
        _obs("raw_h1_h2_proxy_db", 11.0, "sustain_a"),
        _obs("sustained_residual_f0_cents", 10.0, "sustain_a"),
    ]
    obs_i = [
        _obs("cepstral_prominence_proxy_db", 9.2, "sustain_i"),
        _obs("raw_h1_h2_proxy_db", 10.8, "sustain_i"),
    ]
    report = build_premium_report(
        session_id="num",
        task_results=[_task("sustain_a", obs_a), _task("sustain_i", obs_i)],
    )
    for card in report["reliable_findings"]:
        assert "confidence" not in card
        assert card.get("confidence_label") in ("낮음", "중간", "높음")


def test_display_names_softened():
    from audio_analyzer.physiology.config import MECHANISM_DISPLAY

    assert MECHANISM_DISPLAY["phonation_contact_pattern"] == "성대 접촉과 관련된 발성 경향"
    assert MECHANISM_DISPLAY["intensity_phonation_coordination"] == "강도 변화와 발성 협응"
    assert "효율 점수" not in MECHANISM_DISPLAY["phonatory_efficiency"]
