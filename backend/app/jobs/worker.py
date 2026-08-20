"""
SQS analysis worker — one process, concurrency 1.

python -m backend.app.jobs.worker
"""

from __future__ import annotations

import logging
import shutil
import signal
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from audio_analyzer.env_utils import load_dotenv_if_available

from ..jobs.queue import InvalidAnalysisJobError, QueueUnavailableError
from ..jobs.runner import validate_analysis_id
from ..storage.s3 import (
    StorageObjectNotFoundError,
    StorageUnavailableError,
    is_analysis_audio_object_key,
    parse_analysis_audio_key,
)

load_dotenv_if_available()

logger = logging.getLogger("vagent.jobs.worker")

CONCURRENCY = 1
TERMINAL_STATUSES = frozenset({"completed", "failed", "deleted"})


class RetryableWorkerError(Exception):
    """Infrastructure error — do not delete the SQS message."""


class TerminalWorkerError(Exception):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class VisibilityHeartbeat:
    def __init__(
        self,
        *,
        change_visibility: Callable[[str, int], None],
        extend_lease: Callable[[], None],
        receipt_handle: str,
        visibility_timeout: int,
        interval_seconds: float,
    ) -> None:
        self._change_visibility = change_visibility
        self._extend_lease = extend_lease
        self._receipt_handle = receipt_handle
        self._visibility_timeout = visibility_timeout
        self._interval = max(0.05, float(interval_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.visibility_calls = 0
        self.lease_calls = 0
        self.failures = 0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="sqs-heartbeat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._change_visibility(self._receipt_handle, self._visibility_timeout)
                self.visibility_calls += 1
            except Exception:
                self.failures += 1
                logger.warning("[WORKER] heartbeat_visibility_failed")
            try:
                self._extend_lease()
                self.lease_calls += 1
            except Exception:
                self.failures += 1
                logger.warning("[WORKER] heartbeat_lease_failed")


class AnalysisWorker:
    """Long-poll SQS and run AnalysisJobProcessor. Never falls back to JobRunner."""

    def __init__(
        self,
        *,
        storage_service: Any,
        queue_service: Any,
        processor: Any,
        runtime_dir: Path,
        workspace_dir: Path,
        visibility_timeout: int,
        heartbeat_seconds: int,
        lease_seconds: int,
        wait_time_seconds: int = 20,
        retry_visibility_seconds: int = 60,
    ) -> None:
        self.storage = storage_service
        self.queue = queue_service
        self.processor = processor
        self.runtime_dir = Path(runtime_dir)
        self.workspace_dir = Path(workspace_dir)
        self.visibility_timeout = int(visibility_timeout)
        self.heartbeat_seconds = int(heartbeat_seconds)
        self.lease_seconds = int(lease_seconds)
        self.wait_time_seconds = int(wait_time_seconds)
        self.retry_visibility_seconds = max(0, int(retry_visibility_seconds))
        self._shutdown = threading.Event()
        self.last_heartbeat: VisibilityHeartbeat | None = None

    def request_shutdown(self, *_args: Any) -> None:
        self._shutdown.set()

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self.request_shutdown)
        signal.signal(signal.SIGINT, self.request_shutdown)

    def run_forever(self) -> None:
        logger.info("[WORKER] waiting")
        while not self._shutdown.is_set():
            try:
                jobs = self.queue.receive_analysis_jobs(
                    max_messages=CONCURRENCY,
                    wait_time_seconds=self.wait_time_seconds,
                    visibility_timeout=self.visibility_timeout,
                )
            except InvalidAnalysisJobError as exc:
                handle = getattr(exc, "receipt_handle", None)
                if handle:
                    try:
                        self.queue.delete_message(handle)
                    except Exception:
                        logger.warning("[WORKER] poison_delete_failed")
                else:
                    logger.warning("[WORKER] invalid_job")
                continue
            except (QueueUnavailableError, RetryableWorkerError, OSError, TimeoutError):
                logger.warning("[WORKER] receive_failed")
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("[WORKER] receive_failed error_code=%s", type(exc).__name__)
                continue
            if not jobs:
                continue
            if self._shutdown.is_set():
                # Already received: finish this one rather than deleting unseen work.
                pass
            self.process_received(jobs[0])

    def process_received(self, received: Any) -> None:
        from ..db.analysis_repo import (
            claim_analysis_job,
            extend_worker_lease,
            get_analysis_snapshot,
            release_claim_to_queued,
            update_analysis_status,
        )

        job = received.job
        handle = received.receipt_handle
        analysis_id = job.analysis_id
        logger.info(
            "[WORKER] received analysis_id=%s receive_count=%s",
            analysis_id,
            getattr(received, "approximate_receive_count", 1),
        )
        claim_token: str | None = None
        try:
            try:
                row = get_analysis_snapshot(analysis_id)
            except Exception as exc:
                raise RetryableWorkerError("db read failed") from exc
            if row is None:
                raise TerminalWorkerError("analysis not found", error_code="ANALYSIS_NOT_FOUND")
            if row.get("deleted_at") is not None:
                self.queue.delete_message(handle)
                return
            status = str(row.get("status") or "")
            if status == "completed":
                self.queue.delete_message(handle)
                logger.info("[WORKER] duplicate_completed analysis_id=%s", analysis_id)
                return
            if status == "failed":
                self.queue.delete_message(handle)
                logger.info("[WORKER] terminal_skip analysis_id=%s status=failed", analysis_id)
                return
            if status in TERMINAL_STATUSES:
                self.queue.delete_message(handle)
                return
            if status == "analyzing" and _lease_active(row):
                try:
                    self.queue.change_visibility(handle, min(30, self.visibility_timeout))
                except Exception:
                    logger.warning("[WORKER] defer_visibility_failed analysis_id=%s", analysis_id)
                logger.info("[WORKER] active_lease_skip analysis_id=%s", analysis_id)
                return

            self._validate_message_against_db(job, row)

            claim_token = uuid.uuid4().hex
            try:
                claimed = claim_analysis_job(
                    analysis_id,
                    claim_token=claim_token,
                    lease_seconds=self.lease_seconds,
                )
            except Exception as exc:
                raise RetryableWorkerError("db claim failed") from exc
            if claimed is None:
                latest = get_analysis_snapshot(analysis_id) or {}
                if str(latest.get("status") or "") == "completed":
                    self.queue.delete_message(handle)
                    return
                logger.info("[WORKER] claim_lost analysis_id=%s", analysis_id)
                return

            heartbeat = VisibilityHeartbeat(
                change_visibility=self.queue.change_visibility,
                extend_lease=lambda: extend_worker_lease(
                    analysis_id,
                    claim_token=claim_token,
                    lease_seconds=self.lease_seconds,
                ),
                receipt_handle=handle,
                visibility_timeout=self.visibility_timeout,
                interval_seconds=self.heartbeat_seconds,
            )
            self.last_heartbeat = heartbeat
            heartbeat.start()
            workspace: Path | None = None
            outcome = None
            try:
                workspace = self._download_workspace(analysis_id, str(row["audio_storage_key"]))
                outcome = self.processor.process(
                    analysis_id=analysis_id,
                    audio_path=str(workspace),
                    analysis_mode=str(row.get("analysis_mode") or job.analysis_mode),
                    input_mode=str(row.get("input_mode") or job.input_mode),
                    include_feedback=bool(job.include_feedback),
                    separate=row.get("separate"),
                    on_update=_db_progress_update,
                    is_cancelled=lambda: False,
                    notify=True,
                )
            except (StorageUnavailableError, QueueUnavailableError, OSError, TimeoutError, ConnectionError) as exc:
                raise RetryableWorkerError(str(exc)[:200]) from exc
            except StorageObjectNotFoundError as exc:
                raise TerminalWorkerError("audio object missing", error_code="INVALID_AUDIO_KEY") from exc
            finally:
                heartbeat.stop()
                if workspace is not None:
                    self._cleanup_parent(workspace)

            if outcome is None:
                raise RetryableWorkerError("processor returned no outcome")
            if outcome.ok:
                snap = get_analysis_snapshot(analysis_id) or {}
                if str(snap.get("status") or "") != "completed":
                    raise RetryableWorkerError("db completed not persisted")
                try:
                    self.queue.delete_message(handle)
                except QueueUnavailableError:
                    logger.warning("[WORKER] delete_after_completed_failed analysis_id=%s", analysis_id)
                logger.info("[WORKER] completed analysis_id=%s", analysis_id)
                return
            if outcome.status == "cancelled":
                release_claim_to_queued(analysis_id, claim_token=claim_token)
                return
            try:
                self.queue.delete_message(handle)
            except QueueUnavailableError:
                logger.warning("[WORKER] delete_after_failed_failed analysis_id=%s", analysis_id)
            logger.info("[WORKER] analyzer_failed analysis_id=%s", analysis_id)
        except TerminalWorkerError as exc:
            logger.warning(
                "[WORKER] terminal analysis_id=%s error_code=%s",
                analysis_id,
                exc.error_code,
            )
            try:
                update_analysis_status(
                    analysis_id,
                    status="failed",
                    stage="error",
                    progress=100,
                    error_message=str(exc),
                    error_code=exc.error_code,
                )
            except Exception:
                logger.warning("[WORKER] terminal_db_failed analysis_id=%s", analysis_id)
            try:
                self.queue.delete_message(handle)
            except Exception:
                logger.warning("[WORKER] terminal_delete_failed analysis_id=%s", analysis_id)
        except RetryableWorkerError as exc:
            logger.warning("[WORKER] retryable analysis_id=%s error_code=%s", analysis_id, type(exc).__name__)
            if claim_token:
                try:
                    release_claim_to_queued(analysis_id, claim_token=claim_token)
                except Exception:
                    logger.warning("[WORKER] release_failed analysis_id=%s", analysis_id)
            try:
                self.queue.change_visibility(handle, self.retry_visibility_seconds)
            except Exception:
                logger.warning("[WORKER] retry_visibility_failed analysis_id=%s", analysis_id)
            # Do not delete SQS message. Never fall back to local JobRunner.
        except Exception as exc:  # noqa: BLE001
            logger.warning("[WORKER] unexpected analysis_id=%s error_code=%s", analysis_id, type(exc).__name__)
            if claim_token:
                try:
                    release_claim_to_queued(analysis_id, claim_token=str(claim_token))
                except Exception:
                    pass

    def _validate_message_against_db(self, job: Any, row: dict[str, Any]) -> None:
        if not validate_analysis_id(job.analysis_id) or job.analysis_id != row.get("id"):
            raise TerminalWorkerError("analysis_id mismatch", error_code="INVALID_JOB")
        db_key = str(row.get("audio_storage_key") or "")
        if job.audio_key != db_key:
            raise TerminalWorkerError("audio_key mismatch", error_code="AUDIO_KEY_MISMATCH")
        if not is_analysis_audio_object_key(db_key, job.analysis_id):
            raise TerminalWorkerError("non-canonical audio key", error_code="INVALID_AUDIO_KEY")
        parse_analysis_audio_key(job.audio_key)

    def _download_workspace(self, analysis_id: str, object_key: str) -> Path:
        parent = self.workspace_dir / analysis_id
        if parent.exists():
            shutil.rmtree(parent, ignore_errors=True)
        parent.mkdir(parents=True, exist_ok=True)
        _, ext = parse_analysis_audio_key(object_key)
        dest = parent / f"input{ext}"
        return self.storage.download_analysis_audio(object_key, dest)

    def _cleanup_parent(self, downloaded: Path) -> None:
        try:
            parent = downloaded.parent
            parent.resolve().relative_to(self.workspace_dir.resolve())
            if parent.is_dir():
                shutil.rmtree(parent, ignore_errors=True)
        except (OSError, ValueError):
            logger.warning("[WORKER] workspace_cleanup_failed")


def _lease_active(row: dict[str, Any]) -> bool:
    from datetime import datetime, timezone

    expires = row.get("worker_lease_expires_at")
    if expires is None:
        return False
    now = datetime.now(timezone.utc)
    if getattr(expires, "tzinfo", None) is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > now


def _db_progress_update(analysis_id: str, **kwargs: Any) -> None:
    from ..db.analysis_repo import update_analysis_status

    status = str(kwargs.get("status") or "analyzing")
    update_analysis_status(
        analysis_id,
        status=status,
        stage=kwargs.get("stage"),
        progress=kwargs.get("progress") if isinstance(kwargs.get("progress"), int) else None,
        error_message=kwargs.get("error"),
        error_code=kwargs.get("error_code"),
        public_summary=kwargs.get("public_summary"),
        preview_storage_key=kwargs.get("preview_storage_key"),
        result_storage_key=kwargs.get("result_storage_key"),
    )


def build_worker() -> AnalysisWorker:
    from ..config import (
        get_runtime_dir,
        get_worker_workspace_dir,
        sqs_heartbeat_seconds,
        sqs_retry_visibility_seconds,
        sqs_visibility_timeout_seconds,
        sqs_wait_time_seconds,
        validate_worker_config,
        worker_lease_seconds,
    )
    from ..jobs.processor import AnalysisJobProcessor
    from ..jobs.queue import build_queue_service
    from ..storage.s3 import build_storage_service

    blockers = validate_worker_config()
    if blockers:
        raise RuntimeError("worker config not ready: " + ",".join(blockers))
    logger.info("[WORKER] startup")
    from ..db.session import database_reachable

    if not database_reachable():
        raise RuntimeError("database is not reachable")
    logger.info("[WORKER] database_ready")
    storage = build_storage_service()
    logger.info("[WORKER] s3_ready")
    queue = build_queue_service()
    logger.info("[WORKER] sqs_ready")
    runtime = get_runtime_dir()
    processor = AnalysisJobProcessor(runtime)
    return AnalysisWorker(
        storage_service=storage,
        queue_service=queue,
        processor=processor,
        runtime_dir=runtime,
        workspace_dir=get_worker_workspace_dir(),
        visibility_timeout=sqs_visibility_timeout_seconds(),
        heartbeat_seconds=sqs_heartbeat_seconds(),
        lease_seconds=worker_lease_seconds(),
        wait_time_seconds=sqs_wait_time_seconds(),
        retry_visibility_seconds=sqs_retry_visibility_seconds(),
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    worker = build_worker()
    worker.install_signal_handlers()
    worker.run_forever()
    logger.info("[WORKER] shutdown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
