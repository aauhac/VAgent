"""Evidence mode for Precision Diagnostic v2.4 — separate from diagnostic_mode.

diagnostic_mode = CONCERN_FOCUSED | GENERAL_DISCOVERY  (what to analyze)
evidence_mode   = FULL | PARTIAL | CONCERN_ONLY         (how much controlled evidence)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

EVIDENCE_MODE_FULL = "FULL_PRECISION"
EVIDENCE_MODE_PARTIAL = "PARTIAL_PRECISION"
EVIDENCE_MODE_CONCERN_ONLY = "CONCERN_ONLY"

SKIP_REASON_USER_CHOICE = "USER_CHOICE"

# Terminal task outcomes (not quality-retry states)
TERMINAL_PASSED = "PASSED"
TERMINAL_USER_SKIPPED = "USER_SKIPPED"
TERMINAL_SAFETY_BLOCKED = "SAFETY_BLOCKED"

EVIDENCE_MODE_USER_LABEL = {
    EVIDENCE_MODE_FULL: "추가 발성 과제까지 함께 분석",
    EVIDENCE_MODE_PARTIAL: "완료한 추가 발성 과제를 함께 분석",
    EVIDENCE_MODE_CONCERN_ONLY: "추가 녹음 없이 고민 중심으로 분석",
}

EVIDENCE_MODE_COVERAGE_COPY = {
    EVIDENCE_MODE_FULL: "노래와 추가 발성 과제를 함께 분석했어요.",
    EVIDENCE_MODE_PARTIAL: "노래와 완료한 추가 발성 과제를 함께 분석했어요.",
    EVIDENCE_MODE_CONCERN_ONLY: "기존 노래에서 확인된 발성 특징을 바탕으로 선택한 고민을 분석했어요.",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def task_state_terminal(st: Optional[dict[str, Any]]) -> Optional[str]:
    """Return terminal kind or None if still open (retryable quality fail counts as open)."""
    st = st or {}
    if st.get("passed"):
        return TERMINAL_PASSED
    if st.get("safety_blocked"):
        return TERMINAL_SAFETY_BLOCKED
    if st.get("skipped") and str(st.get("skip_reason") or SKIP_REASON_USER_CHOICE) == SKIP_REASON_USER_CHOICE:
        return TERMINAL_USER_SKIPPED
    if st.get("skipped"):
        return TERMINAL_USER_SKIPPED
    return None


def is_task_terminal(st: Optional[dict[str, Any]]) -> bool:
    return task_state_terminal(st) is not None


def is_user_skipped(st: Optional[dict[str, Any]]) -> bool:
    return task_state_terminal(st) == TERMINAL_USER_SKIPPED


def list_user_skipped_tasks(session: dict[str, Any]) -> list[str]:
    selected = list(session.get("selected_tasks") or [])
    tasks = session.get("tasks") or {}
    return [tid for tid in selected if is_user_skipped(tasks.get(tid))]


def list_completed_tasks(session: dict[str, Any]) -> list[str]:
    selected = list(session.get("selected_tasks") or [])
    tasks = session.get("tasks") or {}
    return [tid for tid in selected if task_state_terminal(tasks.get(tid)) == TERMINAL_PASSED]


def list_safety_blocked_tasks(session: dict[str, Any]) -> list[str]:
    selected = list(session.get("selected_tasks") or [])
    tasks = session.get("tasks") or {}
    return [tid for tid in selected if task_state_terminal(tasks.get(tid)) == TERMINAL_SAFETY_BLOCKED]


def valid_controlled_task_count(session: dict[str, Any]) -> int:
    """Count passed tasks that also contributed a task_result."""
    completed = set(list_completed_tasks(session))
    present = {
        tr.get("task_id")
        for tr in (session.get("task_results") or [])
        if tr.get("task_id")
    }
    return len(completed & present) if present else len(completed)


def all_selected_terminal(session: dict[str, Any]) -> bool:
    selected = list(session.get("selected_tasks") or [])
    if not selected:
        return True
    tasks = session.get("tasks") or {}
    return all(is_task_terminal(tasks.get(tid)) for tid in selected)


def derive_evidence_mode(
    session: dict[str, Any],
    *,
    diagnostic_status: Optional[str] = None,
) -> str:
    """Derive evidence_mode without overloading diagnostic_mode.

    SAFETY_LIMITED presentation stays on diagnostic_status / safety_blocked_tasks.
    evidence_mode only describes how much valid controlled evidence exists.
    """
    _ = (diagnostic_status or session.get("diagnostic_status") or "").upper()
    selected = list(session.get("selected_tasks") or [])
    skipped = list_user_skipped_tasks(session)
    valid_n = valid_controlled_task_count(session)

    # Any completed controlled evidence + user skips → partial
    if skipped and valid_n >= 1:
        return EVIDENCE_MODE_PARTIAL

    # No valid controlled results: concern-only (song + concerns). Safety UX is
    # separate via diagnostic_status / safety_blocked_tasks — not USER_SKIPPED.
    if valid_n == 0:
        if skipped:
            return EVIDENCE_MODE_CONCERN_ONLY
        if selected:
            # All remaining terminal via safety block, or empty results after plan
            return EVIDENCE_MODE_CONCERN_ONLY
        # Legacy sessions with no plan and no explicit skip list → treat as full-era
        legacy_skipped = session.get("user_skipped_tasks") or []
        return EVIDENCE_MODE_CONCERN_ONLY if legacy_skipped else EVIDENCE_MODE_FULL

    return EVIDENCE_MODE_FULL


def sync_skip_provenance(session: dict[str, Any]) -> dict[str, Any]:
    """Update completed/skipped lists + evidence_mode on session (mutates)."""
    session["completed_tasks"] = list_completed_tasks(session)
    session["user_skipped_tasks"] = list_user_skipped_tasks(session)
    session["safety_blocked_tasks"] = list_safety_blocked_tasks(session)
    session["valid_task_count"] = valid_controlled_task_count(session)
    session["evidence_mode"] = derive_evidence_mode(session)
    return session


def mark_task_user_skipped(state: Optional[dict[str, Any]]) -> dict[str, Any]:
    st = dict(state or {"attempts": [], "passed": False})
    if st.get("passed"):
        return st
    st["skipped"] = True
    st["skip_reason"] = SKIP_REASON_USER_CHOICE
    st["skipped_at"] = utc_now_iso()
    st["passed"] = False
    return st


def report_title_for_mode(evidence_mode: str) -> str:
    if evidence_mode == EVIDENCE_MODE_CONCERN_ONLY:
        return "고민 중심 분석"
    return "정밀 발성 진단"


def report_subtitle_for_mode(evidence_mode: str) -> Optional[str]:
    if evidence_mode == EVIDENCE_MODE_CONCERN_ONLY:
        return "기존 노래에서 확인된 발성 특징을 바탕으로 선택한 고민을 분석했어요."
    if evidence_mode == EVIDENCE_MODE_PARTIAL:
        return "일부 추가 과제를 건너뛰어 확인 가능한 범위 안에서 분석했어요."
    return None
