# -*- coding: utf-8 -*-
"""Orchestrate full behavioral audit with checkpoints."""

from __future__ import annotations

import itertools
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

from scripts.vocal_behavioral_audit.analyze import get_or_analyze
from scripts.vocal_behavioral_audit.artifacts import (
    build_html_report,
    distribution,
    write_csv,
    write_json,
    write_jsonl,
)
from scripts.vocal_behavioral_audit.detectors import (
    audit_score,
    check_profile_goal_contradiction,
    generic_collapse_pairs,
    lint_case,
)
from scripts.vocal_behavioral_audit.diagnose import (
    axes_from_snap,
    catalog_concern_ids,
    diagnose_case,
    fingerprint_from_axes,
    prescription_family,
    safety_concern_ids,
    target_timbre_ids,
    wrap_song,
)
from scripts.vocal_behavioral_audit.discovery import (
    discover_audio_assets,
    manifest_payload,
)
from audio_analyzer.diagnostic.concerns import CONCERN_CATALOG, PAIN_CONCERN_IDS
from audio_analyzer.diagnostic.song_evidence import get_canonical_snapshot


PAIR_CATEGORY_RULES = [
    ("high_note", "control"),
    ("high_note", "timbre"),
    ("effort", "control"),
    ("timbre", "timbre"),
    ("control", "control"),
]

TRIPLE_SETS = [
    ["HIGH_NOTE_FLIPS", "HIGH_NOTE_UNSTABLE", "REGISTER_CONNECTION_DIFFICULT"],
    ["VOICE_TOO_THIN", "VOICE_TOO_DARK_MUFFLED", "TIMBRE_DISSATISFIED"],
    ["THROAT_EFFORT", "HIGH_NOTE_TOO_EFFORTFUL", "VOCAL_FATIGUE"],
    ["PAIN_WHILE_SINGING", "HIGH_NOTE_FLIPS", "HIGH_NOTE_TOO_EFFORTFUL"],
]

SAFETY_COMBOS = [
    ["PAIN_WHILE_SINGING", "HIGH_NOTE_FLIPS"],
    ["PAIN_WHILE_SINGING", "HIGH_NOTE_TOO_EFFORTFUL"],
    ["PAIN_WHILE_SINGING", "LOUD_VOICE_DIFFICULT"],
    ["PAIN_AFTER_SINGING", "VOCAL_FATIGUE"],
    ["SPEAKING_DISCOMFORT", "THROAT_EFFORT"],
]


def _checkpoint_load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"done": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"done": {}}


def _checkpoint_save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _case_key(kind: str, audio_id: str, *parts: str) -> str:
    return "|".join([kind, audio_id, *parts])


def run_audit(
    *,
    repo_root: Path,
    output_dir: Path,
    audio_root: Optional[Path] = None,
    force_reanalyze: bool = False,
    max_audios: Optional[int] = None,
    quick: bool = False,
    full: bool = False,
    skip_target_sweep: bool = False,
    skip_pairs: bool = False,
    skip_html: bool = False,
    only_concern: Optional[str] = None,
    only_audio: Optional[str] = None,
    generate_md: bool = False,
    human_validation: bool = False,
    reclassify_baseline: bool = False,
    labels_path: Optional[Path] = None,
    baseline_dir: Optional[Path] = None,
) -> dict[str, Any]:
    t0 = time.time()
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_root = output_dir / "cache"
    audit_runtime = repo_root / ".audit_runtime"
    audit_runtime.mkdir(parents=True, exist_ok=True)
    ck_path = output_dir / "checkpoint.json"
    checkpoint = _checkpoint_load(ck_path)

    roots = [str(audio_root)] if audio_root else None
    assets = discover_audio_assets(repo_root, audio_roots=roots)
    skipped = getattr(discover_audio_assets, "last_skipped", [])

    if only_audio:
        assets = [a for a in assets if only_audio in (a.audio_id, a.sha256, a.path)]
    if quick and not full:
        assets = assets[:3]
    if max_audios is not None:
        assets = assets[: max(0, int(max_audios))]

    write_json(output_dir / "audio_manifest.json", manifest_payload(assets, skipped=skipped))

    concerns = catalog_concern_ids()
    if only_concern:
        concerns = [c for c in concerns if c == only_concern]
    targets = target_timbre_ids()
    safety_ids = safety_concern_ids()

    # --- Phase: analyze once ---
    analyses: dict[str, dict[str, Any]] = {}
    songs: dict[str, dict[str, Any]] = {}
    analysis_meta: list[dict[str, Any]] = []
    analysis_failures: list[dict[str, Any]] = []

    for asset in assets:
        analysis, meta = get_or_analyze(
            asset,
            cache_root=cache_root,
            audit_runtime=audit_runtime,
            force_reanalyze=force_reanalyze,
        )
        analysis_meta.append(meta)
        if analysis is None:
            analysis_failures.append(meta)
            continue
        analyses[asset.audio_id] = analysis
        songs[asset.audio_id] = wrap_song(analysis)

    usable = [a for a in assets if a.audio_id in songs]
    write_json(
        output_dir / "analysis_meta.json",
        {"items": analysis_meta, "failures": analysis_failures},
    )

    # --- Audio axes matrix ---
    audio_axes_rows = []
    fingerprints = []
    for a in usable:
        snap = get_canonical_snapshot(songs[a.audio_id])
        axes = axes_from_snap(snap)
        fp = fingerprint_from_axes(axes)
        fingerprints.append(fp)
        from scripts.vocal_behavioral_audit.artifacts import enrich_audio_axes_display
        from scripts.vocal_behavioral_audit.report_labels import display_audio_name

        base_row = {
            "audio_id": a.audio_id,
            "file": a.path,
            "duration": a.duration_sec,
            "effort_status": axes["effort_status"],
            "effort_confidence": axes["effort_confidence"],
            "contact": axes["contact"],
            "breathiness": axes["breathiness"],
            "register_connection": axes.get("register_connection") or axes["register"],
            "register": axes.get("register_connection") or axes["register"],
            "source_balance": axes["source_balance"],
            "stability": axes["stability"],
            "presence": axes["presence"],
            "brightness": axes["brightness"],
            "airiness": axes["airiness"],
            "texture": axes["texture"],
            "harmonic_concentration": axes["harmonic_concentration"],
            "high_note_available": axes["high_note_available"],
            "fingerprint": fp,
        }
        audio_axes_rows.append(
            enrich_audio_axes_display(
                base_row,
                display_name=display_audio_name(
                    path=a.path, audio_id=a.audio_id, sha256=getattr(a, "sha256", "") or ""
                ),
            )
        )
    write_csv(output_dir / "audio_axes.csv", audio_axes_rows)

    fp_counts = Counter(fingerprints)
    identical_pairs = []
    ids_by_fp = defaultdict(list)
    for row in audio_axes_rows:
        ids_by_fp[row["fingerprint"]].append(row["audio_id"])
    for fp, ids in ids_by_fp.items():
        if len(ids) > 1:
            identical_pairs.append({"fingerprint": fp, "audio_ids": ids, "count": len(ids)})

    suspicious_sameness = (
        len(fp_counts) <= 1 and len(usable) >= 5
    ) or (len(usable) >= 8 and len(fp_counts) <= 2)

    # --- Singleton sweep ---
    singleton_rows: list[dict[str, Any]] = []
    all_findings: list[dict[str, Any]] = []
    canonical_mutations: list[dict[str, Any]] = []
    html_cases: list[dict[str, Any]] = []

    done = checkpoint.setdefault("done", {})

    for a in usable:
        song = songs[a.audio_id]
        hashes = set()
        for cid in concerns:
            key = _case_key("singleton", a.audio_id, cid)
            if key in done and not force_reanalyze:
                row = done[key]
            else:
                case = diagnose_case(song, concern_ids=[cid])
                case["audio_id"] = a.audio_id
                case["path"] = a.path
                findings = lint_case(case) + check_profile_goal_contradiction(case)
                score = audit_score(findings)
                row = {
                    **case,
                    "findings": findings,
                    "audit_score": score,
                    "audit_status": score["status"],
                    "prescription_family": prescription_family(case),
                }
                done[key] = {
                    "audio_id": a.audio_id,
                    "path": a.path,
                    "sha256": a.sha256,
                    "concern_id": cid,
                    "question_type": case.get("question_type"),
                    "canonical_hash": case.get("canonical_hash"),
                    "canonical_fingerprint": case.get("canonical_fingerprint"),
                    "canonical_axes": case.get("canonical_axes"),
                    "qa": case.get("qa"),
                    "primary_focus": case.get("primary_focus"),
                    "goal": case.get("goal"),
                    "protocol_id": case.get("protocol_id"),
                    "protocol_entry_id": case.get("protocol_entry_id"),
                    "practice_id": case.get("practice_id"),
                    "safety": case.get("safety"),
                    "focus_selection": case.get("focus_selection"),
                    "findings": findings,
                    "audit_score": score,
                    "audit_status": score["status"],
                    "prescription_family": prescription_family(case),
                    "answer_summary": case.get("answer_summary"),
                }
                row = done[key]
            hashes.add(row.get("canonical_hash"))
            singleton_rows.append(row)
            for f in row.get("findings") or []:
                all_findings.append({**f, "audio_id": a.audio_id, "concern_id": cid, "kind": "singleton"})
            html_cases.append(
                {
                    "audio_id": a.audio_id,
                    "concern_id": cid,
                    "primary_focus": row.get("primary_focus"),
                    "protocol_id": row.get("protocol_id"),
                    "audit_status": row.get("audit_status"),
                    "audit_score": row.get("audit_score"),
                    "findings": row.get("findings"),
                    "focus_selection": row.get("focus_selection"),
                }
            )
        if len(hashes) > 1:
            canonical_mutations.append(
                {
                    "audio_id": a.audio_id,
                    "hashes": sorted(h for h in hashes if h),
                    "code": "CANONICAL_MUTATION_BY_CONCERN",
                    "severity": "CRITICAL",
                }
            )
            all_findings.append(
                {
                    "severity": "CRITICAL",
                    "code": "CANONICAL_MUTATION_BY_CONCERN",
                    "detail": str(sorted(hashes)),
                    "audio_id": a.audio_id,
                    "concern_id": "*",
                    "kind": "canonical",
                }
            )

    write_jsonl(output_dir / "concern_singletons.jsonl", singleton_rows)
    _checkpoint_save(ck_path, checkpoint)

    # concern matrix + focus distribution
    concern_matrix = []
    focus_dist_rows = []
    for cid in concerns:
        subset = [r for r in singleton_rows if r.get("concern_id") == cid]
        focuses = [r.get("primary_focus") for r in subset]
        protocols = [r.get("protocol_id") for r in subset]
        families = [r.get("prescription_family") for r in subset]
        concern_matrix.append(
            {
                "concern_id": cid,
                "category": CONCERN_CATALOG.get(cid, {}).get("category"),
                "cases": len(subset),
                "unique_focus": len(set(focuses)),
                "unique_protocol": len(set(protocols)),
                "unique_prescription_family": len(set(families)),
                "fail_count": sum(1 for r in subset if r.get("audit_status") == "FAIL"),
                "warn_count": sum(1 for r in subset if r.get("audit_status") == "WARN"),
            }
        )
        for focus, cnt in Counter(focuses).items():
            focus_dist_rows.append({"concern_id": cid, "primary_focus": focus, "count": cnt})
    write_csv(output_dir / "concern_matrix.csv", concern_matrix)
    write_csv(output_dir / "concern_focus_distribution.csv", focus_dist_rows)

    # Non-adaptive warnings: multi-fp audios but concern always same coaching
    # Safety concerns intentionally share SAFETY_STOP — exclude from diversity WARN
    non_adaptive = []
    safety_set = set(safety_concern_ids()) | set(PAIN_CONCERN_IDS)
    if len(set(fingerprints)) >= 3:
        for cid in concerns:
            if cid in safety_set or CONCERN_CATALOG.get(cid, {}).get("category") == "safety":
                continue
            subset = [r for r in singleton_rows if r.get("concern_id") == cid]
            # map audio fp
            fps = []
            coach = []
            for r in subset:
                ax = next((x for x in audio_axes_rows if x["audio_id"] == r["audio_id"]), None)
                if not ax:
                    continue
                fps.append(ax["fingerprint"])
                coach.append(
                    (
                        r.get("primary_focus"),
                        r.get("protocol_id"),
                        r.get("prescription_family"),
                    )
                )
            if len(set(fps)) >= 3 and len(set(coach)) == 1:
                non_adaptive.append(
                    {
                        "concern_id": cid,
                        "code": "POSSIBLE_NON_ADAPTIVE_COACHING",
                        "unique_audio_fps": len(set(fps)),
                        "unique_coaching": 1,
                    }
                )
                all_findings.append(
                    {
                        "severity": "WARN",
                        "code": "LOW_COACHING_DIVERSITY",
                        "detail": cid,
                        "audio_id": "*",
                        "concern_id": cid,
                        "kind": "diversity",
                    }
                )

    # Generic collapse — classified
    collapse_rows = generic_collapse_pairs(singleton_rows, threshold=0.88)
    write_csv(output_dir / "generic_collapse.csv", collapse_rows)
    expected_shared = [r for r in collapse_rows if r.get("classification") == "EXPECTED_SHARED_PROTOCOL"]
    over_shared = [r for r in collapse_rows if r.get("classification") == "OVER_SHARED_PRESCRIPTION"]
    wrong_collapse = [r for r in collapse_rows if r.get("classification") == "WRONG_GENERIC_COLLAPSE"]
    # Legacy alias count for dashboards that still look for GENERIC_COLLAPSE
    generic_warns = over_shared + wrong_collapse
    for r in wrong_collapse:
        all_findings.append(
            {
                "severity": "FAIL",
                "code": "WRONG_GENERIC_COLLAPSE",
                "detail": f"{r.get('concern_a')}+{r.get('concern_b')} sim={r.get('similarity')}",
                "audio_id": r.get("audio"),
                "concern_id": f"{r.get('concern_a')}+{r.get('concern_b')}",
                "kind": "collapse",
            }
        )
    for r in over_shared:
        all_findings.append(
            {
                "severity": "WARN",
                "code": "OVER_SHARED_PRESCRIPTION",
                "detail": f"{r.get('concern_a')}+{r.get('concern_b')}",
                "audio_id": r.get("audio"),
                "concern_id": f"{r.get('concern_a')}+{r.get('concern_b')}",
                "kind": "collapse",
            }
        )

    # Unsupported claim classification trace (all candidate claims)
    from scripts.vocal_behavioral_audit.claim_lint import (
        classify_claim_spans,
        evaluate_claim_against_axes,
    )

    claim_traces: list[dict[str, Any]] = []
    claim_class_counts: Counter = Counter()
    for r in singleton_rows:
        axes = r.get("canonical_axes") or {}
        blobs = [
            str((r.get("qa") or {}).get("answer") or ""),
            str(((r.get("qa") or {}).get("prescription") or {}).get("instruction") or ""),
            str(r.get("answer_summary") or ""),
        ]
        for blob in blobs:
            for span in classify_claim_spans(blob):
                evaluated = evaluate_claim_against_axes(span, axes)
                claim_class_counts[str(evaluated.get("classification"))] += 1
                claim_traces.append(
                    {
                        "audio": r.get("audio_id"),
                        "concern": r.get("concern_id"),
                        "claim_text": evaluated.get("sentence"),
                        "claimed_axis": evaluated.get("axis"),
                        "claimed_state": evaluated.get("claimed_state"),
                        "canonical_available": evaluated.get("canonical_available"),
                        "canonical_value": evaluated.get("canonical_value"),
                        "classification": evaluated.get("classification"),
                        "detail": evaluated.get("detail"),
                        "lint_rule": "claim_lint_v1",
                    }
                )
    write_jsonl(output_dir / "remediation_unsupported_claims.jsonl", claim_traces)

    # HIGH_NOTE_CANNOT_REACH breakdown
    hn_rows = []
    for r in singleton_rows:
        if r.get("concern_id") != "HIGH_NOTE_CANNOT_REACH":
            continue
        axes = r.get("canonical_axes") or {}
        sel = r.get("focus_selection") or {}
        reason = sel.get("reason") or "UNKNOWN"
        focus = r.get("primary_focus")
        hn_rows.append(
            {
                "audio_id": r.get("audio_id"),
                "high_note_direct_available": axes.get("high_note_available"),
                "register_connection": axes.get("register_connection") or axes.get("register"),
                "effort_status": axes.get("effort_status"),
                "effort_reliable": axes.get("effort_reliable"),
                "stability": axes.get("stability"),
                "presence": axes.get("presence"),
                "selected_focus": focus,
                "selection_reason": reason,
                "fallback_used": bool(sel.get("fallback_used")),
                "protocol_id": r.get("protocol_id"),
            }
        )
    write_csv(output_dir / "high_note_cannot_reach_breakdown.csv", hn_rows)
    hn_reason_dist = distribution(r.get("selection_reason") for r in hn_rows)
    hn_fallback_register = sum(
        1
        for r in hn_rows
        if r.get("selected_focus") == "REGISTER_CONNECTION"
        and r.get("selection_reason") in ("SEMANTIC_FALLBACK", "GENERAL_HIGH_NOTE_ACCESS", "UNKNOWN")
        and str(r.get("register_connection") or "") not in ("PARTIAL", "DISRUPTED")
    )
    hn_evidence_register = sum(
        1
        for r in hn_rows
        if r.get("selected_focus") == "REGISTER_CONNECTION"
        and r.get("selection_reason") == "REGISTER_EVIDENCE"
    )

    # --- Target sweep ---
    target_rows = []
    if not skip_target_sweep:
        for a in usable:
            song = songs[a.audio_id]
            base_hash = None
            for tid in targets:
                key = _case_key("target", a.audio_id, "TIMBRE_DISSATISFIED", tid)
                if key in done and not force_reanalyze:
                    row = done[key]
                else:
                    case = diagnose_case(
                        song,
                        concern_ids=["TIMBRE_DISSATISFIED"],
                        timbre_goal={"id": tid},
                    )
                    case["audio_id"] = a.audio_id
                    findings = lint_case(case)
                    if base_hash is None:
                        # compute from first
                        base_hash = case["canonical_hash"]
                    if case["canonical_hash"] != (
                        done.get(_case_key("target", a.audio_id, "TIMBRE_DISSATISFIED", targets[0]), {}) or {}
                    ).get("canonical_hash", case["canonical_hash"]):
                        pass
                    row = {
                        "audio_id": a.audio_id,
                        "concern_id": "TIMBRE_DISSATISFIED",
                        "target_id": tid,
                        "canonical_hash": case["canonical_hash"],
                        "primary_focus": case.get("primary_focus"),
                        "protocol_id": case.get("protocol_id"),
                        "goal_title": (case.get("goal") or {}).get("goal_title"),
                        "protocol_entry_title": case.get("protocol_entry_title"),
                        "findings": findings,
                    }
                    # mutation vs first target of this audio
                    done[key] = row
                target_rows.append(row)
            # check mutations within audio targets
            hashes = {r["canonical_hash"] for r in target_rows if r["audio_id"] == a.audio_id}
            if len(hashes) > 1:
                all_findings.append(
                    {
                        "severity": "CRITICAL",
                        "code": "TARGET_MUTATES_ACOUSTIC_TRUTH",
                        "detail": str(hashes),
                        "audio_id": a.audio_id,
                        "concern_id": "TIMBRE_DISSATISFIED",
                        "kind": "target",
                    }
                )
                for r in target_rows:
                    if r["audio_id"] == a.audio_id:
                        r.setdefault("findings", []).append(
                            {
                                "severity": "CRITICAL",
                                "code": "TARGET_MUTATES_ACOUSTIC_TRUTH",
                                "detail": "hash drift across targets",
                            }
                        )
        write_csv(
            output_dir / "target_matrix.csv",
            [
                {
                    "audio_id": r["audio_id"],
                    "target_id": r["target_id"],
                    "canonical_hash": r["canonical_hash"],
                    "primary_focus": r.get("primary_focus"),
                    "protocol_id": r.get("protocol_id"),
                    "goal_title": r.get("goal_title"),
                    "protocol_entry_title": r.get("protocol_entry_title"),
                }
                for r in target_rows
            ],
        )
    _checkpoint_save(ck_path, checkpoint)

    # --- Safety sweep ---
    safety_rows = []
    for a in usable:
        song = songs[a.audio_id]
        for cid in safety_ids:
            if only_concern and cid != only_concern:
                continue
            key = _case_key("safety", a.audio_id, cid)
            if key in done and not force_reanalyze:
                row = done[key]
            else:
                case = diagnose_case(song, concern_ids=[cid])
                case["audio_id"] = a.audio_id
                findings = lint_case(case)
                row = {
                    "audio_id": a.audio_id,
                    "concern_ids": [cid],
                    "primary_focus": case.get("primary_focus"),
                    "protocol_id": case.get("protocol_id"),
                    "practice_id": case.get("practice_id"),
                    "pain": True,
                    "findings": findings,
                    "audit_status": audit_score(findings)["status"],
                }
                done[key] = row
            safety_rows.append(row)
            for f in row.get("findings") or []:
                all_findings.append({**f, "audio_id": a.audio_id, "concern_id": cid, "kind": "safety"})

        for combo in SAFETY_COMBOS:
            if any(c not in CONCERN_CATALOG for c in combo):
                continue
            # normalize_user_concerns max 3 — combo is 2
            key = _case_key("safety_combo", a.audio_id, *combo)
            if key in done and not force_reanalyze:
                row = done[key]
            else:
                case = diagnose_case(song, concern_ids=combo)
                case["audio_id"] = a.audio_id
                findings = lint_case(case)
                row = {
                    "audio_id": a.audio_id,
                    "concern_ids": combo,
                    "primary_focus": case.get("primary_focus"),
                    "protocol_id": case.get("protocol_id"),
                    "practice_id": case.get("practice_id"),
                    "pain": True,
                    "findings": findings,
                    "audit_status": audit_score(findings)["status"],
                }
                done[key] = row
            safety_rows.append(row)
            for f in row.get("findings") or []:
                all_findings.append(
                    {
                        **f,
                        "audio_id": a.audio_id,
                        "concern_id": "+".join(combo),
                        "kind": "safety_combo",
                    }
                )
    write_csv(
        output_dir / "safety_matrix.csv",
        [
            {
                "audio_id": r["audio_id"],
                "concern_ids": ",".join(r.get("concern_ids") or []),
                "primary_focus": r.get("primary_focus"),
                "protocol_id": r.get("protocol_id"),
                "practice_id": r.get("practice_id"),
                "audit_status": r.get("audit_status"),
                "finding_codes": ",".join(f.get("code", "") for f in (r.get("findings") or [])),
            }
            for r in safety_rows
        ],
    )
    _checkpoint_save(ck_path, checkpoint)

    # --- Pairs / triples ---
    pair_rows = []
    triple_rows = []
    if not skip_pairs and usable:
        pair_audios = usable[:3] if full or quick else usable[:1]
        # Prefer all unordered pairs when cheap; else category pairs
        all_pairs = list(itertools.combinations(concerns, 2))
        if len(all_pairs) > 400:
            # category-based
            by_cat = defaultdict(list)
            for cid in concerns:
                by_cat[CONCERN_CATALOG[cid]["category"]].append(cid)
            all_pairs = []
            for ca, cb in PAIR_CATEGORY_RULES:
                for x in by_cat.get(ca, []):
                    for y in by_cat.get(cb, []):
                        if x >= y and ca == cb:
                            continue
                        if x == y:
                            continue
                        all_pairs.append(tuple(sorted((x, y))))
            # safety × each category
            for sid in safety_ids:
                for cat, ids in by_cat.items():
                    if cat == "safety":
                        continue
                    for oid in ids[:2]:
                        all_pairs.append(tuple(sorted((sid, oid))))
            all_pairs = sorted(set(all_pairs))

        for a in pair_audios:
            song = songs[a.audio_id]
            for c1, c2 in all_pairs:
                key = _case_key("pair", a.audio_id, c1, c2)
                if key in done and not force_reanalyze:
                    row = done[key]
                else:
                    case = diagnose_case(song, concern_ids=[c1, c2])
                    findings = lint_case(case) + check_profile_goal_contradiction(case)
                    axes = case.get("canonical_axes") or {}
                    reg = str(axes.get("register_connection") or axes.get("register") or "")
                    # Strong functional bottleneck must beat STYLE/TIMBRE primary
                    bottleneck = (
                        ("HIGH_NOTE_FLIPS" in (c1, c2) or "HIGH_NOTE_CANNOT_REACH" in (c1, c2)
                         or "REGISTER_CONNECTION_DIFFICULT" in (c1, c2))
                        and "TIMBRE_DISSATISFIED" in (c1, c2)
                    ) or (
                        reg == "DISRUPTED"
                        and "TIMBRE_DISSATISFIED" in (c1, c2)
                    )
                    if bottleneck and case.get("primary_focus") in ("STYLE", "TIMBRE"):
                        findings.append(
                            {
                                "severity": "FAIL",
                                "code": "TARGET_OVERRIDES_BOTTLENECK",
                                "detail": f"STYLE/TIMBRE over functional; reg={reg}",
                            }
                        )
                    row = {
                        "audio_id": a.audio_id,
                        "concern_a": c1,
                        "concern_b": c2,
                        "primary_focus": case.get("primary_focus"),
                        "protocol_id": case.get("protocol_id"),
                        "goal_title": (case.get("goal") or {}).get("goal_title"),
                        "secondary_target": (case.get("goal") or {}).get("secondary_target"),
                        "canonical_axes": axes,
                        "findings": findings,
                        "audit_status": audit_score(findings)["status"],
                    }
                    done[key] = row
                pair_rows.append(row)
                for f in row.get("findings") or []:
                    all_findings.append(
                        {
                            **f,
                            "audio_id": a.audio_id,
                            "concern_id": f"{c1}+{c2}",
                            "kind": "pair",
                        }
                    )

            for triple in TRIPLE_SETS:
                if any(c not in CONCERN_CATALOG for c in triple):
                    continue
                # max 3 concerns
                key = _case_key("triple", a.audio_id, *triple)
                if key in done and not force_reanalyze:
                    row = done[key]
                else:
                    case = diagnose_case(song, concern_ids=triple)
                    findings = lint_case(case) + check_profile_goal_contradiction(case)
                    row = {
                        "audio_id": a.audio_id,
                        "concerns": triple,
                        "primary_focus": case.get("primary_focus"),
                        "protocol_id": case.get("protocol_id"),
                        "findings": findings,
                        "audit_status": audit_score(findings)["status"],
                    }
                    done[key] = row
                triple_rows.append(row)
        write_csv(
            output_dir / "pair_matrix.csv",
            [
                {
                    "audio_id": r["audio_id"],
                    "concern_a": r.get("concern_a"),
                    "concern_b": r.get("concern_b"),
                    "primary_focus": r.get("primary_focus"),
                    "protocol_id": r.get("protocol_id"),
                    "audit_status": r.get("audit_status"),
                    "finding_codes": ",".join(f.get("code", "") for f in (r.get("findings") or [])),
                }
                for r in pair_rows
            ],
        )
        write_json(output_dir / "triple_stress.json", triple_rows)
    _checkpoint_save(ck_path, checkpoint)

    # Aggregate failure artifacts
    coherence_failures = [
        f for f in all_findings if f.get("code") in (
            "FOCUS_PROTOCOL_MISMATCH",
            "FOCUS_PRACTICE_MISMATCH",
            "PROFILE_GOAL_DIRECT_CONTRADICTION",
            "CANONICAL_MUTATION_BY_CONCERN",
            "TARGET_MUTATES_ACOUSTIC_TRUTH",
            "UNSUPPORTED_ACOUSTIC_CLAIM",
        )
    ]
    qa_lint_failures = [
        f
        for f in all_findings
        if f.get("code")
        in (
            "ABSTRACT_ACTION",
            "USER_ENGLISH_TOKEN",
            "ANATOMICAL_DIAGNOSIS",
            "TERMINAL_DISCLAIMER",
            "DUPLICATE_SUCCESS_CUE",
            "EMPTY_QA",
            "MISSING_PRESCRIPTION",
            "PLANNER_COPY",
        )
    ]
    failures = [f for f in all_findings if f.get("severity") in ("CRITICAL", "FAIL")]
    write_json(output_dir / "coherence_failures.json", coherence_failures)
    write_json(output_dir / "qa_lint_failures.json", qa_lint_failures)
    write_json(output_dir / "failures.json", failures)

    code_counts = Counter(f.get("code") for f in all_findings)
    top_failures = [
        {"code": c, "count": n}
        for c, n in code_counts.most_common()
        if any(f.get("code") == c and f.get("severity") in ("CRITICAL", "FAIL") for f in all_findings)
    ][:20]
    top_warnings = [
        {"code": c, "count": n}
        for c, n in code_counts.most_common()
        if any(f.get("code") == c and f.get("severity") == "WARN" for f in all_findings)
    ][:20]

    missing_rx = sum(1 for f in all_findings if f.get("code") == "MISSING_PRESCRIPTION")
    abstract_n = sum(1 for f in all_findings if f.get("code") == "ABSTRACT_ACTION")
    english_n = sum(1 for f in all_findings if f.get("code") == "USER_ENGLISH_TOKEN")
    anatomy_n = sum(1 for f in all_findings if f.get("code") == "ANATOMICAL_DIAGNOSIS")
    safety_viol = sum(1 for f in all_findings if f.get("code") == "SAFETY_ACTIVE_EXERCISE")
    focus_mm = sum(1 for f in all_findings if f.get("code") == "FOCUS_PROTOCOL_MISMATCH")
    practice_mm = sum(1 for f in all_findings if f.get("code") == "FOCUS_PRACTICE_MISMATCH")
    target_override_n = sum(1 for f in all_findings if f.get("code") == "TARGET_OVERRIDES_BOTTLENECK")
    true_unsupported = sum(
        1
        for f in all_findings
        if f.get("code") == "UNSUPPORTED_ACOUSTIC_CLAIM"
        and f.get("claim_classification", "TRUE_POSITIVE") == "TRUE_POSITIVE"
    )
    # Dump target-override cases (if any remain) for remediation artifact
    override_cases = [
        r
        for r in pair_rows
        if any(f.get("code") == "TARGET_OVERRIDES_BOTTLENECK" for f in (r.get("findings") or []))
    ]
    write_json(output_dir / "remediation_target_override_cases.json", override_cases)

    thin_dist = distribution(
        r.get("primary_focus") for r in singleton_rows if r.get("concern_id") == "VOICE_TOO_THIN"
    )
    reach_dist = distribution(
        r.get("primary_focus")
        for r in singleton_rows
        if r.get("concern_id") == "HIGH_NOTE_CANNOT_REACH"
    )

    def _axis_sensitivity(rows: list[dict[str, Any]], key: str, unavailable: set[str]) -> dict[str, Any]:
        vals = [str(r.get(key) or "") for r in rows]
        dist = distribution(vals)
        n = len(vals) or 1
        avail = sum(1 for v in vals if v not in unavailable and v)
        return {
            "distribution": dist,
            "available": avail,
            "total": len(vals),
            "available_rate": round(avail / n, 4),
            "unknown_rate": round(sum(1 for v in vals if v in unavailable) / n, 4),
            "class_imbalance_warning": (
                avail >= 10
                and max((c for k, c in dist.items() if k not in unavailable), default=0) / max(avail, 1) >= 0.75
            ),
        }

    detector_sensitivity = {
        "effort": _axis_sensitivity(audio_axes_rows, "effort_status", {"UNKNOWN", ""}),
        "breathiness": _axis_sensitivity(audio_axes_rows, "breathiness", {"UNKNOWN", "UNAVAILABLE", ""}),
        "brightness": _axis_sensitivity(audio_axes_rows, "brightness", {"UNAVAILABLE", ""}),
        "presence": _axis_sensitivity(audio_axes_rows, "presence", {"UNAVAILABLE", ""}),
        "human_labeled_validation_recommended": ["EFFORT", "BREATHINESS", "BRIGHTNESS", "PRESENCE"],
        "threshold_changed": False,
    }

    # Top repeated prescriptions
    presc_counter = Counter()
    for r in singleton_rows:
        inst = str(((r.get("qa") or {}).get("prescription") or {}).get("instruction") or "")[:120]
        if inst:
            presc_counter[inst] += 1

    target_mutations = sum(
        1 for f in all_findings if f.get("code") == "TARGET_MUTATES_ACOUSTIC_TRUTH"
    )
    overlays = {
        (r.get("target_id"), r.get("protocol_entry_title") or r.get("goal_title"))
        for r in target_rows
    }

    summary = {
        "audit_version": "behavioral-audit-remediation-v1",
        "elapsed_sec": round(time.time() - t0, 2),
        "audios": len(usable),
        "audios_discovered": len(assets),
        "audios_skipped_files": len(skipped),
        "analysis_failures": len(analysis_failures),
        "cache_hits": sum(1 for m in analysis_meta if m.get("cache_hit") or m.get("hint_hit")),
        "fresh_analyses": sum(1 for m in analysis_meta if m.get("analyzed")),
        "analyzed_once": True,
        "concerns_catalog": len(catalog_concern_ids()),
        "concerns_swept": len(concerns),
        "missing_concerns": [c for c in catalog_concern_ids() if c not in concerns],
        "singleton_cases": len(singleton_rows),
        "coverage": f"{len(concerns)}/{len(catalog_concern_ids())}",
        "canonical_mutations": len(canonical_mutations),
        "missing_prescriptions": missing_rx,
        "generic_collapse_warnings": len(generic_warns),
        "collapse_classes": {
            "EXPECTED_SHARED_PROTOCOL": len(expected_shared),
            "OVER_SHARED_PRESCRIPTION": len(over_shared),
            "WRONG_GENERIC_COLLAPSE": len(wrong_collapse),
        },
        "unsupported_claim_classes": dict(claim_class_counts),
        "true_unsupported_acoustic_claims": true_unsupported,
        "target_overrides_bottleneck": target_override_n,
        "focus_protocol_mismatches": focus_mm,
        "focus_practice_mismatches": practice_mm,
        "safety_violations": safety_viol,
        "anatomical_claims": anatomy_n,
        "abstract_actions": abstract_n,
        "english_tokens": english_n,
        "unique_canonical_fingerprints": len(set(fingerprints)),
        "suspicious_audio_sameness": suspicious_sameness,
        "identical_fingerprint_groups": identical_pairs,
        "axis_distributions": {
            "effort": distribution(r["effort_status"] for r in audio_axes_rows),
            "contact": distribution(r["contact"] for r in audio_axes_rows),
            "breathiness": distribution(r["breathiness"] for r in audio_axes_rows),
            "register_connection": distribution(
                r.get("register_connection") or r.get("register") for r in audio_axes_rows
            ),
            "source_balance": distribution(r["source_balance"] for r in audio_axes_rows),
            "stability": distribution(r["stability"] for r in audio_axes_rows),
            "presence": distribution(r["presence"] for r in audio_axes_rows),
            "brightness": distribution(r["brightness"] for r in audio_axes_rows),
        },
        "detector_sensitivity": detector_sensitivity,
        "unique_focuses": len({r.get("primary_focus") for r in singleton_rows}),
        "unique_protocols": len({r.get("protocol_id") for r in singleton_rows}),
        "unique_prescription_families": len({r.get("prescription_family") for r in singleton_rows}),
        "top_repeated_prescriptions": presc_counter.most_common(10),
        "non_adaptive_warnings": non_adaptive,
        "voice_too_thin_focus_distribution": thin_dist,
        "high_note_cannot_reach_distribution": reach_dist,
        "high_note_cannot_reach_reasons": hn_reason_dist,
        "high_note_evidence_backed_register": hn_evidence_register,
        "high_note_fallback_register": hn_fallback_register,
        "targets": targets,
        "target_cases": len(target_rows),
        "target_canonical_mutations": target_mutations,
        "target_overlays_distinct": len(overlays),
        "safety_singleton_cases": sum(1 for r in safety_rows if len(r.get("concern_ids") or []) == 1),
        "safety_combination_cases": sum(1 for r in safety_rows if len(r.get("concern_ids") or []) > 1),
        "pairs_tested": len(pair_rows),
        "triples_tested": len(triple_rows),
        "top_failures": top_failures,
        "top_warnings": top_warnings,
        "mode": "full" if full else ("quick" if quick else "default"),
    }
    write_json(output_dir / "summary.json", summary)

    if not skip_html:
        html = build_html_report(summary, cases_sample=html_cases)
        (output_dir / "report.html").write_text(html, encoding="utf-8")

    if generate_md or human_validation or reclassify_baseline:
        from scripts.vocal_behavioral_audit.finalize import finalize_validation_bundle

        bundle = finalize_validation_bundle(
            repo_root=repo_root,
            output_dir=output_dir,
            songs=songs,
            assets=usable,
            analysis_meta=analysis_meta,
            baseline_dir=baseline_dir,
            labels_path=labels_path,
            generate_md=generate_md,
            human_validation=human_validation,
            reclassify_baseline=reclassify_baseline,
        )
        summary = _load_summary(output_dir) or summary
        summary["validation_finalize"] = {
            "reviews": bundle.get("reviews"),
            "markdown_count": (bundle.get("markdown") or {}).get("count"),
            "human_labeled": (bundle.get("human_validation") or {}).get("labeled_audios"),
        }
        write_json(output_dir / "summary.json", summary)

    return summary


def _load_summary(output_dir: Path) -> Optional[dict[str, Any]]:
    p = output_dir / "summary.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
