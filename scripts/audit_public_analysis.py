#!/usr/bin/env python3
"""Safe public-result audit for a single analysis_id. No PII / audio / full dump."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_public(analysis_id: str) -> dict:
    from backend.app.config import get_runtime_dir

    base = get_runtime_dir() / analysis_id
    pub_path = base / "public_result.json"
    if pub_path.exists():
        data = json.loads(pub_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    job_path = base / "job_status.json"
    if job_path.exists():
        job = json.loads(job_path.read_text(encoding="utf-8"))
        result = job.get("result") if isinstance(job, dict) else None
        return result if isinstance(result, dict) else {}
    raise FileNotFoundError(analysis_id)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/audit_public_analysis.py <analysis_id>", file=sys.stderr)
        return 2
    analysis_id = sys.argv[1].strip()
    if not analysis_id or any(ch in analysis_id for ch in r"/\ "):
        print("invalid analysis_id", file=sys.stderr)
        return 2
    try:
        pub = _load_public(analysis_id)
    except FileNotFoundError:
        print(f"analysis_id={analysis_id}")
        print("status=NOT_FOUND")
        return 1
    quality = pub.get("quality") or {}
    metrics = quality.get("metrics") or {}
    score = pub.get("score") or {}
    vt = pub.get("vocal_type_teaser") or {}
    sb = vt.get("source_balance") or {}
    finding = pub.get("main_finding_teaser") or {}
    vf = pub.get("vocal_function_teaser")
    print(f"analysis_id={analysis_id}")
    print(f"quality.status={quality.get('status')}")
    print(f"quality.voiced_ratio={metrics.get('voiced_ratio')}")
    print(f"quality.voiced_duration_sec={metrics.get('voiced_duration_sec')}")
    print(f"score.available={score.get('available')}")
    print(f"score.reliable_axis_count={score.get('reliable_axis_count')}")
    print(f"vocal_type_teaser.available={vt.get('available')}")
    print(f"vocal_type_teaser.confidence={vt.get('confidence')}")
    print(f"vocal_type_teaser.resolution_state={vt.get('resolution_state')}")
    print(f"source_balance.balance_class={sb.get('balance_class')}")
    print(f"main_finding_teaser.state={finding.get('state')}")
    print(f"main_finding_teaser.id={finding.get('id')}")
    print(f"main_finding_teaser.title={finding.get('title') or finding.get('user_title')}")
    print(f"vocal_function_teaser.present={bool(vf)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
