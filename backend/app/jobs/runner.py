"""
In-process background job runner (no Redis/Celery required for MVP).

NOTE:
  Single-process / single-worker is the supported MVP mode.
  Uvicorn --workers > 1 splits the in-memory job registry across processes;
  use one worker (or sticky external store) in production until a shared store exists.
"""

from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from audio_analyzer.env_utils import load_dotenv_if_available

from .processor import AnalysisJobProcessor


load_dotenv_if_available()

_ANALYSIS_ID_RE = re.compile(r"^[a-fA-F0-9]{16,64}$")


def validate_analysis_id(analysis_id: str) -> bool:
    return bool(analysis_id and _ANALYSIS_ID_RE.match(analysis_id))


class JobRunner:
    def __init__(self, runtime_dir: Path, max_workers: int = 1) -> None:
        self.runtime_dir = runtime_dir
        self._jobs: dict[str, dict[str, Any]] = {}
        self._deleted: set[str] = set()
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self.processor = AnalysisJobProcessor(self.runtime_dir)

    def submit(
        self,
        *,
        analysis_id: str,
        audio_path: str,
        separate: bool = False,
        include_feedback: bool = False,
        analysis_mode: str = "QUICK",
        input_mode: str = "AUTO",
    ) -> None:
        if not validate_analysis_id(analysis_id):
            raise ValueError("invalid analysis_id")
        mode = (analysis_mode or "QUICK").upper()
        in_mode = (input_mode or "AUTO").upper()
        if mode == "FUNCTIONAL":
            separate = in_mode != "VOCAL_ONLY"
        with self._lock:
            if analysis_id in self._jobs and self._jobs[analysis_id].get("status") in (
                "queued",
                "analyzing",
            ):
                return
            self._deleted.discard(analysis_id)
            self._jobs[analysis_id] = {
                "analysis_id": analysis_id,
                "status": "queued",
                "stage": "queued",
                "progress": 0,
                "error": None,
                "result": None,
                "analysis_status": None,
                "feedback_status": None,
                "analysis_mode": mode,
                "input_mode": in_mode,
            }
        self._executor.submit(
            self._run,
            analysis_id,
            audio_path,
            separate,
            include_feedback,
            mode,
            in_mode,
        )

    def remember_queued(
        self,
        *,
        analysis_id: str,
        analysis_mode: str = "QUICK",
        input_mode: str = "AUTO",
    ) -> None:
        """Track a queued job for GET /status without starting JobRunner._run."""
        if not validate_analysis_id(analysis_id):
            raise ValueError("invalid analysis_id")
        mode = (analysis_mode or "QUICK").upper()
        in_mode = (input_mode or "AUTO").upper()
        with self._lock:
            self._deleted.discard(analysis_id)
            current = self._jobs.get(analysis_id)
            if current and current.get("status") in ("queued", "analyzing"):
                return
            self._jobs[analysis_id] = {
                "analysis_id": analysis_id,
                "status": "queued",
                "stage": "queued",
                "progress": 0,
                "error": None,
                "result": None,
                "analysis_status": None,
                "feedback_status": None,
                "analysis_mode": mode,
                "input_mode": in_mode,
            }

    def mark_terminal_failed(
        self,
        analysis_id: str,
        *,
        error: str,
        error_code: str,
    ) -> None:
        self._update(
            analysis_id,
            status="failed",
            stage="error",
            progress=100,
            error=error,
            error_code=error_code,
            analysis_status="failed",
            feedback_status="skipped",
        )

    def get(self, analysis_id: str) -> Optional[dict[str, Any]]:
        if not validate_analysis_id(analysis_id):
            return None
        with self._lock:
            if analysis_id in self._deleted:
                return None
            job = self._jobs.get(analysis_id)
            if job:
                return dict(job)
        return self._load_from_disk(analysis_id)

    def get_durable(self, analysis_id: str) -> Optional[dict[str, Any]]:
        """Read runtime artifacts only. Does not use in-memory _jobs."""
        if not validate_analysis_id(analysis_id):
            return None
        return self._load_from_disk(analysis_id, recover_interrupted=False)

    def mark_deleted(self, analysis_id: str) -> None:
        with self._lock:
            self._jobs.pop(analysis_id, None)
            self._deleted.add(analysis_id)

    def delete(self, analysis_id: str) -> bool:
        if not validate_analysis_id(analysis_id):
            return False
        from ..services.deletion import delete_analysis_content

        result = delete_analysis_content(self.runtime_dir, analysis_id)
        if result.ok:
            self.mark_deleted(analysis_id)
        return result.ok

    def resolve_preview_path(self, analysis_id: str) -> Optional[Path]:
        """Safe path resolution — never take user-supplied filesystem paths."""
        if not validate_analysis_id(analysis_id):
            return None
        with self._lock:
            if analysis_id in self._deleted:
                return None
        base = (self.runtime_dir / analysis_id).resolve()
        try:
            base.relative_to(self.runtime_dir.resolve())
        except ValueError:
            return None
        preview = (base / "preview.wav").resolve()
        try:
            preview.relative_to(base)
        except ValueError:
            return None
        if preview.is_file():
            return preview
        # fallback to analysis wav if preview missing
        analysis = (base / "analysis.wav").resolve()
        if analysis.is_file():
            try:
                analysis.relative_to(base)
                return analysis
            except ValueError:
                return None
        return None

    def _is_deleted(self, analysis_id: str) -> bool:
        with self._lock:
            return analysis_id in self._deleted

    def _update(self, analysis_id: str, **kwargs: Any) -> None:
        with self._lock:
            if analysis_id in self._deleted:
                return
            if analysis_id in self._jobs:
                self._jobs[analysis_id].update(kwargs)
        status = kwargs.get("status")
        if status in ("analyzing", "completed", "failed", "queued"):
            self._sync_db_status(analysis_id, **kwargs)

    def _sync_db_status(self, analysis_id: str, **kwargs: Any) -> None:
        try:
            from ..db.analysis_repo import update_analysis_status

            update_analysis_status(
                analysis_id,
                status=str(kwargs.get("status") or "analyzing"),
                stage=kwargs.get("stage"),
                progress=kwargs.get("progress") if isinstance(kwargs.get("progress"), int) else None,
                error_message=kwargs.get("error"),
                error_code=kwargs.get("error_code"),
                public_summary=kwargs.get("public_summary"),
                preview_storage_key=kwargs.get("preview_storage_key"),
                result_storage_key=kwargs.get("result_storage_key"),
            )
        except Exception:
            pass

    def _run(
        self,
        analysis_id: str,
        audio_path: str,
        separate: bool,
        include_feedback: bool,
        analysis_mode: str = "QUICK",
        input_mode: str = "AUTO",
    ) -> None:
        self.processor.process(
            analysis_id=analysis_id,
            audio_path=audio_path,
            analysis_mode=analysis_mode,
            input_mode=input_mode,
            include_feedback=include_feedback,
            separate=separate,
            on_update=self._update,
            is_cancelled=lambda: self._is_deleted(analysis_id),
            notify=True,
        )

    def _load_from_disk(
        self, analysis_id: str, *, recover_interrupted: bool = True
    ) -> Optional[dict[str, Any]]:
        if self._is_deleted(analysis_id):
            return None
        path = self.runtime_dir / analysis_id / "job_status.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    return {
                        "analysis_id": analysis_id,
                        "status": "failed",
                        "error": "corrupted job_status.json",
                        "progress": 100,
                    }
                data.setdefault("analysis_id", analysis_id)
                # Restore mode fields lost on older job_status.json / process restart
                if not data.get("analysis_mode") or not data.get("input_mode"):
                    meta_path = self.runtime_dir / analysis_id / "analysis_meta.json"
                    if meta_path.exists():
                        try:
                            meta = json.loads(meta_path.read_text(encoding="utf-8"))
                            if isinstance(meta, dict):
                                data.setdefault("analysis_mode", meta.get("analysis_mode"))
                                data.setdefault("input_mode", meta.get("input_mode"))
                        except (json.JSONDecodeError, OSError):
                            pass
                # Local in-process restart recovery only. Queue workers still own in-flight jobs.
                if recover_interrupted and str(data.get("status") or "").lower() in (
                    "queued",
                    "analyzing",
                ):
                    data["status"] = "failed"
                    data["stage"] = "interrupted_restart"
                    data["error"] = data.get("error") or "INTERRUPTED_RESTART"
                    data["error_code"] = "INTERRUPTED_RESTART"
                    data["progress"] = 100
                    try:
                        path.write_text(
                            json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    except OSError:
                        pass
                    self._sync_db_status(
                        analysis_id,
                        status="failed",
                        stage="interrupted_restart",
                        progress=100,
                        error="INTERRUPTED_RESTART",
                        error_code="INTERRUPTED_RESTART",
                    )
                if "progress" in data and data["progress"] is not None:
                    try:
                        data["progress"] = max(0, min(100, int(float(data["progress"]))))
                    except (TypeError, ValueError):
                        data["progress"] = None
                return data
            except (json.JSONDecodeError, OSError):
                return {
                    "analysis_id": analysis_id,
                    "status": "failed",
                    "error": "corrupted job_status.json",
                    "progress": 100,
                }

        pub_path = self.runtime_dir / analysis_id / "public_result.json"
        if pub_path.exists():
            try:
                data = json.loads(pub_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {
                    "analysis_id": analysis_id,
                    "status": "failed",
                    "error": "corrupted public_result.json",
                    "progress": 100,
                }
            out = {
                "analysis_id": analysis_id,
                "status": "completed",
                "stage": "done",
                "progress": 100,
                "error": None,
                "result": data,
                "analysis_status": data.get("analysis_status"),
                "feedback_status": data.get("feedback_status"),
                "analysis_mode": data.get("analysis_mode"),
                "input_mode": data.get("input_mode"),
            }
            meta_path = self.runtime_dir / analysis_id / "analysis_meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    if isinstance(meta, dict):
                        out.setdefault("analysis_mode", meta.get("analysis_mode"))
                        out.setdefault("input_mode", meta.get("input_mode"))
                except (json.JSONDecodeError, OSError):
                    pass
            return out
        return None
