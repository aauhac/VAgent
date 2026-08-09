"""API smoke tests."""

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_rejects_bad_ext(tmp_path):
    bad = tmp_path / "x.txt"
    bad.write_text("nope", encoding="utf-8")
    with open(bad, "rb") as f:
        r = client.post(
            "/v1/analyses",
            files={"file": ("x.txt", f, "text/plain")},
        )
    assert r.status_code == 400
