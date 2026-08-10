"""
audio_analyzer/audit/fingerprints.py
------------------------------------
Content fingerprints for analysis inputs (cache / wrong-file detection).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np


def sha256_file(path: Union[str, Path], *, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def waveform_checksum(y: np.ndarray, *, sr: int, window_sec: float = 1.0) -> dict[str, Any]:
    arr = np.asarray(y, dtype=np.float32).reshape(-1)
    n = int(arr.size)
    win = min(n, max(1, int(sr * window_sec)))
    first = arr[:win]
    last = arr[-win:] if n else arr
    return {
        "n_samples": n,
        "duration_sec": round(n / float(sr), 6) if sr else None,
        "sample_rate": int(sr),
        "rms": float(np.sqrt(np.mean(arr**2))) if n else 0.0,
        "peak": float(np.max(np.abs(arr))) if n else 0.0,
        "full_sha256": sha256_bytes(arr.tobytes()),
        "first_1s_sha256": sha256_bytes(first.tobytes()),
        "last_1s_sha256": sha256_bytes(last.tobytes()),
    }


def file_fingerprint(
    path: Union[str, Path],
    *,
    label: str = "file",
    original_filename: Optional[str] = None,
) -> dict[str, Any]:
    path = Path(path)
    out: dict[str, Any] = {
        "label": label,
        "path": str(path),
        "original_filename": original_filename or path.name,
        "exists": path.exists(),
    }
    if not path.exists():
        return out
    out["size_bytes"] = int(path.stat().st_size)
    out["sha256"] = sha256_file(path)
    return out


def analysis_signal_fingerprint(
    *,
    source_path: Union[str, Path],
    analysis_wav: Optional[Union[str, Path]] = None,
    y: Optional[np.ndarray] = None,
    sr: Optional[int] = None,
    source_mode: str = "raw",
    vocals_path: Optional[Union[str, Path]] = None,
    original_filename: Optional[str] = None,
) -> dict[str, Any]:
    fp: dict[str, Any] = {
        "source_mode": source_mode,
        "source": file_fingerprint(
            source_path, label="source", original_filename=original_filename
        ),
    }
    if analysis_wav:
        fp["analysis_wav"] = file_fingerprint(analysis_wav, label="analysis_wav")
    if vocals_path:
        fp["vocals"] = file_fingerprint(vocals_path, label="vocals")
    if y is not None and sr:
        fp["waveform"] = waveform_checksum(y, sr=int(sr))
    return fp


def write_source_sidecar(path: Union[str, Path], source_sha256: str) -> Path:
    """Write .source_sha256 next to a cached converted/separated artifact."""
    path = Path(path)
    side = path.with_suffix(path.suffix + ".source_sha256")
    side.write_text(source_sha256 + "\n", encoding="utf-8")
    return side


def cached_artifact_matches_source(
    artifact: Union[str, Path],
    source_sha256: str,
) -> bool:
    artifact = Path(artifact)
    if not artifact.exists():
        return False
    side = artifact.with_suffix(artifact.suffix + ".source_sha256")
    if not side.exists():
        return False
    try:
        return side.read_text(encoding="utf-8").strip() == source_sha256
    except Exception:
        return False


def fingerprints_equal(a: dict[str, Any], b: dict[str, Any], key: str = "sha256") -> bool:
    return (a or {}).get(key) is not None and (a or {}).get(key) == (b or {}).get(key)


def dump_json(path: Union[str, Path], obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
