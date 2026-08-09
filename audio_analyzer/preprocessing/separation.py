"""
preprocessing/separation.py
---------------------------
Optional Demucs vocal separation. Default: off.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from audio_analyzer.legacy.vocal_separator import separate_vocals as _separate_vocals


def maybe_separate_vocals(
    audio_path: str,
    output_dir: Path,
    *,
    separate: bool = False,
    demucs_model: str = "htdemucs",
) -> dict[str, Any]:
    if not separate:
        return {
            "used": False,
            "source_mode": "raw",
            "vocals_path": audio_path,
        }

    result = _separate_vocals(
        audio_path=audio_path,
        output_dir=str(output_dir / "demucs"),
        model=demucs_model,
    )
    return {
        "used": True,
        "source_mode": "separated",
        "model": demucs_model,
        "vocals_path": result["vocals_path"],
        "no_vocals_path": result.get("no_vocals_path"),
        "skipped": result.get("skipped", False),
    }
