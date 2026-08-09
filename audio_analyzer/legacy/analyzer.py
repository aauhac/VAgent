"""
analyzer.py
-----------
보컬 음색 분석 메인 함수.

analyze_mp3(audio_path, output_dir, ...) → dict

출력 파일 (output_dir/recording_id/ 아래)
    processed.wav    : mono 44.1kHz WAV
    waveform.png
    spectrogram.png
    pitch_curve.png
    analysis.json    : 전체 분석 결과
    llm_input.json   : LLM 피드백용 요약 JSON
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import librosa
import soundfile as sf
from scipy import signal

from .features import (
    extract_waveform_features,
    extract_frequency_features,
    extract_pitch_features,
    extract_timbre_features,
)
from .visualizer import generate_visualizations, show_visualizations
from .issue_detector import detect_issues, detect_issue_events
from .llm_formatter import format_for_llm
from .vocal_separator import separate_vocals
from .vocal_enhancer import preprocess_for_separation, enhance_vocal_stem
from .env_utils import resolve_ffmpeg_executable
from .vocal_score import compute_vocal_score


def analyze_mp3(
    audio_path: str,
    output_dir: str,
    recording_id: Optional[str] = None,
    sample_rate: int = 44100,
    segment_sec: float = 5.0,
    user_id: Optional[str] = None,
    song_title: Optional[str] = None,
    artist: Optional[str] = None,
    section: Optional[str] = None,
    show: bool = False,
    separate: bool = False,
    demucs_model: str = "htdemucs",
    reduce_echo: bool = True,
) -> dict:
    """
    MP3(또는 WAV 등 librosa 지원 포맷) 파일을 분석하여
    보컬 음색 분석 결과를 반환하고 파일로 저장한다.

    Parameters
    ----------
    audio_path    : 분석할 오디오 파일 경로
    output_dir    : 결과 저장 루트 폴더
    recording_id  : 녹음 ID (None 이면 자동 생성)
    sample_rate   : 분석용 샘플레이트 (기본 44100)
    segment_sec   : 구간 분할 단위 초 (기본 5.0)
    user_id       : 사용자 ID (선택)
    song_title    : 곡 제목 (선택)
    artist        : 아티스트명 (선택)
    section       : 구간 이름 (verse / chorus 등, 선택)

    Returns
    -------
    analysis 결과 dict (analysis.json 내용과 동일)
    """

    # ── 1. 준비 ──────────────────────────────────────────────────────────────
    if recording_id is None:
        recording_id = _build_default_recording_id(audio_path)

    rec_dir = Path(output_dir) / recording_id
    rec_dir.mkdir(parents=True, exist_ok=True)

    # ── 1-b. Demucs 보컨 분리 (선택) ────────────────────────────────────────────
    separation_info: dict = {}
    source_path = audio_path  # 분석 대상 파일 (demucs 사용 시 교체됨)

    if separate:
        # Demucs 전: 가벼운 전처리 → 임시 WAV 저장 → Demucs 에 전달
        print("[analyzer] Demucs 전 전처리 중...")
        _pre_wav = rec_dir / "input_preprocessed.wav"
        if not _pre_wav.exists():
            # m4a 등 soundfile 미지원 포맷은 ffmpeg 경유 변환 후 로드
            _src_wav = _ensure_wav(audio_path, rec_dir, sample_rate)
            _y_pre, _sr_pre = librosa.load(str(_src_wav), sr=sample_rate, mono=True)
            _y_pre = preprocess_for_separation(_y_pre, _sr_pre)
            sf.write(str(_pre_wav), _y_pre, _sr_pre)
        sep_result = separate_vocals(
            audio_path=str(_pre_wav),
            output_dir=str(rec_dir / "demucs"),
            model=demucs_model,
        )
        source_path = sep_result["vocals_path"]
        separation_info = {
            "used": True,
            "model": demucs_model,
            "vocals_path": sep_result["vocals_path"],
            "no_vocals_path": sep_result["no_vocals_path"],
            "skipped": sep_result["skipped"],
        }
        print(f"[analyzer] 보컬 분리 완료 → {source_path}")
    else:
        separation_info = {"used": False}

    # ── 2. 오디오 로드 (m4a 등 soundfile 미지원 포맷은 ffmpeg 경유 변환) ────────
    print(f"[analyzer] 로드 중: {source_path}")
    source_path = _ensure_wav(source_path, rec_dir, sample_rate)
    y, sr = librosa.load(source_path, sr=sample_rate, mono=True)

    # ── 2-b. 보컄 stem 전용 음질 정리 (Demucs 이후 적용) ───────────────
    quality_report: dict = {"skipped": True, "reason": "reduce_echo=False"}
    if reduce_echo:
        print("[analyzer] 보컬 stem 음질 정리 중 (dereverb + dynamic EQ + tail gate)...")
        y, quality_report = enhance_vocal_stem(y, sr)
        preprocess_info = {
            "echo_reduction": True,
            "method": quality_report.get("denoise_method"),
            "confidence": quality_report.get("analysis_confidence"),
            "low_cut_hz": 70,
        }
    else:
        preprocess_info = {"echo_reduction": False, "low_cut_hz": None}

    duration_sec = float(librosa.get_duration(y=y, sr=sr))

    # ── 3. WAV 저장 ───────────────────────────────────────────────────────────
    wav_path = rec_dir / "processed.wav"
    sf.write(str(wav_path), y, sr)

    # ── 4. 피처 추출 ─────────────────────────────────────────────────────────
    print("[analyzer] 파형 피처 추출 중...")
    waveform_features = extract_waveform_features(y, sr)

    print("[analyzer] 주파수 피처 추출 중...")
    frequency_features = extract_frequency_features(y, sr)

    print("[analyzer] Pitch 피처 추출 중 (pYIN)...")
    pitch_features = extract_pitch_features(y, sr)

    print("[analyzer] 음색 점수 계산 중...")
    timbre_features = extract_timbre_features(frequency_features)

    # ── 5. 구간별(segment) 피처 추출 ─────────────────────────────────────────
    print("[analyzer] 구간별 피처 추출 중...")
    segment_features = _extract_segment_features(y, sr, segment_sec, pitch_features)

    # ── 6. 이슈 감지 ─────────────────────────────────────────────────────────
    detected_issues = detect_issues(frequency_features, pitch_features, timbre_features)
    issue_events = detect_issue_events(pitch_features, segment_features, waveform_features)

    # ── 6-b. 영역별 보컬 점수 계산 ───────────────────────────────────────────
    vocal_score = compute_vocal_score(
        y=y,
        sr=sr,
        frequency_features=frequency_features,
        pitch_features=pitch_features,
        waveform_features=waveform_features,
        quality_report=quality_report,
    )

    # ── 7. 결과 조합 ──────────────────────────────────────────────────────────
    result = {
        "recording_id": recording_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "audio_meta": {
            "original_path": str(audio_path),
            "source_filename": Path(audio_path).name,
            "analyzed_path": str(source_path),
            "processed_wav_path": str(wav_path),
            "sample_rate": sr,
            "duration_sec": round(duration_sec, 3),
            "channels": 1,
            "separation": separation_info,
            "preprocess": preprocess_info,
        },
        "user_info": {
            "user_id": user_id,
            "song_title": song_title,
            "artist": artist,
            "section": section,
        },
        "waveform_features": waveform_features,
        "frequency_features": frequency_features,
        "pitch_features": {
            k: v for k, v in pitch_features.items() if k != "frame_f0"
        },
        "timbre_features": timbre_features,
        "segment_features": segment_features,
        "detected_issues": detected_issues,
        "issue_events": issue_events,
        "quality_report": quality_report,
        "vocal_score": vocal_score,
    }

    # ── 8. 시각화 ─────────────────────────────────────────────────────────────
    print("[analyzer] 시각화 생성 중...")
    generate_visualizations(y, sr, pitch_features, rec_dir)
    if show:
        show_visualizations(y, sr, pitch_features)
    # ── 9. JSON 저장 ──────────────────────────────────────────────────────────
    analysis_path = rec_dir / "analysis.json"
    _save_json(result, analysis_path)

    llm_input = format_for_llm(result)
    llm_input_path = rec_dir / "llm_input.json"
    _save_json(llm_input, llm_input_path)

    print(f"[analyzer] 완료 → {rec_dir}")
    return result


# ---------------------------------------------------------------------------
# 내부 함수
# ---------------------------------------------------------------------------

def _extract_segment_features(
    y: np.ndarray,
    sr: int,
    segment_sec: float,
    pitch_features: dict,
) -> list[dict]:
    """
    음원을 segment_sec 초 단위로 나눠 각 구간의 핵심 피처를 계산한다.
    """
    n_samples_per_seg = int(segment_sec * sr)
    total_samples = len(y)
    segments = []

    # frame_f0 조회용 맵 (time_sec → f0_hz)
    frame_f0_map: dict[float, Optional[float]] = {}
    for entry in pitch_features.get("frame_f0", []):
        frame_f0_map[entry["time_sec"]] = entry["f0_hz"]

    start_sample = 0
    while start_sample < total_samples:
        end_sample = min(start_sample + n_samples_per_seg, total_samples)
        chunk = y[start_sample:end_sample]

        start_sec = start_sample / sr
        end_sec = end_sample / sr

        rms_mean = float(np.sqrt(np.mean(chunk ** 2)))

        # 구간 내 유성음 F0 평균
        voiced_f0_in_seg = [
            v
            for t, v in frame_f0_map.items()
            if start_sec <= t < end_sec and v is not None
        ]
        f0_mean = float(np.mean(voiced_f0_in_seg)) if voiced_f0_in_seg else None

        # 구간 spectral centroid
        hop_length = 512
        n_fft = 2048
        seg_centroid = librosa.feature.spectral_centroid(
            y=chunk, sr=sr, n_fft=n_fft, hop_length=hop_length
        )
        centroid_mean = float(np.mean(seg_centroid))

        # 구간 band energy
        D = librosa.stft(chunk, n_fft=n_fft, hop_length=hop_length)
        S_power = np.abs(D) ** 2
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

        def _seg_band_db(low: int, high: int) -> Optional[float]:
            mask = (freqs >= low) & (freqs < high)
            if not mask.any():
                return None
            p = float(S_power[mask, :].mean())
            return round(10.0 * np.log10(p + 1e-10), 2)

        segments.append(
            {
                "start_sec": round(start_sec, 3),
                "end_sec": round(end_sec, 3),
                "rms_mean": round(rms_mean, 6),
                "f0_mean_hz": round(f0_mean, 2) if f0_mean is not None else None,
                "spectral_centroid_mean_hz": round(centroid_mean, 2),
                "band_energy_db": {
                    "80_250":    _seg_band_db(80,   250),
                    "500_800":   _seg_band_db(500,  800),
                    "2500_4000": _seg_band_db(2500, 4000),
                    "6000_10000":_seg_band_db(6000, 10000),
                },
            }
        )

        start_sample = end_sample

    return segments


def _ensure_wav(source_path, rec_dir: Path, sample_rate: int) -> Path:
    """
    soundfile 이 지원하지 않는 포맷(m4a, aac 등)은
    ffmpeg 로 wav 로 변환한 뒤 경로를 반환한다.
    wav / flac / ogg 등 soundfile 이 지원하는 포맷은 그대로 반환한다.
    """
    import subprocess

    source_path = Path(source_path)
    SOUNDFILE_NATIVE = {".wav", ".flac", ".ogg", ".aiff", ".aif"}

    if source_path.suffix.lower() in SOUNDFILE_NATIVE:
        return source_path

    # ffmpeg 경유 변환
    converted = rec_dir / "input_converted.wav"
    if converted.exists():
        return converted

    print(f"[analyzer] ffmpeg 변환: {source_path.suffix} → wav")
    ffmpeg_exe = resolve_ffmpeg_executable()
    cmd = [
        ffmpeg_exe, "-y",
        "-i", str(source_path),
        "-ar", str(sample_rate),
        "-ac", "1",
        "-f", "wav",
        str(converted),
    ]
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(
            f"[analyzer] ffmpeg 변환 실패:\n{result.stderr}"
        )
    print(f"[analyzer] 변환 완료 → {converted}")
    return converted


def _save_json(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _build_default_recording_id(audio_path: str) -> str:
    """
    recording_id 미지정 시 `음원명_feedback_YYYYmmdd_HHMMSS` 형태를 만든다.
    파일시스템에 부적합한 문자는 '_'로 치환한다.
    """
    stem = Path(audio_path).stem.strip() or "audio"
    safe_stem = re.sub(r'[\\/:*?"<>|\s]+', "_", stem)
    safe_stem = re.sub(r'_+', "_", safe_stem).strip("_") or "audio"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{safe_stem}_feedback_{ts}"


def _reduce_echo_and_low_mid(y: np.ndarray, sr: int) -> np.ndarray:
    """
    간단한 에코/잔향 완화 + 저역 과다 완화 전처리.

    1) HPSS로 타격성 성분을 줄이고 보컬 중심 성분을 유지
    2) 주파수별 하위 퍼센타일을 노이즈 플로어로 잡아 스펙트럼 감산
    3) 95Hz 하이패스로 과도한 저역 에너지를 완화
    """
    y_harm, y_perc = librosa.effects.hpss(y)
    y_focus = 0.9 * y_harm + 0.1 * y_perc

    n_fft = 2048
    hop = 512
    stft = librosa.stft(y_focus, n_fft=n_fft, hop_length=hop)
    mag = np.abs(stft)
    phase = np.exp(1j * np.angle(stft))

    floor = np.percentile(mag, 20, axis=1, keepdims=True)
    mag_clean = np.maximum(mag - floor * 0.75, 0.0)
    y_clean = librosa.istft(mag_clean * phase, hop_length=hop, length=len(y_focus))

    cutoff = 95.0
    nyq = sr * 0.5
    if cutoff < nyq:
        b, a = signal.butter(2, cutoff / nyq, btype="highpass")
        y_clean = signal.filtfilt(b, a, y_clean)

    peak = float(np.max(np.abs(y_clean))) + 1e-9
    y_clean = (y_clean / peak) * 0.98
    return y_clean.astype(np.float32)
