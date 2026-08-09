"""
In-process background job runner (no Redis/Celery required for MVP).
"""

from __future__ import annotations

import json
import shutil
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from audio_analyzer import analyze_audio, public_result
from audio_analyzer.env_utils import load_dotenv_if_available


load_dotenv_if_available()


class JobRunner:
    def __init__(self, runtime_dir: Path, max_workers: int = 1) -> None:
        self.runtime_dir = runtime_dir
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(
        self,
        *,
        analysis_id: str,
        audio_path: str,
        separate: bool = False,
        include_feedback: bool = False,
    ) -> None:
        with self._lock:
            self._jobs[analysis_id] = {
                "analysis_id": analysis_id,
                "status": "queued",
                "stage": "queued",
                "progress": 0,
                "error": None,
                "result": None,
                "analysis_status": None,
                "feedback_status": None,
            }
        self._executor.submit(
            self._run,
            analysis_id,
            audio_path,
            separate,
            include_feedback,
        )

    def get(self, analysis_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(analysis_id)
            return dict(job) if job else self._load_from_disk(analysis_id)

    def delete(self, analysis_id: str) -> bool:
        with self._lock:
            self._jobs.pop(analysis_id, None)
        path = self.runtime_dir / analysis_id
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            return True
        return False

    def _update(self, analysis_id: str, **kwargs: Any) -> None:
        with self._lock:
            if analysis_id in self._jobs:
                self._jobs[analysis_id].update(kwargs)

    def _run(
        self,
        analysis_id: str,
        audio_path: str,
        separate: bool,
        include_feedback: bool,
    ) -> None:
        self._update(
            analysis_id,
            status="analyzing",
            stage="start",
            progress=1,
        )

        def progress(stage: str, pct: int) -> None:
            self._update(
                analysis_id,
                status="analyzing",
                stage=stage,
                progress=pct,
            )

        try:
            result = analyze_audio(
                audio_path=audio_path,
                output_dir=str(self.runtime_dir),
                recording_id=analysis_id,
                separate=separate,
                include_feedback=include_feedback,
                generate_visuals=False,
                build_preview=True,
                progress_callback=progress,
            )
            pub = public_result(result)
            # persist status snapshot
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
        path = self.runtime_dir / analysis_id / "job_status.json"
        if not path.exists():
            pub = self.runtime_dir / analysis_id / "public_result.json"
            if pub.exists():
                data = json.loads(pub.read_text(encoding="utf-8"))
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
        return json.loads(path.read_text(encoding="utf-8"))
