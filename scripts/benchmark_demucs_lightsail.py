#!/usr/bin/env python3
"""
Demucs (htdemucs) CPU benchmark for AWS Lightsail $7 (1GB RAM + swap).

This is an *offline* benchmark tool:
- does not deploy live backend
- does not require DB / production secrets
- reads a source audio file from a local path (e.g. /var/lib/vocalfb/runtime/.../upload.m4a)

It mimics the current production separation path:
audio_analyzer.preprocessing.maybe_separate_vocals()
-> audio_analyzer.legacy.vocal_separator.separate_vocals()

Cache kinds are recorded separately and must not be conflated:

- MODEL_CACHE_HIT: htdemucs weights under TORCH_HOME. Reused by every stage.
- SEPARATION_ARTIFACT_CACHE_HIT: vocals.wav / no_vocals.wav plus .source_sha256 sidecar.

Stage B clip artifacts are never reused by Stage C (clip SHA != full SHA).
Stage C always separates the full source.
Stage D FUNCTIONAL+MIXED reuses Stage C full artifacts after sidecar SHA verification
and must not run Demucs again on the same full file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def _parse_meminfo_value(key: str, text: str) -> Optional[float]:
    # example line: "MemAvailable:  123456 kB"
    m = re.search(rf"^{re.escape(key)}:\\s+(\\d+)\\s+kB$", text, flags=re.M)
    if not m:
        return None
    return float(m.group(1))


def _read_proc_meminfo() -> dict[str, Optional[float]]:
    try:
        txt = Path("/proc/meminfo").read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {
            "MemAvailable_kb": None,
            "SwapTotal_kb": None,
            "SwapFree_kb": None,
        }
    return {
        "MemAvailable_kb": _parse_meminfo_value("MemAvailable", txt),
        "SwapTotal_kb": _parse_meminfo_value("SwapTotal", txt),
        "SwapFree_kb": _parse_meminfo_value("SwapFree", txt),
    }


def _read_self_rss_mb() -> Optional[float]:
    # "VmRSS:    12345 kB"
    try:
        status = Path("/proc/self/status").read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    m = re.search(r"^VmRSS:\\s+(\\d+)\\s+kB$", status, flags=re.M)
    if not m:
        return None
    return float(m.group(1)) / 1024.0


class MemSampler:
    def __init__(self, interval_sec: float = 0.5):
        self.interval_sec = interval_sec
        self.t0 = time.perf_counter()
        self.samples: list[dict[str, Any]] = []
        self.max_rss_mb: float = 0.0
        self.max_swap_used_mb: float = 0.0
        self._stop = False
        self._th = None

    def start(self) -> None:
        import threading

        def run():
            while not self._stop:
                t = time.perf_counter() - self.t0
                rss_mb = _read_self_rss_mb()
                mi = _read_proc_meminfo()
                swap_total = mi.get("SwapTotal_kb") or 0.0
                swap_free = mi.get("SwapFree_kb") or 0.0
                swap_used_mb = max(0.0, (swap_total - swap_free) / 1024.0)
                if rss_mb is not None:
                    self.max_rss_mb = max(self.max_rss_mb, float(rss_mb))
                self.max_swap_used_mb = max(self.max_swap_used_mb, float(swap_used_mb))
                self.samples.append(
                    {
                        "t_sec": round(t, 3),
                        "rss_mb": rss_mb,
                        "swap_used_mb": round(swap_used_mb, 3),
                        "mem_available_mb": None
                        if mi.get("MemAvailable_kb") is None
                        else round(mi["MemAvailable_kb"] / 1024.0, 3),
                    }
                )
                time.sleep(self.interval_sec)

        self._th = threading.Thread(target=run, daemon=True)
        self._th.start()

    def stop(self) -> None:
        self._stop = True
        if self._th:
            self._th.join(timeout=5)


def _ffprobe_duration_sec(path: str) -> Optional[float]:
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            return None
        return float((r.stdout or "").strip())
    except Exception:
        return None


def _ensure_clip(
    source: str,
    clip_path: Path,
    *,
    start_sec: float,
    duration_sec: float,
) -> None:
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    if clip_path.exists() and clip_path.stat().st_size > 1024 * 1024:
        return
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_sec),
        "-t",
        str(duration_sec),
        "-i",
        source,
        "-ac",
        "2",
        "-ar",
        "44100",
        str(clip_path),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg clip failed: {p.stderr[:300]}")


def _http_get_json(url: str, timeout_sec: float = 3.0) -> Optional[dict[str, Any]]:
    try:
        with urlopen(url, timeout=timeout_sec) as resp:
            txt = resp.read().decode("utf-8", errors="ignore")
        return json.loads(txt)
    except Exception:
        return None


@dataclass
class StageResult:
    name: str
    ok: bool
    wall_sec: float
    max_rss_mb: float
    max_swap_used_mb: float
    error: Optional[str] = None
    extra: dict[str, Any] | None = None
    samples: list[dict[str, Any]] | None = None


def _run_stage(name: str, fn, *, sample_interval_sec: float = 0.5) -> StageResult:
    sampler = MemSampler(interval_sec=sample_interval_sec)
    sampler.start()
    t0 = time.perf_counter()
    ok = True
    err = None
    extra: dict[str, Any] = {}
    try:
        extra = fn() or {}
    except Exception as e:  # noqa: BLE001
        ok = False
        err = str(e)[:300]
    wall = time.perf_counter() - t0
    sampler.stop()
    return StageResult(
        name=name,
        ok=ok,
        wall_sec=round(wall, 3),
        max_rss_mb=round(sampler.max_rss_mb, 3),
        max_swap_used_mb=round(sampler.max_swap_used_mb, 3),
        error=err,
        extra=extra,
        samples=sampler.samples,
    )


def _htdemucs_checkpoint_paths(model_cache: str | Path) -> list[Path]:
    root = Path(model_cache) / "hub" / "checkpoints"
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in {".th", ".pt"})


def _model_cache_hit(model_cache: str | Path) -> bool:
    return bool(_htdemucs_checkpoint_paths(model_cache))


def _sidecar_sha(artifact: Path) -> Optional[str]:
    side = artifact.with_suffix(artifact.suffix + ".source_sha256")
    if not side.exists():
        return None
    try:
        return side.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _separate_to_dir(
    audio_analyzer_out_dir: Path,
    audio_path: str,
    *,
    skip_if_exists: bool,
) -> dict[str, Any]:
    # import inside to ensure Stage A isolates import time
    from audio_analyzer.audit.fingerprints import sha256_file
    from audio_analyzer.legacy.vocal_separator import separate_vocals as _separate_vocals

    source_sha = sha256_file(audio_path)
    vocals_path = audio_analyzer_out_dir / "demucs" / "vocals.wav"
    result = _separate_vocals(
        audio_path=audio_path,
        output_dir=str(audio_analyzer_out_dir / "demucs"),
        model="htdemucs",
        skip_if_exists=skip_if_exists,
    )
    vocals_out = Path(result.get("vocals_path") or vocals_path)
    no_vocals_out = Path(result.get("no_vocals_path") or vocals_path.with_name("no_vocals.wav"))
    skipped = bool(result.get("skipped"))
    return {
        "separation_status": "success" if vocals_out.exists() else "failed",
        "vocals_path": str(vocals_out) if vocals_out.exists() else None,
        "no_vocals_path": str(no_vocals_out) if no_vocals_out.exists() else None,
        "vocals_exists": vocals_out.exists(),
        "no_vocals_exists": no_vocals_out.exists(),
        "source_sha256": source_sha,
        "sidecar_sha256": _sidecar_sha(vocals_out),
        "SEPARATION_ARTIFACT_CACHE_HIT": bool(skipped and skip_if_exists),
        "skipped": skipped,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="Audio path (upload.m4a) to separate")
    ap.add_argument("--out-dir", default="qa_output/demucs_lightsail_benchmark")
    ap.add_argument("--clip-start", type=float, default=None, help="Clip start sec (optional)")
    ap.add_argument("--clip-duration", type=float, default=20.0, help="Clip duration sec")
    ap.add_argument("--backend-health-url", default="http://127.0.0.1:8000/health")
    ap.add_argument("--model-cache", default="/model-cache", help="TORCH_HOME in container")
    ap.add_argument("--build-preview", action="store_true", help="Run analysis preview too (optional)")
    ap.add_argument(
        "--max-stage",
        choices=["A", "B", "C", "D"],
        default="D",
        help="Stop after the given stage",
    )
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Stage 0: server state snapshot
    meminfo0 = _read_proc_meminfo()
    rss0 = _read_self_rss_mb()

    source = str(Path(args.source).resolve())
    audio_duration = _ffprobe_duration_sec(source)

    # Clip planning
    clip_start = args.clip_start
    if clip_start is None and audio_duration and audio_duration > 40:
        # pick a stable middle-ish region for a representative vocal segment
        clip_start = max(0.0, (audio_duration - args.clip_duration) * 0.5)
    if clip_start is None:
        clip_start = 0.0

    clip_path = out_dir / "clip.wav"
    _ensure_clip(source, clip_path, start_sec=clip_start, duration_sec=args.clip_duration)

    # Respect model cache location
    os.environ["TORCH_HOME"] = args.model_cache
    model_cache_before = _model_cache_hit(args.model_cache)

    # Stage A: import/model load (no separation)
    def stage_a() -> dict[str, Any]:
        import torch  # noqa: F401
        from demucs.pretrained import get_model

        m = get_model("htdemucs")
        m.eval()
        return {
            "torch_cuda_available": bool(torch.cuda.is_available()),
            "model_samplerate": int(getattr(m, "samplerate", 0) or 0),
            "MODEL_CACHE_HIT": model_cache_before,
        }

    # Stage B: short clip only. Never reused by Stage C.
    def stage_b() -> dict[str, Any]:
        return _separate_to_dir(out_dir / "stage_b_clip", str(clip_path), skip_if_exists=False)

    # Stage C: full source only. Must recompute even if clip artifacts exist.
    def stage_c() -> dict[str, Any]:
        return _separate_to_dir(out_dir / "stage_c_full", source, skip_if_exists=False)

    backend_health_before = _http_get_json(args.backend_health_url)

    res_a = _run_stage("A_import_model_load", stage_a)
    res_b = StageResult("B_15_30s_clip_separation", False, 0.0, 0.0, 0.0, error="skipped_by_max_stage", extra={})
    res_c = StageResult("C_full_separation", False, 0.0, 0.0, 0.0, error="skipped_by_max_stage", extra={})
    functional: dict[str, Any] = {"skipped": True}
    functional_ok = False
    backend_health_after_b = _http_get_json(args.backend_health_url)
    backend_health_after_c = backend_health_after_b

    if args.max_stage != "A":
        res_b = _run_stage("B_15_30s_clip_separation", stage_b)
        backend_health_after_b = _http_get_json(args.backend_health_url)

    if args.max_stage in ("C", "D") and res_b.ok:
        res_c = _run_stage("C_full_separation", stage_c)
        backend_health_after_c = _http_get_json(args.backend_health_url)
    elif args.max_stage in ("C", "D") and not res_b.ok:
        res_c = StageResult(
            name="C_full_separation",
            ok=False,
            wall_sec=0.0,
            max_rss_mb=0.0,
            max_swap_used_mb=0.0,
            error="stage B failed; skipping stage C",
            extra={},
        )

    vocals_out = out_dir / "stage_c_full" / "demucs" / "vocals.wav"
    no_vocals_out = out_dir / "stage_c_full" / "demucs" / "no_vocals.wav"
    from audio_analyzer.audit.fingerprints import (
        cached_artifact_matches_source,
        sha256_file,
    )

    full_source_sha = sha256_file(source)
    clip_source_sha = sha256_file(str(clip_path)) if clip_path.exists() else None
    model_cache_after = _model_cache_hit(args.model_cache)
    for _res, _hit in ((res_a, model_cache_before), (res_b, model_cache_after), (res_c, model_cache_after)):
        if _res.extra is None:
            _res.extra = {}
        _res.extra.setdefault("MODEL_CACHE_HIT", bool(_hit))
    if res_b.extra is not None:
        res_b.extra["SEPARATION_ARTIFACT_CACHE_HIT"] = False
        res_b.extra.setdefault("source_sha256", clip_source_sha)
    if res_c.extra is not None:
        res_c.extra["SEPARATION_ARTIFACT_CACHE_HIT"] = False
        res_c.extra.setdefault("source_sha256", full_source_sha)
        res_c.extra["clip_source_sha256"] = clip_source_sha
        res_c.extra["clip_sha_equals_full_sha"] = bool(
            clip_source_sha and clip_source_sha == full_source_sha
        )
    res_d = StageResult("D_functional_mixed_verify", False, 0.0, 0.0, 0.0, error="skipped_by_max_stage", extra={})

    def stage_d() -> dict[str, Any]:
        from audio_analyzer import analyze_audio

        if clip_source_sha and clip_source_sha == full_source_sha:
            raise RuntimeError(
                "clip SHA equals full SHA; Stage C would not be a distinct full-source separation"
            )
        vocals_sha_ok = cached_artifact_matches_source(vocals_out, full_source_sha)
        no_vocals_sha_ok = cached_artifact_matches_source(no_vocals_out, full_source_sha)
        if not (vocals_sha_ok and no_vocals_sha_ok):
            raise RuntimeError(
                "Stage D refused Stage C artifacts: full-source SHA sidecar mismatch "
                f"(vocals={vocals_sha_ok}, no_vocals={no_vocals_sha_ok})"
            )

        # FUNCTIONAL + MIXED forces separate=True. Existing Stage C artifacts
        # must then hit skip_if_exists via source SHA sidecar — no second Demucs.
        result = analyze_audio(
            source,
            output_dir=str(out_dir),
            recording_id="stage_c_full",
            sample_rate=44100,
            analysis_mode="FUNCTIONAL",
            input_mode="MIXED",
            include_feedback=False,
            build_preview=bool(args.build_preview),
            generate_visuals=False,
        )
        audio = result.get("audio") or {}
        sep = audio.get("separation") or {}
        skipped_sep = bool(sep.get("skipped"))
        if not skipped_sep:
            raise RuntimeError(
                "Stage D cache contract failed: MIXED pipeline ran Demucs instead of "
                "reusing Stage C full-source vocals/no_vocals"
            )
        return {
            "analysis_quality_status": (result.get("quality") or {}).get("status"),
            "analysis_quality_codes": (result.get("quality") or {}).get("codes"),
            "separation_used": sep.get("used") if "used" in sep else audio.get("separation_used"),
            "separation_status": audio.get("separation_status") or sep.get("separation_status"),
            "source_mode": audio.get("source_mode") or sep.get("source_mode"),
            "functional_quality": (result.get("vocal_function_profile") or {}).get("functional_quality"),
            "vocal_type_resolution_state": (result.get("vocal_type_teaser") or {}).get(
                "resolution_state"
            )
            or (result.get("vocal_function_profile") or {}).get("vocal_type_profile", {}).get(
                "resolution_state"
            ),
            "MODEL_CACHE_HIT": model_cache_after,
            "SEPARATION_ARTIFACT_CACHE_HIT": True,
            "source_sha_verified": True,
            "clip_source_sha256": clip_source_sha,
            "full_source_sha256": full_source_sha,
        }

    if args.max_stage == "D" and res_c.ok:
        res_d = _run_stage("D_functional_mixed_verify", stage_d)
        functional = res_d.extra or {}
        if res_d.error:
            functional = {**functional, "error": res_d.error}
        functional_ok = bool(res_d.ok)

    # PASS/CAUTION/FAIL verdict
    # We only have strong evidence for success if vocals/no_vocals exist and stage C is ok.
    vocals_ok = vocals_out.exists()
    no_vocals_ok = no_vocals_out.exists()
    mix_ok = functional_ok and vocals_ok and no_vocals_ok

    # realtime factor only if duration is known
    realtime_factor = None
    if audio_duration and audio_duration > 0:
        realtime_factor = res_c.wall_sec / float(audio_duration)

    verdict = "FAIL"
    if res_a.ok and res_b.ok and res_c.ok and vocals_ok and no_vocals_ok and mix_ok:
        verdict = "PASS"
    elif res_c.ok and vocals_ok and no_vocals_ok:
        verdict = "CAUTION"

    payload = {
        "source": source,
        "audio_duration_sec": audio_duration,
        "clip": {"clip_start_sec": clip_start, "clip_duration_sec": args.clip_duration},
        "server_snapshot_before": {
            "meminfo": meminfo0,
            "self_rss_mb": rss0,
        },
        "backend_health_before": backend_health_before,
        "backend_health_after_b": backend_health_after_b,
        "backend_health_after_c": backend_health_after_c,
        "stages": {
            "A_import_model_load": asdict(res_a),
            "B_15_30s_clip_separation": asdict(res_b),
            "C_full_separation": asdict(res_c),
            "D_functional_mixed_verify": asdict(res_d),
        },
        "stage_d_verify_mixed": functional,
        "outputs": {
            "vocals_exists": vocals_ok,
            "no_vocals_exists": no_vocals_ok,
            "vocals_path": str(vocals_out) if vocals_ok else None,
            "no_vocals_path": str(no_vocals_out) if no_vocals_ok else None,
        },
        "MODEL_CACHE_HIT": bool(model_cache_before),
        "SEPARATION_ARTIFACT_CACHE_HIT": {
            "stage_b_clip": False,
            "stage_c_full": False,
            "stage_d_mixed_pipeline": bool(
                (functional or {}).get("SEPARATION_ARTIFACT_CACHE_HIT")
            ),
        },
        "cache": {
            "MODEL_CACHE_HIT": {
                "before_stage_a": model_cache_before,
                "after_run": model_cache_after,
                "checkpoint_paths": [str(p) for p in _htdemucs_checkpoint_paths(args.model_cache)],
            },
            "SEPARATION_ARTIFACT_CACHE_HIT": {
                "stage_b_clip": False,
                "stage_c_full": False,
                "stage_d_mixed_pipeline": bool(
                    (functional or {}).get("SEPARATION_ARTIFACT_CACHE_HIT")
                ),
                "clip_source_sha256": clip_source_sha,
                "full_source_sha256": full_source_sha,
                "clip_sha_equals_full_sha": bool(
                    clip_source_sha and clip_source_sha == full_source_sha
                ),
                "note": (
                    "MODEL_CACHE_HIT is TORCH_HOME htdemucs weights, reused by all stages. "
                    "SEPARATION_ARTIFACT_CACHE_HIT is vocals/no_vocals + source SHA sidecar. "
                    "Stage B clip artifacts are never reused by Stage C (clip SHA != full SHA). "
                    "Stage D reuses Stage C full-source artifacts after sidecar SHA verification."
                ),
            },
        },
        "realtime_factor": realtime_factor,
        "verdict": verdict,
    }

    (out_dir / "benchmark.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # memory.csv: we currently sample only inside _run_stage; for compactness dump none.
    # To keep the tool lightweight, we store max values + provide per-stage samples on demand later.
    md_lines = [
        "# Demucs Lightsail Benchmark",
        "",
        f"Source: `{source}`",
        f"Audio duration (ffprobe): {audio_duration}",
        "",
        "## Verdict",
        "",
        f"- verdict: {verdict}",
        f"- vocals/no_vocals: {vocals_ok}/{no_vocals_ok}",
        f"- realtime_factor: {realtime_factor}",
        "",
        "## Cache",
        "",
        f"- MODEL_CACHE_HIT: {payload['MODEL_CACHE_HIT']}",
        f"- SEPARATION_ARTIFACT_CACHE_HIT stage_b_clip: {payload['SEPARATION_ARTIFACT_CACHE_HIT']['stage_b_clip']}",
        f"- SEPARATION_ARTIFACT_CACHE_HIT stage_c_full: {payload['SEPARATION_ARTIFACT_CACHE_HIT']['stage_c_full']}",
        f"- SEPARATION_ARTIFACT_CACHE_HIT stage_d_mixed_pipeline: {payload['SEPARATION_ARTIFACT_CACHE_HIT']['stage_d_mixed_pipeline']}",
        "- note: MODEL_CACHE_HIT is TORCH_HOME htdemucs weights, reused by every stage.",
        "- note: Stage B clip SHA != Stage C full SHA, so Stage C always recomputes full source.",
        "- note: Stage D reuses Stage C full vocals/no_vocals only after source SHA sidecar verification.",
        "",
        "## Stages (summary)",
        "",
    ]
    for k, v in payload["stages"].items():
        md_lines.extend(
            [
                f"- {k}: ok={v['ok']} wall={v['wall_sec']}s max_rss={v['max_rss_mb']}MB max_swap_used={v['max_swap_used_mb']}MB",
            ]
        )
        if v.get("error"):
            md_lines.append(f"  - error: {v['error']}")
    if functional_ok:
        md_lines.extend(["", "## Functional verification (MIXED)"])
        for kk, vv in functional.items():
            md_lines.append(f"- {kk}: {vv}")
    else:
        md_lines.extend(["", "## Functional verification (MIXED)"])
        md_lines.append(f"- error: {functional.get('error')}")

    (out_dir / "benchmark.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    # Flatten stage samples into memory.csv
    rows = ["stage,t_sec,rss_mb,swap_used_mb,mem_available_mb"]
    for stage_key in (
        "A_import_model_load",
        "B_15_30s_clip_separation",
        "C_full_separation",
        "D_functional_mixed_verify",
    ):
        stage = payload["stages"][stage_key]
        for s in stage.get("samples") or []:
            rows.append(
                f"{stage_key},{s.get('t_sec')},{s.get('rss_mb')},{s.get('swap_used_mb')},{s.get('mem_available_mb')}"
            )
    (out_dir / "memory.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

