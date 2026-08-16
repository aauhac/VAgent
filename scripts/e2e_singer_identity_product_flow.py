# -*- coding: utf-8 -*-
"""Dev demo: product integration artifacts from person_drowning_movie 11-song fixture."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.app.services.personal_vocal_baseline import compare_progress, extract_canonical  # noqa: E402
from backend.app.services.voice_profile import PRODUCTION_STRATEGY  # noqa: E402


def main() -> int:
    out = REPO / "singer_identity_output" / "product_integration_demo" / "person_drowning_movie"
    out.mkdir(parents=True, exist_ok=True)

    profile_v3 = REPO / "singer_identity_output" / "confirmed_profile_v3" / "person_drowning_movie"
    confirmed = []
    if (profile_v3 / "confirmed_recordings.csv").exists():
        import csv

        with (profile_v3 / "confirmed_recordings.csv").open(encoding="utf-8") as f:
            confirmed = list(csv.DictReader(f))

    incremental = []
    for i, row in enumerate(confirmed, start=1):
        status = "INITIAL" if i == 1 else ("DEVELOPING" if i < 5 else "EXPANDED")
        incremental.append(
            {
                "step": i,
                "filename": row.get("filename"),
                "audio_id": row.get("audio_id"),
                "profile_status": status,
                "profile_version": i,
                "label_source": "USER_ENROLLED",
                "strategy": PRODUCTION_STRATEGY,
            }
        )

    voice_profile = {
        "singer_id": "person_drowning_movie",
        "enabled": False,
        "production_feature": "OFF",
        "implementation": "READY",
        "multi_singer_gate": "INSUFFICIENT_DATA",
        "recording_count": len(confirmed),
        "profile_status": "EXPANDED" if len(confirmed) >= 5 else "DEVELOPING",
        "strategy": PRODUCTION_STRATEGY,
        "k2_production_enabled": False,
        "global_identification_user_facing": False,
        "current_user_verification_first": True,
        "note": "Demo fixture only — not production DB seed",
    }
    (out / "voice_profile.json").write_text(json.dumps(voice_profile, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "incremental_enrollment.json").write_text(
        json.dumps(incremental, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # verification + shadow from v3 love again LOO if present
    summary = {}
    if (profile_v3 / "run_summary.json").exists():
        summary = json.loads((profile_v3 / "run_summary.json").read_text(encoding="utf-8"))
    love = summary.get("love_loo") or {}
    verification = {
        "heldout": "love again.m4a",
        "production_strategy": "CENTROID",
        "production_score": love.get("centroid_similarity"),
        "production_decision": love.get("verification_decision"),
        "threshold": love.get("threshold", 0.72),
        "threshold_retuned_for_fixture": False,
    }
    shadow = {
        "production_strategy": "CENTROID",
        "production_score": love.get("centroid_similarity"),
        "production_decision": love.get("verification_decision"),
        "shadow_strategy": "K2",
        "shadow_score": love.get("k2_similarity"),
        "shadow_decision": "MATCH" if (love.get("k2_similarity") or 0) >= 0.72 else "UNCERTAIN",
        "disagreement": False,
        "user_facing_affected": False,
        "note": "Shadow-only — does not change production decision",
    }
    (out / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "shadow_k2.json").write_text(json.dumps(shadow, ensure_ascii=False, indent=2), encoding="utf-8")

    # personal baseline from audit reviews
    reviews_path = REPO / "audit_output_final_v2" / "audio_reviews.json"
    snapshots = []
    if reviews_path.exists() and confirmed:
        reviews = json.loads(reviews_path.read_text(encoding="utf-8"))
        items = reviews if isinstance(reviews, list) else reviews.get("audios") or []
        by_id = {r.get("audio_id"): r for r in items}
        for row in confirmed:
            rev = by_id.get(row.get("audio_id")) or {}
            can = extract_canonical(rev.get("canonical") or rev)
            snapshots.append(
                {
                    "filename": row.get("filename"),
                    "audio_id": row.get("audio_id"),
                    "analyzer_version": rev.get("analyzer_version") or rev.get("pipeline_version") or "audit_v2",
                    "canonical_json": can,
                }
            )

    baseline = {
        "experimental": True,
        "production_connected": False,
        "recording_count": len(snapshots),
        "expression": "현재 등록된 녹음에서 나타난 발성 특성 분포",
        "forbidden_generalization": "영구적인 발성 특성",
        "uses_ecapa_as_vocal_quality": False,
        "snapshots_available": len(snapshots),
    }
    if len(snapshots) >= 2:
        current = snapshots[-1]["canonical_json"]
        hist = snapshots[:-1]
        progress = compare_progress(
            current_canonical=current,
            historical_snapshots=hist,
            goal="REGISTER_CONNECTION",
            recent_n=5,
        )
    else:
        progress = {"status": "NO_BASELINE"}

    (out / "personal_baseline.json").write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "progress_comparison.json").write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    report = [
        "# Product Integration Demo — person_drowning_movie",
        "",
        "> 현재 등록된 11개 녹음에서 나타난 발성 특성 분포 (실험용).",
        "> 영구적인 발성 특성이라고 일반화하지 않습니다.",
        "",
        f"- Confirmed recordings: **{len(confirmed)}**",
        f"- Production strategy: **{PRODUCTION_STRATEGY}**",
        "- K2: shadow-only",
        "- Feature flags: OFF by default",
        "- Global cross-user identification (user-facing): **NO**",
        "- Current-user verification: **YES**",
        f"- love again centroid: {love.get('centroid_similarity')} → {love.get('verification_decision')}",
        f"- love again K2 shadow: {love.get('k2_similarity')}",
        "",
        "Implementation: READY · Production feature: OFF · Multi-singer gate: INSUFFICIENT_DATA",
        "",
    ]
    (out / "report.md").write_text("\n".join(report), encoding="utf-8")
    print("DEMO:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
