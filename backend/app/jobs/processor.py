"""Shared analysis execution — used by local JobRunner and the SQS worker."""

from __future__ import annotations

import json
import logging
import shutil
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from audio_analyzer import analyze_audio, public_result

logger = logging.getLogger("vagent.jobs.processor")

ProgressUpdate = Callable[..., None]
CancelledFn = Callable[[], bool]


@dataclass(frozen=True)
class ProcessOutcome:
    ok: bool
    status: str
    error: str | None = None
    error_code: str | None = None


class AnalysisJobProcessor:
    """
    One-job analysis pipeline. Does not talk to SQS.
    Callers supply progress updates (memory+DB or DB-only).
    """

    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = Path(runtime_dir)

    def process(
        self,
        *,
        analysis_id: str,
        audio_path: str,
        analysis_mode: str = "QUICK",
        input_mode: str = "AUTO",
        include_feedback: bool = False,
        separate: bool | None = None,
        on_update: ProgressUpdate,
        is_cancelled: CancelledFn | None = None,
        notify: bool = True,
    ) -> ProcessOutcome:
        mode = (analysis_mode or "QUICK").upper()
        in_mode = (input_mode or "AUTO").upper()
        if separate is None:
            separate = mode == "FUNCTIONAL" and in_mode != "VOCAL_ONLY"
        cancelled = is_cancelled or (lambda: False)

        if cancelled():
            return ProcessOutcome(ok=False, status="cancelled")

        on_update(
            analysis_id,
            status="analyzing",
            stage="start",
            progress=1,
        )

        def progress(stage: str, pct: int) -> None:
            if cancelled():
                return
            on_update(
                analysis_id,
                status="analyzing",
                stage=stage,
                progress=pct,
            )

        try:
            if cancelled():
                return ProcessOutcome(ok=False, status="cancelled")
            result = analyze_audio(
                audio_path=audio_path,
                output_dir=str(self.runtime_dir),
                recording_id=analysis_id,
                separate=bool(separate),
                analysis_mode=mode,
                input_mode=in_mode,
                include_feedback=include_feedback,
                generate_visuals=False,
                build_preview=True,
                progress_callback=progress,
            )
            if cancelled():
                shutil.rmtree(self.runtime_dir / analysis_id, ignore_errors=True)
                return ProcessOutcome(ok=False, status="cancelled")

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
                "analysis_mode": mode,
                "input_mode": in_mode,
            }
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            preview_key = (
                f"{analysis_id}/preview.wav"
                if (self.runtime_dir / analysis_id / "preview.wav").exists()
                else None
            )
            result_key = f"{analysis_id}/public_result.json"
            vt = pub.get("vocal_type_teaser") or pub.get("vocal_type_profile")
            on_update(
                analysis_id,
                status="completed",
                stage="done",
                progress=100,
                error=None,
                result=pub,
                analysis_status=result.get("analysis_status", "completed"),
                feedback_status=result.get("feedback_status", "skipped"),
                public_summary={"vocal_type": vt} if vt else None,
                preview_storage_key=preview_key,
                result_storage_key=result_key,
            )
            if notify:
                try:
                    from ..notifications.completion import send_if_requested

                    send_if_requested(analysis_id, runtime_dir=self.runtime_dir)
                except Exception:
                    logger.warning("[PROCESSOR] notification_failed analysis_id=%s", analysis_id)
            return ProcessOutcome(ok=True, status="completed")
        except Exception as exc:  # noqa: BLE001
            if cancelled():
                return ProcessOutcome(ok=False, status="cancelled")
            err = f"{exc}\n{traceback.format_exc()}"
            on_update(
                analysis_id,
                status="failed",
                stage="error",
                progress=100,
                error=str(exc),
                error_code="ANALYZER_FAILED",
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
                        "error_code": "ANALYZER_FAILED",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return ProcessOutcome(
                ok=False,
                status="failed",
                error=str(exc),
                error_code="ANALYZER_FAILED",
            )
