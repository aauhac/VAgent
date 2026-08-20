"""
Analysis service — validates uploads and delegates to job runner.
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import UploadFile

from ..config import analysis_execution_mode, database_url, get_runtime_dir
from ..jobs.runner import JobRunner, validate_analysis_id

SUPPORTED_EXT = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".webm", ".mp4", ".m4v"}
logger = logging.getLogger("vagent.analysis")


def merge_queue_job_views(
    db_job: Optional[dict[str, Any]],
    disk_job: Optional[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Queue GET: DB owns lifecycle; durable files own the result payload."""
    if db_job is None and disk_job is None:
        return None
    if db_job is None:
        return dict(disk_job or {})
    if disk_job is None:
        return dict(db_job)
    merged = dict(disk_job)
    db_status = str(db_job.get("status") or "").strip()
    merged["analysis_id"] = db_job.get("analysis_id") or merged.get("analysis_id")
    if db_status:
        merged["status"] = db_status
        merged["analysis_status"] = db_job.get("analysis_status") or db_status
    for key in ("analysis_mode", "input_mode"):
        if db_job.get(key):
            merged[key] = db_job[key]
    if db_job.get("error"):
        merged["error"] = db_job["error"]
    if db_job.get("stage") is not None:
        merged["stage"] = db_job["stage"]
    if db_job.get("progress") is not None:
        merged["progress"] = db_job["progress"]
    disk_result = disk_job.get("result")
    if db_status == "completed" and isinstance(disk_result, dict):
        merged["result"] = disk_result
    elif db_status and db_status != "completed":
        merged["result"] = None
    return merged


class AnalysisSubmitError(Exception):
    def __init__(self, message: str, *, status_code: int = 503, code: str = "ANALYSIS_SUBMIT_FAILED") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.detail = message


class AnalysisService:
    def __init__(
        self,
        storage_service: Any | None = None,
        queue_service: Any | None = None,
        execution_mode: str | None = None,
    ) -> None:
        self.runtime_dir = get_runtime_dir()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.max_upload_mb = float(os.environ.get("MAX_UPLOAD_MB", "30"))
        self.runner = JobRunner(self.runtime_dir)
        if execution_mode is None:
            self.execution_mode = analysis_execution_mode()
        else:
            mode = execution_mode.strip().lower()
            if mode not in ("local", "queue"):
                raise RuntimeError(
                    "VAGENT_ANALYSIS_EXECUTION_MODE is invalid; allowed: local, queue"
                )
            self.execution_mode = mode
        self.storage_service = storage_service
        self.queue_service = queue_service

    async def enqueue_upload(
        self,
        *,
        file: UploadFile,
        separate: bool = False,
        include_feedback: bool = False,
        analysis_mode: str = "QUICK",
        input_mode: str = "AUTO",
        user_id: str = "anon",
        user_provider: str = "DEV",
    ) -> str:
        filename = file.filename or "upload.bin"
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXT:
            raise ValueError(
                f"unsupported file type '{ext}'. allowed: {sorted(SUPPORTED_EXT)}"
            )

        mode = (analysis_mode or "QUICK").upper()
        in_mode = (input_mode or "AUTO").upper()
        if mode == "FUNCTIONAL":
            separate = in_mode != "VOCAL_ONLY"

        analysis_id = uuid.uuid4().hex
        job_dir = self.runtime_dir / analysis_id
        job_dir.mkdir(parents=True, exist_ok=True)

        dest = job_dir / f"upload{ext}"
        size = 0
        max_bytes = int(self.max_upload_mb * 1024 * 1024)
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    out.close()
                    shutil.rmtree(job_dir, ignore_errors=True)
                    raise ValueError(f"file too large (max {self.max_upload_mb} MB)")
                out.write(chunk)

        try:
            from .history_service import write_analysis_meta

            write_analysis_meta(
                analysis_id,
                user_id=user_id or "anon",
                filename=filename,
                analysis_mode=mode,
                input_mode=in_mode,
                separate=separate,
                runtime_dir=self.runtime_dir,
            )
        except Exception:
            # Metadata write must not block enqueue
            pass

        if self.execution_mode == "queue":
            return self._submit_queue(
                analysis_id=analysis_id,
                dest=dest,
                job_dir=job_dir,
                filename=filename,
                ext=ext,
                separate=separate,
                include_feedback=include_feedback,
                mode=mode,
                in_mode=in_mode,
                user_id=user_id or "anon",
                user_provider=user_provider or "DEV",
            )

        try:
            self._maybe_persist_db_row(
                analysis_id=analysis_id,
                user_id=user_id or "anon",
                user_provider=user_provider or "DEV",
                filename=filename,
                mode=mode,
                in_mode=in_mode,
                separate=separate,
            )
        except Exception:
            pass

        self.runner.submit(
            analysis_id=analysis_id,
            audio_path=str(dest),
            separate=separate,
            include_feedback=include_feedback,
            analysis_mode=mode,
            input_mode=in_mode,
        )
        return analysis_id

    def _submit_queue(
        self,
        *,
        analysis_id: str,
        dest: Path,
        job_dir: Path,
        filename: str,
        ext: str,
        separate: bool,
        include_feedback: bool,
        mode: str,
        in_mode: str,
        user_id: str,
        user_provider: str,
    ) -> str:
        from ..jobs.queue import AnalysisJobMessage, utc_now_iso

        logger.info("[ANALYSIS_SUBMIT] mode=queue analysis_id=%s", analysis_id)
        if self.storage_service is None or self.queue_service is None:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise AnalysisSubmitError(
                "queue services not configured",
                code="QUEUE_NOT_CONFIGURED",
            )
        if not database_url():
            shutil.rmtree(job_dir, ignore_errors=True)
            raise AnalysisSubmitError(
                "DATABASE_URL is required when analysis execution mode is queue",
                code="QUEUE_DB_REQUIRED",
            )

        try:
            self._maybe_persist_db_row(
                analysis_id=analysis_id,
                user_id=user_id,
                user_provider=user_provider,
                filename=filename,
                mode=mode,
                in_mode=in_mode,
                separate=separate,
                audio_storage_key=None,
                use_default_local_key=False,
                raise_on_error=True,
            )
        except AnalysisSubmitError:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(job_dir, ignore_errors=True)
            raise AnalysisSubmitError(
                "failed to persist analysis",
                code="ANALYSIS_PERSIST_FAILED",
            ) from exc

        self.runner.remember_queued(
            analysis_id=analysis_id,
            analysis_mode=mode,
            input_mode=in_mode,
        )

        audio_key: str | None = None
        try:
            audio_key = self.storage_service.upload_analysis_audio(analysis_id, dest)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[ANALYSIS_SUBMIT] s3_upload_failed analysis_id=%s error_code=%s",
                analysis_id,
                type(exc).__name__,
            )
            self._fail_queue_job(
                analysis_id,
                error="storage upload failed",
                error_code="STORAGE_UPLOAD_FAILED",
            )
            shutil.rmtree(job_dir, ignore_errors=True)
            raise AnalysisSubmitError(
                "audio storage upload failed",
                code="STORAGE_UPLOAD_FAILED",
            ) from exc

        logger.info(
            "[ANALYSIS_SUBMIT] s3_upload_complete analysis_id=%s key=%s",
            analysis_id,
            audio_key,
        )

        try:
            from ..db.analysis_repo import update_analysis_status

            update_analysis_status(
                analysis_id,
                status="queued",
                stage="queued",
                progress=0,
                audio_storage_key=audio_key,
            )
            if not self._db_audio_key_matches(analysis_id, audio_key):
                raise RuntimeError("audio_storage_key update mismatch")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[ANALYSIS_SUBMIT] db_key_update_failed analysis_id=%s error_code=%s",
                analysis_id,
                type(exc).__name__,
            )
            try:
                self.storage_service.delete_analysis_audio(audio_key)
            except Exception:
                logger.warning("[ANALYSIS_SUBMIT] s3_orphan_delete_failed analysis_id=%s", analysis_id)
            self._fail_queue_job(
                analysis_id,
                error="audio_storage_key update failed",
                error_code="STORAGE_KEY_UPDATE_FAILED",
            )
            raise AnalysisSubmitError(
                "failed to record audio storage key",
                code="STORAGE_KEY_UPDATE_FAILED",
            ) from exc

        job = AnalysisJobMessage(
            schema_version=1,
            analysis_id=analysis_id,
            audio_key=str(audio_key),
            analysis_mode=mode,
            input_mode=in_mode,
            created_at=utc_now_iso(),
            include_feedback=bool(include_feedback),
        )
        try:
            message_id = self.queue_service.enqueue_analysis(job)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[ANALYSIS_SUBMIT] enqueue_failed analysis_id=%s error_code=%s",
                analysis_id,
                getattr(exc, "code", None) or type(exc).__name__,
            )
            self._fail_queue_job(
                analysis_id,
                error="queue enqueue failed",
                error_code="ENQUEUE_FAILED",
            )
            raise AnalysisSubmitError(
                "analysis queue enqueue failed",
                code="ENQUEUE_FAILED",
            ) from exc

        logger.info(
            "[ANALYSIS_SUBMIT] enqueue_complete analysis_id=%s message_id=%s",
            analysis_id,
            message_id,
        )
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            logger.warning("[ANALYSIS_SUBMIT] local_temp_cleanup_failed analysis_id=%s", analysis_id)
        return analysis_id

    def _fail_queue_job(self, analysis_id: str, *, error: str, error_code: str) -> None:
        try:
            self.runner.mark_terminal_failed(
                analysis_id, error=error, error_code=error_code
            )
        except Exception:
            logger.warning("[ANALYSIS_SUBMIT] mark_failed_memory_failed analysis_id=%s", analysis_id)
        try:
            from ..db.analysis_repo import update_analysis_status

            update_analysis_status(
                analysis_id,
                status="failed",
                stage="error",
                progress=100,
                error_message=error,
                error_code=error_code,
            )
        except Exception:
            logger.warning("[ANALYSIS_SUBMIT] mark_failed_db_failed analysis_id=%s", analysis_id)

    def _db_audio_key_matches(self, analysis_id: str, audio_key: str) -> bool:
        from ..db.models import Analysis
        from ..db.session import session_scope

        with session_scope() as session:
            row = session.get(Analysis, analysis_id)
            return bool(row and row.audio_storage_key == audio_key)

    def _lookup_audio_storage_key(self, analysis_id: str) -> str | None:
        if not database_url():
            return None
        try:
            from ..db.models import Analysis
            from ..db.session import session_scope

            with session_scope() as session:
                row = session.get(Analysis, analysis_id)
                if row is None or row.deleted_at is not None:
                    return None
                return row.audio_storage_key
        except Exception:
            return None

    def _job_snapshot_from_db(self, analysis_id: str) -> Optional[dict[str, Any]]:
        if not database_url():
            return None
        try:
            from ..db.models import Analysis
            from ..db.session import session_scope

            with session_scope() as session:
                row = session.get(Analysis, analysis_id)
                if row is None or row.deleted_at is not None:
                    return None
                return {
                    "analysis_id": row.id,
                    "status": row.status,
                    "stage": row.stage,
                    "progress": row.progress,
                    "error": row.error_message,
                    "result": None,
                    "analysis_status": row.status,
                    "feedback_status": None,
                    "analysis_mode": row.analysis_mode,
                    "input_mode": row.input_mode,
                }
        except Exception:
            return None

    def get_job(self, analysis_id: str) -> Optional[dict[str, Any]]:
        if not validate_analysis_id(analysis_id):
            return None
        if self.execution_mode != "queue":
            return self.runner.get(analysis_id)
        if self._queue_analysis_deleted(analysis_id):
            return None
        db_job = self._job_snapshot_from_db(analysis_id)
        disk_job = self.runner.get_durable(analysis_id)
        return merge_queue_job_views(db_job, disk_job)

    def _queue_analysis_deleted(self, analysis_id: str) -> bool:
        if not database_url():
            return False
        try:
            from ..db.analysis_repo import get_analysis_snapshot

            snap = get_analysis_snapshot(analysis_id)
            return bool(snap and snap.get("deleted_at") is not None)
        except Exception:
            return False

    def _maybe_persist_db_row(
        self,
        *,
        analysis_id: str,
        user_id: str,
        user_provider: str = "DEV",
        filename: str,
        mode: str,
        in_mode: str,
        separate: bool,
        audio_storage_key: str | None = None,
        use_default_local_key: bool = True,
        raise_on_error: bool = False,
    ) -> None:
        if not database_url():
            if raise_on_error:
                raise AnalysisSubmitError(
                    "DATABASE_URL is required when analysis execution mode is queue",
                    code="QUEUE_DB_REQUIRED",
                )
            return
        from ..db.analysis_repo import get_user_by_subject
        from ..db.models import Analysis
        from ..db.session import session_scope
        from ..db.users import get_or_create_user

        if use_default_local_key and audio_storage_key is None:
            audio_storage_key = f"{analysis_id}/upload{Path(filename).suffix.lower()}"

        with session_scope() as session:
            user = get_user_by_subject(session, user_id)
            if user is None:
                provider = (user_provider or "DEV").strip().upper() or "DEV"
                user = get_or_create_user(session, provider=provider, subject=user_id)
            if session.get(Analysis, analysis_id):
                return
            session.add(
                Analysis(
                    id=analysis_id,
                    user_id=user.id,
                    status="queued",
                    stage="queued",
                    progress=0,
                    analysis_mode=mode,
                    input_mode=in_mode,
                    separate=separate,
                    original_filename=filename,
                    audio_storage_key=audio_storage_key,
                )
            )

    def delete_job(self, analysis_id: str) -> bool:
        if not validate_analysis_id(analysis_id):
            return False
        from ..storage.s3 import is_analysis_audio_object_key
        from .deletion import delete_analysis_content

        audio_key = self._lookup_audio_storage_key(analysis_id)
        if (
            audio_key
            and self.storage_service is not None
            and is_analysis_audio_object_key(audio_key, analysis_id)
        ):
            try:
                self.storage_service.delete_analysis_audio(audio_key)
            except Exception:
                logger.warning("[ANALYSIS_DELETE] s3_delete_failed analysis_id=%s", analysis_id)

        result = delete_analysis_content(self.runtime_dir, analysis_id)
        if result.ok:
            self.runner.mark_deleted(analysis_id)
        return result.ok

    def preview_path(self, analysis_id: str) -> Optional[Path]:
        return self.runner.resolve_preview_path(analysis_id)

    def load_full_analysis(self, analysis_id: str) -> Optional[dict[str, Any]]:
        """Load full analysis.json (server-side). Not for public free API."""
        if not validate_analysis_id(analysis_id):
            return None
        path = self.runtime_dir / analysis_id / "analysis.json"
        if not path.exists():
            return None
        try:
            import json

            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def entitlements(self):
        from ..entitlements import get_entitlement_provider

        return get_entitlement_provider(self.runtime_dir)


def wire_analysis_service() -> "AnalysisService":
    """Startup helper. queue mode builds S3/SQS clients; local mode does not."""
    from ..config import validate_analysis_execution_config

    mode = analysis_execution_mode()
    if mode != "queue":
        return AnalysisService(execution_mode="local")
    blockers = validate_analysis_execution_config()
    if blockers:
        raise RuntimeError("analysis queue mode not ready: " + ",".join(blockers))
    from ..jobs.queue import build_queue_service
    from ..storage.s3 import build_storage_service

    return AnalysisService(
        storage_service=build_storage_service(),
        queue_service=build_queue_service(),
        execution_mode="queue",
    )
