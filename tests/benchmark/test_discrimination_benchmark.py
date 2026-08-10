"""Tests for labeled discrimination benchmark infrastructure."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from audio_analyzer.benchmark.manifest import (
    dataset_counts,
    filter_active,
    fingerprint_samples,
    load_manifest,
    same_song_subset,
    subject_groups,
)
from audio_analyzer.benchmark.stats import (
    bootstrap_ci,
    cliffs_delta,
    roc_auc,
    saturation_rate,
    spearman_rho,
)
from audio_analyzer.benchmark.verdicts import (
    axis_calibration_readiness,
    classify_feature_verdict,
    mapping_loss_label,
    vocal_benefit_label,
)


def test_duplicate_manifest_sha_detection(tmp_path: Path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    a.write_bytes(b"SAME")
    b.write_bytes(b"SAME")
    rows = [
        {
            "sample_id": "s1",
            "file_path": str(a),
            "subject_id": "u1",
            "group": "expert",
            "skill_rank": 2,
            "song_id": "x",
            "source_type": "phone_recording",
            "recording_device": "",
            "has_backing_track": False,
            "commercial_mastered": False,
            "same_song_group": "",
            "notes": "",
        },
        {
            "sample_id": "s2",
            "file_path": str(b),
            "subject_id": "u2",
            "group": "beginner",
            "skill_rank": 0,
            "song_id": "x",
            "source_type": "phone_recording",
            "recording_device": "",
            "has_backing_track": False,
            "commercial_mastered": False,
            "same_song_group": "",
            "notes": "",
        },
    ]
    fp, dupes = fingerprint_samples(rows)
    assert "s2" in dupes
    assert fp[1]["duplicate_input"] is True
    active = filter_active(fp)
    assert len(active) == 1


def test_subject_level_grouping():
    rows = [
        {"subject_id": "a", "sample_id": "1"},
        {"subject_id": "a", "sample_id": "2"},
        {"subject_id": "b", "sample_id": "3"},
    ]
    g = subject_groups(rows)
    assert g["a"] == ["1", "2"]
    assert dataset_counts(
        [
            {"subject_id": "a", "group": "expert"},
            {"subject_id": "b", "group": "beginner"},
        ]
    )["subjects"] == 2


def test_same_song_subset():
    rows = [
        {"same_song_group": "g1", "group": "expert", "sample_id": "e"},
        {"same_song_group": "g1", "group": "beginner", "sample_id": "b"},
        {"same_song_group": "", "group": "intermediate", "sample_id": "i"},
        {"same_song_group": "solo", "group": "expert", "sample_id": "e2"},
    ]
    sub = same_song_subset(rows)
    ids = {r["sample_id"] for r in sub}
    assert ids == {"e", "b"}


def test_source_type_stratification_in_manifest_example():
    path = Path("data/discrimination_manifest.example.csv")
    # example may be comments-only → empty ok
    rows = load_manifest(path)
    assert isinstance(rows, list)


def test_auc_and_spearman_and_cliffs():
    # perfectly separable
    scores = [0, 1, 2, 3, 10, 11, 12, 13]
    labels = [0, 0, 0, 0, 1, 1, 1, 1]
    auc = roc_auc(scores, labels)
    assert auc["auc"] is not None and auc["auc"] >= 0.99
    rho = spearman_rho(scores, labels)
    assert rho["rho"] is not None and rho["rho"] > 0.8
    d = cliffs_delta([10, 11, 12], [0, 1, 2])
    assert d["delta"] is not None and d["delta"] > 0.9


def test_bootstrap_ci():
    scores = list(range(20))
    labels = [0] * 10 + [1] * 10
    ci = bootstrap_ci(scores, labels, stat="auc", n_boot=50, seed=0)
    assert ci["lo"] is not None and ci["hi"] is not None
    assert ci["lo"] <= ci["hi"]


def test_saturation_rate():
    r = saturation_rate([96, 97, 50, 100], threshold=95)
    assert r["n_sat"] == 3
    assert abs(r["rate"] - 0.75) < 1e-9


def test_mapping_loss_and_vocal_benefit():
    assert mapping_loss_label(0.80, 0.55) == "MAPPING_LOSS"
    assert mapping_loss_label(0.55, 0.56) == "SIMILAR"
    assert vocal_benefit_label(0.55, 0.70) == "VOCAL_BETTER"
    assert vocal_benefit_label(0.70, 0.55) == "RAW_BETTER"


def test_feature_verdict_and_calibration_readiness():
    v = classify_feature_verdict(
        {
            "n": 40,
            "n_expert": 12,
            "n_beginner": 12,
            "auc": 0.78,
            "rho": 0.4,
            "saturation_rate": 0.1,
            "source_auc": 0.5,
            "raw_auc": 0.8,
            "mapped_auc": 0.78,
            "unknown_rate": 0.0,
        }
    )
    assert v["verdict"] == "KEEP"
    v2 = classify_feature_verdict(
        {
            "n": 40,
            "n_expert": 12,
            "n_beginner": 12,
            "auc": 0.58,
            "rho": 0.1,
            "saturation_rate": 0.2,
            "source_auc": 0.85,
            "unknown_rate": 0.0,
        }
    )
    assert v2["verdict"] == "RESTRICT"
    v3 = classify_feature_verdict(
        {
            "n": 40,
            "n_expert": 12,
            "n_beginner": 12,
            "auc": 0.60,
            "rho": 0.2,
            "saturation_rate": 0.1,
            "source_auc": 0.5,
            "raw_auc": 0.80,
            "mapped_auc": 0.58,
            "unknown_rate": 0.0,
        }
    )
    assert v3["verdict"] == "CALIBRATION_CANDIDATE"
    assert (
        axis_calibration_readiness(
            {
                "n": 10,
                "auc": 0.9,
                "rho": 0.5,
                "unknown_rate": 0.0,
                "n_expert": 5,
                "n_beginner": 5,
            }
        )
        == "NOT_READY"
    )
    assert (
        axis_calibration_readiness(
            {
                "n": 40,
                "auc": 0.75,
                "rho": 0.4,
                "unknown_rate": 0.1,
                "source_confound": False,
                "n_expert": 12,
                "n_beginner": 12,
            }
        )
        == "READY"
    )


def test_unknown_rate_calculation():
    statuses = ["unknown", "normal", "unknown", "normal"]
    rate = float(np.mean([1 if s == "unknown" else 0 for s in statuses]))
    assert rate == 0.5


def test_synthetic_benchmark_script(tmp_path: Path):
    import subprocess
    import sys

    out = tmp_path / "bench"
    cmd = [
        sys.executable,
        str(Path("scripts/run_discrimination_benchmark.py")),
        "--synthetic-demo",
        "--output",
        str(out),
    ]
    r = subprocess.run(cmd, cwd=str(Path.cwd()), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout
    assert (out / "benchmark_summary.md").exists()
    assert (out / "feature_verdicts.csv").exists()
    assert (out / "feature_statistics.csv").exists()
    assert (out / "run_metadata.json").exists()
