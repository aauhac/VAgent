"""Legacy reconciliation for users migrated by the retired destructive path.

This module used to MOVE every row from an anonymous user onto `(TOSS, userKey)` at login.
That is exactly what emptied history when a session token expired: the anonymous user was
left owning nothing. Ownership migration is gone — `identity_links.link_identities` now
records a mapping instead, and resolution unions the identity.

What remains here is the repair job for users who went through the old path before the
mapping existed. Their hash ↔ userKey pair was never written down, so it has to be
recovered from evidence:

  1. runtime `analysis_meta.json` — stores the ORIGINAL subject at creation time, so a
     TOSS-owned analysis whose meta names an anonymous subject reveals the pair.
  2. `analysis_completion_notifications.recipient_key` — an ANON recipient on an analysis
     now owned by a TOSS user reveals the same pair.

Anything neither source covers repairs itself at that user's next login. Nothing here
moves, deletes, or duplicates rows; it only derives pairs and writes links, idempotently.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .identity_links import link_identities
from .models import Analysis, AnalysisCompletionNotification, User, UserIdentityLink

logger = logging.getLogger("vagent.identity.legacy")


def _toss_owned_analyses(session: Session) -> dict[str, str]:
    """{analysis_id: toss_user_key} for live analyses currently owned by a TOSS user."""
    owned: dict[str, str] = {}
    for row in session.scalars(select(Analysis).where(Analysis.deleted_at.is_(None))):
        user = session.get(User, row.user_id)
        if user is not None and user.external_provider == "TOSS":
            owned[str(row.id)] = str(user.external_subject)
    return owned


def derive_legacy_links(session: Session, runtime_dir: Path) -> dict[str, str]:
    """{anon_subject: toss_user_key} inferred from stored evidence. Read-only."""
    pairs: dict[str, str] = {}
    toss_owned = _toss_owned_analyses(session)
    if not toss_owned:
        return pairs

    for analysis_id, user_key in toss_owned.items():
        meta_path = Path(runtime_dir) / analysis_id / "analysis_meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        subject = str((meta or {}).get("user_id") or "").strip()
        if subject and subject != user_key:
            pairs.setdefault(subject, user_key)

    for note in session.scalars(select(AnalysisCompletionNotification)):
        user_key = toss_owned.get(str(note.analysis_id))
        if not user_key or note.recipient_kind != "ANON":
            continue
        subject = str(note.recipient_key or "").strip()
        if subject and subject != user_key:
            pairs.setdefault(subject, user_key)

    return pairs


def _classify(session: Session, subject: str, user_key: str) -> str:
    """What a dry run would do with this pair, without writing anything."""
    existing = session.scalars(
        select(UserIdentityLink).where(UserIdentityLink.anon_subject == subject).limit(1)
    ).first()
    if existing is None:
        return "to_create"
    if existing.toss_user_key != user_key:
        return "conflict"
    return "already_linked"


def reconcile_legacy_links(
    session: Session,
    runtime_dir: Path,
    *,
    apply: bool = False,
) -> Counter:
    """Derive pairs and, when `apply`, write the links. Idempotent and non-destructive.

    A dry run reports `discovered` split into `already_linked` / `to_create` / `conflict`,
    so an already-repaired database does not look like pending work. Counts only — never
    subjects or user keys.
    """
    pairs = derive_legacy_links(session, runtime_dir)
    tally: Counter = Counter()
    tally["discovered"] = len(pairs)
    for subject, user_key in pairs.items():
        tally[_classify(session, subject, user_key)] += 1
    if not apply:
        return tally
    for subject, user_key in pairs.items():
        try:
            result = link_identities(
                session, anonymous_subject=subject, toss_user_key=user_key
            )
            tally[f"applied_{str(result.get('reason')).lower()}"] += 1
        except Exception:
            logger.exception("legacy_link_failed")
            tally["applied_error"] += 1
    return tally
