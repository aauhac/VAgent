"""STEP 3 analysis execution mode: local JobRunner vs queue producer."""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.api import routes as routes_mod
from backend.app.config import get_runtime_dir, validate_analysis_execution_config
from backend.app.db.models import Analysis, Base
from backend.app.db.session import reset_engine, session_scope
from backend.app.db.users import get_or_create_user
from backend.app.jobs.queue import AnalysisJobMessage, FORBIDDEN_BODY_KEYS
from backend.app.jobs.runner import JobRunner
from backend.app.main import app
from backend.app.payments.session_tokens import issue_session
from backend.app.services.analysis_service import AnalysisService, AnalysisSubmitError, merge_queue_job_views, wire_analysis_service
from backend.app.storage.s3 import StorageUnavailableError
from backend.app.jobs.queue import QueueUnavailableError


def _wav_bytes(duration=0.4, amp=0.2, freq=220.0, sr=16000) -> bytes:
    t = np.arange(int(sr * duration)) / sr
    y = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    return buf.getvalue()


class FakeStorage:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, str]] = []
        self.deleted: list[str] = []
        self.fail_upload = False
        self.fail_delete = False

    def upload_analysis_audio(self, analysis_id, local_path, content_type=None):
        if self.fail_upload:
            raise StorageUnavailableError("upload failed")
        key = f"analyses/{analysis_id}/input{Path(local_path).suffix.lower()}"
        self.uploads.append((analysis_id, str(local_path), key))
        return key

    def delete_analysis_audio(self, object_key):
        if self.fail_delete:
            raise StorageUnavailableError("delete failed")
        self.deleted.append(object_key)

    def object_exists(self, object_key):
        return any(item[2] == object_key for item in self.uploads) and object_key not in self.deleted


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[AnalysisJobMessage] = []
        self.fail = False

    def enqueue_analysis(self, job: AnalysisJobMessage) -> str:
        if self.fail:
            raise QueueUnavailableError("enqueue failed")
        self.jobs.append(job)
        return "msg-test-1"


@pytest.fixture()
def sqlite_runtime(tmp_path, monkeypatch):
    db = tmp_path / "mode.sqlite"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("VAGENT_SESSION_SECRET", "test-session-secret-not-for-prod")
    monkeypatch.delenv("VAGENT_ANALYSIS_EXECUTION_MODE", raising=False)
    reset_engine()
    get_runtime_dir.cache_clear()
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    original_service = routes_mod.service
    yield runtime
    routes_mod.service = original_service
    reset_engine()
    get_runtime_dir.cache_clear()


def _client_for(svc: AnalysisService) -> TestClient:
    routes_mod.service = svc
    return TestClient(app, raise_server_exceptions=True)


def test_queue_mode_happy_path(sqlite_runtime):
    storage = FakeStorage()
    queue = FakeQueue()
    svc = AnalysisService(storage_service=storage, queue_service=queue, execution_mode="queue")
    svc.runtime_dir = sqlite_runtime
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    submit_calls: list[dict] = []
    svc.runner.submit = lambda **kwargs: submit_calls.append(kwargs)  # type: ignore[method-assign]
    client = _client_for(svc)
    r = client.post(
        "/v1/analyses",
        files={"file": ("tone.wav", _wav_bytes(), "audio/wav")},
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "MIXED"},
        headers={"X-VAgent-User-Key": "anon-queue-user"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    aid = body["analysis_id"]
    assert len(storage.uploads) == 1
    assert storage.uploads[0][0] == aid
    assert storage.uploads[0][2] == f"analyses/{aid}/input.wav"
    assert len(queue.jobs) == 1
    assert submit_calls == []
    with session_scope() as session:
        row = session.get(Analysis, aid)
        assert row is not None
        assert row.status == "queued"
        assert row.stage == "queued"
        assert row.progress == 0
        assert row.audio_storage_key == f"analyses/{aid}/input.wav"
        assert row.analysis_mode == "FUNCTIONAL"
        assert row.input_mode == "MIXED"
    job = svc.get_job(aid)
    assert job is not None
    assert job["status"] == "queued"


def test_local_mode_uses_job_runner_not_s3_or_sqs(sqlite_runtime):
    storage = FakeStorage()
    queue = FakeQueue()
    svc = AnalysisService(storage_service=storage, queue_service=queue, execution_mode="local")
    svc.runtime_dir = sqlite_runtime
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    submit_calls: list[dict] = []
    svc.runner.submit = lambda **kwargs: submit_calls.append(kwargs)  # type: ignore[method-assign]
    client = _client_for(svc)
    r = client.post(
        "/v1/analyses",
        files={"file": ("tone.wav", _wav_bytes(), "audio/wav")},
    )
    assert r.status_code == 200
    aid = r.json()["analysis_id"]
    assert len(submit_calls) == 1
    assert submit_calls[0]["analysis_id"] == aid
    assert storage.uploads == []
    assert queue.jobs == []
    local_upload = sqlite_runtime / aid / "upload.wav"
    assert local_upload.is_file()
    with session_scope() as session:
        row = session.get(Analysis, aid)
        assert row is not None
        assert row.audio_storage_key == f"{aid}/upload.wav"


def test_s3_upload_failure_does_not_enqueue_or_run_local(sqlite_runtime):
    storage = FakeStorage()
    storage.fail_upload = True
    queue = FakeQueue()
    svc = AnalysisService(storage_service=storage, queue_service=queue, execution_mode="queue")
    svc.runtime_dir = sqlite_runtime
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    submit_calls: list[dict] = []
    svc.runner.submit = lambda **kwargs: submit_calls.append(kwargs)  # type: ignore[method-assign]
    client = _client_for(svc)
    r = client.post(
        "/v1/analyses",
        files={"file": ("tone.wav", _wav_bytes(), "audio/wav")},
        headers={"X-VAgent-User-Key": "anon-queue-user"},
    )
    assert r.status_code == 503
    assert queue.jobs == []
    assert submit_calls == []
    with session_scope() as session:
        rows = list(session.scalars(select(Analysis)))
        assert rows
        assert all(row.status != "queued" or row.error_code for row in rows)
        assert any(row.status == "failed" and row.error_code == "STORAGE_UPLOAD_FAILED" for row in rows)


def test_sqs_enqueue_failure_does_not_fallback_to_job_runner(sqlite_runtime):
    storage = FakeStorage()
    queue = FakeQueue()
    queue.fail = True
    svc = AnalysisService(storage_service=storage, queue_service=queue, execution_mode="queue")
    svc.runtime_dir = sqlite_runtime
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    submit_calls: list[dict] = []
    svc.runner.submit = lambda **kwargs: submit_calls.append(kwargs)  # type: ignore[method-assign]
    client = _client_for(svc)
    r = client.post(
        "/v1/analyses",
        files={"file": ("tone.wav", _wav_bytes(), "audio/wav")},
        headers={"X-VAgent-User-Key": "anon-queue-user"},
    )
    assert r.status_code == 503
    assert len(storage.uploads) == 1
    assert queue.jobs == []
    assert submit_calls == []
    with session_scope() as session:
        rows = list(session.scalars(select(Analysis)))
        assert any(row.status == "failed" and row.error_code == "ENQUEUE_FAILED" for row in rows)
        failed = next(row for row in rows if row.error_code == "ENQUEUE_FAILED")
        assert failed.audio_storage_key == storage.uploads[0][2]


def test_queue_message_fields_and_no_secrets(sqlite_runtime):
    storage = FakeStorage()
    queue = FakeQueue()
    svc = AnalysisService(storage_service=storage, queue_service=queue, execution_mode="queue")
    svc.runtime_dir = sqlite_runtime
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    client = _client_for(svc)
    r = client.post(
        "/v1/analyses",
        files={"file": ("tone.wav", _wav_bytes(), "audio/wav")},
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "VOCAL_ONLY"},
        headers={"X-VAgent-User-Key": "should-not-appear-in-message"},
    )
    assert r.status_code == 200
    job = queue.jobs[0]
    payload = job.to_dict()
    assert payload["analysis_id"] == r.json()["analysis_id"]
    assert payload["audio_key"] == f"analyses/{payload['analysis_id']}/input.wav"
    assert payload["analysis_mode"] == "FUNCTIONAL"
    assert payload["input_mode"] == "VOCAL_ONLY"
    assert payload["include_feedback"] is False
    assert payload["schema_version"] == 1
    for key in FORBIDDEN_BODY_KEYS:
        assert key not in payload
    dumped = job.to_json()
    assert "should-not-appear-in-message" not in dumped
    assert "Bearer" not in dumped
    assert "aws_" not in dumped


def test_anonymous_queue_submission_keeps_owner_meta(sqlite_runtime):
    storage = FakeStorage()
    queue = FakeQueue()
    svc = AnalysisService(storage_service=storage, queue_service=queue, execution_mode="queue")
    svc.runtime_dir = sqlite_runtime
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    client = _client_for(svc)
    r = client.post(
        "/v1/analyses",
        files={"file": ("tone.wav", _wav_bytes(), "audio/wav")},
        headers={"X-VAgent-User-Key": "anon-subject-1"},
    )
    assert r.status_code == 200
    aid = r.json()["analysis_id"]
    meta = (sqlite_runtime / aid / "analysis_meta.json").read_text(encoding="utf-8")
    assert "anon-subject-1" in meta
    poll = client.get(f"/v1/analyses/{aid}", headers={"X-VAgent-User-Key": "anon-subject-1"})
    assert poll.status_code == 200
    assert poll.json()["status"] == "queued"
    denied = client.get(f"/v1/analyses/{aid}", headers={"X-VAgent-User-Key": "other-user"})
    assert denied.status_code == 404


def test_authenticated_queue_submission_keeps_toss_owner(sqlite_runtime):
    storage = FakeStorage()
    queue = FakeQueue()
    svc = AnalysisService(storage_service=storage, queue_service=queue, execution_mode="queue")
    svc.runtime_dir = sqlite_runtime
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    client = _client_for(svc)
    token, session = issue_session(toss_user_key="toss-user-queue")
    r = client.post(
        "/v1/analyses",
        files={"file": ("tone.wav", _wav_bytes(), "audio/wav")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    aid = r.json()["analysis_id"]
    with session_scope() as db:
        row = db.get(Analysis, aid)
        assert row is not None
        assert str(row.user_id)
    poll = client.get(f"/v1/analyses/{aid}", headers={"Authorization": f"Bearer {token}"})
    assert poll.status_code == 200
    assert session.subject == "toss-user-queue"


def test_s3_backed_delete_does_not_treat_key_as_local_path(sqlite_runtime):
    storage = FakeStorage()
    queue = FakeQueue()
    svc = AnalysisService(storage_service=storage, queue_service=queue, execution_mode="queue")
    svc.runtime_dir = sqlite_runtime
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    client = _client_for(svc)
    r = client.post(
        "/v1/analyses",
        files={"file": ("tone.wav", _wav_bytes(), "audio/wav")},
        headers={"X-VAgent-User-Key": "owner-del"},
    )
    aid = r.json()["analysis_id"]
    s3_key = f"analyses/{aid}/input.wav"
    analyses_dir = sqlite_runtime / "analyses" / aid
    analyses_dir.mkdir(parents=True, exist_ok=True)
    (analyses_dir / "input.wav").write_bytes(b"should-not-be-used-as-delete-root")
    ok = svc.delete_job(aid)
    assert ok is True
    assert s3_key in storage.deleted
    assert analyses_dir.exists()
    assert not (sqlite_runtime / aid).exists()


def test_queue_mode_missing_env_fail_fast(monkeypatch):
    monkeypatch.setenv("VAGENT_ANALYSIS_EXECUTION_MODE", "queue")
    monkeypatch.delenv("VAGENT_S3_BUCKET", raising=False)
    monkeypatch.delenv("VAGENT_ANALYSIS_QUEUE_URL", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert validate_analysis_execution_config()
    with pytest.raises(RuntimeError, match="queue mode not ready"):
        wire_analysis_service()
    svc = AnalysisService(execution_mode="queue")
    assert svc.storage_service is None
    assert svc.queue_service is None


def test_local_mode_allows_boot_without_aws_env(monkeypatch):
    monkeypatch.setenv("VAGENT_ANALYSIS_EXECUTION_MODE", "local")
    monkeypatch.delenv("VAGENT_S3_BUCKET", raising=False)
    monkeypatch.delenv("VAGENT_ANALYSIS_QUEUE_URL", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    assert validate_analysis_execution_config() == []
    svc = wire_analysis_service()
    assert svc.execution_mode == "local"
    assert svc.storage_service is None
    assert svc.queue_service is None


def test_invalid_execution_mode_does_not_fallback_to_local(monkeypatch):
    monkeypatch.setenv("VAGENT_ANALYSIS_EXECUTION_MODE", "queu")
    with pytest.raises(RuntimeError, match="invalid"):
        wire_analysis_service()
    from backend.app.main import _on_startup

    with pytest.raises(RuntimeError, match="execution mode not ready"):
        _on_startup()


def _queue_service(runtime: Path) -> AnalysisService:
    svc = AnalysisService(storage_service=FakeStorage(), queue_service=FakeQueue(), execution_mode="queue")
    svc.runtime_dir = runtime
    svc.runner = JobRunner(runtime, max_workers=1)
    return svc


def _seed_analysis(
    aid: str,
    *,
    subject: str,
    status: str,
    stage: str | None = None,
    progress: int | None = None,
    error: str | None = None,
) -> None:
    with session_scope() as session:
        user = get_or_create_user(session, provider="DEV", subject=subject)
        session.add(
            Analysis(
                id=aid,
                user_id=user.id,
                status=status,
                stage=stage,
                progress=progress,
                analysis_mode="FUNCTIONAL",
                input_mode="MIXED",
                error_message=error,
            )
        )


def _write_job_status(runtime: Path, aid: str, payload: dict) -> None:
    folder = runtime / aid
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "job_status.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_queue_get_job_merges_db_completed_with_disk_result(sqlite_runtime):
    aid = uuid.uuid4().hex
    result = {"vocal_type_teaser": {"label": "mix"}, "score": {"overall": 72}}
    _seed_analysis(aid, subject="anon-queue-get", status="completed", stage="done", progress=100)
    _write_job_status(
        sqlite_runtime,
        aid,
        {
            "analysis_id": aid,
            "status": "completed",
            "stage": "done",
            "progress": 100,
            "result": result,
            "analysis_status": "completed",
            "feedback_status": "skipped",
        },
    )
    svc = _queue_service(sqlite_runtime)
    job = svc.get_job(aid)
    assert job is not None
    assert job["status"] == "completed"
    assert job["result"] == result
    assert job["feedback_status"] == "skipped"


def test_queue_get_http_returns_disk_result(sqlite_runtime):
    aid = uuid.uuid4().hex
    subject = "anon-queue-http"
    result = {"vocal_type_teaser": {"label": "mix"}, "physiology_assessments": [{"x": 1}]}
    _seed_analysis(aid, subject=subject, status="completed", stage="done", progress=100)
    _write_job_status(
        sqlite_runtime,
        aid,
        {
            "analysis_id": aid,
            "status": "completed",
            "stage": "done",
            "progress": 100,
            "result": result,
        },
    )
    (sqlite_runtime / aid / "public_result.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8"
    )
    svc = _queue_service(sqlite_runtime)
    client = _client_for(svc)
    r = client.get(f"/v1/analyses/{aid}", headers={"X-VAgent-User-Key": subject})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert isinstance(body["result"], dict)
    assert body["result"]["vocal_type_teaser"]["label"] == "mix"
    assert "physiology_assessments" not in body["result"]


def test_queue_get_job_ignores_stale_api_memory(sqlite_runtime):
    aid = uuid.uuid4().hex
    result = {"ok": True, "label": "from-disk"}
    _seed_analysis(aid, subject="anon-stale", status="completed", stage="done", progress=100)
    _write_job_status(
        sqlite_runtime,
        aid,
        {
            "analysis_id": aid,
            "status": "completed",
            "stage": "done",
            "progress": 100,
            "result": result,
        },
    )
    svc = _queue_service(sqlite_runtime)
    svc.runner.remember_queued(analysis_id=aid, analysis_mode="FUNCTIONAL", input_mode="MIXED")
    mem = svc.runner.get(aid)
    assert mem is not None
    assert mem["status"] == "queued"
    assert mem.get("result") is None
    job = svc.get_job(aid)
    assert job["status"] == "completed"
    assert job["result"] == result


def test_queue_get_job_db_analyzing_beats_stale_disk_queued(sqlite_runtime):
    aid = uuid.uuid4().hex
    _seed_analysis(aid, subject="anon-analyzing", status="analyzing", stage="start", progress=1)
    _write_job_status(
        sqlite_runtime,
        aid,
        {
            "analysis_id": aid,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "result": None,
        },
    )
    svc = _queue_service(sqlite_runtime)
    job = svc.get_job(aid)
    assert job["status"] == "analyzing"
    assert job["stage"] == "start"
    assert job["progress"] == 1
    assert job["result"] is None
    disk = json.loads((sqlite_runtime / aid / "job_status.json").read_text(encoding="utf-8"))
    assert disk["status"] == "queued"


def test_queue_get_job_db_failed_not_overridden_by_stale_disk_completed(sqlite_runtime):
    aid = uuid.uuid4().hex
    _seed_analysis(
        aid,
        subject="anon-failed",
        status="failed",
        stage="error",
        progress=100,
        error="ANALYZER_FAILED",
    )
    _write_job_status(
        sqlite_runtime,
        aid,
        {
            "analysis_id": aid,
            "status": "completed",
            "stage": "done",
            "progress": 100,
            "result": {"should_not_win": True},
        },
    )
    svc = _queue_service(sqlite_runtime)
    job = svc.get_job(aid)
    assert job["status"] == "failed"
    assert job["error"] == "ANALYZER_FAILED"
    assert job["result"] is None


def test_local_mode_get_job_still_prefers_memory(sqlite_runtime):
    aid = uuid.uuid4().hex
    svc = AnalysisService(execution_mode="local")
    svc.runtime_dir = sqlite_runtime
    svc.runner = JobRunner(sqlite_runtime, max_workers=1)
    svc.runner.remember_queued(analysis_id=aid, analysis_mode="QUICK", input_mode="AUTO")
    _write_job_status(
        sqlite_runtime,
        aid,
        {
            "analysis_id": aid,
            "status": "completed",
            "stage": "done",
            "progress": 100,
            "result": {"from_disk": True},
        },
    )
    job = svc.get_job(aid)
    assert job["status"] == "queued"
    assert job.get("result") is None


def test_queue_get_missing_analysis_is_none_and_http_404(sqlite_runtime):
    svc = _queue_service(sqlite_runtime)
    missing = "a" * 32
    assert svc.get_job(missing) is None
    client = _client_for(svc)
    r = client.get(f"/v1/analyses/{missing}", headers={"X-VAgent-User-Key": "anon-missing"})
    assert r.status_code == 404


def test_merge_queue_job_views_disk_only_and_db_only():
    disk = {"analysis_id": "a" * 32, "status": "completed", "result": {"x": 1}}
    assert merge_queue_job_views(None, disk)["result"] == {"x": 1}
    db = {"analysis_id": "a" * 32, "status": "queued", "result": None, "stage": "queued"}
    assert merge_queue_job_views(db, None)["status"] == "queued"
    assert merge_queue_job_views(None, None) is None
