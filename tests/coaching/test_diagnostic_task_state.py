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
