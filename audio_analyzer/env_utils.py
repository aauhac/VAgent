"""
env_utils.py
------------
환경변수(.env) 로딩과 ffmpeg 실행파일 탐색 유틸.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional


def load_dotenv_if_available() -> None:
    """
    python-dotenv 이 설치되어 있으면 루트의 .env 를 로드한다.
    설치되지 않았으면 조용히 무시한다.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(override=False)


def resolve_ffmpeg_executable() -> str:
    """
    ffmpeg 실행파일 경로를 찾아 반환한다.

    우선순위:
    1) FFMPEG_PATH (파일 경로)
    2) PATH 상 ffmpeg
    3) 알려진 Windows 설치 경로
    """
    env_path = os.environ.get("FFMPEG_PATH")
    if env_path and Path(env_path).exists():
        return str(Path(env_path))

    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        return which_ffmpeg

    local_appdata = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")

    candidates = [
        Path(local_appdata) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe",
        Path(local_appdata)
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
        / "ffmpeg-8.1.1-full_build"
        / "bin"
        / "ffmpeg.exe",
        Path(program_files) / "ffmpeg" / "bin" / "ffmpeg.exe",
        Path(program_files) / "SteelSeries" / "GG" / "apps" / "moments" / "ffmpeg.exe",
    ]

    for p in candidates:
        if p.exists():
            return str(p)

    raise FileNotFoundError(
        "ffmpeg 실행파일을 찾지 못했습니다. FFMPEG_PATH 환경변수에 ffmpeg.exe 경로를 설정하세요."
    )
