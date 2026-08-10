"""
pipeline.py
-----------
VAgent v2 analysis pipeline.

Original Audio
  ├── Analysis Signal  → acoustic / phonation / score
  └── Preview Signal   → listening-only enhancement

Quality gate runs before scoring.
Global pitch variance is never used for skill / issues.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from .features import (
    extract_frequency_features,
    extract_pitch_features,
    extract_timbre_features,
    extract_waveform_features,
)
from .features.phonation import extract_phonation_features
from .legacy.acoustic_metrics import compute_core_acoustic_metrics
from .models import ANALYSIS_VERSION, empty_score_unavailable, public_result
from .preprocessing import (
    build_preview_signal,
    load_analysis_audio,
    maybe_separate_vocals,
    save_wav,
)
from .quality import evaluate_quality
from .scoring import compute_score_v3


ProgressCallback = Optional[Callable[[str, int], None]]


def analyze_audio(
    audio_path: str,
    output_dir: str = "runtime",
    recording_id: Optional[str] = None,
    sample_rate: int = 44100,
    user_id: Optional[str] = None,
    song_title: Optional[str] = None,
    artist: Optional[str] = None,
    section: Optional[str] = None,
    separate: bool = False,
    analysis_mode: str = "QUICK",
    demucs_model: str = "htdemucs",
    generate_visuals: bool = False,
    show: bool = False,
    build_preview: bool = True,
    include_feedback: bool = False,
    feedback_kwargs: Optional[dict[str, Any]] = None,
    progress_callback: ProgressCallback = None,
) -> dict[str, Any]:
    """
    Main v2 entry point. Returns full internal analysis result.

    analysis_mode:
      QUICK — free path; raw allowed; separate follows caller flag
      FUNCTIONAL — Song Detail / Functional Coach; forces separation
      DIAGNOSTIC — caller controls separation
    """

    def _progress(stage: str, pct: int) -> None:
        if progress_callback:
            progress_callback(stage, pct)

    mode = (analysis_mode or "QUICK").upper()
    if mode == "FUNCTIONAL":
        separate = True

    if recording_id is None:
        recording_id = _build_default_recording_id(audio_path)

    rec_dir = Path(output_dir) / recording_id
    rec_dir.mkdir(parents=True, exist_ok=True)

    _progress("load", 5)

    sep = maybe_separate_vocals(
        audio_path,
        rec_dir,
        separate=separate,
        demucs_model=demucs_model,
    )
    source_path = sep["vocals_path"]
    source_mode = sep["source_mode"]
    separation_failed = bool(sep.get("failed"))
    separation_status = sep.get("separation_status") or (
        "success" if source_mode == "separated" else ("failed" if separation_failed else "skipped")
    )

    _progress("preprocess", 15)
    y_full, sr, wav_used = load_analysis_audio(source_path, rec_dir, sample_rate=sample_rate)
    analysis_wav = save_wav(rec_dir / "analysis.wav", y_full, sr)
    duration_full = float(len(y_full) / max(sr, 1))

    # Load full no_vocals BEFORE clipping so we can align windows
    y_no_vocals_full = _load_no_vocals(sep, sr) if source_mode == "separated" else None

    preview_path = None
    preview_report: dict[str, Any] = {"skipped": True}
    if build_preview:
        # Preview uses full analysis signal so original_* timestamps seek correctly
        y_preview, preview_report = build_preview_signal(y_full, sr)
        preview_path = str(save_wav(rec_dir / "preview.wav", y_preview, sr))
        preview_report["skipped"] = False
        preview_report["time_base"] = "original_file"

    _progress("features", 35)
    pitch_full = extract_pitch_features(y_full, sr)
    from .scoring.duration_policy_v3 import select_score_clip, slice_audio
    from .vocal_function.alignment import build_time_context, slice_aligned_stems

    duration_policy = select_score_clip(duration_full, pitch_full)
    time_context = build_time_context(
        duration_policy=duration_policy,
        original_duration_sec=duration_full,
    )
    clip_start = float(duration_policy.get("start_sec") or 0.0)
    clip_end = float(duration_policy.get("end_sec") or duration_full)

    if duration_policy.get("truncated"):
        aligned = slice_aligned_stems(
            y_vocals_full=y_full,
            y_no_vocals_full=y_no_vocals_full,
            sr=sr,
            start_sec=clip_start,
            end_sec=clip_end,
        )
        y = aligned["vocals_clip"]
        y_no_vocals = aligned["no_vocals_clip"]
        pitch_features = extract_pitch_features(y, sr)
    else:
        y = y_full
        y_no_vocals = y_no_vocals_full
        pitch_features = pitch_full

    waveform_features = extract_waveform_features(y, sr)
    frequency_features = extract_frequency_features(y, sr)
    timbre_features = extract_timbre_features(frequency_features)
    acoustic = compute_core_acoustic_metrics(y, sr)

    _progress("phonation", 55)
    phonation = extract_phonation_features(y, sr, pitch_features)

    voiced_ratio = float(pitch_features.get("voiced_ratio") or 0.0)
    duration_sec = float(len(y) / max(sr, 1))
    voiced_duration_sec = voiced_ratio * duration_sec

    _progress("quality", 65)
    quality = evaluate_quality(
        y,
        sr,
        voiced_ratio=voiced_ratio,
        voiced_duration_sec=voiced_duration_sec,
        rumble_ratio_db=acoustic.get("rumble_ratio_db"),
    )

    artifact_flags = _artifact_flags(frequency_features, source_mode)

    from .audit.fingerprints import analysis_signal_fingerprint

    fingerprints = analysis_signal_fingerprint(
        source_path=audio_path,
        analysis_wav=analysis_wav,
        y=y,
        sr=sr,
        source_mode=source_mode,
        vocals_path=sep.get("vocals_path") if source_mode == "separated" else None,
        original_filename=Path(audio_path).name,
    )
    fingerprints["duration_policy"] = duration_policy
    fingerprints["full_duration_sec"] = round(duration_full, 3)
    fingerprints["score_duration_sec"] = round(duration_sec, 3)
    fingerprints["time_context"] = time_context

    _progress("scoring", 75)
    if quality["status"] == "fail":
        score = empty_score_unavailable("quality_gate_failed")
        issues: list[dict[str, Any]] = []
        timeline: list[dict[str, Any]] = []
        strengths: list[dict[str, Any]] = []
        analysis_notes = [
            "녹음 품질이 분석 기준을 통과하지 못해 실력 점수를 제공하지 않아요.",
            quality.get("user_message") or "",
        ]
    else:
        score = compute_score_v3(
            phonation=phonation,
            acoustic=acoustic,
            waveform=waveform_features,
            quality=quality,
            source_mode=source_mode,
            artifact_flags=artifact_flags,
            y=y,
            sr=sr,
            pitch=pitch_features,
        )
        timeline = list(phonation.get("instability_events") or [])
        issues = _build_issues(score, timeline, phonation)
        strengths = list(score.get("strengths") or [])
        analysis_notes = _build_analysis_notes(quality, score, source_mode, artifact_flags)
        if duration_policy.get("truncated") and duration_policy.get("note"):
            analysis_notes.insert(0, str(duration_policy["note"]))

    from .vocal_quality import compute_vocal_quality_profile
    from .vocal_function import compute_vocal_function_profile

    functional_quality, sep_note = _functional_quality_policy(
        analysis_mode=mode,
        source_mode=source_mode,
        separation_status=separation_status,
        has_no_vocals=y_no_vocals is not None,
    )
    if sep_note:
        analysis_notes.append(sep_note)

    if quality["status"] == "fail":
        vocal_quality_profile: dict[str, Any] = {
            "available": False,
            "reason": "quality_gate_failed",
        }
        vocal_function_profile: dict[str, Any] = {
            "available": False,
            "reason": "quality_gate_failed",
            "functional_quality": "UNAVAILABLE",
        }
    else:
        vocal_quality_profile = compute_vocal_quality_profile(
            y=y,
            sr=sr,
            pitch=pitch_features,
            acoustic=acoustic,
            quality=quality,
            source_mode=source_mode,
            artifact_flags=artifact_flags,
        )
        vocal_function_profile = compute_vocal_function_profile(
            y=y,
            sr=sr,
            pitch=pitch_features,
            acoustic=acoustic,
            quality=quality,
            optional_analysis={
                "vibrato": phonation.get("vibrato") or {"available": False},
            },
            source_mode=source_mode,
            artifact_flags=artifact_flags,
            y_no_vocals=y_no_vocals,
            time_origin_sec=float(time_context["analysis_time_origin_sec"]),
            functional_quality=functional_quality,
            separation_note=sep_note,
        )

    optional_analysis = {
        "vibrato": phonation.get("vibrato") or {"available": False},
    }

    if generate_visuals or show:
        _progress("visuals", 88)
        try:
            from .legacy.visualizer import generate_visualizations, show_visualizations

            generate_visualizations(y, sr, pitch_features, rec_dir)
            if show:
                show_visualizations(y, sr, pitch_features)
        except Exception as exc:  # noqa: BLE001
            analysis_notes.append(f"시각화 생성 실패: {exc}")

    result: dict[str, Any] = {
        "analysis_version": ANALYSIS_VERSION,
        "recording_id": recording_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analysis_status": "completed",
        "feedback_status": "skipped",
        "analysis_mode": mode,
        "analysis_time_origin_sec": time_context["analysis_time_origin_sec"],
        "analysis_clip_start_sec": time_context["analysis_clip_start_sec"],
        "analysis_clip_end_sec": time_context["analysis_clip_end_sec"],
        "original_duration_sec": time_context["original_duration_sec"],
        "time_context": time_context,
        "audio": {
            "duration_sec": round(duration_full, 3),
            "score_duration_sec": round(duration_sec, 3),
            "sample_rate": sr,
            "source_mode": source_mode,
            "original_path": str(audio_path),
            "original_filename": Path(audio_path).name,
            "analysis_wav_path": str(analysis_wav),
            "preview_path": preview_path,
            "separation": sep,
            "separation_status": separation_status,
            "duration_policy": duration_policy,
            "time_context": time_context,
            "content_sha256": (fingerprints.get("source") or {}).get("sha256"),
            "analysis_waveform_sha256": (fingerprints.get("waveform") or {}).get(
                "full_sha256"
            ),
        },
        "fingerprints": fingerprints,
        "user_info": {
            "user_id": user_id,
            "song_title": song_title,
            "artist": artist,
            "section": section,
        },
        "quality": quality,
        "vocal_quality_profile": vocal_quality_profile,
        "vocal_function_profile": vocal_function_profile,
        "features": {
            "waveform": _public_waveform(waveform_features),
            "spectral": {
                "band_energy_db": frequency_features.get("band_energy_db"),
                "spectral_centroid_mean_hz": frequency_features.get(
                    "spectral_centroid_mean_hz"
                ),
                "acoustic_metrics": acoustic,
            },
            "phonation": {
                "sustained_regions": phonation.get("sustained_regions", []),
                "median_residual_std_cents": phonation.get("median_residual_std_cents"),
                "median_rms_variation_db": phonation.get("median_rms_variation_db"),
                "sustained_count": phonation.get("sustained_count", 0),
                "legacy_pitch_stability_cents": pitch_features.get(
                    "pitch_stability_cents"
                ),
                "f0_mean_hz": pitch_features.get("f0_mean_hz"),
                "voiced_ratio": pitch_features.get("voiced_ratio"),
            },
            "timbre": timbre_features,
        },
        "score": score,
        "optional_analysis": optional_analysis,
        "issues": issues,
        "timeline": timeline,
        "strengths": strengths,
        "analysis_notes": [n for n in analysis_notes if n],
        "preview_path": preview_path,
        "preview_report": preview_report,
        "artifact_flags": artifact_flags,
    }

    if include_feedback:
        _progress("feedback", 92)
        try:
            from .feedback.llm import generate_feedback

            fb_kwargs = feedback_kwargs or {}
            feedback = generate_feedback(result, **fb_kwargs)
            result["feedback"] = feedback
            result["feedback_status"] = "completed"
        except Exception as exc:  # noqa: BLE001
            result["feedback"] = None
            result["feedback_status"] = "failed"
            result["analysis_notes"].append(
                f"피드백 생성에 실패했지만 분석 점수는 정상입니다. ({exc})"
            )

    _progress("save", 97)
    analysis_path = rec_dir / "analysis.json"
    _save_json(_json_safe(result), analysis_path)

    public = public_result(result)
    _save_json(public, rec_dir / "public_result.json")

    try:
        from .feedback.formatter import format_for_llm

        llm_input = format_for_llm(result)
        _save_json(llm_input, rec_dir / "llm_input.json")
    except Exception:
        pass

    _progress("done", 100)
    return result


def _functional_quality_policy(
    *,
    analysis_mode: str,
    source_mode: str,
    separation_status: str,
    has_no_vocals: bool,
) -> tuple[str, Optional[str]]:
    """
    FULL: separated + no_vocals contrast available
    LIMITED: separated but no_vocals missing, or QUICK raw
    UNAVAILABLE: FUNCTIONAL mode but separation failed
    """
    note_fail = (
        "반주와 보컬을 충분히 분리하지 못해 "
        "일부 기능적 발성 분석은 제공하지 않았어요."
    )
    if analysis_mode == "FUNCTIONAL":
        if source_mode != "separated" or separation_status == "failed":
            return "UNAVAILABLE", note_fail
        if not has_no_vocals:
            return "LIMITED", note_fail
        return "FULL", None
    # QUICK / DIAGNOSTIC
    if source_mode == "separated" and has_no_vocals:
        return "FULL", None
    if source_mode == "separated":
        return "LIMITED", note_fail
    return "LIMITED", None


def analyze_mp3(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """
    Compatibility wrapper for v1 callers.

    Maps old flags:
      reduce_echo → ignored for analysis (preview still available)
      generate_visuals default False (v1 always generated; use generate_visuals=True)
    """
    # v1 always wrote visuals; keep opt-in False for service, but allow CLI --show
    kwargs.setdefault("generate_visuals", False)
    kwargs.pop("reduce_echo", None)
    kwargs.pop("segment_sec", None)
    return analyze_audio(*args, **kwargs)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _artifact_flags(frequency_features: dict, source_mode: str) -> dict[str, Any]:
    """
    Demucs high-band loss heuristic.

    RAW recordings must NOT treat a naturally dark spectrum as Demucs artifact.
    Only apply when source_mode == "separated".
    """
    if source_mode != "separated":
        return {
            "demucs_high_band_loss_likely": False,
            "high_band_loss_likely": False,  # compat alias
            "relative_low_mid_inflation_likely": False,
            "source_mode": source_mode,
        }

    band = frequency_features.get("band_energy_db") or {}
    low_mid = band.get("80_250")
    presence = band.get("2500_4000")
    air = band.get("6000_10000")
    demucs_hf = False
    if low_mid is not None and air is not None and (low_mid - air) > 14.0:
        demucs_hf = True
    if presence is not None and air is not None and (presence - air) > 10.0:
        demucs_hf = True
    return {
        "demucs_high_band_loss_likely": demucs_hf,
        "high_band_loss_likely": demucs_hf,  # compat alias
        "relative_low_mid_inflation_likely": demucs_hf,
        "source_mode": source_mode,
    }


def _load_no_vocals(sep: dict[str, Any], target_sr: int) -> Optional[np.ndarray]:
    """Load accompaniment stem for vocal-vs-no_vocals contrast (optional)."""
    path = (sep or {}).get("no_vocals_path")
    if not path:
        return None
    try:
        import soundfile as sf
        import librosa

        y_nv, sr_nv = sf.read(path, always_2d=False)
        if getattr(y_nv, "ndim", 1) > 1:
            y_nv = np.mean(y_nv, axis=1)
        if int(sr_nv) != int(target_sr):
            y_nv = librosa.resample(
                np.asarray(y_nv, dtype=float),
                orig_sr=int(sr_nv),
                target_sr=int(target_sr),
            )
        return np.asarray(y_nv, dtype=np.float32)
    except Exception:
        return None


def _build_issues(
    score: dict[str, Any],
    timeline: list[dict[str, Any]],
    phonation: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if timeline:
        issues.append(
            {
                "type": "phonation_instability",
                "severity": max(
                    (e.get("severity") or "medium") for e in timeline
                ),
                "confidence": float(np.mean([e.get("confidence", 0.5) for e in timeline])),
                "user_message": (
                    "길게 유지한 일부 음에서 소리가 일정하게 유지되지 않는 구간이 측정됐어요."
                ),
                "regions": len(timeline),
            }
        )

    for item in score.get("priority_issues") or []:
        issues.append(
            {
                "type": f"area_{item['area_id']}",
                "area_id": item["area_id"],
                "severity": "medium",
                "confidence": 0.7,
                "user_message": f"{item['display_name']}에서 개선 여지가 측정됐어요.",
                "score": item.get("score"),
            }
        )
    return issues


def _build_analysis_notes(
    quality: dict[str, Any],
    score: dict[str, Any],
    source_mode: str,
    artifact_flags: dict[str, Any],
) -> list[str]:
    notes: list[str] = []
    if quality.get("status") == "warn":
        notes.append(quality.get("user_message") or "녹음 조건이 완벽하지 않아 참고용으로 봐 주세요.")
    codes = quality.get("codes") or []
    if "RUMBLE" in codes:
        notes.append("저역 잡음은 녹음 환경 영향일 수 있어 실력 점수에는 직접 반영하지 않았어요.")
    if source_mode == "separated":
        notes.append("보컬 분리를 사용했어요. 스펙트럼 측정 신뢰도가 낮아질 수 있어요.")
    if artifact_flags.get("demucs_high_band_loss_likely") and source_mode == "separated":
        notes.append("Demucs 고역 손실 가능성이 있어 일부 전달력/공명 측정은 unknown으로 처리될 수 있어요.")
    for area in score.get("areas") or []:
        if area.get("status") == "unknown":
            notes.append(
                f"{area.get('display_name')}은(는) 이번 녹음에서 신뢰하기 어려워 참고하지 않았어요."
            )
    notes.append("점수는 아직 보정되지 않은(uncalibrated) 잠정 기준입니다.")
    notes.append("이 서비스는 의료 진단이 아니며, 발성 특성 분석과 연습 참고용입니다.")
    return notes


def _public_waveform(waveform: dict[str, Any]) -> dict[str, Any]:
    return {
        "rms_mean": waveform.get("rms_mean"),
        "rms_max": waveform.get("rms_max"),
        "peak_amplitude": waveform.get("peak_amplitude"),
        "dynamic_range_db": waveform.get("dynamic_range_db"),
        "silent_ratio": waveform.get("silent_ratio"),
        # compact envelope for frontend waveform (1s buckets)
        "envelope": [
            {"t": e.get("start", i), "rms": e.get("rms_mean")}
            for i, e in enumerate(waveform.get("per_second_summary") or [])
        ],
    }


def _save_json(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        return None if f != f else f
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, float) and obj != obj:
        return None
    return obj


def _build_default_recording_id(audio_path: str) -> str:
    stem = Path(audio_path).stem.strip() or "audio"
    safe_stem = re.sub(r'[\\/:*?"<>|\s]+', "_", stem)
    safe_stem = re.sub(r"_+", "_", safe_stem).strip("_") or "audio"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{safe_stem}_{ts}_{uuid.uuid4().hex[:6]}"
