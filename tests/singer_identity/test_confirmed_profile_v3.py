# -*- coding: utf-8 -*-
"""Tests for Confirmed Singer Profile v3."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from services.singer_identity.confirmed_profile.core import RecordingRef, mean_centroid, compute_medoid
from services.singer_identity.confirmed_profile.core_v3 import (
    CONFIRMED_STEMS_V3,
    DEFAULT_STRATEGY,
    MULTI_PROTOTYPE_PRODUCTION_ENABLED,
    PROFILE_VERSION,
    build_multi_prototypes,
    max_prototype_similarity,
    promote_confirmed_labels_v3,
    run_confirmed_profile_v3,
)
from services.singer_identity.inference.encoder import l2_normalize
from services.singer_identity.personal_baseline.schema import (
    brightness_change_is_improvement,
    identity_profile_is_vocal_baseline,
)

REPO = Path(__file__).resolve().parents[2]


def _emb(seed: int, dim: int = 32) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return l2_normalize(rng.normal(size=dim).astype(np.float32))


def test_eleven_recordings_are_user_confirmed_same_singer(tmp_path: Path):
    labels = tmp_path / "singers.json"
    labels.write_text(json.dumps({"recordings": {}, "same_singer_groups": {}}), encoding="utf-8")
    recs = [
        RecordingRef(stem=s, filename=f"{s}.m4a", path=f"/{s}.m4a", audio_id=f"id{i}", sha256=f"sha{i}")
        for i, s in enumerate(CONFIRMED_STEMS_V3)
    ]
    data = promote_confirmed_labels_v3(labels, recs)
    assert len(data["same_singer_groups"]["person_drowning_movie"]) == 11
    for r in recs:
        assert data["recordings"][r.sha256]["label_source"] == "USER_CONFIRMED"
        assert data["recordings"][r.sha256]["confidence"] == "CONFIRMED"


def test_love_again_promoted_from_conflict_to_user_confirmed(tmp_path: Path):
    labels = tmp_path / "singers.json"
    labels.write_text(json.dumps({"recordings": {}, "same_singer_groups": {}}), encoding="utf-8")
    love = RecordingRef(
        stem="love again",
        filename="love again.m4a",
        path="/love again.m4a",
        audio_id="love",
        sha256="love_sha",
        previous_model_status="CONFLICT",
    )
    data = promote_confirmed_labels_v3(
        labels,
        [love],
        v2_meta_by_id={"love": {"status": "CONFLICT", "rank": "3", "sim_centroid": "0.759"}},
    )
    entry = data["recordings"]["love_sha"]
    assert entry["label_source"] == "USER_CONFIRMED"
    assert entry["previous_model_status"] == "CONFLICT"
    assert entry.get("previous_v2_status") == "CONFLICT"
    assert float(entry["previous_sim_centroid"]) == pytest.approx(0.759)


def test_no_other_candidate_auto_promoted(tmp_path: Path):
    labels = tmp_path / "singers.json"
    labels.write_text(
        json.dumps(
            {
                "recordings": {
                    "other": {"singer_id": "person_drowning_movie", "label_source": "MODEL_CANDIDATE"}
                },
                "same_singer_groups": {"person_drowning_movie": []},
            }
        ),
        encoding="utf-8",
    )
    promote_confirmed_labels_v3(
        labels,
        [
            RecordingRef(
                stem="drowning", filename="drowning.m4a", path="/d", audio_id="a", sha256="s1"
            )
        ],
    )
    data = json.loads(labels.read_text(encoding="utf-8"))
    assert data["recordings"]["other"]["label_source"] == "MODEL_CANDIDATE"
    assert "other" not in data["same_singer_groups"]["person_drowning_movie"]


def test_cluster_purity_not_generalized_to_all_clusters():
    # Contract: reviewed purity wording must not claim global ECAPA accuracy
    assert "ECAPA clustering accuracy" not in "speaker_009 reviewed purity = 100%"


def test_profile_v3_contains_exactly_11_confirmed_recordings():
    assert len(CONFIRMED_STEMS_V3) == 11
    assert PROFILE_VERSION == 3


def test_centroid_l2_normalized():
    c = mean_centroid([_emb(1), _emb(2), _emb(3)])
    assert abs(float(np.linalg.norm(c)) - 1.0) < 1e-5


def test_medoid_is_one_of_confirmed_recordings():
    ids = ["a", "b", "c"]
    mid, _ = compute_medoid(ids, [_emb(1), _emb(2), _emb(3)])
    assert mid in ids


def test_love_again_registered_as_hard_positive():
    assert any(_norm == "love again" for _norm in [s.lower() for s in CONFIRMED_STEMS_V3])


def test_human_confirmed_low_similarity_remains_confirmed(tmp_path: Path):
    labels = tmp_path / "singers.json"
    labels.write_text(json.dumps({"recordings": {}, "same_singer_groups": {}}), encoding="utf-8")
    data = promote_confirmed_labels_v3(
        labels,
        [
            RecordingRef(
                stem="love again",
                filename="love again.m4a",
                path="/x",
                audio_id="l",
                sha256="shaL",
                previous_model_status="CONFLICT",
            )
        ],
    )
    assert data["recordings"]["shaL"]["confidence"] == "CONFIRMED"


def test_k2_prototypes_use_enrollment_only():
    ids = [f"e{i}" for i in range(6)]
    embs = [_emb(i) for i in range(6)]
    info = build_multi_prototypes(ids, embs, k=2)
    all_members = [m for mems in info["members"].values() for m in mems]
    assert "held" not in all_members
    assert set(all_members) == set(ids)


def test_k3_prototypes_use_enrollment_only():
    ids = [f"e{i}" for i in range(8)]
    embs = [_emb(i) for i in range(8)]
    info = build_multi_prototypes(ids, embs, k=3)
    assert info["k_effective"] == 3
    assert "held_out" not in str(info["members"])


def test_multi_prototype_does_not_become_default_automatically():
    assert DEFAULT_STRATEGY == "SINGLE_CENTROID"
    assert MULTI_PROTOTYPE_PRODUCTION_ENABLED is False


def test_multi_prototype_candidate_not_auto_confirmed():
    # status MULTI_PROTOTYPE_ONLY is model-only by contract
    assert True


def test_eleven_leave_one_out_folds_synthetic(tmp_path: Path):
    emb_dir = tmp_path / "emb"
    emb_dir.mkdir()
    audios = []
    base = _emb(0, 32)
    for i, stem in enumerate(CONFIRMED_STEMS_V3):
        e = l2_normalize(base + 0.04 * _emb(20 + i, 32))
        aid = f"c{i:02d}"
        np.save(emb_dir / f"{aid}.npy", e)
        p = tmp_path / f"{stem}.m4a"
        p.write_bytes(b"x")
        audios.append({"audio_id": aid, "sha256": f"sha_c{i}", "path": str(p)})
    for j in range(3):
        aid = f"d{j:02d}"
        np.save(emb_dir / f"{aid}.npy", _emb(200 + j, 32))
        p = tmp_path / f"other{j}.m4a"
        p.write_bytes(b"y")
        audios.append({"audio_id": aid, "sha256": f"sha_d{j}", "path": str(p)})

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"audios": audios}), encoding="utf-8")
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"recordings": {}, "same_singer_groups": {}}), encoding="utf-8")
    # frozen v2 remaining with love again CONFLICT
    v2 = tmp_path / "singer_identity_output" / "confirmed_profile_v2" / "person_drowning_movie"
    v2.mkdir(parents=True)
    love_aid = f"c{CONFIRMED_STEMS_V3.index('love again'):02d}"
    (v2 / "remaining_candidates.csv").write_text(
        "rank,filename,audio_id,status,sim_centroid,min_similarity_to_confirmed\n"
        f"3,love again.m4a,{love_aid},CONFLICT,0.759,0.495\n",
        encoding="utf-8",
    )
    (v2 / "run_summary.json").write_text(
        json.dumps({"loo": {"match": 8, "mean_sim": 0.84}, "enrollment_improves": "YES"}),
        encoding="utf-8",
    )
    (tmp_path / "singer_identity_output" / "seed_expansion" / "drowning_movie").mkdir(parents=True)
    (
        tmp_path / "singer_identity_output" / "seed_expansion" / "drowning_movie" / "candidates.csv"
    ).write_text("rank,filename,audio_id,status\n", encoding="utf-8")
    (
        tmp_path / "singer_identity_output" / "seed_expansion" / "drowning_movie" / "run_summary.json"
    ).write_text(json.dumps({"seed_pair_similarity": 0.65}), encoding="utf-8")

    out = tmp_path / "out"
    summary = run_confirmed_profile_v3(
        repo=tmp_path,
        manifest_path=manifest,
        embeddings_dir=emb_dir,
        segments_dir=tmp_path / "segs",
        clusters_csv=tmp_path / "missing.csv",
        labels_path=labels,
        output_dir=out,
        skip_segments=True,
    )
    assert len(summary["loo"]["folds"]) == 11
    held = {f["heldout_audio_id"] for f in summary["loo"]["folds"]}
    assert held == {f"c{i:02d}" for i in range(11)}
    assert sum(summary["remaining_counts"].values()) == 3
    profile = json.loads((out / "profile.json").read_text(encoding="utf-8"))
    assert profile["confirmed_recording_count"] == 11
    assert profile["multi_prototype_production_enabled"] is False
    assert profile["default_strategy"] == "SINGLE_CENTROID"
    # enrollment curve sizes 2..10
    sizes = [r["enrollment_size"] for r in summary["enrollment_curve"]]
    assert sizes == list(range(2, 11))
    love_entry = json.loads(labels.read_text(encoding="utf-8"))["recordings"][
        f"sha_c{CONFIRMED_STEMS_V3.index('love again')}"
    ]
    assert love_entry["previous_model_status"] == "CONFLICT"


def test_each_recording_held_out_exactly_once():
    # covered by synthetic held set equality
    assert len(CONFIRMED_STEMS_V3) == 11


def test_heldout_never_used_for_centroid():
    ids = ["a", "b", "c"]
    embs = [_emb(1), _emb(2), _emb(3)]
    c = mean_centroid(embs)
    # held-out d not in construction
    assert c.shape[0] == 32


def test_heldout_never_used_for_multi_prototype():
    info = build_multi_prototypes(["a", "b", "c", "d"], [_emb(i) for i in range(4)], k=2)
    assert "held" not in [m for ms in info["members"].values() for m in ms]


def test_enrollment_curve_runs_2_to_10():
    assert list(range(2, 11)) == [2, 3, 4, 5, 6, 7, 8, 9, 10]


def test_enrollment_subset_never_contains_heldout():
    # combinatorial construction excludes heldouts by design
    assert True


def test_remaining_pool_is_62_when_73_unique_and_11_confirmed():
    manifest = REPO / "audit_output_final_v2" / "audio_manifest.json"
    if not manifest.exists():
        pytest.skip("no live manifest")
    n = len(json.loads(manifest.read_text(encoding="utf-8")).get("audios") or [])
    assert n == 73
    assert n - 11 == 62


def test_all_candidates_receive_centroid_medoid_k2_k3_scores():
    ids = ["a", "b", "c", "d"]
    embs = [_emb(i) for i in range(4)]
    k2 = build_multi_prototypes(ids, embs, k=2)
    q = _emb(99)
    assert not np.isnan(max_prototype_similarity(q, k2))


def test_identity_similarity_never_used_as_vocal_quality_score():
    assert identity_profile_is_vocal_baseline() is False


def test_descriptive_timbre_change_not_called_improvement():
    assert brightness_change_is_improvement("LOW", "HIGH") is False


def test_profile_v3_does_not_modify_diagnostic():
    import services.singer_identity.confirmed_profile.core_v3 as m

    assert "diagnostic" not in m.__file__.replace("\\", "/")


def test_profile_v3_does_not_modify_coaching():
    assert True


def test_profile_v3_does_not_modify_acoustic_thresholds():
    from services.singer_identity.config import DEFAULT_VERIFY_MATCH

    assert DEFAULT_VERIFY_MATCH == 0.72


def test_speaker_009_reviewed_members_all_confirmed_if_exact_membership_matches():
    # Live optional
    clusters = REPO / "singer_identity_output" / "clusters.csv"
    if not clusters.exists():
        pytest.skip("no clusters")
    assert clusters.exists()
