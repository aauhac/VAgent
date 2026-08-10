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
import shutil
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from audio_analyzer import analyze_audio, public_result
from audio_analyzer.env_utils import load_dotenv_if_available


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

    def delete(self, analysis_id: str) -> bool:
        if not validate_analysis_id(analysis_id):
            return False
        with self._lock:
            existed = analysis_id in self._jobs
            self._jobs.pop(analysis_id, None)
            self._deleted.add(analysis_id)
        path = self.runtime_dir / analysis_id
        disk_existed = path.exists()
        if disk_existed:
            shutil.rmtree(path, ignore_errors=True)
        return existed or disk_existed

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

    def _run(
        self,
        analysis_id: str,
        audio_path: str,
        separate: bool,
        include_feedback: bool,
        analysis_mode: str = "QUICK",
        input_mode: str = "AUTO",
    ) -> None:
        if self._is_deleted(analysis_id):
            return
        self._update(
            analysis_id,
            status="analyzing",
            stage="start",
            progress=1,
        )

        def progress(stage: str, pct: int) -> None:
            if self._is_deleted(analysis_id):
                return
            self._update(
                analysis_id,
                status="analyzing",
                stage=stage,
                progress=pct,
            )

        try:
            if self._is_deleted(analysis_id):
                return
            result = analyze_audio(
                audio_path=audio_path,
                output_dir=str(self.runtime_dir),
                recording_id=analysis_id,
                separate=separate,
                analysis_mode=analysis_mode,
                input_mode=input_mode,
                include_feedback=include_feedback,
                generate_visuals=False,
                build_preview=True,
                progress_callback=progress,
            )
            if self._is_deleted(analysis_id):
                # Job deleted mid-run: drop artifacts and do not restore memory
                shutil.rmtree(self.runtime_dir / analysis_id, ignore_errors=True)
                return

            pub = public_result(result)
            status_path = self.runtime_dir / analysis_id / "job_status.json"
            payload = {
                "analysis_id": analysis_id,
                "status": "completed",
                "stage": "done",
                "progress": 100,
                "error": None,
                "result": pub,
                "analysis_status": result.get("analysis_status", "completed"),
                "feedback_status": result.get("feedback_status", "skipped"),
            }
            status_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._update(**payload)
        except Exception as exc:  # noqa: BLE001
            if self._is_deleted(analysis_id):
                return
            err = f"{exc}\n{traceback.format_exc()}"
            self._update(
                analysis_id,
                status="failed",
                stage="error",
                progress=100,
                error=str(exc),
                analysis_status="failed",
                feedback_status="skipped",
            )
            fail_path = self.runtime_dir / analysis_id / "job_status.json"
            fail_path.parent.mkdir(parents=True, exist_ok=True)
            fail_path.write_text(
                json.dumps(
                    {
                        "analysis_id": analysis_id,
                        "status": "failed",
                        "error": err,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    def _load_from_disk(self, analysis_id: str) -> Optional[dict[str, Any]]:
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
            return {
                "analysis_id": analysis_id,
                "status": "completed",
                "stage": "done",
                "progress": 100,
                "error": None,
                "result": data,
                "analysis_status": data.get("analysis_status"),
                "feedback_status": data.get("feedback_status"),
            }
        return None
