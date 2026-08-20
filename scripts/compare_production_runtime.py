#!/usr/bin/env python3
"""
Compare LOCAL exact-production-config audit vs PRODUCTION runtime artifacts.

Usage:
  # After QR uploads, with SSH access to Lightsail:
  python scripts/compare_production_runtime.py \\
    --ssh ubuntu@LIGHTSAIL_HOST \\
    --runtime-root /var/lib/vocalfb/runtime \\
    kang1=abc123... kang2=def456... park1=ghi789...

  # Or with locally copied runtime dirs:
  python scripts/compare_production_runtime.py \\
    --prod-dir qa_output/prod_runtime_mirror \\
    kang1=abc123... kang2=def456... park1=ghi789...

  # Local fingerprint only (no production ids yet):
  python scripts/compare_production_runtime.py --local-only

Does NOT deploy, commit, or modify production.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "qa_output" / "vocal_type_3sample_audit"
LOCAL_AUDIT_DIR = OUT_DIR
LOCAL_BASELINE_PATH = OUT_DIR / "local_baseline.json"
FINGERPRINT_PATH = OUT_DIR / "local_fingerprint.json"
COMPARE_REPORT_PATH = OUT_DIR / "production_vs_local.md"
COMPARE_JSON_PATH = OUT_DIR / "production_vs_local.json"

LOCAL_SAMPLES = {
    "kang1": {"label": "강1", "sex": "male", "source_glob": "강1.m4a"},
    "kang2": {"label": "강2", "sex": "male", "source_glob": "강2.m4a"},
    "park1": {"label": "박1", "sex": "female", "source_glob": "박1.m4a"},
}

EXPECTED_CONFIG = {
    "analysis_mode": "FUNCTIONAL",
    "input_mode": "VOCAL_ONLY",
    "separate": False,
}

KEY_FILES = [
    "audio_analyzer/pipeline.py",
    "audio_analyzer/coach_profile/engine.py",
    "audio_analyzer/coach_profile/config.py",
    "audio_analyzer/models.py",
    "backend/app/jobs/runner.py",
    "backend/app/services/analysis_service.py",
    "miniapp/src/pages/Upload.tsx",
    "miniapp/src/api/client.ts",
]

PACKAGED_HEAD = ROOT / "qa_output" / "production_release_v1" / "DEPLOY_HEAD.txt"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(cmd: list[str]) -> str:
    try:
        r = subprocess.run(
            ["git", *cmd],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return (r.stdout or r.stderr or "").strip()
    except OSError:
        return ""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _safe_get(d: Any, *keys: str, default: Any = None) -> Any:
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def build_local_fingerprint() -> dict[str, Any]:
    ait = ROOT / "miniapp" / "vocalfb.ait"
    ait_meta: dict[str, Any] = {}
    if ait.is_file():
        ait_meta = {
            "path": str(ait),
            "size_bytes": ait.stat().st_size,
            "last_write_time": datetime.fromtimestamp(
                ait.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
            "sha256": _sha256_file(ait),
        }

    packaged_head = None
    if PACKAGED_HEAD.is_file():
        raw = PACKAGED_HEAD.read_bytes()
        if raw.startswith(b"\xff\xfe"):
            packaged_head = raw.decode("utf-16-le").strip()
        elif raw.startswith(b"\xfe\xff"):
            packaged_head = raw.decode("utf-16-be").strip()
        else:
            packaged_head = raw.decode("utf-8", errors="replace").strip()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git": {
            "head": _git(["rev-parse", "HEAD"]),
            "status_short": _git(["status", "--short"]),
            "latest_commit": _git(["log", "-1", "--format=%H %ci %s"]),
        },
        "packaged_release_head": packaged_head,
        "deploy_lag_vs_local_head": packaged_head != _git(["rev-parse", "HEAD"]) if packaged_head else None,
        "analysis_version": "2.0",
        "coach_profile_version": "vocal-type-v1.4",
        "calibration_status": "semantic_calibration_v1_4_naq_time_derivative",
        "expected_production_config": EXPECTED_CONFIG,
        "ait": ait_meta,
        "manual_confirmation_required": ["LATEST_AIT_REGISTERED"],
        "key_file_sha256": {
            rel: _sha256_file(ROOT / rel) for rel in KEY_FILES if (ROOT / rel).is_file()
        },
        "source_content_sha256": {
            sid: _sha256_file(next(ROOT.rglob(meta["source_glob"])))
            for sid, meta in LOCAL_SAMPLES.items()
            if list(ROOT.rglob(meta["source_glob"]))
        },
    }


def extract_local_baseline() -> dict[str, Any]:
    baseline: dict[str, Any] = {"samples": {}}
    for sid, meta in LOCAL_SAMPLES.items():
        analysis_path = LOCAL_AUDIT_DIR / sid / "prod" / "analysis.json"
        public_path = LOCAL_AUDIT_DIR / sid / "prod" / "public_result.json"
        analysis = _load_json(analysis_path)
        public = _load_json(public_path)
        vf = analysis.get("vocal_function_profile") or {}
        vt = vf.get("vocal_type_profile") or {}
        ev = vt.get("evidence") or {}
        q = analysis.get("quality") or public.get("quality") or {}
        metrics = q.get("metrics") or {}
        sb = vt.get("source_balance") or {}
        vt_pub = public.get("vocal_type_teaser") or {}
        finding = public.get("main_finding_teaser") or {}

        pitch_summary = _load_json(LOCAL_AUDIT_DIR / sid / "prod" / "analysis.json")
        # pitch from details if present
        details_path = OUT_DIR / "details.json"
        pitch_stages = {}
        if details_path.is_file():
            details = _load_json(details_path)
            pitch_stages = _safe_get(details, sid, "production", "pitch_stages", default={}) or {}

        baseline["samples"][sid] = {
            "label": meta["label"],
            "sex": meta["sex"],
            "content_sha256": _safe_get(analysis, "audio", "content_sha256")
            or _safe_get(analysis, "fingerprints", "source", "sha256"),
            "analysis_mode": analysis.get("analysis_mode"),
            "input_mode": analysis.get("input_mode"),
            "separation_required": analysis.get("separation_required"),
            "separation_used": analysis.get("separation_used"),
            "source_mode": _safe_get(analysis, "audio", "separation", "source_mode")
            or _safe_get(analysis, "audio", "source_mode"),
            "separation_status": _safe_get(analysis, "audio", "separation_status"),
            "original_duration_sec": analysis.get("original_duration_sec")
            or _safe_get(analysis, "audio", "duration_sec"),
            "score_duration_sec": _safe_get(analysis, "audio", "score_duration_sec"),
            "quality_status": q.get("status"),
            "quality_codes": q.get("codes") or [],
            "rms_dbfs": metrics.get("rms_dbfs"),
            "silent_ratio": metrics.get("silent_ratio"),
            "voiced_ratio": metrics.get("voiced_ratio"),
            "voiced_duration_sec": metrics.get("voiced_duration_sec"),
            "f0_mean_hz": pitch_stages.get("f0_mean_hz"),
            "f0_min_hz": pitch_stages.get("f0_min_hz"),
            "f0_max_hz": pitch_stages.get("f0_max_hz"),
            "n_usable_segments": ev.get("n_usable_segments"),
            "evidence_mass": ev.get("mass") or ev.get("total_evidence_mass"),
            "mean_source_families": ev.get("mean_source_families"),
            "family_agreement": ev.get("family_agreement")
            or _safe_get(sb, "family_agreement"),
            "ratio_eligible": ev.get("ratio_eligible"),
            "balance_class": sb.get("balance_class"),
            "vocal_type": vt.get("display_name") or vt_pub.get("display_name"),
            "type_id": vt.get("type_id") or vt.get("base_type"),
            "confidence": vt.get("confidence") or vt_pub.get("confidence"),
            "resolution_state": vt.get("resolution_state") or vt_pub.get("resolution_state"),
            "main_finding_state": finding.get("state"),
            "main_finding_title": finding.get("title") or finding.get("user_title"),
            "analysis_rms_dbfs": _safe_get(analysis, "fingerprints", "waveform", "rms"),
        }
    return baseline


def _ssh_cat(ssh_target: str, remote_path: str) -> Optional[str]:
    try:
        r = subprocess.run(
            ["ssh", ssh_target, f"cat {remote_path}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        return r.stdout
    except (OSError, subprocess.TimeoutExpired):
        return None


def _ssh_run(ssh_target: str, cmd: str) -> str:
    try:
        r = subprocess.run(
            ["ssh", ssh_target, cmd],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        return (r.stdout or r.stderr or "").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: {exc}"


def fetch_production_runtime(
    analysis_id: str,
    *,
    ssh_target: Optional[str],
    runtime_root: Path,
    prod_mirror: Optional[Path],
) -> dict[str, Any]:
    out: dict[str, Any] = {"analysis_id": analysis_id, "files_found": []}
    rel_names = [
        "analysis_meta.json",
        "job_status.json",
        "public_result.json",
        "analysis.json",
    ]
    base: Optional[Path] = None
    if prod_mirror:
        base = prod_mirror / analysis_id
    elif ssh_target:
        remote_base = f"{runtime_root.as_posix().rstrip('/')}/{analysis_id}"
        listing = _ssh_run(ssh_target, f"ls -1 {remote_base} 2>/dev/null || true")
        out["remote_listing"] = listing.splitlines() if listing else []
        for name in rel_names:
            text = _ssh_cat(ssh_target, f"{remote_base}/{name}")
            if text:
                out[name.replace(".json", "")] = json.loads(text)
                out["files_found"].append(name)
        return out

    if base and base.is_dir():
        out["local_mirror_path"] = str(base)
        for name in rel_names:
            p = base / name
            if p.is_file():
                out[name.replace(".json", "")] = _load_json(p)
                out["files_found"].append(name)
        # waveform listing only
        for wav in ["upload.m4a", "upload.wav", "upload.mp4", "input_converted.wav", "analysis.wav", "preview.wav"]:
            if (base / wav).is_file():
                out["files_found"].append(wav)
    else:
        out["error"] = "runtime directory not found"
    return out


def extract_production_metrics(prod: dict[str, Any]) -> dict[str, Any]:
    analysis = prod.get("analysis") or {}
    public = prod.get("public_result") or {}
    meta = prod.get("analysis_meta") or {}
    vf = analysis.get("vocal_function_profile") or {}
    vt = vf.get("vocal_type_profile") or {}
    ev = vt.get("evidence") or {}
    q = analysis.get("quality") or public.get("quality") or {}
    metrics = q.get("metrics") or {}
    sb = vt.get("source_balance") or {}
    vt_pub = public.get("vocal_type_teaser") or {}
    finding = public.get("main_finding_teaser") or {}

    return {
        "content_sha256": _safe_get(analysis, "audio", "content_sha256")
        or _safe_get(analysis, "fingerprints", "source", "sha256")
        or meta.get("content_sha256"),
        "analysis_mode": analysis.get("analysis_mode") or meta.get("analysis_mode"),
        "input_mode": analysis.get("input_mode") or meta.get("input_mode"),
        "separation_required": analysis.get("separation_required") or meta.get("separation_required"),
        "separation_used": analysis.get("separation_used") or meta.get("separation_used"),
        "source_mode": _safe_get(analysis, "audio", "separation", "source_mode")
        or _safe_get(analysis, "audio", "source_mode"),
        "separation_status": _safe_get(analysis, "audio", "separation_status"),
        "original_duration_sec": analysis.get("original_duration_sec")
        or _safe_get(analysis, "audio", "duration_sec"),
        "score_duration_sec": _safe_get(analysis, "audio", "score_duration_sec"),
        "quality_status": q.get("status"),
        "quality_codes": q.get("codes") or [],
        "rms_dbfs": metrics.get("rms_dbfs"),
        "silent_ratio": metrics.get("silent_ratio"),
        "voiced_ratio": metrics.get("voiced_ratio"),
        "voiced_duration_sec": metrics.get("voiced_duration_sec"),
        "n_usable_segments": ev.get("n_usable_segments"),
        "evidence_mass": ev.get("mass") or ev.get("total_evidence_mass"),
        "mean_source_families": ev.get("mean_source_families"),
        "family_agreement": ev.get("family_agreement") or _safe_get(sb, "family_agreement"),
        "ratio_eligible": ev.get("ratio_eligible"),
        "balance_class": sb.get("balance_class"),
        "vocal_type": vt.get("display_name") or vt_pub.get("display_name"),
        "type_id": vt.get("type_id") or vt.get("base_type"),
        "confidence": vt.get("confidence") or vt_pub.get("confidence"),
        "resolution_state": vt.get("resolution_state") or vt_pub.get("resolution_state"),
        "main_finding_state": finding.get("state"),
        "main_finding_title": finding.get("title") or finding.get("user_title"),
    }


def compare_sample(local: dict[str, Any], prod: dict[str, Any]) -> dict[str, Any]:
    diff: dict[str, Any] = {"fields": {}, "tags": []}
    keys = [
        "content_sha256",
        "analysis_mode",
        "input_mode",
        "separation_used",
        "quality_status",
        "silent_ratio",
        "voiced_ratio",
        "rms_dbfs",
        "n_usable_segments",
        "evidence_mass",
        "family_agreement",
        "ratio_eligible",
        "resolution_state",
        "vocal_type",
        "confidence",
    ]
    for k in keys:
        lv, pv = local.get(k), prod.get(k)
        match = lv == pv
        if k == "content_sha256":
            if lv and pv:
                match = lv == pv
            elif not lv or not pv:
                match = None
        diff["fields"][k] = {"local": lv, "production": pv, "match": match}

    sha_local = local.get("content_sha256")
    sha_prod = prod.get("content_sha256")
    if sha_local and sha_prod:
        if sha_local != sha_prod:
            diff["tags"].append("UPLOAD_CONTENT_MISMATCH")
        else:
            diff["tags"].append("CONTENT_SHA_MATCH")
    else:
        diff["tags"].append("CONTENT_SHA_NOT_AVAILABLE")

    if local.get("input_mode") == prod.get("input_mode") and local.get("separation_used") == prod.get("separation_used"):
        diff["tags"].append("REQUEST_CONFIG_MATCH")
    else:
        diff["tags"].append("FRONTEND_CONFIG_MISMATCH")

    if prod.get("separation_used") is True:
        diff["tags"].append("SEPARATION_ENABLED_UNEXPECTEDLY")

    if sha_local == sha_prod and local.get("input_mode") == prod.get("input_mode"):
        if local.get("voiced_ratio", 0) > 0.5 and (prod.get("voiced_ratio") or 0) < 0.08:
            diff["tags"].append("PITCH_RUNTIME_DIFFERENCE")
            diff["tags"].append("ANALYSIS_PATH_REGRESSION")

    if local.get("resolution_state") == "RESOLVED" and prod.get("resolution_state") not in (None, "RESOLVED"):
        diff["tags"].append("COACH_ENGINE_VERSION_DIFFERENCE")

    silent = prod.get("silent_ratio")
    voiced = prod.get("voiced_ratio")
    if silent is not None and silent >= 0.9:
        diff["tags"].append("UPLOADED_AUDIO_LOW_LEVEL")
    if voiced is not None and voiced < 0.08 and (local.get("voiced_ratio") or 0) >= 0.5:
        diff["tags"].append("PITCH_DETECTION_RUNTIME_DIFFERENCE")

    return diff


def fetch_production_code_hashes(ssh_target: str, app_root: str = "/opt/vocalfb/app") -> dict[str, str]:
    joined = " ".join(f"{app_root}/{p}" for p in KEY_FILES if "miniapp" not in p)
    text = _ssh_run(ssh_target, f"sha256sum {joined} 2>/dev/null || true")
    out: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            rel = parts[1].replace(f"{app_root}/", "")
            out[rel] = parts[0]
    return out


def write_report(
    fingerprint: dict[str, Any],
    local_baseline: dict[str, Any],
    production: dict[str, Any],
    comparisons: dict[str, Any],
    code_compare: Optional[dict[str, Any]],
) -> None:
    lines = [
        "# Production vs Local Runtime Comparison",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Local fingerprint",
        "",
        f"- git HEAD: `{fingerprint['git']['head']}`",
        f"- packaged release HEAD: `{fingerprint.get('packaged_release_head')}`",
        f"- deploy lag vs local HEAD: `{fingerprint.get('deploy_lag_vs_local_head')}`",
        f"- coach profile: `{fingerprint.get('coach_profile_version')}`",
        "",
        "### AIT (local latest build)",
        "",
    ]
    ait = fingerprint.get("ait") or {}
    if ait:
        lines.extend(
            [
                f"- path: `{ait.get('path')}`",
                f"- size: {ait.get('size_bytes')}",
                f"- last_write: {ait.get('last_write_time')}",
                f"- sha256: `{ait.get('sha256')}`",
                "",
                "**MANUAL_CONFIRMATION_REQUIRED: LATEST_AIT_REGISTERED**",
                "",
                "Apps in Toss Console 테스트 버전에 위 .ait가 등록됐는지 사람이 확인해야 합니다.",
                "",
            ]
        )

    if code_compare:
        lines.extend(["## Backend code SHA256", "", "| file | local | production | match |", "|---|---|---|---|"])
        for rel, local_hash in (fingerprint.get("key_file_sha256") or {}).items():
            if "miniapp" in rel:
                continue
            prod_hash = (code_compare.get("production") or {}).get(rel)
            match = "SAME" if prod_hash and prod_hash == local_hash else ("DIFFERENT" if prod_hash else "N/A")
            lines.append(f"| {rel} | `{local_hash[:12]}…` | `{ (prod_hash or '')[:12]}…` | {match} |")
        lines.append("")

    for sid, comp in comparisons.items():
        meta = LOCAL_SAMPLES.get(sid, {})
        lines.extend([f"## {meta.get('label', sid)} ({sid})", ""])
        prod_id = (production.get(sid) or {}).get("analysis_id")
        if prod_id:
            lines.append(f"- production analysis_id: `{prod_id}`")
        local = (local_baseline.get("samples") or {}).get(sid) or {}
        prod_m = (production.get(sid) or {}).get("metrics") or {}
        lines.extend(
            [
                "",
                "| Metric | LOCAL | PRODUCTION |",
                "|---|---|---|",
            ]
        )
        for k in [
            "content_sha256",
            "analysis_mode",
            "input_mode",
            "separation_used",
            "rms_dbfs",
            "silent_ratio",
            "voiced_ratio",
            "n_usable_segments",
            "evidence_mass",
            "family_agreement",
            "ratio_eligible",
            "resolution_state",
            "vocal_type",
            "confidence",
        ]:
            lv = local.get(k)
            pv = prod_m.get(k)
            if k == "content_sha256" and isinstance(lv, str) and isinstance(pv, str):
                lv, pv = lv[:16] + "…", pv[:16] + "…"
            lines.append(f"| {k} | {lv} | {pv} |")
        tags = comp.get("tags") or []
        lines.extend(["", f"**Tags:** {', '.join(tags)}", ""])

    lines.extend(
        [
            "## Root cause hypotheses",
            "",
            "Fill after production analysis_ids are provided.",
            "",
            "| hypothesis | status |",
            "|---|---|",
            "| PRODUCTION_DEPLOY_LAG | PENDING — compare git HEAD vs packaged HEAD |",
            "| STALE_AIT_BUNDLE | PENDING — MANUAL_CONFIRMATION_REQUIRED |",
            "| FRONTEND_CONFIG_MISMATCH | check input_mode / separation_used |",
            "| UPLOAD_CONTENT_MISMATCH | check content_sha256 |",
            "| female calibration | REJECTED — not in scope |",
            "| evidence threshold change | REJECTED — audit only |",
            "",
        ]
    )

    COMPARE_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_id_mapping(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"expected sid=analysis_id, got: {item}")
        sid, aid = item.split("=", 1)
        sid, aid = sid.strip(), aid.strip()
        if sid not in LOCAL_SAMPLES:
            raise ValueError(f"unknown sample id {sid}; expected kang1|kang2|park1")
        if not aid or any(c in aid for c in r"/\ "):
            raise ValueError(f"invalid analysis_id for {sid}")
        out[sid] = aid
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare local audit vs production runtime")
    parser.add_argument("--local-only", action="store_true", help="Write local fingerprint/baseline only")
    parser.add_argument("--ssh", help="SSH target, e.g. ubuntu@LIGHTSAIL_HOST")
    parser.add_argument(
        "--runtime-root",
        default="/var/lib/vocalfb/runtime",
        help="Production runtime root on server",
    )
    parser.add_argument(
        "--prod-dir",
        type=Path,
        help="Local mirror of production runtime/<analysis_id>/ dirs",
    )
    parser.add_argument(
        "analysis_ids",
        nargs="*",
        help="Mappings: kang1=<id> kang2=<id> park1=<id>",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fingerprint = build_local_fingerprint()
    FINGERPRINT_PATH.write_text(json.dumps(fingerprint, ensure_ascii=False, indent=2), encoding="utf-8")

    local_baseline = extract_local_baseline()
    LOCAL_BASELINE_PATH.write_text(json.dumps(local_baseline, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.local_only or not args.analysis_ids:
        write_report(fingerprint, local_baseline, {}, {}, None)
        print(f"Wrote {FINGERPRINT_PATH}")
        print(f"Wrote {LOCAL_BASELINE_PATH}")
        print(f"Wrote {COMPARE_REPORT_PATH}")
        if not args.analysis_ids:
            print("\nNext: QR upload 강1→강2→박1, then rerun with:")
            print("  python scripts/compare_production_runtime.py --ssh ubuntu@HOST kang1=... kang2=... park1=...")
        return 0

    id_map = parse_id_mapping(args.analysis_ids)
    runtime_root = Path(args.runtime_root)
    production: dict[str, Any] = {}
    comparisons: dict[str, Any] = {}

    for sid, aid in id_map.items():
        raw = fetch_production_runtime(
            aid,
            ssh_target=args.ssh,
            runtime_root=runtime_root,
            prod_mirror=args.prod_dir,
        )
        metrics = extract_production_metrics(raw)
        production[sid] = {"analysis_id": aid, "raw_files": raw.get("files_found"), "metrics": metrics}
        local = (local_baseline.get("samples") or {}).get(sid) or {}
        comparisons[sid] = compare_sample(local, metrics)

    code_compare = None
    if args.ssh:
        prod_hashes = fetch_production_code_hashes(args.ssh)
        code_compare = {"production": prod_hashes}
        local_hashes = fingerprint.get("key_file_sha256") or {}
        same = all(
            prod_hashes.get(k) == local_hashes.get(k)
            for k in KEY_FILES
            if "miniapp" not in k and k in local_hashes
        )
        code_compare["backend_match"] = "SAME" if same and prod_hashes else "DIFFERENT"

    payload = {
        "fingerprint": fingerprint,
        "local_baseline": local_baseline,
        "production": production,
        "comparisons": comparisons,
        "code_compare": code_compare,
    }
    COMPARE_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(fingerprint, local_baseline, production, comparisons, code_compare)

    print(f"Wrote {COMPARE_JSON_PATH}")
    print(f"Wrote {COMPARE_REPORT_PATH}")
    for sid, comp in comparisons.items():
        tags = ", ".join(comp.get("tags") or [])
        print(f"  {sid}: {tags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
