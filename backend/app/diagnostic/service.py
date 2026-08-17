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
    build_final_diagnostic_profile,
    build_personalized_qa,
    get_task,
    has_pain_safety_flag,
    normalize_user_concerns,
    plan_from_song_analysis,
    public_concern_catalog,
    tasks_for_ids,
)
from audio_analyzer.diagnostic.concerns import normalize_diagnostic_mode
from audio_analyzer.diagnostic.evidence_mode import (
    EVIDENCE_MODE_CONCERN_ONLY,
    EVIDENCE_MODE_FULL,
    EVIDENCE_MODE_PARTIAL,
    EVIDENCE_MODE_COVERAGE_COPY,
    SKIP_REASON_USER_CHOICE,
    all_selected_terminal,
    derive_evidence_mode,
    is_task_terminal,
    is_user_skipped,
    list_completed_tasks,
    list_safety_blocked_tasks,
    list_user_skipped_tasks,
    mark_task_user_skipped,
    report_subtitle_for_mode,
    report_title_for_mode,
    sync_skip_provenance,
    valid_controlled_task_count,
)
from audio_analyzer.diagnostic.task_registry import (
    DIAGNOSTIC_MODE_CONCERN,
    DIAGNOSTIC_MODE_GENERAL,
    DIAGNOSTIC_STATUS_SAFETY_LIMITED,
    PLANNER_VERSION,
    TASK_REGISTRY,
)
from audio_analyzer.diagnostic.report_versions import (
    GOAL_VERSION as QA_GOAL_VERSION,
    QA_GUIDANCE_VERSION,
    REPORT_LOGIC_VERSION,
)
from audio_analyzer.physiology import build_premium_report
from audio_analyzer.physiology.report import public_premium_report
from audio_analyzer.preprocessing.audio_io import load_analysis_audio
from audio_analyzer.quality import evaluate_quality

from ..entitlements import allow_dev_bypass, get_entitlement_provider
from ..jobs.runner import validate_analysis_id

_SESSION_ID_RE = re.compile(r"^[a-fA-F0-9]{16,64}$")


def _log_plan(session: dict[str, Any], *, persisted: bool) -> None:
    print(
        "[DIAGNOSTIC_PLAN]",
        f"session_id={session.get('session_id')}",
        f"mode={session.get('diagnostic_mode')}",
        f"concerns={[c.get('id') for c in (session.get('user_concerns') or [])]}",
        f"safety={session.get('safety_flags') or []}",
        f"core_tasks={session.get('core_tasks') or []}",
        f"adaptive_tasks={session.get('adaptive_tasks') or []}",
        f"selected_tasks={session.get('selected_tasks') or []}",
        f"diagnostic_status={session.get('diagnostic_status')}",
        f"persisted={persisted}",
        flush=True,
    )

STATUSES = {
    "CREATED",
    "PAID",
    "SAFETY_CHECK",
    "RECORDING_CHOICE",
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
        # Production / DATABASE_URL: PostgreSQL is SoT (file is cache only)
        try:
            from ..db.diagnostic_repo import db_enabled, load_session_dict

            if db_enabled():
                db_session = load_session_dict(session_id)
                if db_session is not None:
                    return db_session
                # DB enabled but row missing: do not resurrect from file in production
                from ..config import is_production

                if is_production():
                    return None
        except Exception:
            from ..config import is_production

            if is_production():
                raise

        p = self._path(session_id)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _save(self, session: dict[str, Any]) -> None:
        # File cache for artifacts/compat (never overwrites DB as SoT when DB enabled)
        d = self._dir(session["session_id"])
        d.mkdir(parents=True, exist_ok=True)
        self._path(session["session_id"]).write_text(
            json.dumps(session, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            from ..db.diagnostic_repo import upsert_session_from_dict

            upsert_session_from_dict(session)
        except Exception:
            # Never break mock-pay / safety unit paths when DB is unavailable
            pass

    def _load_song_payload(self, source_analysis_id: Optional[str]) -> Optional[dict[str, Any]]:
        """Load song analysis for diagnostic evidence.

        Prefer analysis.json (full vocal_function_profile). public_result.json is a
        teaser-only free payload and must not silently wipe VF evidence.
        """
        if not source_analysis_id:
            return None
        analysis: Optional[dict[str, Any]] = None
        public: Optional[dict[str, Any]] = None
        for name in ("analysis.json", "public_result.json"):
            p = self.runtime_dir / source_analysis_id / name
            if not p.exists():
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if name == "analysis.json":
                analysis = data
            else:
                public = data
        if analysis and public:
            merged = dict(public)
            # Always prefer full VF from analysis when public lacks it
            avf = analysis.get("vocal_function_profile")
            pvf = merged.get("vocal_function_profile")
            if avf and (not pvf or not isinstance(pvf, dict) or not pvf):
                merged["vocal_function_profile"] = avf
            elif avf and isinstance(pvf, dict):
                # Fill missing nested profiles without inventing
                for key in (
                    "timbre_profile",
                    "effort_assessment",
                    "dimensions",
                    "vocal_type_profile",
                    "vocal_style_profile",
                    "high_note_function_profile",
                    "criteria_matrix",
                    "contact_effort_plane",
                    "coaching_decision",
                ):
                    if key in avf and key not in pvf:
                        pvf[key] = avf[key]
                merged["vocal_function_profile"] = pvf
            # Keep analysis-only top-level VF path for extractors
            if not merged.get("vocal_function_profile") and avf:
                merged["vocal_function_profile"] = avf
            merged["_song_evidence_source"] = "analysis.json+public_result.json"
            return merged
        if analysis:
            analysis = dict(analysis)
            analysis["_song_evidence_source"] = "analysis.json"
            return analysis
        if public:
            public = dict(public)
            public["_song_evidence_source"] = "public_result.json"
            return public
        return None

    def _build_plan(
        self,
        source_analysis_id: Optional[str],
        *,
        user_concerns: Optional[list[dict[str, Any]]] = None,
        pain_safety_flag: bool = False,
        diagnostic_mode: Optional[str] = None,
        safety_flags: Optional[list[str]] = None,
        precision: bool = False,
    ) -> dict[str, Any]:
        song = self._load_song_payload(source_analysis_id)
        concerns = normalize_user_concerns(user_concerns)
        pain = pain_safety_flag or has_pain_safety_flag(concerns)
        mode = normalize_diagnostic_mode(diagnostic_mode, concerns)
        if song:
            return plan_from_song_analysis(
                song,
                user_concerns=concerns if mode == DIAGNOSTIC_MODE_CONCERN else None,
                pain_safety_flag=pain,
                diagnostic_mode=mode if precision else None,
                safety_flags=safety_flags,
                precision=precision,
            )
        from audio_analyzer.diagnostic.planner import (
            build_uncertainty_profile,
            explain_task_selection,
            plan_precision_protocol,
            select_diagnostic_tasks,
        )

        profile = build_uncertainty_profile(
            criteria_matrix=[], dimensions={}, measurement_candidates=[]
        )
        if precision:
            plan = plan_precision_protocol(
                profile,
                diagnostic_mode=mode,
                user_concerns=concerns if mode == DIAGNOSTIC_MODE_CONCERN else None,
                pain_safety_flag=pain,
                safety_flags=safety_flags,
            )
        else:
            plan = select_diagnostic_tasks(
                profile, fallback_all_if_empty_song=True, user_concerns=concerns, pain_safety_flag=pain
            )
        explain = explain_task_selection(plan)
        return {**plan, **explain, "uncertainty_profile": profile}

    def create(
        self,
        *,
        user_id: str = "anon",
        source_analysis_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if source_analysis_id and not validate_analysis_id(source_analysis_id):
            raise ValueError("invalid source_analysis_id")
        if source_analysis_id:
            from ..services.ownership import can_access_analysis

            if not can_access_analysis(user_id, source_analysis_id, self.runtime_dir):
                raise ValueError("source analysis not found")
        session_id = uuid.uuid4().hex
        # Provisional song-only offer — final tasks planned after concern intake
        plan = self._build_plan(source_analysis_id, precision=False)
        selected: list[str] = []  # filled after concerns / general discovery
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "source_analysis_id": source_analysis_id,
            "analysis_mode": "diagnostic",
            "protocol_version": VOCAL_DIAGNOSTIC_PROTOCOL_VERSION,
            "planner_version": plan.get("planner_version") or PLANNER_VERSION,
            "status": "CREATED",
            "entitlement_id": None,
            "safety_flags": [],
            "safety_answers": {},
            "user_concerns": [],
            "diagnostic_mode": None,
            "diagnostic_status": "NORMAL",
            "unresolved_dimensions": plan.get("unresolved_dimensions") or [],
            "selected_tasks": selected,
            "core_tasks": [],
            "adaptive_tasks": [],
            "provisional_task_count": plan.get("provisional_task_count"),
            "planned_task_count": None,
            "current_task_index": 0,
            "diagnostic_offer": plan.get("diagnostic_offer"),
            "plan_rationale": plan.get("rationale"),
            "tasks": {},
            "task_results": [],
            "final_diagnostic_profile": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "error": None,
        }
        self._save(session)
        return self.public_session(session)

    def mock_pay(
        self,
        session_id: str,
        user_id: str = "anon",
        *,
        product_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if not allow_dev_bypass():
            raise PermissionError("mock pay disabled in production")
        session = self._load(session_id)
        if not session:
            raise KeyError("session not found")
        owner = session.get("user_id") or "anon"
        if owner != user_id:
            raise KeyError("session not found")
        from ..products import (
            PRODUCT_DIAGNOSTIC_FULL,
            PRODUCT_DIAGNOSTIC_UPGRADE,
            resolve_diagnostic_product,
        )

        src = session.get("source_analysis_id")
        song_owned = bool(
            src and self.entitlements.has_song_detail(user_id, src)
        )
        resolved = product_id or resolve_diagnostic_product(song_owned)
        if resolved not in (PRODUCT_DIAGNOSTIC_FULL, PRODUCT_DIAGNOSTIC_UPGRADE):
            resolved = PRODUCT_DIAGNOSTIC_FULL

        entitlement_id = f"mock_{uuid.uuid4().hex[:12]}"
        self.entitlements.grant_unlock(
            user_id,
            "DIAGNOSTIC_SESSION",
            session_id,
            "DIAGNOSTIC",
            entitlement_id,
            product_id=resolved,
            meta={"source_analysis_id": src} if src else None,
        )
        # Diagnostic Full/Upgrade always includes Song Detail for source analysis
        if src:
            if not self.entitlements.has_song_detail(user_id, src):
                self.entitlements.grant_song_detail(
                    user_id,
                    src,
                    f"bundle_{entitlement_id}",
                    product_id=resolved,
                )
            if hasattr(self.entitlements, "link_diagnostic_session"):
                self.entitlements.link_diagnostic_session(user_id, src, session_id)

        session["user_id"] = user_id
        session["entitlement_id"] = entitlement_id
        session["product_id"] = resolved
        session["status"] = "PAID"
        self._save(session)
        return self.public_session(session)

    def submit_concerns(
        self,
        session_id: str,
        user_concerns: list[dict[str, Any]],
        user_id: str = "anon",
        *,
        diagnostic_mode: Optional[str] = None,
        timbre_goal: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        session = self._require_unlocked(session_id, user_id)
        if session["status"] not in ("PAID", "SAFETY_CHECK"):
            raise ValueError("invalid status for concern intake")
        concerns = normalize_user_concerns(user_concerns)
        mode = normalize_diagnostic_mode(diagnostic_mode, concerns)
        if mode == DIAGNOSTIC_MODE_GENERAL:
            concerns = []
        elif mode == DIAGNOSTIC_MODE_CONCERN:
            if not concerns:
                raise ValueError("CONCERN_FOCUSED requires 1–3 concerns")
            if len(concerns) > 3:
                raise ValueError("max 3 concerns allowed")
        session["user_concerns"] = concerns
        session["diagnostic_mode"] = mode
        from audio_analyzer.diagnostic.timbre_goals import normalize_timbre_goal

        session["timbre_goal"] = normalize_timbre_goal(timbre_goal, concerns=concerns)
        session["safety_flag_pain"] = has_pain_safety_flag(concerns)
        src = session.get("source_analysis_id")
        plan = self._build_plan(
            src,
            user_concerns=concerns,
            pain_safety_flag=bool(session.get("safety_flag_pain")),
            diagnostic_mode=mode,
            precision=True,
        )
        selected = list(plan.get("selected_tasks") or [])
        session["selected_tasks"] = selected
        session["core_tasks"] = plan.get("core_tasks") or []
        session["adaptive_tasks"] = plan.get("adaptive_tasks") or []
        session["planned_task_count"] = plan.get("planned_task_count")
        session["provisional_task_count"] = plan.get("provisional_task_count")
        session["diagnostic_status"] = plan.get("diagnostic_status") or "NORMAL"
        session["unresolved_dimensions"] = plan.get("unresolved_dimensions") or []
        session["diagnostic_offer"] = plan.get("diagnostic_offer")
        session["plan_rationale"] = plan.get("rationale")
        session["planner_version"] = plan.get("planner_version") or session.get("planner_version")
        session["tasks"] = {tid: {"attempts": [], "passed": False} for tid in selected}
        session["current_task_index"] = 0
        # Plan is ready, but execution starts only after safety + recording choice
        session["status"] = "SAFETY_CHECK"
        self._save(session)
        _log_plan(session, persisted=True)
        return self.public_session(session)

    def submit_safety(
        self,
        session_id: str,
        answers: dict[str, bool],
        user_id: str = "anon",
    ) -> dict[str, Any]:
        session = self._require_unlocked(session_id, user_id)
        status = (session.get("status") or "").upper()
        # Idempotent / stale-UI recovery: already past safety
        if status in (
            "RECORDING_CHOICE",
            "TASKS_IN_PROGRESS",
            "READY_FOR_ANALYSIS",
            "ANALYZING",
            "COMPLETED",
        ):
            return self.public_session(session)
        if status not in ("PAID", "SAFETY_CHECK"):
            raise ValueError("invalid status for safety check")
        flags = [qid for qid, val in answers.items() if val]
        session["safety_answers"] = answers
        session["safety_flags"] = flags

        # Replan with safety state after concern intake
        mode = session.get("diagnostic_mode") or normalize_diagnostic_mode(
            None, session.get("user_concerns") or []
        )
        if not session.get("diagnostic_mode"):
            # Legacy: if concerns never submitted, default to general discovery + plan now
            session["diagnostic_mode"] = DIAGNOSTIC_MODE_GENERAL
            mode = DIAGNOSTIC_MODE_GENERAL

        plan = self._build_plan(
            session.get("source_analysis_id"),
            user_concerns=session.get("user_concerns") or [],
            pain_safety_flag=bool(session.get("safety_flag_pain")) or bool(flags),
            diagnostic_mode=mode,
            safety_flags=flags,
            precision=True,
        )
        selected = list(plan.get("selected_tasks") or [])
        session["selected_tasks"] = selected
        session["core_tasks"] = plan.get("core_tasks") or []
        session["adaptive_tasks"] = plan.get("adaptive_tasks") or []
        session["planned_task_count"] = len(selected)
        session["diagnostic_status"] = plan.get("diagnostic_status") or "NORMAL"
        session["plan_rationale"] = plan.get("rationale")
        session["diagnostic_offer"] = plan.get("diagnostic_offer")
        session["tasks"] = {
            tid: session.get("tasks", {}).get(tid) or {"attempts": [], "passed": False}
            for tid in selected
        }

        if not selected:
            # Only safety-limited may proceed with zero controlled recordings
            if session.get("diagnostic_status") == DIAGNOSTIC_STATUS_SAFETY_LIMITED or flags:
                session["diagnostic_status"] = DIAGNOSTIC_STATUS_SAFETY_LIMITED
                session["status"] = "READY_FOR_ANALYSIS"
                session["current_task_index"] = 0
            else:
                # Invariant fallback — should not happen if planner works
                from audio_analyzer.diagnostic.task_registry import PRECISION_CORE_FALLBACK

                selected = list(PRECISION_CORE_FALLBACK)
                session["selected_tasks"] = selected
                session["core_tasks"] = selected
                session["tasks"] = {tid: {"attempts": [], "passed": False} for tid in selected}
                session["planned_task_count"] = len(selected)
                session["status"] = "RECORDING_CHOICE"
                session["current_task_index"] = 0
        else:
            # User chooses FULL / PARTIAL / CONCERN_ONLY next — do not start tasks yet
            session["status"] = "RECORDING_CHOICE"
            session["current_task_index"] = 0
        self._save(session)
        _log_plan(session, persisted=True)
        try:
            print(
                "[DIAG_FLOW]",
                f"session={session_id}",
                "action=submit_safety",
                f"after={session.get('status')}",
                f"diagnostic_status={session.get('diagnostic_status')}",
                f"selected={session.get('selected_tasks') or []}",
                f"safety_flags={session.get('safety_flags') or []}",
            )
        except Exception:
            pass
        return self.public_session(session)

    def start_controlled_recordings(
        self,
        session_id: str,
        user_id: str = "anon",
    ) -> dict[str, Any]:
        """RECORDING_CHOICE → TASKS_IN_PROGRESS (explicit user choice)."""
        session = self._require_unlocked(session_id, user_id)
        status = (session.get("status") or "").upper()
        if status == "TASKS_IN_PROGRESS":
            return self.public_session(session)
        if status in ("READY_FOR_ANALYSIS", "ANALYZING", "COMPLETED"):
            return self.public_session(session)
        if status not in ("RECORDING_CHOICE", "PAID", "SAFETY_CHECK"):
            raise ValueError("invalid status for starting controlled recordings")
        selected = list(session.get("selected_tasks") or [])
        if not selected:
            self.ensure_planned_tasks(session_id, user_id=user_id)
            session = self._require_unlocked(session_id, user_id)
            selected = list(session.get("selected_tasks") or [])
        if not selected:
            if session.get("diagnostic_status") == DIAGNOSTIC_STATUS_SAFETY_LIMITED:
                session["status"] = "READY_FOR_ANALYSIS"
                self._save(session)
                return self.public_session(session)
            raise ValueError("no planned tasks to start")
        session["status"] = "TASKS_IN_PROGRESS"
        session["current_task_index"] = 0
        self._save(session)
        return self.public_session(session)

    def ensure_planned_tasks(
        self,
        session_id: str,
        user_id: str = "anon",
    ) -> dict[str, Any]:
        """Recover empty NORMAL plans without new payment / new session."""
        session = self._require_unlocked(session_id, user_id)
        status = (session.get("status") or "").upper()
        if status in ("COMPLETED", "ANALYZING"):
            return self.public_session(session)

        selected = list(session.get("selected_tasks") or [])
        diag_status = session.get("diagnostic_status") or "NORMAL"
        if selected:
            return self.public_session(session)
        if diag_status == DIAGNOSTIC_STATUS_SAFETY_LIMITED:
            return self.public_session(session)

        mode = session.get("diagnostic_mode") or normalize_diagnostic_mode(
            None, session.get("user_concerns") or []
        )
        session["diagnostic_mode"] = mode
        flags = list(session.get("safety_flags") or [])
        plan = self._build_plan(
            session.get("source_analysis_id"),
            user_concerns=session.get("user_concerns") or [],
            pain_safety_flag=bool(session.get("safety_flag_pain")) or bool(flags),
            diagnostic_mode=mode,
            safety_flags=flags,
            precision=True,
        )
        selected = list(plan.get("selected_tasks") or [])
        session["selected_tasks"] = selected
        session["core_tasks"] = plan.get("core_tasks") or []
        session["adaptive_tasks"] = plan.get("adaptive_tasks") or []
        session["planned_task_count"] = len(selected)
        session["diagnostic_status"] = plan.get("diagnostic_status") or "NORMAL"
        session["diagnostic_offer"] = plan.get("diagnostic_offer")
        session["plan_rationale"] = plan.get("rationale")
        session["tasks"] = {
            tid: session.get("tasks", {}).get(tid) or {"attempts": [], "passed": False}
            for tid in selected
        }
        if not selected and session.get("diagnostic_status") == DIAGNOSTIC_STATUS_SAFETY_LIMITED:
            session["status"] = "READY_FOR_ANALYSIS"
        elif selected:
            # Never jump from safety/recording-choice straight into task execution
            cur = (session.get("status") or "").upper()
            if cur in ("TASKS_IN_PROGRESS",):
                session["status"] = "TASKS_IN_PROGRESS"
                session["current_task_index"] = session.get("current_task_index") or 0
            elif cur in ("READY_FOR_ANALYSIS", "ANALYZING", "COMPLETED", "RECORDING_CHOICE"):
                pass
            elif cur in ("SAFETY_CHECK", "PAID", "CREATED"):
                # Keep pre-recording statuses; plan only
                pass
            else:
                session["status"] = "RECORDING_CHOICE"
                session["current_task_index"] = 0
        self._save(session)
        _log_plan(session, persisted=True)
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
        selected = list(session.get("selected_tasks") or [])
        if selected and task_id not in selected:
            raise ValueError("task not in session plan")
        if task_id not in (session.get("tasks") or {}):
            # Legacy sessions may lack selected_tasks — allow catalog/registry tasks
            if task_id not in TASK_REGISTRY and task_id not in {t["task_id"] for t in TASKS}:
                raise ValueError("unknown task")
            session.setdefault("tasks", {})[task_id] = {"attempts": [], "passed": False}
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
        audio_key = f"diagnostic_sessions/{session_id}/tasks/{task_id}/attempt_{attempt}/analysis.wav"

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

        attempt_rec["audio_storage_key"] = audio_key
        state["attempts"].append(attempt_rec)
        session["tasks"][task_id] = state

        plan_ids = list(session.get("selected_tasks") or [t["task_id"] for t in TASKS])
        # Advance index when this task passes
        if attempt_rec["passed"] and task_id in plan_ids:
            session["current_task_index"] = min(
                plan_ids.index(task_id) + 1, len(plan_ids)
            )

        required = plan_ids
        if required and all(
            is_task_terminal((session["tasks"].get(tid) or {})) for tid in required
        ):
            session["status"] = "READY_FOR_ANALYSIS"
        elif not required:
            session["status"] = "READY_FOR_ANALYSIS"
        else:
            session["status"] = "TASKS_IN_PROGRESS"

        sync_skip_provenance(session)
        self._save(session)
        try:
            from ..db.diagnostic_repo import insert_task_attempt

            insert_task_attempt(
                session_id=session_id,
                task_id=task_id,
                attempt_number=attempt,
                audio_storage_key=audio_key,
                quality_status=attempt_rec.get("quality_status"),
                passed=attempt_rec.get("passed"),
                dimension_evidence=(attempt_rec.get("result") or {}).get("dimension_evidence")
                if isinstance(attempt_rec.get("result"), dict)
                else None,
            )
        except Exception:
            from ..config import is_production

            if is_production():
                raise
        return {
            "session": self.public_session(session),
            "task_id": task_id,
            "attempt": attempt_rec,
            "retry_allowed": (not attempt_rec["passed"])
            and len(state["attempts"]) < task["max_attempts"],
        }

    def skip_task(
        self,
        session_id: str,
        task_id: str,
        user_id: str = "anon",
        *,
        reason: str = SKIP_REASON_USER_CHOICE,
    ) -> dict[str, Any]:
        """Mark one planned task as USER_SKIPPED — never invents task_results."""
        del reason  # canonical USER_CHOICE only for now
        session = self._require_unlocked(session_id, user_id)
        if session["status"] not in ("TASKS_IN_PROGRESS", "READY_FOR_ANALYSIS"):
            raise ValueError("tasks not in progress")
        selected = list(session.get("selected_tasks") or [])
        if selected and task_id not in selected:
            raise ValueError("task not in session plan")
        session.setdefault("tasks", {})
        if task_id not in session["tasks"]:
            session["tasks"][task_id] = {"attempts": [], "passed": False}
        st = session["tasks"][task_id]
        if st.get("passed"):
            raise ValueError("task already passed")
        if is_user_skipped(st):
            sync_skip_provenance(session)
            self._save(session)
            return self.public_session(session)

        session["tasks"][task_id] = mark_task_user_skipped(st)
        session["task_results"] = [
            r for r in (session.get("task_results") or []) if r.get("task_id") != task_id
        ]
        if task_id in selected:
            session["current_task_index"] = min(selected.index(task_id) + 1, len(selected))
        if all_selected_terminal(session):
            session["status"] = "READY_FOR_ANALYSIS"
        else:
            session["status"] = "TASKS_IN_PROGRESS"
        sync_skip_provenance(session)
        self._save(session)
        return self.public_session(session)

    def skip_controlled_recordings(
        self,
        session_id: str,
        user_id: str = "anon",
        *,
        remaining_only: bool = True,
    ) -> dict[str, Any]:
        """USER_SKIP remaining/all planned tasks. Preserves selected_tasks plan."""
        session = self._require_unlocked(session_id, user_id)
        if session["status"] not in (
            "RECORDING_CHOICE",
            "TASKS_IN_PROGRESS",
            "READY_FOR_ANALYSIS",
        ):
            raise ValueError("cannot skip controlled recordings in current status")

        selected = list(session.get("selected_tasks") or [])
        session.setdefault("tasks", {})
        for tid in selected:
            st = session["tasks"].get(tid) or {"attempts": [], "passed": False}
            if remaining_only and is_task_terminal(st):
                session["tasks"][tid] = st
                continue
            if st.get("passed"):
                continue
            session["tasks"][tid] = mark_task_user_skipped(st)
            session["task_results"] = [
                r for r in (session.get("task_results") or []) if r.get("task_id") != tid
            ]

        session["current_task_index"] = len(selected)
        session["status"] = "READY_FOR_ANALYSIS"
        sync_skip_provenance(session)
        self._save(session)
        return self.public_session(session)

    def _compose_premium_report(self, session: dict[str, Any]) -> dict[str, Any]:
        """Rebuild QA/goal/coaching presentation from stored session evidence.

        Does not re-run song analysis, task audio, or payment.
        """
        session_id = session["session_id"]
        song_summary = None
        song_payload = None
        src = session.get("source_analysis_id")
        if src:
            song_payload = self._load_song_payload(src)
            if song_payload:
                song_summary = {
                    "timeline_preview": [],
                    "overall": (song_payload.get("score") or {}).get("overall"),
                    "label": (song_payload.get("score") or {}).get("label"),
                }
        report = build_premium_report(
            session_id=session_id,
            task_results=session.get("task_results") or [],
            song_summary=song_summary,
            safety_flags=session.get("safety_flags") or [],
            include_scientific_debug=True,  # stored server-side for developer mode
        )
        from audio_analyzer.diagnostic.song_evidence import (
            extract_vocal_function_profile,
            wrap_song_profile_with_snapshot,
            snapshot_to_ui_acoustic_axes,
            get_canonical_snapshot,
        )

        vf, vf_path = extract_vocal_function_profile(song_payload)
        song_wrapped = wrap_song_profile_with_snapshot(song_payload or {"vocal_function_profile": vf})
        final_dx = build_final_diagnostic_profile(
            song_profile=vf,
            task_results=session.get("task_results") or [],
            plan={
                "unresolved_dimensions": session.get("unresolved_dimensions") or [],
                "selected_tasks": session.get("selected_tasks") or [],
                "user_skipped_tasks": list_user_skipped_tasks(session),
                "completed_tasks": list_completed_tasks(session),
                "safety_blocked_tasks": list_safety_blocked_tasks(session),
            },
        )
        if song_wrapped.get("canonical_song_evidence"):
            final_dx["canonical_song_evidence"] = song_wrapped["canonical_song_evidence"]
            final_dx["song_evidence_source_path"] = vf_path
        sync_skip_provenance(session)
        evidence_mode = session.get("evidence_mode") or derive_evidence_mode(session)
        concerns = session.get("user_concerns") or []
        personalized = build_personalized_qa(
            user_concerns=concerns,
            song_profile=song_wrapped,
            task_results=session.get("task_results") or [],
            fused_profile=final_dx,
            diagnostic_mode=session.get("diagnostic_mode"),
            timbre_goal=session.get("timbre_goal"),
        )
        from audio_analyzer.diagnostic.goal_planner import plan_coaching_goal

        pain = bool(
            session.get("diagnostic_status") == DIAGNOSTIC_STATUS_SAFETY_LIMITED
            or session.get("safety_flag_pain")
            or has_pain_safety_flag(concerns)
        )
        coaching_goal = plan_coaching_goal(
            user_concerns=concerns,
            timbre_goal=session.get("timbre_goal"),
            concern_evaluations=personalized.get("concern_evaluations") or [],
            song_profile=song_wrapped,
            pain=pain,
        )
        personalized["coaching_goal"] = coaching_goal
        personalized["qa_guidance_version"] = QA_GUIDANCE_VERSION
        if coaching_goal.get("coaching_protocol"):
            personalized["coaching_protocol"] = coaching_goal["coaching_protocol"]
        if coaching_goal.get("practices"):
            coach = dict(personalized.get("coaching") or {})
            goal_dirs = []
            for p in coaching_goal["practices"][:2]:
                if not p:
                    continue
                goal_dirs.append(
                    {
                        **p,
                        "mode": coaching_goal.get("mode") or "GUIDE",
                        "mode_label": "맞춤" if coaching_goal.get("mode") != "STYLE" else "탐색",
                    }
                )
            coach["practice_directions"] = goal_dirs
            personalized["coaching"] = coach
        session["timbre_goal"] = session.get("timbre_goal")
        session["coaching_goal"] = coaching_goal
        session["final_diagnostic_profile"] = final_dx
        session["evidence_mode"] = evidence_mode
        report["protocol_version"] = session.get("protocol_version") or VOCAL_DIAGNOSTIC_PROTOCOL_VERSION
        report["planner_version"] = session.get("planner_version") or PLANNER_VERSION
        report["qa_guidance_version"] = QA_GUIDANCE_VERSION
        report["goal_version"] = coaching_goal.get("goal_version") or QA_GOAL_VERSION
        report["report_logic_version"] = REPORT_LOGIC_VERSION
        report["selected_tasks"] = session.get("selected_tasks") or []
        report["completed_tasks"] = session.get("completed_tasks") or []
        report["user_skipped_tasks"] = session.get("user_skipped_tasks") or []
        report["safety_blocked_tasks"] = session.get("safety_blocked_tasks") or []
        report["core_tasks"] = session.get("core_tasks") or []
        report["adaptive_tasks"] = session.get("adaptive_tasks") or []
        report["planned_task_count"] = session.get("planned_task_count") or len(
            session.get("selected_tasks") or []
        )
        report["completed_task_count"] = len(report["completed_tasks"])
        report["user_skipped_task_count"] = len(report["user_skipped_tasks"])
        report["safety_blocked_task_count"] = len(report["safety_blocked_tasks"])
        report["valid_task_count"] = session.get("valid_task_count") or valid_controlled_task_count(
            session
        )
        report["evidence_mode"] = evidence_mode
        report["evidence_mode_label"] = EVIDENCE_MODE_COVERAGE_COPY.get(evidence_mode)
        report["report_title"] = report_title_for_mode(evidence_mode)
        report["report_subtitle"] = report_subtitle_for_mode(evidence_mode)
        report["unresolved_dimensions"] = session.get("unresolved_dimensions") or []
        report["source_analysis_id"] = session.get("source_analysis_id")
        report["diagnostic_mode"] = session.get("diagnostic_mode")
        report["diagnostic_status"] = session.get("diagnostic_status")
        report["final_diagnostic_profile"] = final_dx
        report["user_concerns"] = concerns
        report["timbre_goal"] = session.get("timbre_goal")
        report["coaching_goal"] = coaching_goal
        if coaching_goal.get("coaching_protocol"):
            report["coaching_protocol"] = coaching_goal["coaching_protocol"]
        # Debug-only coherence audit (never shown in production UI)
        try:
            from audio_analyzer.diagnostic.qa_coaching_depth import audit_report_coherence

            snap_for_audit = song_wrapped.get("canonical_song_evidence") or get_canonical_snapshot(
                song_wrapped
            )
            coherence = audit_report_coherence(snap_for_audit or {}, coaching_goal)
            report["_debug_canonical_consistency"] = coherence.get("canonical_consistency")
            report["_debug_coherence_issues"] = coherence.get("issues") or []
            if coherence.get("issues"):
                import logging

                logging.getLogger(__name__).warning(
                    "report coherence issues session=%s issues=%s",
                    session.get("session_id"),
                    coherence.get("issues"),
                )
        except Exception:
            pass
        report["personalized_qa"] = personalized
        if coaching_goal.get("practices"):
            report["improvement_priorities"] = coaching_goal["practices"]
        else:
            report["improvement_priorities"] = personalized.get("improvement_priorities") or []
        report["coaching"] = personalized.get("coaching") or {}
        report["discovered_features"] = personalized.get("discovered_features") or []
        snap = song_wrapped.get("canonical_song_evidence") or {}
        report["song_key_features"] = snap.get("key_features") or personalized.get("song_key_features") or []
        ui_axes = snapshot_to_ui_acoustic_axes(snap)
        report["canonical_song_evidence"] = {
            "source_path": snap.get("source_path"),
            "availability": snap.get("availability"),
            "key_features": snap.get("key_features") or [],
            "register": snap.get("register"),
            "effort": snap.get("effort"),
            "contact": snap.get("contact"),
            "breathiness": snap.get("breathiness"),
            "timbre": {
                "available": (snap.get("timbre") or {}).get("available"),
                "presence": (snap.get("timbre") or {}).get("presence"),
                "brightness": (snap.get("timbre") or {}).get("brightness"),
                "airiness": (snap.get("timbre") or {}).get("airiness"),
            },
            "stability": snap.get("stability"),
        }
        report["canonical_acoustic_axes"] = ui_axes
        if snap.get("register"):
            report["canonical_register"] = {
                "status": (snap.get("register") or {}).get("status"),
                "title": (snap.get("register") or {}).get("description"),
                "profile_label": (snap.get("register") or {}).get("description"),
            }
        song_vf = song_wrapped.get("vocal_function_profile") or vf or {}
        if isinstance(song_vf, dict):
            if song_vf.get("vocal_style_profile"):
                report["vocal_style_profile"] = song_vf.get("vocal_style_profile")
            if song_vf.get("vocal_type_profile"):
                report["vocal_type_profile"] = song_vf.get("vocal_type_profile")
                report["baseline_vocal_type"] = song_vf.get("vocal_type_profile")
        if personalized.get("coaching"):
            report["coaching_version"] = personalized["coaching"].get("coaching_version")
        if session.get("diagnostic_status") == DIAGNOSTIC_STATUS_SAFETY_LIMITED or session.get("safety_flag_pain") or has_pain_safety_flag(concerns):
            report["safety_note"] = (
                "통증이나 지속적인 불편감은 음향 분석만으로 원인을 판단할 수 없어요. "
                "불편한 상태에서는 강한 고음이나 큰 소리를 반복하지 마세요."
            )
        report["diagnostic_report_version"] = final_dx.get("report_version")
        return report

    def _persist_premium_report(self, session: dict[str, Any], report: dict[str, Any]) -> None:
        session_id = session["session_id"]
        report_path = self._dir(session_id) / "premium_report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        session["report_storage_key"] = f"diagnostic_sessions/{session_id}/premium_report.json"

    def analyze(self, session_id: str, user_id: str = "anon") -> dict[str, Any]:
        session = self._require_unlocked(session_id, user_id)
        if session["status"] not in ("READY_FOR_ANALYSIS", "COMPLETED"):
            raise ValueError("not ready for analysis")
        if session["status"] == "COMPLETED" and (self._dir(session_id) / "premium_report.json").exists():
            return self.get_report(session_id, user_id)

        session["status"] = "ANALYZING"
        self._save(session)
        try:
            report = self._compose_premium_report(session)
            self._persist_premium_report(session, report)
            session["status"] = "COMPLETED"
            session["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._save(session)
            return public_premium_report(report)
        except Exception as exc:  # noqa: BLE001
            session["status"] = "FAILED"
            session["error"] = str(exc)
            self._save(session)
            raise

    def regenerate_report(self, session_id: str, user_id: str = "anon") -> dict[str, Any]:
        """DEV-only: rebuild QA/goal presentation from stored evidence. Never re-analyzes audio."""
        from ..config import is_production

        if is_production():
            raise PermissionError("REGENERATE_DISABLED")
        session = self._require_unlocked(session_id, user_id)
        if session.get("status") != "COMPLETED":
            raise ValueError("report can only be regenerated when completed")
        report_path = self._dir(session_id) / "premium_report.json"
        if not report_path.exists():
            raise FileNotFoundError("report not ready")
        backup = report_path.read_text(encoding="utf-8")
        try:
            report = self._compose_premium_report(session)
            self._persist_premium_report(session, report)
            session["status"] = "COMPLETED"
            self._save(session)
            return public_premium_report(report)
        except Exception:
            report_path.write_text(backup, encoding="utf-8")
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
        owner = session.get("user_id") or "anon"
        if owner != user_id:
            raise KeyError("session not found")
        if not self._is_unlocked(session, user_id):
            return {
                "error": "REPORT_LOCKED",
                "message": "상세 발성 진단이 아직 해제되지 않았어요.",
                "session_id": session_id,
            }
        path = self._dir(session_id) / "premium_report.json"
        if not path.exists():
            status = session.get("status")
            if status == "READY_FOR_ANALYSIS":
                return self.analyze(session_id, user_id)
            if status == "ANALYZING":
                return {
                    "error": "REPORT_GENERATING",
                    "status": "ANALYZING",
                    "message": "결과를 분석하고 있어요…",
                    "session_id": session_id,
                }
            if status == "FAILED":
                return {
                    "error": "REPORT_FAILED",
                    "status": "FAILED",
                    "message": session.get("error") or "분석에 실패했어요.",
                    "session_id": session_id,
                }
            raise FileNotFoundError("report not ready")
        report = json.loads(path.read_text(encoding="utf-8"))
        try:
            from ..config import is_production

            stored = report.get("qa_guidance_version")
            if not is_production() and stored != QA_GUIDANCE_VERSION:
                print(
                    "[DIAG_STALE_REPORT]",
                    f"session_id={session_id}",
                    f"stored={stored}",
                    f"current={QA_GUIDANCE_VERSION}",
                    flush=True,
                )
        except Exception:
            pass
        if include_scientific_debug:
            return report
        return public_premium_report(report)

    def get_session(self, session_id: str, user_id: str = "anon") -> Optional[dict[str, Any]]:
        session = self._load(session_id)
        if not session:
            return None
        owner = session.get("user_id") or "anon"
        if owner != user_id:
            return None
        pub = self.public_session(session)
        pub["unlocked"] = self._is_unlocked(session, user_id)
        return pub

    def protocol(self) -> dict[str, Any]:
        return {
            "protocol_version": VOCAL_DIAGNOSTIC_PROTOCOL_VERSION,
            "planner_version": PLANNER_VERSION,
            "tasks": TASKS,
            "supported_task_ids": list(TASK_REGISTRY.keys()),
            "safety_questions": SAFETY_QUESTIONS,
            "qa_guidance_version": QA_GUIDANCE_VERSION,
            "goal_version": QA_GOAL_VERSION,
            "report_logic_version": REPORT_LOGIC_VERSION,
            "adaptive": True,
            "concern_catalog": public_concern_catalog(),
        }

    def _require_owner(self, session_id: str, user_id: str) -> dict[str, Any]:
        session = self._load(session_id)
        if not session:
            raise KeyError("session not found")
        owner = session.get("user_id") or "anon"
        if owner != user_id:
            raise KeyError("session not found")
        return session

    def _is_unlocked(self, session: dict[str, Any], user_id: str) -> bool:
        sid = str(session.get("session_id") or "")
        if sid and self.entitlements.has_session_unlock(user_id, sid):
            return True
        src = session.get("source_analysis_id")
        if src and self.entitlements.has_unlock(
            user_id, "ANALYSIS", str(src), "DIAGNOSTIC"
        ):
            return True
        return False

    def _require_unlocked(self, session_id: str, user_id: str) -> dict[str, Any]:
        session = self._require_owner(session_id, user_id)
        if not self._is_unlocked(session, user_id):
            raise PermissionError("REPORT_LOCKED")
        return session

    def public_session(self, session: dict[str, Any]) -> dict[str, Any]:
        """No filesystem paths."""
        sync_skip_provenance(session)
        tasks_pub = {}
        for tid, st in (session.get("tasks") or {}).items():
            tasks_pub[tid] = {
                "passed": st.get("passed"),
                "skipped": bool(st.get("skipped")),
                "skip_reason": st.get("skip_reason"),
                "safety_blocked": bool(st.get("safety_blocked")),
                "attempt_count": len(st.get("attempts") or []),
                "last_quality": (st.get("attempts") or [{}])[-1].get("quality")
                if st.get("attempts")
                else None,
            }
        selected = list(session.get("selected_tasks") or [])
        idx = int(session.get("current_task_index") or 0)
        tasks_state = session.get("tasks") or {}
        next_task = None
        for i, tid in enumerate(selected):
            st = tasks_state.get(tid) or {}
            if not is_task_terminal(st):
                next_task = tid
                idx = i
                break
        return {
            "session_id": session["session_id"],
            "user_id": session.get("user_id"),
            "source_analysis_id": session.get("source_analysis_id"),
            "analysis_mode": "diagnostic",
            "protocol_version": session.get("protocol_version"),
            "planner_version": session.get("planner_version"),
            "status": session.get("status"),
            "safety_flags": session.get("safety_flags") or [],
            "tasks": tasks_pub,
            "selected_tasks": selected,
            "completed_tasks": session.get("completed_tasks") or [],
            "user_skipped_tasks": session.get("user_skipped_tasks") or [],
            "safety_blocked_tasks": session.get("safety_blocked_tasks") or [],
            "valid_task_count": session.get("valid_task_count") or 0,
            "evidence_mode": session.get("evidence_mode") or derive_evidence_mode(session),
            "unresolved_dimensions": session.get("unresolved_dimensions") or [],
            "current_task_index": idx,
            "next_task_id": next_task,
            "diagnostic_offer": session.get("diagnostic_offer"),
            "user_concerns": session.get("user_concerns") or [],
            "timbre_goal": session.get("timbre_goal"),
            "diagnostic_mode": session.get("diagnostic_mode"),
            "diagnostic_status": session.get("diagnostic_status") or "NORMAL",
            "safety_flag_pain": bool(session.get("safety_flag_pain")),
            "core_tasks": session.get("core_tasks") or [],
            "adaptive_tasks": session.get("adaptive_tasks") or [],
            "planned_task_count": session.get("planned_task_count"),
            "provisional_task_count": session.get("provisional_task_count"),
            "task_plan": tasks_for_ids(selected),
            "created_at": session.get("created_at"),
            "completed_at": session.get("completed_at"),
            "error": session.get("error"),
        }
