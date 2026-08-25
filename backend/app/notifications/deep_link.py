"""Completion-alert deep link resolution.

Backs `intoss://vocalfb/notification-result`.

A Smart Message campaign has ONE fixed 이동 URL, so the click cannot carry the analysis id.
No official contract for injecting a per-send parameter into that URL has been confirmed,
so none is invented here: the server instead answers "which delivered alert does this
device most recently have?" and the app forwards to that result.

Known limitation: tapping a very old notification after newer ones have since been sent
opens the newest usable analysis, not the one that alert was about. Tapping a freshly
received alert — the normal case — always lands on the right analysis.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..identity import ResolvedIdentity
from ..services.ownership import can_access_analysis
from .completion import (
    analysis_is_completed,
    recipient_from_identity,
    sent_notifications_for_recipients,
)

logger = logging.getLogger("vagent.notifications.deep_link")


def _analysis_is_open(analysis_id: str, runtime_dir: Path | None) -> bool:
    """Exists, not deleted, and actually has a result to open."""
    try:
        from ..db.analysis_repo import db_enabled
        from ..db.models import Analysis
        from ..db.session import session_scope

        if db_enabled():
            with session_scope() as session:
                row = session.get(Analysis, analysis_id)
                if row is None:
                    return False
                if row.deleted_at is not None:
                    return False
                if str(row.status or "").lower() == "deleted":
                    return False
    except Exception:
        # Storage trouble must not hand out a link to an analysis we cannot vouch for.
        return False
    return analysis_is_completed(analysis_id, runtime_dir)


def resolve_latest_sent_analysis_for_identity(
    identities: list[ResolvedIdentity],
    runtime_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Newest delivered completion alert this request may actually open.

    `identities` are the identities the request legitimately presented — a verified Toss
    session and/or the client-asserted anonymous header. Their recipients scope the query;
    nothing outside that scope is ever read.

    Both are needed together because the payment fix migrates an anonymous user's analyses
    onto the verified Toss user at login while the notification keeps its ANON recipient.
    Access is still decided by the normal `can_access_analysis` gate, so an anonymous
    header alone cannot reopen an analysis that now belongs to a verified user.

    Deleted or unfinished analyses are skipped rather than ending the search, so a newer
    deleted alert does not hide an older usable one.
    """
    if not identities:
        return None
    recipients = []
    for ident in identities:
        try:
            recipients.append(recipient_from_identity(ident))
        except ValueError:
            continue
    if not recipients:
        return None

    for record in sent_notifications_for_recipients(recipients, runtime_dir=runtime_dir):
        analysis_id = str(record.get("analysis_id") or "")
        if not analysis_id or not _analysis_is_open(analysis_id, runtime_dir):
            continue
        if not any(
            can_access_analysis(ident.subject, analysis_id, runtime_dir) for ident in identities
        ):
            continue
        return {"analysis_id": analysis_id, "sent_at": record.get("sent_at")}
    return None
