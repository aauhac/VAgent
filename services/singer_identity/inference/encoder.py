# -*- coding: utf-8 -*-
"""Singer encoder interface + adapters (speaker embeddings only)."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np

from services.singer_identity.config import (
    EMBEDDING_DIM,
    ENCODER_NAME_BASELINE,
    MODEL_VERSION,
    PREPROCESSING_VERSION,
)
from services.singer_identity.embeddings.aggregate import aggregate_segment_embeddings
from services.singer_identity.preprocessing.segments import (
    VocalSegment,
    load_mono,
    prefer_vocal_stem,
    select_vocal_segments,
)
from services.singer_identity.schemas.models import AudioEmbeddingResult, ModelInfo


def l2_normalize(v: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    n = float(np.linalg.norm(v))
    if n < eps:
        return v.astype(np.float32)
    return (v / n).astype(np.float32)


class SingerEncoder(ABC):
    encoder_name: str = "abstract"
    model_version: str = MODEL_VERSION
    embedding_dim: int = EMBEDDING_DIM
    preprocessing_version: str = PREPROCESSING_VERSION

    @abstractmethod
    def encode_segment(self, audio: np.ndarray, sr: int) -> np.ndarray:
        ...

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            encoder_name=self.encoder_name,
            model_version=self.model_version,
            embedding_dim=self.embedding_dim,
            preprocessing_version=self.preprocessing_version,
        )

    def encode_audio(
        self,
        audio: np.ndarray,
        sr: int,
        *,
        audio_id: str = "",
        sha256: str = "",
        filename: str = "",
        include_embedding: bool = True,
    ) -> AudioEmbeddingResult:
        segments = select_vocal_segments(audio, sr)
        # Fallback: whole clip as one segment if energy gate yields nothing
        if not segments and audio.size >= int(0.5 * sr):
            from services.singer_identity.preprocessing.segments import VocalSegment

            segments = [
                VocalSegment(
                    start_sec=0.0,
                    end_sec=len(audio) / sr,
                    audio=audio.astype(np.float32, copy=False),
                    sr=sr,
                    quality=0.3,
                )
            ]
        embs: list[np.ndarray] = []
        weights: list[float] = []
        for seg in segments:
            e = self.encode_segment(seg.audio, seg.sr)
            e = l2_normalize(e)
            embs.append(e)
            weights.append(seg.quality)
        agg, used = aggregate_segment_embeddings(embs, weights)
        quality = "FAILED"
        if used >= 4:
            quality = "GOOD"
        elif used >= 2:
            quality = "FAIR"
        elif used >= 1:
            quality = "POOR"
        return AudioEmbeddingResult(
            audio_id=audio_id,
            embedding_dim=self.embedding_dim,
            segment_count=len(segments),
            used_segment_count=used,
            quality=quality,  # type: ignore[arg-type]
            model_version=self.model_version,
            encoder_name=self.encoder_name,
            preprocessing_version=self.preprocessing_version,
            embedding=agg.tolist() if include_embedding and agg is not None else None,
            sha256=sha256,
            filename=filename,
        )

    def encode_path(
        self,
        path: str,
        *,
        audio_id: str = "",
        sha256: str = "",
        include_embedding: bool = True,
    ) -> AudioEmbeddingResult:
        from pathlib import Path

        p = prefer_vocal_stem(path)
        y, sr = load_mono(p)
        return self.encode_audio(
            y,
            sr,
            audio_id=audio_id,
            sha256=sha256,
            filename=Path(path).name,
            include_embedding=include_embedding,
        )


class MelXVectorStatsEncoder(SingerEncoder):
    """Stage-0 baseline: log-mel + MFCC stats pooling → fixed 192-d projection.

    Not a full ECAPA substitute; adapter-ready for SpeechBrain when installed.
    Identity features only — never reads VAgent diagnostic axes.
    """

    encoder_name = ENCODER_NAME_BASELINE
    model_version = MODEL_VERSION
    embedding_dim = EMBEDDING_DIM

    def __init__(self, dim: int = EMBEDDING_DIM, seed: int = 20250816):
        self.embedding_dim = dim
        rng = np.random.default_rng(seed)
        # Fixed projection from feature vector (~160) to dim
        self._proj = rng.normal(0, 1.0 / np.sqrt(160), size=(160, dim)).astype(np.float64)

    def encode_segment(self, audio: np.ndarray, sr: int) -> np.ndarray:
        import librosa

        y = np.asarray(audio, dtype=np.float32)
        if y.size < int(0.4 * sr):
            # pad short
            pad = int(0.4 * sr) - y.size
            y = np.pad(y, (0, pad))
        # Remove gross DC
        y = y - float(np.mean(y))
        # Log-mel
        mel = librosa.feature.melspectrogram(
            y=y, sr=sr, n_fft=512, hop_length=160, n_mels=40, fmin=20, fmax=7600
        )
        logmel = librosa.power_to_db(mel, ref=np.max)
        mfcc = librosa.feature.mfcc(S=librosa.power_to_db(mel), n_mfcc=20)
        # Stats: mean+std over time for mel(40) + mfcc(20) → 120, pad/truncate to 160
        feats = []
        for mat in (logmel, mfcc):
            feats.append(np.mean(mat, axis=1))
            feats.append(np.std(mat, axis=1))
        vec = np.concatenate(feats).astype(np.float64)
        if vec.size < 160:
            vec = np.pad(vec, (0, 160 - vec.size))
        else:
            vec = vec[:160]
        # Light CMVN-ish
        vec = (vec - vec.mean()) / (vec.std() + 1e-6)
        out = vec @ self._proj
        return l2_normalize(out)


class SpeechBrainSingerEncoder(SingerEncoder):
    """Optional ECAPA-TDNN adapter (requires speechbrain)."""

    encoder_name = "speechbrain_ecapa_tdnn"
    model_version = "speechbrain-spkrec-ecapa-voxceleb-v1"
    embedding_dim = 192

    def __init__(self, savedir: Optional[str] = None):
        import os

        # Windows often lacks symlink privilege — force copy strategy
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
        from speechbrain.inference.speaker import EncoderClassifier  # type: ignore

        try:
            from speechbrain.utils.fetching import LocalStrategy

            self._clf = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir=savedir or "pretrained_models/spkrec-ecapa-voxceleb",
                local_strategy=LocalStrategy.COPY,
            )
        except TypeError:
            self._clf = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir=savedir or "pretrained_models/spkrec-ecapa-voxceleb",
            )
        import torch

        wav = torch.zeros(1, 16000)
        emb = self._clf.encode_batch(wav)
        self.embedding_dim = int(emb.reshape(-1).numel())

    def encode_segment(self, audio: np.ndarray, sr: int) -> np.ndarray:
        import torch
        import torchaudio.functional as F

        y = np.asarray(audio, dtype=np.float32)
        wav = torch.from_numpy(y).unsqueeze(0)
        if sr != 16000:
            wav = F.resample(wav, sr, 16000)
        with torch.no_grad():
            emb = self._clf.encode_batch(wav).squeeze().cpu().numpy().reshape(-1)
        return l2_normalize(emb)


def get_default_encoder() -> SingerEncoder:
    try:
        # Prefer local pretrained cache under runtime/
        from services.singer_identity.config import REPO_ROOT

        savedir = str(REPO_ROOT / "runtime" / "singer_identity" / "pretrained_ecapa")
        return SpeechBrainSingerEncoder(savedir=savedir)
    except Exception:
        return MelXVectorStatsEncoder()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = l2_normalize(a)
    b = l2_normalize(b)
    return float(np.dot(a, b))


def deterministic_noise_seed(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
