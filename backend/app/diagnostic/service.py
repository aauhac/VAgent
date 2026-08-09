"""
Diagnostic session store + workflow (file-based MVP).
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import soundfile as sf

from audio_analyzer.diagnostic import (
    SAFETY_QUESTIONS,
    TASKS,
    VOCAL_DIAGNOSTIC_PROTOCOL_VERSION,
    analyze_task_audio,
    get_task,
)
from audio_analyzer.physiology import build_premium_report
from audio_analyzer.physiology.report import public_premium_report
from audio_analyzer.preprocessing.audio_io import load_analysis_audio
from audio_analyzer.quality import evaluate_quality

from ..entitlements import allow_dev_bypass, get_entitlement_provider
from ..jobs.runner import validate_analysis_id

_SESSION_ID_RE = re.compile(r"^[a-fA-F0-9]{16,64}$")

STATUSES = {
    "CREATED",
    "PAID",
    "SAFETY_CHECK",
    "TASKS_IN_PROGRESS",
    "READY_FOR_ANALYSIS",
    "ANALYZING",
    "COMPLETED",
    "FAILED",
}


def validate_session_id(session_id: str) -> bool:
    return bool(session_id and _SESSION_ID_RE.match(session_id))


class DiagnosticSessionService:
    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.entitlements = get_entitlement_provider(runtime_dir)

    def _dir(self, session_id: str) -> Path:
        return self.runtime_dir / "diagnostic_sessions" / session_id

    def _path(self, session_id: str) -> Path:
        return self._dir(session_id) / "session.json"

    def _load(self, session_id: str) -> Optional[dict[str, Any]]:
        if not validate_session_id(session_id):
            return None
        p = self._path(session_id)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _save(self, session: dict[str, Any]) -> None:
        d = self._dir(session["session_id"])
        d.mkdir(parents=True, exist_ok=True)
        self._path(session["session_id"]).write_text(
            json.dumps(session, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def create(
        self,
        *,
        user_id: str = "anon",
        source_analysis_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if source_analysis_id and not validate_analysis_id(source_analysis_id):
            raise ValueError("invalid source_analysis_id")
        session_id = uuid.uuid4().hex
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "source_analysis_id": source_analysis_id,
            "analysis_mode": "diagnostic",
            "protocol_version": VOCAL_DIAGNOSTIC_PROTOCOL_VERSION,
            "status": "CREATED",
            "entitlement_id": None,
            "safety_flags": [],
            "safety_answers": {},
            "tasks": {
                t["task_id"]: {"attempts": [], "passed": False} for t in TASKS
            },
            "task_results": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "error": None,
        }
        self._save(session)
        return self.public_session(session)

    def mock_pay(self, session_id: str, user_id: str = "anon") -> dict[str, Any]:
        if not allow_dev_bypass():
            raise PermissionError("mock pay disabled in production")
        session = self._load(session_id)
        if not session:
            raise KeyError("session not found")
        entitlement_id = f"mock_{uuid.uuid4().hex[:12]}"
        self.entitlements.grant_session_unlock(user_id, session_id, entitlement_id)
        session["user_id"] = user_id
        session["entitlement_id"] = entitlement_id
        session["status"] = "PAID"
        self._save(session)
        return self.public_session(session)

    def submit_safety(
        self,
        session_id: str,
        answers: dict[str, bool],
        user_id: str = "anon",
    ) -> dict[str, Any]:
        session = self._require_unlocked(session_id, user_id)
        if session["status"] not in ("PAID", "SAFETY_CHECK"):
            raise ValueError("invalid status for safety check")
        flags = [qid for qid, val in answers.items() if val]
        session["safety_answers"] = answers
        session["safety_flags"] = flags
        session["status"] = "TASKS_IN_PROGRESS"
        self._save(session)
        return self.public_session(session)

    def upload_task(
        self,
        session_id: str,
        task_id: str,
        audio_bytes: bytes,
        filename: str,
        user_id: str = "anon",
    ) -> dict[str, Any]:
        session = self._require_unlocked(session_id, user_id)
        if session["status"] not in ("TASKS_IN_PROGRESS", "READY_FOR_ANALYSIS"):
            raise ValueError("tasks not in progress")
        task = get_task(task_id)
        state = session["tasks"][task_id]
        if len(state["attempts"]) >= task["max_attempts"] and not state["passed"]:
            # allow replace only if last failed? protocol: 2 attempts
            if state["passed"]:
                raise ValueError("task already passed")
            if len(state["attempts"]) >= task["max_attempts"]:
                raise ValueError("max attempts reached")

        attempt = len(state["attempts"]) + 1
        work = self._dir(session_id) / "tasks" / task_id / f"attempt_{attempt}"
        work.mkdir(parents=True, exist_ok=True)
        ext = Path(filename).suffix.lower() or ".wav"
        raw_path = work / f"upload{ext}"
        raw_path.write_bytes(audio_bytes)

        y, sr, _ = load_analysis_audio(str(raw_path), work, sample_rate=44100)
        duration = len(y) / sr
        # Diagnostic clips are short by design — soften song-oriented voiced-duration fails
        quality = evaluate_quality(
            y,
            sr,
            voiced_ratio=max(0.2, 1.0 - float(np.mean(np.abs(y) < 1e-4))),
            voiced_duration_sec=min(duration, max(1.2, duration * 0.85)),
        )
        if duration < task["min_sec"]:
            quality = {
                **quality,
                "status": "fail",
                "codes": list(dict.fromkeys((quality.get("codes") or []) + ["SHORT_DURATION"])),
                "reasons": (quality.get("reasons") or [])
                + [f"Task 최소 {task['min_sec']}초 필요"],
                "user_message": f"조금 더 길게 녹음해 주세요. (최소 {task['min_sec']}초)",
            }
        elif quality.get("status") == "fail":
            # Keep hard fails (clipping / silence / level); drop SHORT_VOICED when duration OK
            codes = [c for c in (quality.get("codes") or []) if c != "SHORT_VOICED_DURATION"]
            if not codes or set(codes) <= {"SHORT_VOICED_DURATION", "LOW_VOICED_RATIO"}:
                quality = {
                    **quality,
                    "status": "warn",
                    "codes": codes or ["TASK_SOFT_WARN"],
                    "user_message": "분석은 가능하지만 녹음 조건이 완벽하지 않아요.",
                }
            elif "SHORT_VOICED_DURATION" in (quality.get("codes") or []):
                quality = {
                    **quality,
                    "status": "warn" if "CLIPPING" not in codes and "LOW_LEVEL" not in codes else "fail",
                    "codes": codes,
                }

        attempt_rec = {
            "attempt": attempt,
            "quality_status": quality.get("status"),
            "quality": {
                "status": quality.get("status"),
                "codes": quality.get("codes"),
                "reasons": quality.get("reasons"),
                "user_message": quality.get("user_message"),
            },
            "passed": quality.get("status") != "fail",
        }
        # Persist wav for analysis
        sf.write(str(work / "analysis.wav"), y, sr)

        if attempt_rec["passed"]:
            result = analyze_task_audio(y, sr, task_id=task_id, attempt=attempt)
            # strip non-serializable
            result = json.loads(json.dumps(result, default=str))
            attempt_rec["result"] = result
            state["passed"] = True
            # replace previous result for this task
            session["task_results"] = [
                r for r in session["task_results"] if r.get("task_id") != task_id
            ]
            session["task_results"].append(result)

        state["attempts"].append(attempt_rec)
        session["tasks"][task_id] = state

        if all(session["tasks"][t["task_id"]]["passed"] for t in TASKS):
            session["status"] = "READY_FOR_ANALYSIS"
        else:
            session["status"] = "TASKS_IN_PROGRESS"

        self._save(session)
        return {
            "session": self.public_session(session),
            "task_id": task_id,
            "attempt": attempt_rec,
            "retry_allowed": (not attempt_rec["passed"])
            and len(state["attempts"]) < task["max_attempts"],
        }

    def analyze(self, session_id: str, user_id: str = "anon") -> dict[str, Any]:
        session = self._require_unlocked(session_id, user_id)
        if session["status"] not in ("READY_FOR_ANALYSIS", "COMPLETED"):
            raise ValueError("not ready for analysis")
        if session["status"] == "COMPLETED" and (self._dir(session_id) / "premium_report.json").exists():
            return self.get_report(session_id, user_id)

        session["status"] = "ANALYZING"
        self._save(session)
        try:
            song_summary = None
            src = session.get("source_analysis_id")
            if src:
                pub = self.runtime_dir / src / "public_result.json"
                if pub.exists():
                    song = json.loads(pub.read_text(encoding="utf-8"))
                    song_summary = {
                        "timeline_preview": [],
                        "overall": (song.get("score") or {}).get("overall"),
                        "label": (song.get("score") or {}).get("label"),
                    }
            report = build_premium_report(
                session_id=session_id,
                task_results=session.get("task_results") or [],
                song_summary=song_summary,
                safety_flags=session.get("safety_flags") or [],
                include_scientific_debug=True,  # stored server-side for developer mode
            )
            report_path = self._dir(session_id) / "premium_report.json"
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            session["status"] = "COMPLETED"
            session["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._save(session)
            return public_premium_report(report)
        except Exception as exc:  # noqa: BLE001
            session["status"] = "FAILED"
            session["error"] = str(exc)
            self._save(session)
            raise

    def get_report(
        self,
        session_id: str,
        user_id: str = "anon",
        *,
        include_scientific_debug: bool = False,
    ) -> dict[str, Any]:
        session = self._load(session_id)
        if not session:
            raise KeyError("session not found")
        if not self.entitlements.has_session_unlock(user_id, session_id):
            return {
                "error": "REPORT_LOCKED",
                "message": "상세 발성 진단이 아직 해제되지 않았어요.",
                "session_id": session_id,
            }
        path = self._dir(session_id) / "premium_report.json"
        if not path.exists():
            if session.get("status") == "READY_FOR_ANALYSIS":
                return self.analyze(session_id, user_id)
            raise FileNotFoundError("report not ready")
        report = json.loads(path.read_text(encoding="utf-8"))
        if include_scientific_debug:
            return report
        return public_premium_report(report)

    def get_session(self, session_id: str, user_id: str = "anon") -> Optional[dict[str, Any]]:
        session = self._load(session_id)
        if not session:
            return None
        pub = self.public_session(session)
        pub["unlocked"] = self.entitlements.has_session_unlock(user_id, session_id)
        return pub

    def protocol(self) -> dict[str, Any]:
        return {
            "protocol_version": VOCAL_DIAGNOSTIC_PROTOCOL_VERSION,
            "tasks": TASKS,
            "safety_questions": SAFETY_QUESTIONS,
        }

    def _require_unlocked(self, session_id: str, user_id: str) -> dict[str, Any]:
        session = self._load(session_id)
        if not session:
            raise KeyError("session not found")
        if not self.entitlements.has_session_unlock(user_id, session_id):
            raise PermissionError("REPORT_LOCKED")
        return session

    def public_session(self, session: dict[str, Any]) -> dict[str, Any]:
        """No filesystem paths."""
        tasks_pub = {}
        for tid, st in (session.get("tasks") or {}).items():
            tasks_pub[tid] = {
                "passed": st.get("passed"),
                "attempt_count": len(st.get("attempts") or []),
                "last_quality": (st.get("attempts") or [{}])[-1].get("quality")
                if st.get("attempts")
                else None,
            }
        return {
            "session_id": session["session_id"],
            "user_id": session.get("user_id"),
            "source_analysis_id": session.get("source_analysis_id"),
            "analysis_mode": "diagnostic",
            "protocol_version": session.get("protocol_version"),
            "status": session.get("status"),
            "safety_flags": session.get("safety_flags") or [],
            "tasks": tasks_pub,
            "created_at": session.get("created_at"),
            "completed_at": session.get("completed_at"),
            "error": session.get("error"),
        }
