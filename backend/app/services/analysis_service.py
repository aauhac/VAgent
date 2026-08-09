"""
Analysis service — validates uploads and delegates to job runner.
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import UploadFile

from ..jobs.runner import JobRunner, validate_analysis_id

SUPPORTED_EXT = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".webm", ".mp4", ".m4v"}


class AnalysisService:
    def __init__(self) -> None:
        self.runtime_dir = Path(os.environ.get("RUNTIME_DIR", "runtime"))
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.max_upload_mb = float(os.environ.get("MAX_UPLOAD_MB", "30"))
        self.runner = JobRunner(self.runtime_dir)

    async def enqueue_upload(
        self,
        *,
        file: UploadFile,
        separate: bool = False,
        include_feedback: bool = False,
    ) -> str:
        filename = file.filename or "upload.bin"
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXT:
            raise ValueError(
                f"unsupported file type '{ext}'. allowed: {sorted(SUPPORTED_EXT)}"
            )

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

        self.runner.submit(
            analysis_id=analysis_id,
            audio_path=str(dest),
            separate=separate,
            include_feedback=include_feedback,
        )
        return analysis_id

    def get_job(self, analysis_id: str) -> Optional[dict[str, Any]]:
        if not validate_analysis_id(analysis_id):
            return None
        return self.runner.get(analysis_id)

    def delete_job(self, analysis_id: str) -> bool:
        if not validate_analysis_id(analysis_id):
            return False
        return self.runner.delete(analysis_id)

    def preview_path(self, analysis_id: str) -> Optional[Path]:
        return self.runner.resolve_preview_path(analysis_id)

    def load_full_analysis(self, analysis_id: str) -> Optional[dict[str, Any]]:
        """Load full analysis.json (server-side). Not for free public API."""
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
