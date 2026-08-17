"""Source + production bundle must not bake loopback API endpoints."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_frontend_api_source_has_no_loopback_endpoint():
    files = [
        ROOT / "miniapp/src/api/client.ts",
        ROOT / "miniapp/src/api/base.ts",
        ROOT / "miniapp/src/lib/reportAudio.ts",
    ]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "127.0.0.1" not in text, path
        assert "localhost" not in text.lower(), path
        assert "example.com" not in text.lower(), path


def test_production_bundle_has_no_banned_hosts():
    spec = importlib.util.spec_from_file_location(
        "check_production_bundle",
        ROOT / "scripts" / "check_production_bundle.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    dist = ROOT / "miniapp" / "dist"
    runtime_files = list(mod.iter_runtime_files(dist))
    if not dist.is_dir() or not runtime_files:
        pytest.skip("miniapp/dist not built yet")
    sources = [
        ROOT / "miniapp/src/api/client.ts",
        ROOT / "miniapp/src/api/base.ts",
        ROOT / "miniapp/src/lib/reportAudio.ts",
        ROOT / "miniapp/vite.config.ts",
    ]
    src_mtime = max(p.stat().st_mtime for p in sources if p.is_file())
    dist_mtime = max(p.stat().st_mtime for p in runtime_files)
    if dist_mtime < src_mtime:
        pytest.skip("miniapp/dist is older than API source; rebuild then rescan")
    findings = mod.scan_dist(dist)
    assert findings == [], findings
