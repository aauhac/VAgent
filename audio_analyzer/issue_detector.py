"""Legacy issue detector disabled for skill scoring.

v2 uses phonation_instability timeline events instead of global pitch deviation.
"""


def detect_issues(*_args, **_kwargs) -> list:
    return []


def detect_issue_events(*_args, **_kwargs) -> list:
    return []
