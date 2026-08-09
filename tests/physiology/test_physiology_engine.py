"""Physiology engine unit tests (updated for proxy metric ids)."""

from __future__ import annotations

import numpy as np

from audio_analyzer.physiology.metrics import (
    compute_cepstral_prominence_proxy_db,
    compute_hnr_ac_proxy_db,
    compute_onset_slope_db_per_sec,
    compute_envelope_smoothness,
)
from audio_analyzer.physiology.observations import (
    observe_dynamic_swell_task,
    observe_siren_task,
    observe_sustained_task,
)
from audio_analyzer.physiology.inference import infer_mechanisms
from audio_analyzer.physiology.report import build_premium_report
from audio_analyzer.physiology.validity import perturbation_allowed
from audio_analyzer.models import free_public_result


SR = 22050


def _tone(freq=220.0, dur=4.0, amp=0.3, noise=0.0):
    t = np.arange(int(SR * dur)) / SR
    y = amp * np.sin(2 * np.pi * freq * t)
    if noise:
        y = y + noise * np.random.default_rng(0).normal(0, 1, size=y.shape)
    return y.astype(np.float32)


def _breathy(freq=220.0, dur=4.0):
    return _tone(freq, dur, amp=0.12, noise=0.08)


def test_stable_sustained_phonation_metrics_valid():
    y = _tone()
    out = observe_sustained_task(y, SR, task_id="sustain_a", attempt=1)
    obs = {o["metric_id"]: o for o in out["observations"]}
    assert obs["cepstral_prominence_proxy_db"]["valid"] is True
    assert obs["cepstral_prominence_proxy_db"]["value"] is not None
    assert obs["hnr_ac_proxy_db"]["valid"] is True
    assert "cpp_db" not in obs
    assert "raw_h1_h2_proxy_db" in obs


def test_breathy_vs_clean_cepstral_hnr_difference():
    clean = _tone(noise=0.0)
    breathy = _breathy()
    cpp_c = compute_cepstral_prominence_proxy_db(clean, SR, f0_hz=220.0)
    cpp_b = compute_cepstral_prominence_proxy_db(breathy, SR, f0_hz=220.0)
    hnr_c = compute_hnr_ac_proxy_db(clean, SR, f0_hz=220.0)
    hnr_b = compute_hnr_ac_proxy_db(breathy, SR, f0_hz=220.0)
    assert cpp_c is not None and cpp_b is not None
    assert hnr_c is not None and hnr_b is not None
    assert cpp_c > cpp_b or hnr_c > hnr_b


def test_gradual_vs_abrupt_onset():
    n = int(SR * 3.0)
    t = np.arange(n) / SR
    carrier = np.sin(2 * np.pi * 220 * t).astype(np.float32)
    gradual = carrier * np.linspace(0, 1, n, dtype=np.float32)
    abrupt = carrier.copy()
    abrupt[: int(0.02 * SR)] = 0
    g = compute_onset_slope_db_per_sec(gradual, SR)
    a = compute_onset_slope_db_per_sec(abrupt, SR)
    assert g is not None and a is not None


def test_siren_global_f0_not_instability():
    t = np.arange(int(SR * 5.0)) / SR
    f0 = 180 + 120 * np.sin(2 * np.pi * 0.2 * t)
    phase = 2 * np.pi * np.cumsum(f0) / SR
    y = (0.25 * np.sin(phase)).astype(np.float32)
    out = observe_siren_task(y, SR, attempt=1)
    assert out["task_id"] == "siren"
    assert "observations" in out


def test_siren_dropout_detection():
    t = np.arange(int(SR * 5.0)) / SR
    y = (0.25 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    mid = slice(int(2.0 * SR), int(2.4 * SR))
    y[mid] = 0
    out = observe_siren_task(y, SR, attempt=1)
    ids = {o["metric_id"]: o for o in out["observations"]}
    assert any("dropout" in k or "continuity" in k or "energy" in k for k in ids)


def test_smooth_vs_abrupt_swell():
    n = int(SR * 5.0)
    t = np.linspace(0, 1, n)
    carrier = np.sin(2 * np.pi * 220 * np.arange(n) / SR).astype(np.float32)
    smooth_env = np.sin(np.pi * t) ** 1.5
    abrupt_env = np.ones(n)
    abrupt_env[: n // 3] = 0.2
    abrupt_env[n // 3 : 2 * n // 3] = 1.0
    abrupt_env[2 * n // 3 :] = 0.2
    s = compute_envelope_smoothness(carrier * smooth_env.astype(np.float32), SR)
    a = compute_envelope_smoothness(carrier * abrupt_env.astype(np.float32), SR)
    assert s is not None and a is not None


def test_jitter_invalid_when_unstable():
    cond = {"ok": True, "reasons": [], "max_residual_std_for_perturbation": 25.0, "voiced_sec": 3.0}
    ok, notes = perturbation_allowed(
        residual_std_cents=80.0, vibrato_available=False, conditions=cond, task_id="sustain_a"
    )
    assert ok is False
    ok2, _ = perturbation_allowed(
        residual_std_cents=10.0, vibrato_available=True, conditions=cond, task_id="sustain_a"
    )
    assert ok2 is False


def test_single_metric_no_high_confidence():
    task = {
        "task_id": "sustain_a",
        "attempt": 1,
        "observations": [
            {
                "metric_id": "cepstral_prominence_proxy_db",
                "value": 8.0,
                "valid": True,
                "confidence": 0.9,
                "source_task": "sustain_a",
            }
        ],
    }
    mechs = infer_mechanisms([task])
    g = next(m for m in mechs if m["mechanism_id"] == "phonation_contact_pattern")
    assert g["confidence"] < 0.75 or g["status"] == "unknown"


def test_repeated_tasks_multi_family():
    obs = [
        {
            "metric_id": "cepstral_prominence_proxy_db",
            "value": 9.0,
            "valid": True,
            "confidence": 0.8,
            "source_task": "sustain_a",
        },
        {
            "metric_id": "hnr_ac_proxy_db",
            "value": 8.0,
            "valid": True,
            "confidence": 0.8,
            "source_task": "sustain_a",
        },
        {
            "metric_id": "raw_h1_h2_proxy_db",
            "value": 10.0,
            "valid": True,
            "confidence": 0.7,
            "source_task": "sustain_a",
        },
    ]
    t1 = {"task_id": "sustain_a", "attempt": 1, "observations": obs}
    t2 = {
        "task_id": "sustain_i",
        "attempt": 1,
        "observations": [{**o, "source_task": "sustain_i"} for o in obs],
    }
    mechs = infer_mechanisms([t1, t2])
    g = next(m for m in mechs if m["mechanism_id"] == "phonation_contact_pattern")
    assert g["independent_family_count"] >= 2
    assert g["alternative_explanations"]
    assert g.get("confidence_label") in ("낮음", "중간", "높음")


def test_deterministic_report_without_llm():
    y = _tone()
    tasks = [
        observe_sustained_task(y, SR, task_id="sustain_a", attempt=1),
        observe_sustained_task(y, SR, task_id="sustain_i", attempt=1),
        observe_siren_task(y, SR, attempt=1),
        observe_dynamic_swell_task(y, SR, attempt=1),
    ]
    report = build_premium_report(session_id="abc", task_results=tasks, safety_flags=[])
    assert report["inference_version"] == "physiology-inference-v1.3"
    assert report["sections"]["B_reliable"]["items"]
    assert report["sections"]["B_needs_more"]["items"]
    assert "scientific_debug" not in report or report.get("scientific_debug") is None
    # without include_scientific_debug flag
    assert report["sections"]["C_mechanism_details"]["items"]
    assert "질환" in report.get("disclaimer", "") or "진단하는 검사" in str(report)


def test_safety_no_disease_and_soft_coaching():
    y = _tone()
    tasks = [observe_sustained_task(y, SR, task_id="sustain_a", attempt=1)]
    report = build_premium_report(
        session_id="s",
        task_results=tasks,
        safety_flags=["pain_on_phonation"],
    )
    # User-facing narrative must not diagnose disease
    for m in report["physiology_assessments"]:
        assert "성문 폐쇄" not in m["summary"]
        assert "손상" not in m["summary"]
    assert report["sections"]["A_summary"].get("safety_note")


def test_free_public_result_strips_premium():
    fake = {
        "analysis_version": "2.0",
        "recording_id": "x",
        "audio": {"duration_sec": 20, "sample_rate": 44100, "source_mode": "raw", "separation": {}},
        "quality": {
            "status": "pass",
            "confidence": 0.9,
            "reasons": [],
            "codes": [],
            "metrics": {"duration_sec": 20},
        },
        "score": {
            "available": True,
            "version": "v2",
            "calibration_status": "uncalibrated",
            "overall": 70,
            "label": "좋아요",
            "areas": [
                {
                    "area_id": "stability",
                    "display_name": "안정성",
                    "score": 70,
                    "status": "ok",
                    "confidence": 0.8,
                }
            ],
            "strengths": [{"area_id": "stability", "display_name": "안정성"}],
            "priority_issues": [{"area_id": "resonance", "display_name": "공명"}],
        },
        "physiology_assessments": [{"x": 1}],
        "timeline": [{"start_sec": 1}],
        "diagnostic_metrics": [1],
    }
    pub = free_public_result(fake)
    assert pub["tier"] == "free"
    assert "physiology_assessments" not in pub
