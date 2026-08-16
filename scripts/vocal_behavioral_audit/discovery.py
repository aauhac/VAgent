# -*- coding: utf-8 -*-
"""Audio asset discovery with SHA-256 dedup."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".webm"}

DEFAULT_SKIP_DIRS = {
    ".venv",
    "node_modules",
    ".git",
    "dist",
    "build",
    "__pycache__",
    ".audit_runtime",
    "audit_output",
    "audit_output_after",
    "audit_output_baseline",
    "audit_output_final",
    "audit_labels",
    ".pytest_cache",
    "miniapp",
}

GENERATED_NAMES = {
    "analysis.wav",
    "preview.wav",
    "input_converted.wav",
    "input_preprocessed.wav",
    "processed.wav",
    "_e2e_upload.wav",
    "_e2e_upload.webm",
    "_tmp_probe.wav",
    "_tmp_probe3.wav",
    "_tmp_probe4.wav",
    # Demucs / pipeline intermediates — not original user assets
    "vocals.wav",
    "no_vocals.wav",
    "drums.wav",
    "bass.wav",
    "other.wav",
    "accompaniment.wav",
}

SKIP_NAME_SUBSTRINGS = (
    "demucs",
    "htdemucs",
    "separated",
)

PREFERRED_ROOTS = (
    "data",
    "samples",
    "fixtures",
    "test_assets",
    "uploads",
    "audio",
    "local_samples",
    "validation",
)


@dataclass
class AudioAsset:
    audio_id: str
    path: str
    sha256: str
    aliases: list[str] = field(default_factory=list)
    duration_sec: Optional[float] = None
    sample_rate: Optional[int] = None
    analysis_json_hint: Optional[str] = None
    bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "audio_id": self.audio_id,
            "path": self.path,
            "sha256": self.sha256,
            "duration_sec": self.duration_sec,
            "sample_rate": self.sample_rate,
            "aliases": list(self.aliases),
            "analysis_json_hint": self.analysis_json_hint,
            "bytes": self.bytes,
        }


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _should_skip_dir(parts: tuple[str, ...], skip: set[str]) -> bool:
    return any(p in skip for p in parts)


def _priority(path: Path, repo: Path) -> tuple[int, int, str]:
    """Lower is better representative."""
    rel = path.relative_to(repo) if path.is_relative_to(repo) else path
    name = path.name.lower()
    parts = rel.parts
    score = 50
    if path.parent == repo:
        score = 0
    elif parts and parts[0] in PREFERRED_ROOTS:
        score = 5
    elif "runtime" in parts and name == "upload.wav":
        score = 10
    elif "runtime" in parts:
        score = 40
    elif name in GENERATED_NAMES:
        score = 80
    if name in GENERATED_NAMES:
        score += 20
    if name.startswith("_tmp") or "tmp" in parts[0:1]:
        score += 30
    return (score, -path.stat().st_size if path.exists() else 0, str(rel).lower())


def _probe_duration(path: Path) -> tuple[Optional[float], Optional[int]]:
    try:
        import soundfile as sf

        info = sf.info(str(path))
        return float(info.duration), int(info.samplerate)
    except Exception:
        # Avoid slow/deprecated audioread fallback during discovery
        return None, None


def _find_analysis_hint(path: Path, aliases: Iterable[str]) -> Optional[str]:
    candidates = [path, *[Path(a) for a in aliases]]
    for p in candidates:
        parent = p.parent
        for name in ("analysis.json", "public_result.json"):
            hint = parent / name
            if hint.exists() and hint.stat().st_size > 100:
                # Prefer full analysis.json
                full = parent / "analysis.json"
                if full.exists():
                    return str(full.resolve())
                return str(hint.resolve())
    return None


def discover_audio_assets(
    repo_root: Path | str,
    *,
    audio_roots: Optional[list[str]] = None,
    skip_dirs: Optional[set[str]] = None,
    include_generated: bool = False,
) -> list[AudioAsset]:
    repo = Path(repo_root).resolve()
    skip = set(DEFAULT_SKIP_DIRS)
    if skip_dirs:
        skip |= set(skip_dirs)

    search_roots: list[Path] = []
    if audio_roots:
        for r in audio_roots:
            p = Path(r)
            if not p.is_absolute():
                p = repo / p
            if p.exists():
                search_roots.append(p.resolve())
    else:
        search_roots.append(repo)

    by_sha: dict[str, list[Path]] = {}
    skipped: list[dict[str, str]] = []

    for root in search_roots:
        if root.is_file():
            paths = [root]
        else:
            paths = list(root.rglob("*"))
        for p in paths:
            if not p.is_file():
                continue
            if p.suffix.lower() not in AUDIO_EXTS:
                continue
            try:
                rel_parts = p.resolve().relative_to(repo).parts
            except ValueError:
                rel_parts = p.parts
            if _should_skip_dir(rel_parts, skip):
                continue
            name = p.name.lower()
            if not include_generated and name in GENERATED_NAMES:
                skipped.append({"path": str(p), "reason": "generated_name"})
                continue
            if any(s in str(p).lower().replace("\\", "/") for s in SKIP_NAME_SUBSTRINGS):
                skipped.append({"path": str(p), "reason": "pipeline_intermediate"})
                continue
            if name.startswith("_tmp") or re.match(r"^_tmp", name):
                skipped.append({"path": str(p), "reason": "tmp"})
                continue
            # Prefer original singing assets: skip tiny synthetic fixtures under outputs/runtime stems
            if name in {"tone.wav", "a.wav", "b.wav", "silence.wav"}:
                skipped.append({"path": str(p), "reason": "fixture_tone"})
                continue
            # runtime: only keep upload.* (original session audio), not derived wavs
            if "runtime" in rel_parts and not name.startswith("upload."):
                skipped.append({"path": str(p), "reason": "runtime_non_upload"})
                continue
            # outputs feedback trees: skip preprocessed derivatives
            if "outputs" in rel_parts and name.endswith(".wav"):
                skipped.append({"path": str(p), "reason": "outputs_derivative"})
                continue
            if "_tmp_effort_audit" in rel_parts or "audits" in rel_parts:
                skipped.append({"path": str(p), "reason": "prior_audit_runtime"})
                continue
            try:
                size = p.stat().st_size
            except OSError as e:
                skipped.append({"path": str(p), "reason": f"stat:{e}"})
                continue
            if size <= 0:
                skipped.append({"path": str(p), "reason": "empty"})
                continue
            if size < 1_000:
                skipped.append({"path": str(p), "reason": "too_small"})
                continue
            try:
                digest = sha256_file(p)
            except OSError as e:
                skipped.append({"path": str(p), "reason": f"read:{e}"})
                continue
            by_sha.setdefault(digest, []).append(p.resolve())

    assets: list[AudioAsset] = []
    for digest, paths in sorted(by_sha.items(), key=lambda kv: kv[0]):
        ranked = sorted(paths, key=lambda p: _priority(p, repo))
        primary = ranked[0]
        aliases = [str(p) for p in ranked]
        dur, sr = _probe_duration(primary)
        hint = _find_analysis_hint(primary, aliases)
        audio_id = digest[:12]
        assets.append(
            AudioAsset(
                audio_id=audio_id,
                path=str(primary),
                sha256=digest,
                aliases=aliases,
                duration_sec=dur,
                sample_rate=sr,
                analysis_json_hint=hint,
                bytes=primary.stat().st_size,
            )
        )

    # Attach skip metadata via module attr for callers that want it
    discover_audio_assets.last_skipped = skipped  # type: ignore[attr-defined]
    return assets


def manifest_payload(assets: list[AudioAsset], *, skipped: Optional[list] = None) -> dict[str, Any]:
    return {
        "audit_version": "behavioral-audit-v1",
        "count": len(assets),
        "skipped_count": len(skipped or []),
        "skipped": skipped or [],
        "audios": [a.to_dict() for a in assets],
    }
