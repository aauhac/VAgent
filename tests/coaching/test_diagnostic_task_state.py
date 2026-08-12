"""Mirror of miniapp diagnosticTaskState — lifecycle reset contracts."""

from __future__ import annotations


def initial_recorder_ui_state() -> dict:
    return {"recording": False, "busy": False, "seconds": 0, "msg": None}


def reset_recorder_ui_state() -> dict:
    return initial_recorder_ui_state()


def can_start_recording(state: dict, stopping: bool) -> bool:
    return (not state.get("busy")) and (not state.get("recording")) and (not stopping)


def after_quality_fail(state: dict) -> dict:
    return {**state, "busy": False, "recording": False, "seconds": 0}


def test_task_id_change_resets_seconds():
    prev = {"recording": False, "busy": True, "seconds": 5, "msg": "ok"}
    nxt = reset_recorder_ui_state()
    assert nxt["seconds"] == 0
    assert prev["seconds"] == 5  # old state discarded


def test_task_id_change_resets_busy():
    assert reset_recorder_ui_state()["busy"] is False


def test_task_id_change_resets_recording():
    assert reset_recorder_ui_state()["recording"] is False


def test_next_task_start_enabled():
    st = reset_recorder_ui_state()
    assert can_start_recording(st, stopping=False) is True


def task_progress_label(selected_tasks: list[str], task_id: str) -> str:
    order = selected_tasks or []
    idx = order.index(task_id) if task_id in order else -1
    if not order:
        return "0 / 0"
    if idx < 0:
        return f"— / {len(order)}"
    return f"{idx + 1} / {len(order)}"


def next_task_id(selected_tasks: list[str], task_id: str):
    idx = selected_tasks.index(task_id) if task_id in selected_tasks else -1
    if idx < 0:
        return None
    return selected_tasks[idx + 1] if idx + 1 < len(selected_tasks) else None


def test_adaptive_progress_two_tasks():
    order = ["sustain_a", "siren"]
    assert task_progress_label(order, "sustain_a") == "1 / 2"
    assert task_progress_label(order, "siren") == "2 / 2"
    assert next_task_id(order, "sustain_a") == "siren"
    assert next_task_id(order, "siren") is None


def test_zero_tasks_progress():
    assert task_progress_label([], "sustain_a") == "0 / 0"


def test_task_page_empty_is_not_loading():
    """Mirror of miniapp classifyTaskPageState — empty ≠ loading."""
    def classify(*, loading, error, session_loaded, protocol_loaded, selected, diag_status, task_id, has_meta):
        if loading:
            return "loading"
        if error:
            return "error"
        if not session_loaded or not protocol_loaded:
            return "loading"
        if diag_status == "SAFETY_LIMITED" and not selected:
            return "safety-limited"
        if not selected:
            return "loaded-empty"
        if not has_meta:
            return "loaded-missing-task"
        return "loaded-with-tasks"

    assert (
        classify(
            loading=False,
            error=None,
            session_loaded=True,
            protocol_loaded=True,
            selected=[],
            diag_status="NORMAL",
            task_id="sustain_a",
            has_meta=False,
        )
        == "loaded-empty"
    )
    assert (
        classify(
            loading=False,
            error="boom",
            session_loaded=True,
            protocol_loaded=True,
            selected=["sustain_a"],
            diag_status="NORMAL",
            task_id="sustain_a",
            has_meta=True,
        )
        == "error"
    )


def test_task_page_api_error_is_not_infinite_loading():
    def classify(loading, error):
        if loading:
            return "loading"
        if error:
            return "error"
        return "loaded"

    assert classify(False, "SESSION_NOT_FOUND") == "error"

def test_retry_after_quality_fail():
    st = after_quality_fail({"busy": True, "recording": True, "seconds": 5, "msg": "retry"})
    assert st["busy"] is False
    assert st["seconds"] == 0
    assert can_start_recording(st, stopping=False) is True


def test_permission_error_recovers():
    st = reset_recorder_ui_state()
    st = {**st, "msg": "permission denied"}
    assert can_start_recording(st, stopping=False) is True


def test_double_stop_guard():
    st = {"recording": True, "busy": True, "seconds": 5, "msg": None}
    assert can_start_recording(st, stopping=True) is False
