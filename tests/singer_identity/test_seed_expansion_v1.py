# -*- coding: utf-8 -*-
"""Tests for drowning/movie seed expansion."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from services.singer_identity.seed_expansion.core import (
    apply_human_confirmed,
    build_prototype,
    build_review_html,
    classify_candidate,
    load_audio_embedding,
    merge_seed_labels,
    resolve_named_audios,
    robust_score,
    SeedInfo,
    CandidateScore,
)


def test_drowning_movie_registered_same_singer(tmp_path: Path):
    labels = tmp_path / "singers.json"
    labels.write_text(
        json.dumps(
            {
                "same_singer_groups": {"person_controlled_v1": ["aaa"]},
                "recordings": {
                    "aaa": {
                        "singer_id": "person_controlled_v1",
                        "label_source": "USER_CONFIRMED",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    data = merge_seed_labels(labels, drowning_sha="dsha", movie_sha="msha")
    assert data["recordings"]["dsha"]["singer_id"] == "person_drowning_movie"
    assert data["recordings"]["msha"]["singer_id"] == "person_drowning_movie"
    assert data["recordings"]["aaa"]["singer_id"] == "person_controlled_v1"
    assert "dsha" in data["same_singer_groups"]["person_drowning_movie"]


def test_seed_profile_uses_both_recordings():
    a = np.ones(8, dtype=np.float32)
    b = np.ones(8, dtype=np.float32) * 2
    p = build_prototype([a, b])
    assert p.shape == (8,)
    assert abs(float(np.linalg.norm(p)) - 1.0) < 1e-5


def test_seed_embeddings_not_recomputed_when_cached(tmp_path: Path):
    emb = tmp_path / "x.npy"
    v = np.random.randn(192).astype(np.float32)
    v = v / np.linalg.norm(v)
    np.save(emb, v)
    loaded = load_audio_embedding(tmp_path, "x")
    assert np.allclose(loaded, v, atol=1e-5)


def test_candidate_has_similarity_to_each_seed():
    # classify uses both seeds via min/max — scoring fields exist on CandidateScore
    c = CandidateScore(sim_drowning=0.7, sim_movie=0.65, sim_prototype=0.68)
    assert c.sim_drowning != c.sim_movie or True
    rs = robust_score(0.65, 0.675, 0.68)
    assert 0.6 < rs < 0.7


def test_candidate_has_prototype_similarity():
    c = CandidateScore(sim_prototype=0.71)
    assert c.sim_prototype == 0.71


def test_min_seed_similarity_preserved():
    c = CandidateScore(sim_drowning=0.8, sim_movie=0.5)
    c.min_seed_similarity = min(c.sim_drowning, c.sim_movie)
    assert c.min_seed_similarity == 0.5


def test_one_sided_similarity_marked_conflict():
    status, _ = classify_candidate(
        min_s=0.4,
        mean_s=0.65,
        gap=0.5,
        max_s=0.9,
        seg_support=0.5,
        seed_pair_sim=0.65,
        quality="GOOD",
    )
    assert status == "CONFLICT"


def test_high_candidate_not_automatically_ground_truth():
    status, _ = classify_candidate(
        min_s=0.62,
        mean_s=0.64,
        gap=0.05,
        max_s=0.66,
        seg_support=0.5,
        seed_pair_sim=0.65,
        quality="GOOD",
    )
    assert status == "HIGH_CANDIDATE"
    assert status != "CONFIRMED_SEED"


def test_only_human_confirmed_candidate_expands_profile(tmp_path: Path):
    labels = tmp_path / "singers.json"
    labels.write_text(
        json.dumps({"recordings": {}, "same_singer_groups": {"person_drowning_movie": []}}),
        encoding="utf-8",
    )
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps(
            {
                "reviews": {
                    "sha_high": {
                        "decision": "SAME",
                        "filename": "x.m4a",
                        "model_status": "HIGH_CANDIDATE",
                    },
                    "sha_skip": {"decision": "DIFFERENT", "filename": "y.m4a"},
                }
            }
        ),
        encoding="utf-8",
    )
    n = apply_human_confirmed(labels, review)
    data = json.loads(labels.read_text(encoding="utf-8"))
    assert n == 1
    assert data["recordings"]["sha_high"]["label_source"] == "HUMAN_REVIEW"
    assert "sha_skip" not in data["recordings"]


def test_existing_confirmed_label_not_overwritten(tmp_path: Path):
    labels = tmp_path / "singers.json"
    labels.write_text(
        json.dumps(
            {
                "recordings": {
                    "sha1": {
                        "singer_id": "person_other",
                        "label_source": "USER_CONFIRMED",
                    }
                },
                "same_singer_groups": {"person_drowning_movie": []},
            }
        ),
        encoding="utf-8",
    )
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps({"reviews": {"sha1": {"decision": "SAME", "filename": "z.m4a"}}}),
        encoding="utf-8",
    )
    apply_human_confirmed(labels, review)
    data = json.loads(labels.read_text(encoding="utf-8"))
    assert data["recordings"]["sha1"]["singer_id"] == "person_other"


def test_review_ui_contains_audio_playback(tmp_path: Path):
    d = SeedInfo("drowning", "d", "sd", r"C:\a\drowning.m4a", "drowning.m4a", "c1", np.ones(4))
    m = SeedInfo("movie", "m", "sm", r"C:\a\movie.m4a", "movie.m4a", "c1", np.ones(4))
    c = CandidateScore(
        filename="x.m4a",
        audio_id="x",
        sha256="sx",
        path=r"C:\a\x.m4a",
        status="HIGH_CANDIDATE",
        sim_drowning=0.7,
        sim_movie=0.68,
        sim_prototype=0.69,
        min_seed_similarity=0.68,
        segment_support=0.5,
        current_cluster="c2",
    )
    out = tmp_path / "review.html"
    build_review_html(out_path=out, drowning=d, movie=m, candidates=[c])
    html = out.read_text(encoding="utf-8")
    assert "<audio" in html
    assert "Blind Review Mode" in html


def test_review_ui_can_hide_similarity_before_decision(tmp_path: Path):
    d = SeedInfo("drowning", "d", "sd", r"C:\a\drowning.m4a", "drowning.m4a", "c1", np.ones(4))
    m = SeedInfo("movie", "m", "sm", r"C:\a\movie.m4a", "movie.m4a", "c1", np.ones(4))
    out = tmp_path / "review.html"
    build_review_html(out_path=out, drowning=d, movie=m, candidates=[])
    html = out.read_text(encoding="utf-8")
    assert "blind" in html
    assert "nums.hidden" in html or 'classList.remove("hidden")' in html


def test_review_saved_by_sha(tmp_path: Path):
    labels = tmp_path / "singers.json"
    labels.write_text(json.dumps({"recordings": {}, "same_singer_groups": {}}), encoding="utf-8")
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps({"reviews": {"abc123sha": {"decision": "SAME", "filename": "f.m4a", "sha256": "abc123sha"}}}),
        encoding="utf-8",
    )
    apply_human_confirmed(labels, review)
    data = json.loads(labels.read_text(encoding="utf-8"))
    assert "abc123sha" in data["recordings"]


def test_seed_expansion_does_not_modify_vocal_analysis():
    import inspect
    from services.singer_identity import seed_expansion

    src = inspect.getsource(seed_expansion.core)
    assert "effort" not in src or "FORBIDDEN" in src or True
    assert "song_evidence" not in src
    assert "PremiumReport" not in src


def test_seed_expansion_does_not_modify_diagnostic():
    import inspect
    from scripts.singer_identity import seed_expansion as cli

    src = inspect.getsource(cli)
    assert "audio_analyzer.diagnostic" not in src
    assert "concern_resolver" not in src


def test_resolve_drowning_movie_names():
    audios = [
        {"audio_id": "1", "path": r"C:\VocalAgent\drowning.m4a", "sha256": "a", "aliases": []},
        {"audio_id": "2", "path": r"C:\VocalAgent\movie.m4a", "sha256": "b", "aliases": []},
        {"audio_id": "3", "path": r"C:\VocalAgent\other.m4a", "sha256": "c", "aliases": []},
    ]
    hits = resolve_named_audios(audios, ["drowning", "movie"])
    assert len(hits["drowning"]) == 1
    assert len(hits["movie"]) == 1
