"""
Import existing runtime/*/ metadata into PostgreSQL (dev migration).

Does not delete runtime artifacts. Skips duplicate analysis IDs.

Usage:
  set DATABASE_URL=postgresql+psycopg://vagent:vagent@localhost:5432/vagent
  python scripts/import_runtime_metadata.py --dry-run
  python scripts/import_runtime_metadata.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import get_runtime_dir  # noqa: E402
from backend.app.db.models import Analysis, Base, Entitlement  # noqa: E402
from backend.app.db.session import require_database  # noqa: E402
from backend.app.db.users import get_or_create_user  # noqa: E402
from backend.app.jobs.runner import validate_analysis_id  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


def _read_json(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def write_backup_manifest(runtime: Path, out: Path) -> None:
    items = []
    for child in sorted(runtime.iterdir()):
        if not child.is_dir() or not validate_analysis_id(child.name):
            continue
        items.append(
            {
                "analysis_id": child.name,
                "job_status": (child / "job_status.json").exists(),
                "public_result": (child / "public_result.json").exists(),
                "analysis_json": (child / "analysis.json").exists(),
                "preview": (child / "preview.wav").exists(),
                "meta": (child / "analysis_meta.json").exists(),
            }
        )
    ents = runtime / "entitlements.json"
    payload = {
        "runtime": str(runtime.resolve()),
        "analyses": items,
        "entitlements_present": ents.exists(),
        "entitlements_bytes": ents.stat().st_size if ents.exists() else 0,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if ents.exists():
        shutil.copy2(ents, out.with_name("entitlements.backup.json"))


def import_entitlements(session: Session, runtime: Path, *, dry_run: bool) -> dict[str, int]:
    path = runtime / "entitlements.json"
    stats = {"ent_imported": 0, "ent_skipped": 0, "ent_malformed": 0, "ent_legacy": 0}
    data = _read_json(path)
    if not data:
        return stats

    for subject, blob in data.items():
        if not isinstance(blob, dict):
            stats["ent_malformed"] += 1
            continue
        if "sessions" not in blob and "analyses" not in blob:
            # legacy flat session map
            sessions = blob
            analyses = {}
            stats["ent_legacy"] += 1
        else:
            sessions = blob.get("sessions") or {}
            analyses = blob.get("analyses") or {}
        if not isinstance(sessions, dict):
            stats["ent_malformed"] += 1
            sessions = {}
        if not isinstance(analyses, dict):
            stats["ent_malformed"] += 1
            analyses = {}

        user = get_or_create_user(session, provider="DEV", subject=str(subject))
        for sid, rec in sessions.items():
            if not isinstance(rec, dict):
                stats["ent_malformed"] += 1
                continue
            from sqlalchemy import select

            existing = session.scalar(
                select(Entitlement).where(
                    Entitlement.user_id == user.id,
                    Entitlement.resource_type == "DIAGNOSTIC_SESSION",
                    Entitlement.resource_id == str(sid),
                    Entitlement.entitlement_type == "DIAGNOSTIC",
                )
            )
            if existing:
                stats["ent_skipped"] += 1
                continue
            if dry_run:
                stats["ent_imported"] += 1
                continue
            session.add(
                Entitlement(
                    user_id=user.id,
                    resource_type="DIAGNOSTIC_SESSION",
                    resource_id=str(sid),
                    entitlement_type="DIAGNOSTIC",
                    product_id=rec.get("product_id"),
                    status="ACTIVE",
                )
            )
            stats["ent_imported"] += 1
            src = (rec.get("meta") or {}).get("source_analysis_id") if isinstance(rec.get("meta"), dict) else None
            if src:
                arow = session.get(Analysis, str(src))
                if arow:
                    summary = dict(arow.public_summary or {})
                    summary["diagnostic_session_id"] = str(sid)
                    arow.public_summary = summary

        for aid, rec in analyses.items():
            if not isinstance(rec, dict):
                stats["ent_malformed"] += 1
                continue
            song = rec.get("SONG_DETAIL") or rec.get("song_detail_unlocked")
            if not song:
                continue
            from sqlalchemy import select

            existing = session.scalar(
                select(Entitlement).where(
                    Entitlement.user_id == user.id,
                    Entitlement.resource_type == "ANALYSIS",
                    Entitlement.resource_id == str(aid),
                    Entitlement.entitlement_type == "SONG_DETAIL",
                )
            )
            if existing:
                stats["ent_skipped"] += 1
                continue
            if dry_run:
                stats["ent_imported"] += 1
                continue
            session.add(
                Entitlement(
                    user_id=user.id,
                    resource_type="ANALYSIS",
                    resource_id=str(aid),
                    entitlement_type="SONG_DETAIL",
                    status="ACTIVE",
                )
            )
            stats["ent_imported"] += 1
            if rec.get("diagnostic_session_id"):
                arow = session.get(Analysis, str(aid))
                if arow:
                    summary = dict(arow.public_summary or {})
                    summary["diagnostic_session_id"] = rec["diagnostic_session_id"]
                    arow.public_summary = summary
    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=str, default=None)
    parser.add_argument("--default-user", type=str, default="demo-user")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup-manifest", type=str, default="runtime_backup_manifest.json")
    parser.add_argument("--skip-entitlements", action="store_true")
    args = parser.parse_args()

    runtime = Path(args.runtime) if args.runtime else get_runtime_dir()
    write_backup_manifest(runtime, Path(args.backup_manifest))

    engine = require_database()
    # Schema must come from alembic upgrade head — do not create_all here.
    from sqlalchemy import inspect

    insp = inspect(engine)
    if "analyses" not in insp.get_table_names():
        raise SystemExit("DB schema missing — run: alembic upgrade head")

    imported = skipped = invalid = corrupt = 0
    with Session(engine) as session:
        get_or_create_user(session, provider="DEV", subject=args.default_user)
        for child in sorted(runtime.iterdir()):
            if not child.is_dir():
                continue
            if not validate_analysis_id(child.name):
                invalid += 1
                continue
            if session.get(Analysis, child.name):
                skipped += 1
                continue
            meta = _read_json(child / "analysis_meta.json") or {}
            status = _read_json(child / "job_status.json")
            if (child / "job_status.json").exists() and status is None:
                corrupt += 1
                continue
            status = status or {}
            pub = _read_json(child / "public_result.json")
            owner_subject = meta.get("user_id") or args.default_user
            st = status.get("status") or ("completed" if pub else "failed")
            if str(st).lower() in ("queued", "analyzing") and not pub:
                st = "failed"
            if args.dry_run:
                imported += 1
                continue
            owner = get_or_create_user(session, provider="DEV", subject=str(owner_subject))
            row = Analysis(
                id=child.name,
                user_id=owner.id,
                status=str(st),
                stage=status.get("stage"),
                progress=status.get("progress") if isinstance(status.get("progress"), int) else None,
                analysis_mode=meta.get("analysis_mode"),
                input_mode=meta.get("input_mode"),
                separate=meta.get("separate"),
                original_filename=meta.get("original_filename"),
                audio_storage_key=f"{child.name}/upload",
                preview_storage_key=f"{child.name}/preview.wav" if (child / "preview.wav").exists() else None,
                result_storage_key=f"{child.name}/public_result.json" if pub else None,
                public_summary={"vocal_type": (pub or {}).get("vocal_type_teaser")} if pub else None,
                error_message=status.get("error"),
                error_code="INTERRUPTED_RESTART" if st == "failed" and status.get("stage") == "interrupted_restart" else None,
            )
            session.add(row)
            imported += 1

        ent_stats = {"ent_imported": 0, "ent_skipped": 0, "ent_malformed": 0, "ent_legacy": 0}
        if not args.skip_entitlements:
            ent_stats = import_entitlements(session, runtime, dry_run=args.dry_run)

        if not args.dry_run:
            session.commit()
        else:
            session.rollback()

    print(
        f"dry_run={args.dry_run} imported={imported} skipped={skipped} "
        f"invalid={invalid} corrupt={corrupt} "
        f"ent_imported={ent_stats['ent_imported']} ent_skipped={ent_stats['ent_skipped']} "
        f"ent_malformed={ent_stats['ent_malformed']} ent_legacy={ent_stats['ent_legacy']} "
        f"runtime={runtime}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
