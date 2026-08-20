"""SQS worker tests with fake S3/SQS. No live AWS. No JobRunner fallback."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.db.analysis_repo import get_analysis_snapshot
from backend.app.db.models import Analysis, Base
from backend.app.db.session import reset_engine, session_scope
from backend.app.db.users import get_or_create_user
from backend.app.jobs.processor import AnalysisJobProcessor, ProcessOutcome
from backend.app.jobs.queue import AnalysisJobMessage, QueueUnavailableError, ReceivedAnalysisJob, utc_now_iso
from backend.app.jobs.runner import JobRunner
from backend.app.jobs.worker import CONCURRENCY, AnalysisWorker
from backend.app.storage.s3 import StorageUnavailableError


AID = "c7045e107d714b64880a468748b1f8b7"
KEY = f"analyses/{AID}/input.m4a"


class FakeStorage:
    def __init__(self) -> None:
        self.downloaded: list[tuple[str, str]] = []
        self.objects: dict[str, bytes] = {KEY: b"audio-bytes"}
        self.fail = False

    def download_analysis_audio(self, object_key: str, destination: Path) -> Path:
        if self.fail:
            raise StorageUnavailableError("s3 unavailable")
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.objects.get(object_key, b"audio-bytes"))
        self.downloaded.append((object_key, str(dest)))
        return dest


class FakeQueue:
    def __init__(self) -> None:
        self.pending: list[ReceivedAnalysisJob] = []
        self.deleted: list[str] = []
        self.visibility: list[tuple[str, int]] = []
        self.receive_kwargs: list[dict] = []
        self.delete_fail_once = False
        self.delete_always_fail = False

    def receive_analysis_jobs(self, max_messages=1, wait_time_seconds=20, visibility_timeout=600):
        self.receive_kwargs.append(
            {
                "max_messages": max_messages,
                "wait_time_seconds": wait_time_seconds,
                "visibility_timeout": visibility_timeout,
            }
        )
        if not self.pending:
            return []
        return [self.pending.pop(0)]

    def delete_message(self, receipt_handle: str) -> None:
        if self.delete_fail_once:
            self.delete_fail_once = False
            raise QueueUnavailableError("delete failed")
        if self.delete_always_fail:
            raise QueueUnavailableError("delete failed")
        self.deleted.append(receipt_handle)

    def change_visibility(self, receipt_handle: str, timeout_seconds: int) -> None:
        self.visibility.append((receipt_handle, int(timeout_seconds)))


class FakeProcessor:
    def __init__(self, *, delay: float = 0, fail: bool = False) -> None:
        self.calls: list[dict] = []
        self.delay = delay
        self.fail = fail

    def process(self, **kwargs):
        self.calls.append(kwargs)
        if self.delay:
            time.sleep(self.delay)
        on_update = kwargs["on_update"]
        analysis_id = kwargs["analysis_id"]
        if self.fail:
            on_update(
                analysis_id,
                status="failed",
                stage="error",
                progress=100,
                error="boom",
                error_code="ANALYZER_FAILED",
            )
            return ProcessOutcome(ok=False, status="failed", error="boom", error_code="ANALYZER_FAILED")
        on_update(analysis_id, status="completed", stage="done", progress=100)
        return ProcessOutcome(ok=True, status="completed")


def _job(**overrides) -> AnalysisJobMessage:
    payload = dict(
        schema_version=1,
        analysis_id=AID,
        audio_key=KEY,
        analysis_mode="FUNCTIONAL",
        input_mode="MIXED",
        created_at=utc_now_iso(),
        include_feedback=False,
    )
    payload.update(overrides)
    return AnalysisJobMessage(**payload)


def _received(job: AnalysisJobMessage | None = None, handle: str = "rh-1") -> ReceivedAnalysisJob:
    return ReceivedAnalysisJob(
        job=job or _job(),
        receipt_handle=handle,
        message_id="msg-1",
        approximate_receive_count=1,
    )


@pytest.fixture()
def worker_env(tmp_path, monkeypatch):
    db = tmp_path / "worker.sqlite"
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    runtime.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("WORKER_RUNTIME_DIR", str(workspace))
    reset_engine()
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    with session_scope() as session:
        user = get_or_create_user(session, provider="DEV", subject="anon-worker")
        user_id = user.id
        session.add(
            Analysis(
                id=AID,
                user_id=user.id,
                status="queued",
                stage="queued",
                progress=0,
                analysis_mode="FUNCTIONAL",
                input_mode="MIXED",
                separate=True,
                audio_storage_key=KEY,
                worker_attempt_count=0,
            )
        )
    yield {"runtime": runtime, "workspace": workspace, "user_id": user_id}
    reset_engine()


def _worker(env, storage=None, queue=None, processor=None, heartbeat_seconds=120) -> AnalysisWorker:
    return AnalysisWorker(
        storage_service=storage or FakeStorage(),
        queue_service=queue or FakeQueue(),
        processor=processor or FakeProcessor(),
        runtime_dir=env["runtime"],
        workspace_dir=env["workspace"],
        visibility_timeout=600,
        heartbeat_seconds=heartbeat_seconds,
        lease_seconds=600,
        wait_time_seconds=0,
    )


def test_worker_receives_one_job(worker_env):
    queue = FakeQueue()
    processor = FakeProcessor()
    worker = _worker(worker_env, queue=queue, processor=processor)
    worker.process_received(_received())
    worker.queue.receive_analysis_jobs(
        max_messages=CONCURRENCY, wait_time_seconds=0, visibility_timeout=600
    )
    assert worker.queue.receive_kwargs[0]["max_messages"] == 1
    snap = get_analysis_snapshot(AID)
    assert snap["status"] == "completed"
    assert queue.deleted == ["rh-1"]
    assert len(processor.calls) == 1


def test_worker_max_receive_is_one(worker_env):
    queue = FakeQueue()
    worker = _worker(worker_env, queue=queue, processor=FakeProcessor())
    original = worker.queue.receive_analysis_jobs

    def receive(**kwargs):
        worker.request_shutdown()
        return original(**kwargs)

    worker.queue.receive_analysis_jobs = receive  # type: ignore[method-assign]
    worker.run_forever()
    assert queue.receive_kwargs
    assert all(item["max_messages"] == 1 for item in queue.receive_kwargs)


def test_s3_download_to_workspace(worker_env):
    storage = FakeStorage()
    processor = FakeProcessor()
    worker = _worker(worker_env, storage=storage, processor=processor)
    worker.process_received(_received())
    assert storage.downloaded
    assert Path(storage.downloaded[0][1]).name == "input.m4a"
    assert AID in storage.downloaded[0][1]


def test_canonical_audio_key_rejected(worker_env):
    with session_scope() as session:
        row = session.get(Analysis, AID)
        row.audio_storage_key = f"{AID}/upload.m4a"
    processor = FakeProcessor()
    queue = FakeQueue()
    worker = _worker(worker_env, queue=queue, processor=processor)
    job = SimpleNamespace(
        analysis_id=AID,
        audio_key=f"{AID}/upload.m4a",
        analysis_mode="FUNCTIONAL",
        input_mode="MIXED",
        include_feedback=False,
    )
    worker.process_received(
        ReceivedAnalysisJob(job=job, receipt_handle="rh-bad", message_id="m", approximate_receive_count=1)
    )
    assert processor.calls == []
    snap = get_analysis_snapshot(AID)
    assert snap["status"] == "failed"
    assert snap["error_code"] == "INVALID_AUDIO_KEY"
    assert queue.deleted == ["rh-bad"]


def test_message_audio_key_mismatch_rejected(worker_env):
    other = "a" * 32
    processor = FakeProcessor()
    queue = FakeQueue()
    worker = _worker(worker_env, queue=queue, processor=processor)
    job = SimpleNamespace(
        analysis_id=AID,
        audio_key=f"analyses/{other}/input.m4a",
        analysis_mode="FUNCTIONAL",
        input_mode="MIXED",
        include_feedback=False,
    )
    worker.process_received(
        ReceivedAnalysisJob(job=job, receipt_handle="rh-mis", message_id="m", approximate_receive_count=1)
    )
    assert processor.calls == []
    snap = get_analysis_snapshot(AID)
    assert snap["status"] == "failed"
    assert snap["error_code"] == "AUDIO_KEY_MISMATCH"
    assert queue.deleted == ["rh-mis"]


def test_active_lease_skips_process(worker_env):
    from backend.app.db.analysis_repo import claim_analysis_job

    claim_analysis_job(AID, claim_token="owner", lease_seconds=600)
    processor = FakeProcessor()
    queue = FakeQueue()
    worker = _worker(worker_env, queue=queue, processor=processor)
    worker.process_received(_received(handle="rh-active"))
    assert processor.calls == []
    assert queue.deleted == []
    assert queue.visibility
    snap = get_analysis_snapshot(AID)
    assert snap["worker_claim_token"] == "owner"


def test_expired_lease_reclaim_processes(worker_env):
    from backend.app.db.analysis_repo import claim_analysis_job

    claim_analysis_job(AID, claim_token="owner", lease_seconds=600)
    past = datetime.now(timezone.utc) - timedelta(seconds=60)
    with session_scope() as session:
        row = session.get(Analysis, AID)
        row.worker_lease_expires_at = past
    processor = FakeProcessor()
    queue = FakeQueue()
    worker = _worker(worker_env, queue=queue, processor=processor)
    worker.process_received(_received(handle="rh-reclaim"))
    assert len(processor.calls) == 1
    snap = get_analysis_snapshot(AID)
    assert snap["status"] == "completed"
    assert queue.deleted == ["rh-reclaim"]


def test_duplicate_messages_process_once(worker_env):
    processor = FakeProcessor()
    queue = FakeQueue()
    worker = _worker(worker_env, queue=queue, processor=processor)
    worker.process_received(_received(handle="rh-a"))
    worker.process_received(_received(handle="rh-b"))
    assert len(processor.calls) == 1
    snap = get_analysis_snapshot(AID)
    assert snap["status"] == "completed"
    assert queue.deleted == ["rh-a", "rh-b"]


def test_heartbeat_changes_visibility_and_extends_lease(worker_env):
    processor = FakeProcessor(delay=0.25)
    queue = FakeQueue()
    worker = _worker(worker_env, queue=queue, processor=processor, heartbeat_seconds=0.08)
    worker.process_received(_received())
    assert worker.last_heartbeat is not None
    assert worker.last_heartbeat.visibility_calls >= 1
    assert worker.last_heartbeat.lease_calls >= 1
    assert any(item[1] == 600 for item in queue.visibility)


def test_heartbeat_failure_does_not_kill_job(worker_env):
    class BoomQueue(FakeQueue):
        def change_visibility(self, receipt_handle, timeout_seconds):
            raise QueueUnavailableError("vis failed")

    processor = FakeProcessor(delay=0.2)
    queue = BoomQueue()
    worker = _worker(worker_env, queue=queue, processor=processor, heartbeat_seconds=0.08)
    worker.process_received(_received())
    snap = get_analysis_snapshot(AID)
    assert snap["status"] == "completed"
    assert processor.calls


def test_success_completes_db_then_deletes(worker_env):
    processor = FakeProcessor()
    queue = FakeQueue()
    worker = _worker(worker_env, queue=queue, processor=processor)
    worker.process_received(_received())
    snap = get_analysis_snapshot(AID)
    assert snap["status"] == "completed"
    assert queue.deleted == ["rh-1"]
    assert len(processor.calls) == 1


def test_completed_then_delete_failure_redelivery_does_not_reprocess(worker_env):
    processor = FakeProcessor()
    queue = FakeQueue()
    queue.delete_fail_once = True
    worker = _worker(worker_env, queue=queue, processor=processor)
    worker.process_received(_received(handle="rh-1"))
    assert get_analysis_snapshot(AID)["status"] == "completed"
    assert queue.deleted == []
    assert len(processor.calls) == 1
    worker.process_received(_received(handle="rh-1"))
    assert len(processor.calls) == 1
    assert queue.deleted == ["rh-1"]


def test_retryable_s3_error_does_not_delete_or_fallback(worker_env, monkeypatch):
    submits: list[int] = []
    monkeypatch.setattr(JobRunner, "submit", lambda *a, **k: submits.append(1))
    storage = FakeStorage()
    storage.fail = True
    processor = FakeProcessor()
    queue = FakeQueue()
    worker = _worker(worker_env, storage=storage, queue=queue, processor=processor)
    worker.process_received(_received())
    assert processor.calls == []
    assert queue.deleted == []
    assert submits == []
    snap = get_analysis_snapshot(AID)
    assert snap["status"] == "queued"
    assert snap["worker_claim_token"] is None
    assert snap["worker_lease_expires_at"] is None
    assert ("rh-1", 60) in queue.visibility


def test_retryable_visibility_change_failure_does_not_delete(worker_env):
    class BoomVisibilityQueue(FakeQueue):
        def change_visibility(self, receipt_handle, timeout_seconds):
            self.visibility.append((receipt_handle, int(timeout_seconds)))
            raise QueueUnavailableError("vis failed")

    storage = FakeStorage()
    storage.fail = True
    queue = BoomVisibilityQueue()
    worker = _worker(worker_env, storage=storage, queue=queue, processor=FakeProcessor())
    worker.process_received(_received())
    snap = get_analysis_snapshot(AID)
    assert snap["status"] == "queued"
    assert snap["worker_claim_token"] is None
    assert snap["worker_lease_expires_at"] is None
    assert queue.deleted == []
    assert ("rh-1", 60) in queue.visibility


def test_terminal_analyzer_failure_deletes_message(worker_env):
    processor = FakeProcessor(fail=True)
    queue = FakeQueue()
    worker = _worker(worker_env, queue=queue, processor=processor)
    worker.process_received(_received())
    snap = get_analysis_snapshot(AID)
    assert snap["status"] == "failed"
    assert queue.deleted == ["rh-1"]


def test_temp_workspace_cleanup(worker_env):
    storage = FakeStorage()
    worker = _worker(worker_env, storage=storage, processor=FakeProcessor())
    worker.process_received(_received())
    leftover = list(Path(worker_env["workspace"]).glob("**/*"))
    assert leftover == []


def test_idle_shutdown(worker_env):
    queue = FakeQueue()
    worker = _worker(worker_env, queue=queue, processor=FakeProcessor())

    def receive(**kwargs):
        worker.request_shutdown()
        return []

    worker.queue.receive_analysis_jobs = receive  # type: ignore[method-assign]
    worker.run_forever()


def test_local_and_queue_share_processor_class():
    runner = JobRunner(Path("."), max_workers=1)
    assert isinstance(runner.processor, AnalysisJobProcessor)


def test_job_runner_delegates_to_processor(tmp_path):
    runner = JobRunner(tmp_path, max_workers=1)
    calls: list[dict] = []

    def fake_process(**kwargs):
        calls.append(kwargs)
        return ProcessOutcome(ok=True, status="completed")

    runner.processor.process = fake_process  # type: ignore[method-assign]
    aid = "b" * 32
    runner._run(aid, str(tmp_path / "x.wav"), False, False, "QUICK", "AUTO")
    assert len(calls) == 1
    assert calls[0]["analysis_id"] == aid
    assert calls[0]["notify"] is True


def test_ownership_unchanged_after_worker(worker_env):
    owner = worker_env["user_id"]
    worker = _worker(worker_env, processor=FakeProcessor())
    worker.process_received(_received())
    with session_scope() as session:
        row = session.get(Analysis, AID)
        assert row.user_id == owner


def test_completed_redelivery_does_not_notify(worker_env, monkeypatch):
    sends: list[str] = []

    def fake_send(analysis_id, runtime_dir=None):
        sends.append(analysis_id)

    monkeypatch.setattr("backend.app.notifications.completion.send_if_requested", fake_send)
    monkeypatch.setattr(
        "backend.app.jobs.processor.analyze_audio",
        lambda **kwargs: {"analysis_status": "completed", "feedback_status": "skipped"},
    )
    monkeypatch.setattr("backend.app.jobs.processor.public_result", lambda result: {"ok": True})
    processor = AnalysisJobProcessor(worker_env["runtime"])
    worker = _worker(worker_env, processor=processor)
    worker.process_received(_received(handle="rh-1"))
    assert sends == [AID]
    worker.process_received(_received(handle="rh-2"))
    assert sends == [AID]


def test_worker_source_has_no_jobrunner_fallback():
    text = Path(__file__).resolve().parents[2] / "backend" / "app" / "jobs" / "worker.py"
    source = text.read_text(encoding="utf-8")
    assert "JobRunner(" not in source
    assert ".submit(" not in source
    assert "CONCURRENCY = 1" in source
