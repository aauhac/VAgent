"""
preprocessing/separation.py
---------------------------
Optional Demucs vocal separation. Default: off.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from audio_analyzer.legacy.vocal_separator import separate_vocals as _separate_vocals

# Path used for existence checks after Demucs


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
            "separation_status": "skipped",
            "failed": False,
        }

    try:
        result = _separate_vocals(
            audio_path=audio_path,
            output_dir=str(output_dir / "demucs"),
            model=demucs_model,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "used": False,
            "source_mode": "raw",
            "vocals_path": audio_path,
            "separation_status": "failed",
            "failed": True,
            "error": str(exc),
            "model": demucs_model,
        }

    no_vocals = result.get("no_vocals_path")
    ok = bool(result.get("vocals_path")) and Path(result["vocals_path"]).exists()
    if not ok:
        return {
            "used": False,
            "source_mode": "raw",
            "vocals_path": audio_path,
            "separation_status": "failed",
            "failed": True,
            "model": demucs_model,
        }

    return {
        "used": True,
        "source_mode": "separated",
        "model": demucs_model,
        "vocals_path": result["vocals_path"],
        "no_vocals_path": no_vocals,
        "skipped": result.get("skipped", False),
        "separation_status": "success",
        "failed": False,
        "has_no_vocals": bool(no_vocals) and Path(str(no_vocals)).exists(),
    }
