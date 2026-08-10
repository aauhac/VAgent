"""
preprocessing/audio_io.py
-------------------------
Minimal analysis-signal preprocessing.

Analysis signal may only:
  - convert to mono
  - unify sample rate
  - remove DC offset
  - light peak safety (optional)

No EQ / high shelf / compressor / aggressive dereverb on analysis path.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional, Union

import librosa
import numpy as np
import soundfile as sf

from audio_analyzer.audit.fingerprints import (
    cached_artifact_matches_source,
    sha256_file,
    write_source_sidecar,
)
from audio_analyzer.env_utils import resolve_ffmpeg_executable


SOUNDFILE_NATIVE = {".wav", ".flac", ".ogg", ".aiff", ".aif"}


def ensure_wav(
    source_path: Union[str, Path],
    work_dir: Path,
    sample_rate: int,
) -> Path:
    source_path = Path(source_path)
    if source_path.suffix.lower() in SOUNDFILE_NATIVE:
        return source_path

    converted = work_dir / "input_converted.wav"
    source_sha = sha256_file(source_path)
    # Existence-only cache is unsafe if another source reused the same work_dir
    if converted.exists() and cached_artifact_matches_source(converted, source_sha):
        return converted
    if converted.exists():
        converted.unlink(missing_ok=True)

    ffmpeg_exe = resolve_ffmpeg_executable()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i",
        str(source_path),
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        "-f",
        "wav",
        str(converted),
    ]
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed:\n{result.stderr}")
    write_source_sidecar(converted, source_sha)
    return converted


def load_analysis_audio(
    audio_path: Union[str, Path],
    work_dir: Path,
    sample_rate: int = 44100,
) -> tuple[np.ndarray, int, Path]:
    """
    Load audio for analysis with minimal preprocessing.
    Returns (y_analysis, sr, wav_path_used).
    """
    wav_path = ensure_wav(audio_path, work_dir, sample_rate)
    y, sr = librosa.load(str(wav_path), sr=sample_rate, mono=True)
    y = prepare_analysis_signal(y)
    return y.astype(np.float32), int(sr), wav_path


def prepare_analysis_signal(y: np.ndarray) -> np.ndarray:
    """DC offset removal + peak safety only."""
    if y.size == 0:
        return y.astype(np.float32)
    y = y.astype(np.float64)
    y = y - float(np.mean(y))
    peak = float(np.max(np.abs(y))) + 1e-12
    if peak > 1.0:
        y = y / peak * 0.99
    return y.astype(np.float32)


def save_wav(path: Path, y: np.ndarray, sr: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), y, sr)
    return path
