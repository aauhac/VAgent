#!/usr/bin/env python3
"""
Audit vocal-type UNRESOLVED root cause on real samples.
Does NOT change production thresholds or scoring code.

Usage:
  python scripts/audit_vocal_type_samples.py
  python scripts/audit_vocal_type_samples.py path/to/file.m4a ...
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import librosa
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audio_analyzer import analyze_audio  # noqa: E402
from audio_analyzer.coach_profile import config as coach_cfg  # noqa: E402
from audio_analyzer.coach_profile.engine import (  # noqa: E402
    classify_vocal_type_resolution_state,
    compute_vocal_type_profile,
)
from audio_analyzer.coach_profile.head_chest import (  # noqa: E402
    ratio_eligible,
    score_all_segments,
    song_evidence_stats,
)
from audio_analyzer.env_utils import resolve_ffmpeg_executable  # noqa: E402
from audio_analyzer.features.pitch import (  # noqa: E402
    F0_VALID_MAX_HZ,
    F0_VALID_MIN_HZ,
    FMAX,
    FMIN,
    OCTAVE_JUMP_CENTS,
    RMS_VOICED_THRESHOLD_RATIO,
)
from audio_analyzer.models import free_public_result  # noqa: E402
from audio_analyzer.preprocessing import load_analysis_audio, maybe_separate_vocals, save_wav  # noqa: E402
from audio_analyzer.quality.gate import _clipping_ratio, _rms_dbfs, _silent_ratio, evaluate_quality  # noqa: E402

OUT_DIR = ROOT / "qa_output" / "vocal_type_3sample_audit"

DEFAULT_SAMPLES: dict[str, dict[str, str]] = {
    "kang1": {"label": "강1", "sex": "male", "glob": "강1.m4a"},
    "kang2": {"label": "강2", "sex": "male", "glob": "강2.m4a"},
    "park1": {"label": "박1", "sex": "female", "glob": "박1.m4a"},
}

PRODUCTION_CONFIG = {
    "analysis_mode": "FUNCTIONAL",
    "input_mode": "VOCAL_ONLY",
    "separate": False,
    "include_feedback": False,
    "sample_rate": 44100,
}


def _find_by_glob(name: str) -> list[Path]:
    return sorted(ROOT.rglob(name))


def resolve_samples(args: list[str]) -> dict[str, dict[str, Any]]:
    resolved: dict[str, dict[str, Any]] = {}
    if args:
        for i, p in enumerate(args):
            path = Path(p)
            if not path.is_file():
                path = ROOT / p
            if not path.is_file():
                raise FileNotFoundError(p)
            sid = f"sample{i+1}"
            resolved[sid] = {"path": path, "label": path.stem, "sex": "unknown"}
        return resolved

    for sid, meta in DEFAULT_SAMPLES.items():
        hits = _find_by_glob(meta["glob"])
        if not hits:
            raise FileNotFoundError(meta["glob"])
        resolved[sid] = {
            "path": hits[0],
            "label": meta["label"],
            "sex": meta["sex"],
            "all_matches": [str(h) for h in hits],
        }
    return resolved


def ffprobe_info(path: Path) -> dict[str, Any]:
    ffmpeg = resolve_ffmpeg_executable()
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    if not Path(ffprobe).exists():
        ffprobe = "ffprobe"
    try:
        out = subprocess.check_output(
            [
                ffprobe,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            encoding="utf-8",
            errors="replace",
        )
        data = json.loads(out)
        fmt = data.get("format") or {}
        streams = data.get("streams") or []
        audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
        return {
            "codec": audio.get("codec_name"),
            "sample_rate": int(audio.get("sample_rate") or 0) or None,
            "channels": audio.get("channels"),
            "bit_rate": fmt.get("bit_rate"),
            "format_name": fmt.get("format_name"),
        }
    except Exception as exc:
        return {"error": str(exc)}


def waveform_stats(y: np.ndarray, sr: int) -> dict[str, Any]:
    if len(y) == 0:
        return {
            "duration_sec": 0.0,
            "sample_rate": sr,
            "rms_dbfs": None,
            "peak": 0.0,
            "dc_offset": 0.0,
            "silent_ratio": 1.0,
        }
    y64 = y.astype(np.float64)
    peak = float(np.max(np.abs(y64)))
    dc = float(np.mean(y64))
    return {
        "duration_sec": round(len(y64) / max(sr, 1), 3),
        "sample_rate": sr,
        "rms_dbfs": round(_rms_dbfs(y64), 2),
        "peak": round(peak, 5),
        "dc_offset": round(dc, 6),
        "silent_ratio": round(_silent_ratio(y64, sr), 4),
    }


def audit_pitch_stages(y: np.ndarray, sr: int) -> dict[str, Any]:
    hop_length = 512
    f0, voiced_flag, _ = librosa.pyin(y, fmin=FMIN, fmax=FMAX, sr=sr, hop_length=hop_length)
    frame_rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    min_len = min(len(f0), len(frame_rms))
    f0 = f0[:min_len]
    voiced_flag = voiced_flag[:min_len]
    frame_rms = frame_rms[:min_len]
    total = len(f0)
    pyin_voiced = int(np.sum(voiced_flag))
    rms_threshold = float(np.max(frame_rms)) * RMS_VOICED_THRESHOLD_RATIO + 1e-9
    after_rms = int(
        np.sum(voiced_flag & (frame_rms >= rms_threshold) & (~np.isnan(f0)))
    )
    after_range = int(
        np.sum(
            voiced_flag
            & (frame_rms >= rms_threshold)
            & (~np.isnan(f0))
            & (f0 >= F0_VALID_MIN_HZ)
            & (f0 <= F0_VALID_MAX_HZ)
        )
    )
    valid_mask = (
        voiced_flag
        & (frame_rms >= rms_threshold)
        & (~np.isnan(f0))
        & (f0 >= F0_VALID_MIN_HZ)
        & (f0 <= F0_VALID_MAX_HZ)
    )
    valid_indices = np.where(valid_mask)[0]
    if len(valid_indices) > 1:
        prev_hz = None
        for idx in valid_indices:
            hz = f0[idx]
            if prev_hz is not None:
                cents_jump = abs(1200.0 * np.log2(hz / prev_hz + 1e-10))
                if cents_jump > OCTAVE_JUMP_CENTS:
                    valid_mask[idx] = False
                    prev_hz = None
                    continue
            prev_hz = hz
    after_octave = int(np.sum(valid_mask))
    voiced_f0 = f0[valid_mask]
    stats = {
        "fmin_hz": round(float(FMIN), 2),
        "fmax_hz": round(float(FMAX), 2),
        "f0_valid_min_hz": F0_VALID_MIN_HZ,
        "f0_valid_max_hz": F0_VALID_MAX_HZ,
        "total_frames": total,
        "pyin_voiced_frames": pyin_voiced,
        "after_rms_frames": after_rms,
        "after_range_frames": after_range,
        "after_octave_frames": after_octave,
        "pyin_voiced_ratio": round(float(np.mean(voiced_flag)), 4) if total else 0.0,
        "f0_mean_hz": round(float(np.mean(voiced_f0)), 2) if len(voiced_f0) else None,
        "f0_min_hz": round(float(np.min(voiced_f0)), 2) if len(voiced_f0) else None,
        "f0_max_hz": round(float(np.max(voiced_f0)), 2) if len(voiced_f0) else None,
        "f0_std_hz": round(float(np.std(voiced_f0)), 2) if len(voiced_f0) else None,
        "rms_threshold": round(rms_threshold, 6),
    }
    return stats


def stage_audit_for_signal(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        return {"label": label, "missing": True}
    try:
        y, sr = librosa.load(str(path), sr=None, mono=True)
    except Exception as exc:
        return {"label": label, "error": str(exc)}
    wf = waveform_stats(y, sr)
    pitch = audit_pitch_stages(y, sr)
    quality = evaluate_quality(
        y,
        sr,
        voiced_ratio=pitch["pyin_voiced_ratio"],
        voiced_duration_sec=pitch["pyin_voiced_ratio"] * wf["duration_sec"],
    )
    return {"label": label, "path": str(path), "waveform": wf, "pitch": pitch, "quality": quality}


def classify_root_cause(detail: dict[str, Any]) -> tuple[list[str], str]:
    tags: list[str] = []
    orig = detail.get("original") or {}
    orig_wf = orig.get("waveform") or {}
    orig_pitch = orig.get("pitch") or {}
    prod = detail.get("production") or {}
    quality = prod.get("quality") or {}
    qstatus = str(quality.get("status") or "").lower()
    metrics = quality.get("metrics") or {}
    vt = prod.get("vocal_type") or {}
    evidence = vt.get("evidence") or {}
    thresholds = detail.get("thresholds") or {}

    silent = float(metrics.get("silent_ratio") or orig_wf.get("silent_ratio") or 0)
    voiced = float(metrics.get("voiced_ratio") or orig_pitch.get("pyin_voiced_ratio") or 0)
    voiced_dur = float(metrics.get("voiced_duration_sec") or 0)

    if qstatus == "fail":
        if silent >= 0.9:
            tags.append("INPUT_AUDIO_SILENT")
        if voiced < 0.08:
            tags.append("QUALITY_GATE_FAILED")
            tags.append("PITCH_DETECTION_FAILURE")
        if not tags:
            tags.append("QUALITY_GATE_FAILED")
        return tags, tags[0]

    pipeline = detail.get("pipeline_stages") or {}
    orig_rms = (pipeline.get("ORIGINAL") or {}).get("waveform", {}).get("rms_dbfs")
    ana_rms = (pipeline.get("analysis.wav") or {}).get("waveform", {}).get("rms_dbfs")
    if orig_rms is not None and ana_rms is not None and ana_rms < orig_rms - 15:
        tags.append("VOCAL_SEPARATION_ATTENUATION")

    if voiced < 0.05:
        tags.append("PITCH_DETECTION_FAILURE")
    pitch = prod.get("pitch_stages") or {}
    if pitch.get("pyin_voiced_frames", 0) > 0 and pitch.get("after_rms_frames", 0) == 0:
        tags.append("INPUT_AUDIO_LOW_LEVEL")
    if pitch.get("after_rms_frames", 0) > 0 and pitch.get("after_range_frames", 0) == 0:
        tags.append("PITCH_VALID_MASK_TOO_AGGRESSIVE")
    if pitch.get("after_range_frames", 0) > 0 and pitch.get("after_octave_frames", 0) == 0:
        tags.append("OCTAVE_JUMP_FILTER_TOO_AGGRESSIVE")

    n_usable = int(evidence.get("n_usable_segments") or 0)
    mass = float(evidence.get("total_evidence_mass") or 0)
    fam = float(evidence.get("mean_source_families") or 0)
    agree = float(evidence.get("mean_family_agreement") or 0)
    ratio_ok = bool(evidence.get("ratio_eligible"))

    min_seg = thresholds.get("MIN_SEGMENTS_FOR_RATIO", 3)
    min_mass = thresholds.get("MIN_SONG_EVIDENCE_MASS", 1.8)
    min_fam_cov = thresholds.get("MIN_FAMILY_COVERAGE_SONG", 1.5)

    if n_usable < min_seg:
        tags.append("SEGMENT_EXTRACTION_INSUFFICIENT")
    if mass < min_mass:
        tags.append("EVIDENCE_MASS_INSUFFICIENT")
    if fam < min_fam_cov * 0.5:
        tags.append("SOURCE_FAMILY_INSUFFICIENT")

    sb = (vt.get("source_balance") or {})
    bal = str(sb.get("balance_class") or "").upper()
    if bal == "CONFLICTED":
        tags.append("SOURCE_FAMILY_CONFLICT")
    if bal in ("NEUTRAL", "BALANCED") and not ratio_ok:
        tags.append("NEUTRAL_EVIDENCE")

    res = str(vt.get("resolution_state") or "").upper()
    if res == "INSUFFICIENT_EVIDENCE":
        tags.append("EVIDENCE_MASS_INSUFFICIENT")
    elif res == "CONFLICTED_EVIDENCE":
        tags.append("SOURCE_FAMILY_CONFLICT")
    elif res == "NEUTRAL_EVIDENCE":
        tags.append("NEUTRAL_EVIDENCE")

    if not ratio_ok and n_usable >= min_seg:
        tags.append("REGISTER_COVERAGE_INSUFFICIENT")

    if not tags:
        if str(vt.get("base_type") or "") == "UNRESOLVED":
            tags.append("CLASSIFICATION_LOGIC_BUG")
        else:
            tags.append("RESOLVED")

    primary = tags[0]
    priority = [
        "QUALITY_GATE_FAILED",
        "INPUT_AUDIO_SILENT",
        "PITCH_DETECTION_FAILURE",
        "INPUT_AUDIO_LOW_LEVEL",
        "VOCAL_SEPARATION_ATTENUATION",
        "SEGMENT_EXTRACTION_INSUFFICIENT",
        "EVIDENCE_MASS_INSUFFICIENT",
        "SOURCE_FAMILY_CONFLICT",
        "NEUTRAL_EVIDENCE",
        "SOURCE_FAMILY_INSUFFICIENT",
    ]
    for p in priority:
        if p in tags:
            primary = p
            break
    return sorted(set(tags)), primary


def run_production_analysis(source: Path, sid: str, out_base: Path) -> dict[str, Any]:
    prod_dir = out_base / sid / "prod"
    if prod_dir.exists():
        shutil.rmtree(prod_dir)
    prod_dir.mkdir(parents=True, exist_ok=True)

    result = analyze_audio(
        str(source),
        output_dir=str(out_base / sid),
        recording_id="prod",
        sample_rate=PRODUCTION_CONFIG["sample_rate"],
        separate=PRODUCTION_CONFIG["separate"],
        analysis_mode=PRODUCTION_CONFIG["analysis_mode"],
        input_mode=PRODUCTION_CONFIG["input_mode"],
        include_feedback=PRODUCTION_CONFIG["include_feedback"],
        build_preview=True,
    )
    pub = free_public_result(result)
    vf = result.get("vocal_function_profile") or {}
    vt_raw = vf.get("vocal_type_profile") or {}
    vt = vt_raw if isinstance(vt_raw, dict) else {}

    # Prefer engine-written evidence on vocal_type_profile (source of truth).
    ev_raw = vt.get("evidence") or {}
    sb_raw = vt.get("source_balance") or {}
    hc_raw = vt.get("head_chest") or {}
    stats = {
        "total_evidence_mass": ev_raw.get("mass") or ev_raw.get("total_evidence_mass"),
        "n_usable": ev_raw.get("n_usable_segments"),
        "mean_source_families": ev_raw.get("mean_source_families"),
        "mean_family_agreement": ev_raw.get("family_agreement")
        or sb_raw.get("family_agreement"),
        "global_ratio_directionality": ev_raw.get("global_ratio_directionality")
        or hc_raw.get("global_ratio_directionality"),
    }
    ratio_ok = bool(ev_raw.get("ratio_eligible"))
    if not ratio_ok and stats.get("n_usable"):
        segments = vf.get("segments") or []
        hc_rows = score_all_segments(segments) if segments else []
        fallback_stats = song_evidence_stats(hc_rows) if hc_rows else {}
        if fallback_stats:
            stats = fallback_stats
            ratio_ok = ratio_eligible(fallback_stats)

    resolution_state = vt.get("resolution_state")
    if not resolution_state:
        resolution_state = classify_vocal_type_resolution_state(
            base_type=str(vt.get("base_type") or vt.get("type_id") or "UNRESOLVED"),
            confidence=str(vt.get("confidence") or "low"),
            ratios_available=bool((vt.get("head_chest") or {}).get("available")),
            balance_class=str((vt.get("source_balance") or {}).get("balance_class") or ""),
            neutral_collapse=any("NEUTRAL_COLLAPSE" in str(w) for w in (vt.get("warnings") or [])),
        )

    prod_dir_path = out_base / sid / "prod"
    analysis_wav = prod_dir_path / "analysis.wav"
    pitch_stages = {}
    if analysis_wav.exists():
        y, sr = librosa.load(str(analysis_wav), sr=None, mono=True)
        pitch_stages = audit_pitch_stages(y, sr)

    main_finding = pub.get("main_finding_teaser") or {}
    finding_issue = None
    if str((pub.get("quality") or {}).get("status")).lower() == "fail":
        if main_finding.get("none") or main_finding.get("state") == "NONE":
            finding_issue = "ANALYSIS_UNAVAILABLE_SHOWN_AS_NO_PROBLEM"

    return {
        "result_paths": {
            "analysis_wav": str(analysis_wav) if analysis_wav.exists() else None,
            "preview_wav": str(prod_dir_path / "preview.wav"),
            "input_converted": str(prod_dir_path / "input_converted.wav"),
        },
        "quality": pub.get("quality") or result.get("quality"),
        "score": pub.get("score") or result.get("score"),
        "main_finding_teaser": main_finding,
        "vocal_function_teaser": pub.get("vocal_function_teaser"),
        "vocal_type_teaser": pub.get("vocal_type_teaser"),
        "finding_issue": finding_issue,
        "vocal_type": {
            "available": vt.get("available"),
            "type_id": vt.get("type_id") or vt.get("base_type"),
            "base_type": vt.get("base_type"),
            "display_name": vt.get("display_name"),
            "confidence": vt.get("confidence"),
            "confidence_label": vt.get("confidence_label"),
            "resolution_state": resolution_state,
            "source_balance": vt.get("source_balance"),
            "head_chest": vt.get("head_chest"),
            "bridge": vt.get("bridge"),
            "warnings": vt.get("warnings") or [],
            "evidence": {
                "total_evidence_mass": stats.get("total_evidence_mass"),
                "n_usable_segments": stats.get("n_usable"),
                "mean_source_families": stats.get("mean_source_families"),
                "mean_family_agreement": stats.get("mean_family_agreement"),
                "ratio_eligible": ratio_ok,
                "global_ratio_directionality": stats.get("global_ratio_directionality"),
            },
            "range_coverage": (vt.get("range_coverage") or {}),
        },
        "pitch_stages": pitch_stages,
    }


def collect_pipeline_stages(source: Path, sid: str, out_base: Path) -> dict[str, Any]:
    prod_dir = out_base / sid / "prod"
    stages: dict[str, Any] = {}
    stages["ORIGINAL"] = stage_audit_for_signal(source, "ORIGINAL")
    conv = prod_dir / "input_converted.wav"
    if conv.exists():
        stages["input_converted.wav"] = stage_audit_for_signal(conv, "CONVERTED")
    demucs_voc = prod_dir / "demucs" / "vocals.wav"
    if demucs_voc.exists():
        stages["demucs/vocals.wav"] = stage_audit_for_signal(demucs_voc, "VOCALS_STEM")
    analysis = prod_dir / "analysis.wav"
    if analysis.exists():
        stages["analysis.wav"] = stage_audit_for_signal(analysis, "ANALYSIS")
    preview = prod_dir / "preview.wav"
    if preview.exists():
        stages["preview.wav"] = stage_audit_for_signal(preview, "PREVIEW")
    return stages


def run_experiments(source: Path, sid: str, out_base: Path) -> dict[str, Any]:
    exp: dict[str, Any] = {}
    work = out_base / sid / "experiments"
    work.mkdir(parents=True, exist_ok=True)

    # CASE B: decode-only diagnostic
    y, sr = librosa.load(str(source), sr=44100, mono=True)
    exp["decode_only"] = {
        "waveform": waveform_stats(y, sr),
        "pitch": audit_pitch_stages(y, sr),
    }

    # CASE C/D: separation comparison (diagnostic only, not production)
    sep_dir = work / "separation"
    sep_dir.mkdir(exist_ok=True)
    sep = maybe_separate_vocals(str(source), sep_dir, separate=True)
    exp["separation_meta"] = {k: v for k, v in sep.items() if k != "vocals_path"}
    pre_path = Path(sep.get("vocals_path") or source)
    if pre_path.exists():
        y_pre, sr_pre = librosa.load(str(pre_path), sr=44100, mono=True)
        exp["pre_separation_vocals_path"] = {
            "path": str(pre_path),
            "waveform": waveform_stats(y_pre, sr_pre),
            "pitch": audit_pitch_stages(y_pre, sr_pre),
        }
    vocals = sep_dir / "demucs" / "vocals.wav"
    if vocals.exists():
        y_v, sr_v = librosa.load(str(vocals), sr=44100, mono=True)
        exp["post_separation_vocals"] = {
            "waveform": waveform_stats(y_v, sr_v),
            "pitch": audit_pitch_stages(y_v, sr_v),
        }

    # Normalized diagnostic copy
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    if peak > 1e-6:
        y_norm = (y / peak * 0.95).astype(np.float32)
        norm_path = work / "diagnostic_peak_normalized.wav"
        sf.write(str(norm_path), y_norm, sr)
        exp["peak_normalized"] = {
            "path": str(norm_path),
            "waveform": waveform_stats(y_norm, sr),
            "pitch": audit_pitch_stages(y_norm, sr),
        }
    return exp


def run_api_path(source: Path) -> dict[str, Any]:
    try:
        import io

        from fastapi.testclient import TestClient

        from backend.app.api import routes as routes_mod
        from backend.app.diagnostic import DiagnosticSessionService
        from backend.app.jobs.runner import JobRunner
        from backend.app.main import app
        from backend.app.services.analysis_service import AnalysisService

        runtime = OUT_DIR / "_api_runtime"
        if runtime.exists():
            shutil.rmtree(runtime)
        runtime.mkdir(parents=True)
        svc = AnalysisService()
        svc.runtime_dir = runtime
        svc.runner = JobRunner(runtime, max_workers=1)
        routes_mod.service = svc
        routes_mod.diag = DiagnosticSessionService(runtime)
        client = TestClient(app, raise_server_exceptions=True)
        data = source.read_bytes()
        files = {"file": (source.name, io.BytesIO(data), "audio/mp4")}
        form = {
            "separate": "false",
            "include_feedback": "false",
            "analysis_mode": PRODUCTION_CONFIG["analysis_mode"],
            "input_mode": PRODUCTION_CONFIG["input_mode"],
        }
        headers = {"X-VAgent-User-Key": "audit-anon"}
        r = client.post("/v1/analyses", files=files, data=form, headers=headers)
        if r.status_code != 200:
            return {"ok": False, "status": r.status_code, "body": r.text[:500]}
        aid = r.json()["analysis_id"]
        t0 = time.time()
        while time.time() - t0 < 180:
            job = client.get(f"/v1/analyses/{aid}", headers=headers).json()
            if job.get("status") in ("completed", "failed"):
                break
            time.sleep(0.5)
        result = job.get("result") or {}
        vt = (result.get("vocal_type_teaser") or {})
        return {
            "ok": job.get("status") == "completed",
            "analysis_id": aid,
            "status": job.get("status"),
            "quality_status": (result.get("quality") or {}).get("status"),
            "vocal_type_display": vt.get("display_name"),
            "resolution_state": vt.get("resolution_state"),
            "main_finding_state": (result.get("main_finding_teaser") or {}).get("state"),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def audit_one(sid: str, meta: dict[str, Any]) -> dict[str, Any]:
    source: Path = meta["path"]
    detail: dict[str, Any] = {
        "sample_id": sid,
        "label": meta.get("label"),
        "sex_label": meta.get("sex"),
        "source_path": str(source),
        "all_matches": meta.get("all_matches"),
        "production_config": PRODUCTION_CONFIG,
        "thresholds": {
            "MIN_EVIDENCE_MASS_SEGMENT": coach_cfg.MIN_EVIDENCE_MASS_SEGMENT,
            "MIN_SEGMENTS_FOR_RATIO": coach_cfg.MIN_SEGMENTS_FOR_RATIO,
            "MIN_SEGMENTS_FOR_HIGH_CONF": coach_cfg.MIN_SEGMENTS_FOR_HIGH_CONF,
            "MIN_SONG_EVIDENCE_MASS": coach_cfg.MIN_SONG_EVIDENCE_MASS,
            "MIN_FAMILY_COVERAGE_SONG": coach_cfg.MIN_FAMILY_COVERAGE_SONG,
            "MIN_FAMILY_AGREEMENT_HIGH": coach_cfg.MIN_FAMILY_AGREEMENT_HIGH,
            "FMIN_HZ": round(float(FMIN), 2),
            "FMAX_HZ": round(float(FMAX), 2),
            "F0_VALID_MIN_HZ": F0_VALID_MIN_HZ,
            "F0_VALID_MAX_HZ": F0_VALID_MAX_HZ,
        },
    }

    y_orig, sr_orig = librosa.load(str(source), sr=None, mono=True)
    detail["original"] = {
        "file": {
            "filename": source.name,
            "extension": source.suffix,
            "size_bytes": source.stat().st_size,
            "ffprobe": ffprobe_info(source),
        },
        "waveform": waveform_stats(y_orig, sr_orig),
        "pitch": audit_pitch_stages(y_orig, sr_orig),
        "quality": evaluate_quality(
            y_orig,
            sr_orig,
            voiced_ratio=audit_pitch_stages(y_orig, sr_orig)["pyin_voiced_ratio"],
            voiced_duration_sec=audit_pitch_stages(y_orig, sr_orig)["pyin_voiced_ratio"]
            * (len(y_orig) / max(sr_orig, 1)),
        ),
    }

    detail["production"] = run_production_analysis(source, sid, OUT_DIR)
    detail["pipeline_stages"] = collect_pipeline_stages(source, sid, OUT_DIR)
    detail["experiments"] = run_experiments(source, sid, OUT_DIR)
    detail["api_path"] = run_api_path(source)
    tags, primary = classify_root_cause(detail)
    detail["root_cause_tags"] = tags
    detail["root_cause_primary"] = primary
    return detail


def row_from_detail(d: dict[str, Any]) -> dict[str, Any]:
    orig_wf = (d.get("original") or {}).get("waveform") or {}
    orig_pitch = (d.get("original") or {}).get("pitch") or {}
    prod = d.get("production") or {}
    quality = prod.get("quality") or {}
    metrics = quality.get("metrics") or {}
    pipeline = d.get("pipeline_stages") or {}
    ana_wf = (pipeline.get("analysis.wav") or {}).get("waveform") or {}
    vt = prod.get("vocal_type") or {}
    ev = vt.get("evidence") or {}
    return {
        "sample": d.get("label"),
        "sex_label": d.get("sex_label"),
        "duration": metrics.get("duration_sec") or orig_wf.get("duration_sec"),
        "source_rms_dbfs": orig_wf.get("rms_dbfs"),
        "analysis_rms_dbfs": ana_wf.get("rms_dbfs"),
        "quality_status": quality.get("status"),
        "silent_ratio": metrics.get("silent_ratio") or orig_wf.get("silent_ratio"),
        "voiced_ratio": metrics.get("voiced_ratio") or orig_pitch.get("pyin_voiced_ratio"),
        "voiced_duration_sec": metrics.get("voiced_duration_sec"),
        "f0_mean": orig_pitch.get("f0_mean_hz"),
        "f0_min": orig_pitch.get("f0_min_hz"),
        "f0_max": orig_pitch.get("f0_max_hz"),
        "usable_segments": ev.get("n_usable_segments"),
        "evidence_mass": ev.get("total_evidence_mass"),
        "mean_source_families": ev.get("mean_source_families"),
        "family_agreement": ev.get("mean_family_agreement"),
        "ratio_eligible": ev.get("ratio_eligible"),
        "source_balance_class": (vt.get("source_balance") or {}).get("balance_class"),
        "vocal_type": vt.get("display_name"),
        "confidence": vt.get("confidence"),
        "resolution": vt.get("resolution_state"),
        "root_cause": d.get("root_cause_primary"),
    }


def write_report(details: dict[str, dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Vocal Type 3-Sample Audit",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## PRODUCTION_ANALYSIS_CONFIG",
        "",
        "| key | value |",
        "|---|---|",
    ]
    for k, v in PRODUCTION_CONFIG.items():
        lines.append(f"| {k} | {v} |")
    lines.extend(
        [
            "",
            "Default miniapp upload (no accompaniment): FUNCTIONAL + VOCAL_ONLY + separate=false.",
            "",
            "## Comparison",
            "",
            "| Metric | 강1(남) | 강2(남) | 박1(여) |",
            "|---|---|---|---|",
        ]
    )
    order = ["강1", "강2", "박1"]
    by_label = {r["sample"]: r for r in rows}

    def cell(label: str, key: str) -> str:
        r = by_label.get(label) or {}
        v = r.get(key)
        return "" if v is None else str(v)

    metrics = [
        ("Source RMS", "source_rms_dbfs"),
        ("Analysis RMS", "analysis_rms_dbfs"),
        ("Quality", "quality_status"),
        ("Silent ratio", "silent_ratio"),
        ("Voiced ratio", "voiced_ratio"),
        ("F0 mean", "f0_mean"),
        ("F0 min/max", "f0_min"),
        ("Usable segments", "usable_segments"),
        ("Evidence mass", "evidence_mass"),
        ("Source families", "mean_source_families"),
        ("Family agreement", "family_agreement"),
        ("Ratio eligible", "ratio_eligible"),
        ("Vocal type", "vocal_type"),
        ("Confidence", "confidence"),
        ("Root cause", "root_cause"),
    ]
    for title, key in metrics:
        if key == "f0_min":
            vals = []
            for lb in order:
                r = by_label.get(lb) or {}
                mn = r.get("f0_min")
                mx = r.get("f0_max")
                vals.append(f"{mn}/{mx}" if mn is not None else "")
            lines.append(f"| {title} | {vals[0]} | {vals[1]} | {vals[2]} |")
        else:
            lines.append(
                f"| {title} | {cell(order[0], key)} | {cell(order[1], key)} | {cell(order[2], key)} |"
            )

    for sid, d in details.items():
        lines.extend(["", f"## {d.get('label')} ({sid})", ""])
        lines.append(f"**ROOT CAUSE:** {d.get('root_cause_primary')}  ")
        lines.append(f"**Tags:** {', '.join(d.get('root_cause_tags') or [])}")
        q = (d.get("production") or {}).get("quality") or {}
        lines.append(f"- quality: {(q.get('status'))}")
        m = q.get("metrics") or {}
        lines.append(
            f"- silent_ratio={m.get('silent_ratio')} voiced_ratio={m.get('voiced_ratio')} voiced_duration_sec={m.get('voiced_duration_sec')}"
        )
        vt = (d.get("production") or {}).get("vocal_type") or {}
        ev = vt.get("evidence") or {}
        lines.append(
            f"- usable_segments={ev.get('n_usable_segments')} evidence_mass={ev.get('total_evidence_mass')} mean_source_families={ev.get('mean_source_families')} family_agreement={ev.get('mean_family_agreement')} ratio_eligible={ev.get('ratio_eligible')}"
        )
        if d.get("production", {}).get("finding_issue"):
            lines.append(f"- **FINDING ISSUE:** {d['production']['finding_issue']}")

    # Common failure
    causes = [d.get("root_cause_primary") for d in details.values()]
    if len(set(causes)) == 1:
        lines.extend(["", "## COMMON FAILURE POINT", "", causes[0]])
    else:
        lines.extend(["", "## COMMON FAILURE POINT", "", "Mixed — see per-sample root causes."])

    lines.extend(["", "## SAFE TO FIX NOW", "", "NEED MORE EVIDENCE — audit only, no production code changes applied."])
    (OUT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    samples = resolve_samples(args)

    print("SAMPLE FILES")
    for sid, meta in samples.items():
        print(f"  {meta['label']} -> {meta['path']}")
        if meta.get("all_matches") and len(meta["all_matches"]) > 1:
            print(f"    duplicates: {meta['all_matches'][1:]}")

    details: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for sid, meta in samples.items():
        print(f"\n=== Auditing {meta['label']} ({sid}) ===")
        d = audit_one(sid, meta)
        details[sid] = d
        rows.append(row_from_detail(d))
        print(f"  ROOT CAUSE: {d.get('root_cause_primary')}")

    # summary.csv
    if rows:
        with (OUT_DIR / "summary.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    safe_details = json.loads(json.dumps(details, default=str))
    (OUT_DIR / "details.json").write_text(
        json.dumps(safe_details, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report(details, rows)
    print(f"\nWrote {OUT_DIR / 'summary.csv'}")
    print(f"Wrote {OUT_DIR / 'report.md'}")
    print(f"Wrote {OUT_DIR / 'details.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
