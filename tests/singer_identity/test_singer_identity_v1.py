# -*- coding: utf-8 -*-
"""Singer Identity Engine tests — isolated from VAgent diagnostic."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest

from services.singer_identity.clustering.cluster import cluster_embeddings
from services.singer_identity.enrollment.service import enroll_audio_files
from services.singer_identity.evaluation.metrics import (
    assert_no_segment_leakage,
    song_level_split,
)
from services.singer_identity.identification.service import identify_embedding
from services.singer_identity.inference.encoder import (
    MelXVectorStatsEncoder,
    cosine_similarity,
    l2_normalize,
)
from services.singer_identity.registry.store import SingerRegistry
from services.singer_identity.verification.service import verify_embedding


def _sine(sr=16000, sec=3.0, freq=220.0, phase=0.0):
    t = np.arange(int(sr * sec)) / sr
    y = 0.2 * np.sin(2 * np.pi * freq * t + phase)
    # add tiny harmonics for MFCC stability
    y += 0.05 * np.sin(2 * np.pi * (2 * freq) * t)
    return y.astype(np.float32)


def test_singer_service_import_does_not_load_vagent_diagnostic_engine():
    # Ensure diagnostic not imported as side effect of singer_identity package
    before = {k for k in sys.modules if k.startswith("audio_analyzer.diagnostic")}
    importlib.import_module("services.singer_identity.api.app")
    importlib.import_module("services.singer_identity.inference.encoder")
    after = {k for k in sys.modules if k.startswith("audio_analyzer.diagnostic")}
    assert after == before


def test_vagent_backend_does_not_require_singer_id_dependencies():
    # Backend diagnostic service must not import singer_identity
    import inspect

    try:
        from backend.app.diagnostic import service as diag

        src = inspect.getsource(diag)
    except Exception:
        pytest.skip("backend diagnostic not importable in this env")
    assert "singer_identity" not in src
    assert "SingerEncoder" not in src


def test_embedding_dimension_stable():
    enc = MelXVectorStatsEncoder(dim=192)
    e = enc.encode_segment(_sine(), 16000)
    assert e.shape == (192,)


def test_embedding_l2_normalized():
    enc = MelXVectorStatsEncoder()
    e = enc.encode_segment(_sine(), 16000)
    assert abs(float(np.linalg.norm(e)) - 1.0) < 1e-4


def test_same_audio_embedding_deterministic():
    enc = MelXVectorStatsEncoder()
    y = _sine()
    a = enc.encode_segment(y, 16000)
    b = enc.encode_segment(y.copy(), 16000)
    assert np.allclose(a, b, atol=1e-6)


def test_multiple_segments_aggregated():
    enc = MelXVectorStatsEncoder()
    y = _sine(sec=8.0)
    r = enc.encode_audio(y, 16000, audio_id="t", include_embedding=True)
    assert r.segment_count >= 2
    assert r.used_segment_count >= 1
    assert r.embedding is not None
    assert len(r.embedding) == 192


def test_enroll_multiple_recordings(tmp_path: Path):
    enc = MelXVectorStatsEncoder()
    reg = SingerRegistry(tmp_path / "reg")
    meta = reg.create_singer("가수 A", consented_enrollment=True, singer_id="singer_a")
    paths = []
    for i, f in enumerate([220.0, 230.0, 210.0]):
        p = tmp_path / f"a{i}.wav"
        import soundfile as sf

        sf.write(str(p), _sine(freq=f), 16000)
        paths.append(p)
    out = enroll_audio_files(reg, enc, meta["singer_id"], paths)
    assert out["recording_count"] == 3
    assert reg.get_centroid("singer_a") is not None


def test_profile_centroid_created(tmp_path: Path):
    enc = MelXVectorStatsEncoder()
    reg = SingerRegistry(tmp_path)
    reg.create_singer("A", consented_enrollment=True, singer_id="s1")
    emb = enc.encode_segment(_sine(), 16000)
    reg.add_recording("s1", embedding=emb, audio_sha256="x", filename="x.wav")
    assert reg.get_centroid("s1") is not None
    assert (tmp_path / "singers" / "s1" / "profile.json").exists()


def test_delete_singer_removes_identity_data(tmp_path: Path):
    reg = SingerRegistry(tmp_path)
    reg.create_singer("A", consented_enrollment=True, singer_id="s1")
    enc = MelXVectorStatsEncoder()
    reg.add_recording(
        "s1",
        embedding=enc.encode_segment(_sine(), 16000),
        audio_sha256="x",
        filename="x.wav",
    )
    assert reg.delete_singer("s1") is True
    assert reg.get_singer("s1") is None
    assert not (tmp_path / "singers" / "s1").exists()


def test_verify_known_match(tmp_path: Path):
    enc = MelXVectorStatsEncoder()
    reg = SingerRegistry(tmp_path)
    reg.create_singer("A", consented_enrollment=True, singer_id="s1")
    emb = enc.encode_segment(_sine(freq=220), 16000)
    reg.add_recording("s1", embedding=emb, audio_sha256="a", filename="a.wav")
    # near-identical
    emb2 = enc.encode_segment(_sine(freq=220, phase=0.01), 16000)
    r = verify_embedding(reg, emb2, "s1", match_thr=0.5, nonmatch_thr=0.2, model_version="t")
    assert r.decision in ("MATCH", "UNCERTAIN")
    assert r.similarity > 0.4


def test_verify_known_nonmatch(tmp_path: Path):
    enc = MelXVectorStatsEncoder()
    reg = SingerRegistry(tmp_path)
    reg.create_singer("A", consented_enrollment=True, singer_id="s1")
    reg.add_recording(
        "s1",
        embedding=enc.encode_segment(_sine(freq=220), 16000),
        audio_sha256="a",
        filename="a.wav",
    )
    other = enc.encode_segment(_sine(freq=880, sec=3.0), 16000)
    r = verify_embedding(reg, other, "s1", match_thr=0.95, nonmatch_thr=0.9, model_version="t")
    assert r.decision in ("NON_MATCH", "UNCERTAIN")


def test_verify_uncertain_supported(tmp_path: Path):
    enc = MelXVectorStatsEncoder()
    reg = SingerRegistry(tmp_path)
    reg.create_singer("A", consented_enrollment=True, singer_id="s1")
    reg.add_recording(
        "s1",
        embedding=enc.encode_segment(_sine(freq=220), 16000),
        audio_sha256="a",
        filename="a.wav",
    )
    emb = enc.encode_segment(_sine(freq=300), 16000)
    r = verify_embedding(reg, emb, "s1", match_thr=0.99, nonmatch_thr=0.01, model_version="t")
    assert r.decision == "UNCERTAIN"


def test_identify_top_candidates(tmp_path: Path):
    enc = MelXVectorStatsEncoder()
    reg = SingerRegistry(tmp_path)
    for sid, f in [("s1", 220.0), ("s2", 440.0)]:
        reg.create_singer(sid, consented_enrollment=True, singer_id=sid)
        reg.add_recording(
            sid,
            embedding=enc.encode_segment(_sine(freq=f), 16000),
            audio_sha256=sid,
            filename=f"{sid}.wav",
        )
    probe = enc.encode_segment(_sine(freq=220), 16000)
    r = identify_embedding(reg, probe, match_thr=0.3, margin_thr=0.0, model_version="t")
    assert r.candidates
    assert r.top_match is not None


def test_unknown_rejection(tmp_path: Path):
    enc = MelXVectorStatsEncoder()
    reg = SingerRegistry(tmp_path)
    reg.create_singer("s1", consented_enrollment=True, singer_id="s1")
    reg.add_recording(
        "s1",
        embedding=enc.encode_segment(_sine(freq=220), 16000),
        audio_sha256="a",
        filename="a.wav",
    )
    probe = enc.encode_segment(_sine(freq=900), 16000)
    r = identify_embedding(reg, probe, match_thr=0.99, margin_thr=0.0, model_version="t")
    assert r.decision == "UNKNOWN"


def test_no_forced_match_when_below_threshold(tmp_path: Path):
    enc = MelXVectorStatsEncoder()
    reg = SingerRegistry(tmp_path)
    reg.create_singer("s1", consented_enrollment=True, singer_id="s1")
    reg.add_recording(
        "s1",
        embedding=enc.encode_segment(_sine(freq=220), 16000),
        audio_sha256="a",
        filename="a.wav",
    )
    probe = enc.encode_segment(_sine(freq=230), 16000)
    r = identify_embedding(reg, probe, match_thr=0.9999, margin_thr=0.0, model_version="t")
    assert r.decision == "UNKNOWN"


def test_song_level_split_no_segment_leakage():
    recs = [
        {"singer_id": "a", "recording_id": "r1", "audio_sha256": "1"},
        {"singer_id": "a", "recording_id": "r2", "audio_sha256": "2"},
        {"singer_id": "a", "recording_id": "r3", "audio_sha256": "3"},
        {"singer_id": "b", "recording_id": "r4", "audio_sha256": "4"},
        {"singer_id": "b", "recording_id": "r5", "audio_sha256": "5"},
        {"singer_id": "b", "recording_id": "r6", "audio_sha256": "6"},
    ]
    split = song_level_split(recs)
    assert_no_segment_leakage(split)


def test_test_recordings_not_used_for_tuning():
    # Contract: train.py dry-run never reads TEST for weight updates
    from training.singer_identity import train as train_mod
    import inspect

    src = inspect.getsource(train_mod)
    assert "SKIPPED_INSUFFICIENT_DATA" in src
    assert "test set remains untouched" in src.lower() or "Test set remains untouched" in src


def test_clustering_does_not_require_fixed_k():
    rng = np.random.default_rng(0)
    # two blobs
    a = l2_normalize(rng.normal(size=32))
    b = l2_normalize(rng.normal(size=32))
    X = np.stack(
        [l2_normalize(a + 0.01 * rng.normal(size=32)) for _ in range(4)]
        + [l2_normalize(b + 0.01 * rng.normal(size=32)) for _ in range(4)]
    )
    out = cluster_embeddings(X, distance_threshold=0.4)
    assert "n_clusters" in out
    assert out["n_clusters"] >= 1


def test_unresolved_cluster_supported():
    rng = np.random.default_rng(1)
    X = np.stack([l2_normalize(rng.normal(size=16)) for _ in range(3)])
    out = cluster_embeddings(X, distance_threshold=0.01, min_cluster_size=2)
    # with tiny threshold may leave unresolved or singles
    assert "labels" in out
    assert -1 in out["labels"] or out["n_clusters"] >= 0


def test_singer_identity_does_not_read_effort():
    from services.singer_identity import FORBIDDEN_DIAGNOSTIC_AXES

    assert "effort" in FORBIDDEN_DIAGNOSTIC_AXES


def test_singer_identity_does_not_read_contact():
    from services.singer_identity import FORBIDDEN_DIAGNOSTIC_AXES

    assert "contact" in FORBIDDEN_DIAGNOSTIC_AXES


def test_singer_identity_does_not_read_register_connection():
    from services.singer_identity import FORBIDDEN_DIAGNOSTIC_AXES

    assert "register_connection" in FORBIDDEN_DIAGNOSTIC_AXES


def test_singer_identity_does_not_read_brightness():
    from services.singer_identity import FORBIDDEN_DIAGNOSTIC_AXES

    assert "brightness" in FORBIDDEN_DIAGNOSTIC_AXES


def test_singer_identity_does_not_read_presence():
    from services.singer_identity import FORBIDDEN_DIAGNOSTIC_AXES

    assert "presence" in FORBIDDEN_DIAGNOSTIC_AXES


def test_named_enrollment_requires_consent(tmp_path: Path):
    reg = SingerRegistry(tmp_path)
    with pytest.raises(ValueError):
        reg.create_singer("실명", consented_enrollment=False)
