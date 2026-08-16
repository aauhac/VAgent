# -*- coding: utf-8 -*-
"""Audio load + vocal segment selection (no VAgent diagnostic axes)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from services.singer_identity.config import (
    DEFAULT_SR,
    MIN_SEGMENT_SEC,
    SEGMENT_HOP_SEC,
    SEGMENT_SEC,
)

FORBIDDEN_STEMS = {
    "no_vocals.wav",
    "instrumental.wav",
    "no_vocals",
    "instrumental",
}


@dataclass
class VocalSegment:
    start_sec: float
    end_sec: float
    audio: np.ndarray
    sr: int
    quality: float


def load_mono(path: str | Path, sr: int = DEFAULT_SR) -> tuple[np.ndarray, int]:
    path = Path(path)
    if path.name.lower() in FORBIDDEN_STEMS or path.stem.lower() in FORBIDDEN_STEMS:
        raise ValueError(f"forbidden stem for singer-id: {path.name}")

    def _resample(y: np.ndarray, file_sr: int) -> tuple[np.ndarray, int]:
        if int(file_sr) == sr:
            return y.astype(np.float32, copy=False), int(file_sr)
        import torch
        import torchaudio.functional as F

        wav = torch.from_numpy(np.asarray(y, dtype=np.float32)).unsqueeze(0)
        y2 = F.resample(wav, int(file_sr), sr).squeeze(0).numpy().astype(np.float32)
        return y2, sr

    # 1) soundfile (wav/flac/ogg)
    try:
        import soundfile as sf

        y, file_sr = sf.read(str(path), always_2d=False)
        y = np.asarray(y, dtype=np.float32)
        if y.ndim > 1:
            y = y.mean(axis=1)
        return _resample(y, int(file_sr))
    except Exception:
        pass

    # 2) ffmpeg decode to temp wav (m4a/webm/mp3) — avoids librosa+speechbrain clash
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            str(sr),
            str(tmp_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        import soundfile as sf

        y, file_sr = sf.read(str(tmp_path), always_2d=False)
        y = np.asarray(y, dtype=np.float32)
        if y.ndim > 1:
            y = y.mean(axis=1)
        return _resample(y, int(file_sr))
    except Exception as e:
        raise RuntimeError(f"failed to load audio for singer-id: {path}: {e}") from e
    finally:
        tmp_path.unlink(missing_ok=True)


def prefer_vocal_stem(path: str | Path) -> Path:
    """Reuse Demucs vocals.wav sibling if present; never no_vocals."""
    p = Path(path)
    for cand in (p.parent / "vocals.wav", p.parent / "vocals" / "vocals.wav"):
        if cand.exists() and cand.name.lower() not in FORBIDDEN_STEMS:
            return cand
    return p


def _frame_energy(y: np.ndarray, sr: int, win: float = 0.025, hop: float = 0.010) -> np.ndarray:
    n_win = max(1, int(win * sr))
    n_hop = max(1, int(hop * sr))
    if len(y) < n_win:
        return np.array([float(np.mean(y**2))], dtype=np.float32)
    frames = []
    for i in range(0, len(y) - n_win + 1, n_hop):
        frames.append(float(np.mean(y[i : i + n_win] ** 2)))
    return np.asarray(frames, dtype=np.float32)


def select_vocal_segments(
    y: np.ndarray,
    sr: int,
    *,
    segment_sec: float = SEGMENT_SEC,
    hop_sec: float = SEGMENT_HOP_SEC,
    min_sec: float = MIN_SEGMENT_SEC,
    max_segments: int = 24,
) -> list[VocalSegment]:
    """Energy-based usable segments; reject silence / very short / low-energy."""
    if y.size == 0:
        return []
    energy = _frame_energy(y, sr)
    if energy.size == 0:
        return []
    thr = max(float(np.percentile(energy, 40)) * 0.5, 1e-8)
    hop = max(1, int(0.010 * sr))
    seg_len = int(segment_sec * sr)
    hop_len = int(hop_sec * sr)
    min_len = int(min_sec * sr)
    out: list[VocalSegment] = []
    for start in range(0, max(1, len(y) - min_len + 1), max(hop_len, 1)):
        end = min(len(y), start + seg_len)
        if end - start < min_len:
            break
        chunk = y[start:end]
        # map to energy frames
        f0 = start // hop
        f1 = max(f0 + 1, end // hop)
        e = energy[f0:f1] if f1 <= len(energy) else energy[f0:]
        if e.size == 0:
            continue
        mean_e = float(np.mean(e))
        if mean_e < thr:
            continue
        # quality: relative energy + coverage of above-threshold frames
        cov = float(np.mean(e >= thr))
        quality = float(np.clip(0.4 * cov + 0.6 * min(1.0, mean_e / (thr * 8 + 1e-9)), 0.0, 1.0))
        if quality < 0.25:
            continue
        out.append(
            VocalSegment(
                start_sec=start / sr,
                end_sec=end / sr,
                audio=chunk.astype(np.float32, copy=False),
                sr=sr,
                quality=quality,
            )
        )
        if len(out) >= max_segments:
            break
    # Prefer higher quality, keep temporal diversity
    out.sort(key=lambda s: -s.quality)
    if len(out) > 12:
        out = out[:12]
    out.sort(key=lambda s: s.start_sec)
    return out
