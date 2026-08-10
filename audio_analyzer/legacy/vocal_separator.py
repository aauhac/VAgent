"""
vocal_separator.py
------------------
Demucs Python API를 이용해 오디오에서 보컬을 분리한다.

subprocess CLI 대신 Python API를 직접 사용하고,
저장은 soundfile 로 수행한다 (torchaudio/torchcodec 의존 우회).

반환 구조
    {
        "vocals_path"    : str,   # 보컬 전용 WAV 경로
        "no_vocals_path" : str,   # 반주 (MR) WAV 경로
        "skipped"        : bool,  # True 이면 캐시 사용
    }
"""

from pathlib import Path
from typing import Optional
import numpy as np
import soundfile as sf

from audio_analyzer.audit.fingerprints import (
    cached_artifact_matches_source,
    sha256_file,
    write_source_sidecar,
)
from audio_analyzer.env_utils import resolve_ffmpeg_executable


DEFAULT_MODEL = "htdemucs"


def separate_vocals(
    audio_path: str,
    output_dir: str,
    model: str = DEFAULT_MODEL,
    skip_if_exists: bool = True,
) -> dict:
    """
    Demucs Python API 로 보컬 분리를 수행하고 결과 경로를 반환한다.

    Parameters
    ----------
    audio_path     : 원본 오디오 파일 경로
    output_dir     : 분리 결과 저장 폴더
    model          : Demucs 모델명 (기본값: htdemucs)
    skip_if_exists : True 이면 vocals.wav 가 있을 때 재실행 생략
                     (단 source SHA256 sidecar가 일치할 때만)

    Returns
    -------
    {
        "vocals_path"    : str,
        "no_vocals_path" : str | None,
        "skipped"        : bool,
    }
    """
    audio_path = Path(audio_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    vocals_path = out_dir / "vocals.wav"
    no_vocals_path = out_dir / "no_vocals.wav"
    source_sha = sha256_file(audio_path)

    # 캐시 확인 — source hash mismatch면 재생성
    if (
        skip_if_exists
        and vocals_path.exists()
        and cached_artifact_matches_source(vocals_path, source_sha)
    ):
        print(f"[separator] 캐시 사용: {vocals_path}")
        return {
            "vocals_path": str(vocals_path),
            "no_vocals_path": str(no_vocals_path) if no_vocals_path.exists() else None,
            "skipped": True,
            "source_sha256": source_sha,
        }

    print(f"[separator] 보컬 분리 시작 (모델: {model}) ...")
    print(f"[separator] 입력: {audio_path}")

    import torch
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    import librosa

    # ── 모델 로드 ──────────────────────────────────────────────────────────
    demucs_model = get_model(model)
    demucs_model.eval()

    # ── 오디오 로드 (torchaudio 완전 우회 → librosa 사용) ──────────────────
    # m4a 등 soundfile 미지원 포맷은 먼저 wav로 변환
    target_sr = demucs_model.samplerate
    audio_path_str = str(audio_path)
    if Path(audio_path).suffix.lower() not in {".wav", ".flac", ".ogg", ".aiff"}:
        import subprocess
        converted_input = out_dir / "input_converted.wav"
        if not (
            converted_input.exists()
            and cached_artifact_matches_source(converted_input, source_sha)
        ):
            ffmpeg_exe = resolve_ffmpeg_executable()
            conv_result = subprocess.run(
                [ffmpeg_exe, "-y", "-i", audio_path_str,
                 "-ar", str(target_sr), "-ac", "2", str(converted_input)],
                capture_output=True, encoding="utf-8", errors="replace",
            )
            if conv_result.returncode != 0:
                raise RuntimeError(
                    f"[separator] ffmpeg 변환 실패:\n{conv_result.stderr}"
                )
            write_source_sidecar(converted_input, source_sha)
        audio_path_str = str(converted_input)

    y_mono, _ = librosa.load(audio_path_str, sr=target_sr, mono=False)
    # librosa mono=False 반환: (channels, samples) 또는 (samples,) for mono file
    if y_mono.ndim == 1:
        y_stereo = np.stack([y_mono, y_mono])          # (2, samples)
    elif y_mono.shape[0] == 1:
        y_stereo = np.repeat(y_mono, 2, axis=0)        # (2, samples)
    elif y_mono.shape[0] > 2:
        y_stereo = y_mono[:2]
    else:
        y_stereo = y_mono

    wav = torch.from_numpy(y_stereo.astype(np.float32))  # (2, samples)

    # ── 분리 실행 ──────────────────────────────────────────────────────────
    with torch.no_grad():
        # apply_model 은 (batch, channels, samples) 형태 입력
        sources = apply_model(
            demucs_model,
            wav.unsqueeze(0),   # (1, 2, samples)
            progress=True,
        )
    # sources: (1, n_stems, 2, samples)
    sources = sources.squeeze(0)   # (n_stems, 2, samples)

    stem_names = demucs_model.sources   # ['drums', 'bass', 'other', 'vocals']
    vocal_idx = stem_names.index("vocals")

    vocals_tensor = sources[vocal_idx]   # (2, samples)
    # no_vocals: 나머지 stems 합산
    no_vocals_tensor = sources[[i for i in range(len(stem_names)) if i != vocal_idx]].sum(0)

    # ── soundfile 로 저장 (torchaudio 우회) ────────────────────────────────
    target_sr = demucs_model.samplerate
    _save_wav(vocals_tensor, target_sr, vocals_path)
    _save_wav(no_vocals_tensor, target_sr, no_vocals_path)

    write_source_sidecar(vocals_path, source_sha)
    write_source_sidecar(no_vocals_path, source_sha)
    print(f"[separator] 완료 → {vocals_path}")
    return {
        "vocals_path": str(vocals_path),
        "no_vocals_path": str(no_vocals_path),
        "skipped": False,
        "source_sha256": source_sha,
    }


# ---------------------------------------------------------------------------
# 내부 함수
# ---------------------------------------------------------------------------

def _save_wav(tensor, sr: int, path: Path) -> None:
    """
    torch tensor (channels, samples) 를 soundfile 로 WAV 저장한다.
    stereo → mono 변환 후 저장.
    """
    # (channels, samples) → numpy (samples, channels) → mono
    arr = tensor.cpu().numpy()          # (2, samples)
    mono = arr.mean(axis=0)             # (samples,)
    mono = np.clip(mono, -1.0, 1.0).astype(np.float32)
    sf.write(str(path), mono, sr, subtype="FLOAT")
