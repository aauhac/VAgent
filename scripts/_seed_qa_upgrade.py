"""Seed one analysis row for the existing-upgrade gate. DATABASE_URL must already be set."""

from backend.app.db.models import Analysis
from backend.app.db.session import reset_engine, session_scope
from backend.app.db.users import get_or_create_user

reset_engine()
with session_scope() as session:
    user = get_or_create_user(session, provider="DEV", subject="upgrade-seed")
    existing = session.get(Analysis, "c" * 32)
    if existing is None:
        session.add(
            Analysis(
                id="c" * 32,
                user_id=user.id,
                status="completed",
                original_filename="keep.wav",
            )
        )
print("seeded")
