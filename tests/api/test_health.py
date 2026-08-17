"""API smoke tests."""

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "vocalfb"
    assert "database" not in body


def test_ready_does_not_require_toss():
    r = client.get("/ready")
    assert r.status_code in (200, 503)
    body = r.json()
    assert "ready" in body
    assert "database" in body
    assert "payments" in body
    assert body.get("multi_instance_safe") is False


def test_create_rejects_bad_ext(tmp_path):
    bad = tmp_path / "x.txt"
    bad.write_text("nope", encoding="utf-8")
    with open(bad, "rb") as f:
        r = client.post(
            "/v1/analyses",
            files={"file": ("x.txt", f, "text/plain")},
        )
    assert r.status_code == 400
