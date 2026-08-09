"""
scripts/e2e_api_smoke.py
------------------------
Simple FastAPI E2E smoke (upload → poll → preview → delete).
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.main import app  # noqa: E402


def main() -> int:
    client = TestClient(app)
    sr = 22050
    t = np.arange(int(sr * 3.5)) / sr
    y = (0.25 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")

    r = client.post(
        "/v1/analyses",
        files={"file": ("smoke.wav", buf.getvalue(), "audio/wav")},
        data={"include_feedback": "false"},
    )
    assert r.status_code == 200, r.text
    aid = r.json()["analysis_id"]
    print("queued", aid)

    for _ in range(200):
        body = client.get(f"/v1/analyses/{aid}").json()
        if body["status"] in ("completed", "failed"):
            break
        time.sleep(0.25)
    else:
        print("TIMEOUT")
        return 1

    print("status", body["status"], "score", body.get("result", {}).get("score", {}).get("available"))
    assert body["status"] == "completed"
    blob = str(body["result"])
    assert "analysis.wav" not in blob

    prev = client.get(f"/v1/analyses/{aid}/preview")
    print("preview", prev.status_code, prev.headers.get("content-type"))
    assert prev.status_code == 200

    d = client.delete(f"/v1/analyses/{aid}")
    assert d.status_code == 200
    assert client.get(f"/v1/analyses/{aid}").status_code == 404
    print("E2E OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
