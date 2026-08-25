"""Production readiness checks for analysis-complete Smart Message send."""

from __future__ import annotations

from .completion import analysis_complete_template_set_code


def validate_notification_production_config() -> list[str]:
    """
    Return blocker codes when Smart Message send config is incomplete.
    Independent of PAYMENTS_ENABLED — notification may be ON while payments are OFF.
    deploymentId belongs to /messenger/send-test-message and is not a live-send
    prerequisite. Does not print secret values.
    """
    blockers: list[str] = []
    if not analysis_complete_template_set_code():
        blockers.append("NOTIFICATION_TEMPLATE_SET_MISSING")
    return blockers
