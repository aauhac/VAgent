# -*- coding: utf-8 -*-
"""Batch embed + cluster + evaluate 73 qualifying audios."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

# Allow running as script from repo root
REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from services.singer_identity.clustering.cluster import (  # noqa: E402
    cluster_embeddings,
    cluster_stats,
    cosine_matrix,
)
from services.singer_identity.config import DEFAULT_GATE, DEFAULT_OUTPUT, MODEL_VERSION  # noqa: E402
from services.singer_identity.evaluation.metrics import (  # noqa: E402
    assert_no_segment_leakage,
    evaluate_integration_gate,
    identification_metrics,
    load_gate,
    song_level_split,
    unknown_rejection_metrics,
    verification_metrics,
    write_csv,
)
from services.singer_identity.inference.encoder import (  # noqa: E402
    cosine_similarity,
    get_default_encoder,
)
from services.singer_identity.registry.store import SingerRegistry  # noqa: E402


def _display_name(path: str, audio_id: str) -> str:
    try:
        from scripts.vocal_behavioral_audit.report_labels import display_audio_name

        return display_audio_name(path=path, audio_id=audio_id)
    except Exception:
        return Path(path).name or audio_id


def load_manifest(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("audios") or [])


def load_singer_labels(path: Path) -> dict:
    if not path.exists():
        return {"singers": {}, "recordings": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=REPO / "audit_output_final_v2" / "audio_manifest.json")
    ap.add_argument("--labels", type=Path, default=REPO / "singer_identity_labels" / "singers.json")
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--runtime", type=Path, default=REPO / "runtime" / "singer_identity_batch")
    ap.add_argument("--gate", type=Path, default=DEFAULT_GATE)
    ap.add_argument("--distance-threshold", type=float, default=0.35)
    args = ap.parse_args()

    out = args.output
    for sub in (
        "audio_embeddings",
        "segment_embeddings",
        "enrollment_eval",
    ):
        (out / sub).mkdir(parents=True, exist_ok=True)

    encoder = get_default_encoder()
    model_info = encoder.model_info().model_dump()
    (out / "model_info.json").write_text(json.dumps(model_info, indent=2), encoding="utf-8")

    audios = load_manifest(args.manifest)
    labels = load_singer_labels(args.labels)
    rec_labels = labels.get("recordings") or {}

    emb_rows = []
    embeddings = []
    meta_rows = []
    failures = []
    total_segments = 0
    used_segments = 0

    for a in audios:
        aid = a.get("audio_id") or ""
        path = a.get("path") or ""
        sha = a.get("sha256") or ""
        name = _display_name(path, aid)
        try:
            if not Path(path).exists():
                # try aliases
                for alt in a.get("aliases") or []:
                    if Path(alt).exists():
                        path = alt
                        break
            result = encoder.encode_path(path, audio_id=aid, sha256=sha, include_embedding=True)
            if not result.embedding:
                failures.append({"audio_id": aid, "filename": name, "error": "empty_embedding"})
                continue
            emb = np.asarray(result.embedding, dtype=np.float32)
            np.save(out / "audio_embeddings" / f"{aid}.npy", emb)
            (out / "audio_embeddings" / f"{aid}.json").write_text(
                json.dumps(
                    {
                        **result.model_dump(exclude={"embedding"}),
                        "display_name": name,
                        "path": path,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            embeddings.append(emb)
            meta_rows.append(
                {
                    "audio_id": aid,
                    "sha256": sha,
                    "filename": name,
                    "path": path,
                    "quality": result.quality,
                    "segment_count": result.segment_count,
                    "used_segment_count": result.used_segment_count,
                }
            )
            emb_rows.append({"audio_id": aid, "filename": name})
            total_segments += result.segment_count
            used_segments += result.used_segment_count
        except Exception as e:
            failures.append({"audio_id": aid, "filename": name, "error": str(e)})

    write_csv(out / "speaker_manifest.csv", meta_rows)
    (out / "failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")

    if not embeddings:
        print("No embeddings extracted")
        return 1

    X = np.stack(embeddings, axis=0)
    sim = cosine_matrix(X)
    np.save(out / "similarity_matrix.npy", sim)
    # CSV similarity
    with (out / "similarity_matrix.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        header = ["audio_id"] + [m["audio_id"] for m in meta_rows]
        w.writerow(header)
        for i, m in enumerate(meta_rows):
            w.writerow([m["audio_id"]] + [f"{sim[i, j]:.6f}" for j in range(len(meta_rows))])

    # nearest neighbors
    nn_rows = []
    for i, m in enumerate(meta_rows):
        order = np.argsort(-sim[i])
        nn_i = [j for j in order if j != i][:3]
        nn_rows.append(
            {
                "audio_id": m["audio_id"],
                "filename": m["filename"],
                "nearest_neighbor": meta_rows[nn_i[0]]["filename"] if nn_i else "",
                "nearest_similarity": float(sim[i, nn_i[0]]) if nn_i else 0.0,
                "nn2": meta_rows[nn_i[1]]["filename"] if len(nn_i) > 1 else "",
                "nn2_sim": float(sim[i, nn_i[1]]) if len(nn_i) > 1 else 0.0,
            }
        )
    write_csv(out / "nearest_neighbors.csv", nn_rows)

    clustering = cluster_embeddings(X, distance_threshold=args.distance_threshold)
    labels_c = clustering["labels"]
    stats = cluster_stats(labels_c, clustering["similarity"], names=[m["filename"] for m in meta_rows])

    cluster_rows = []
    for i, m in enumerate(meta_rows):
        cid = labels_c[i]
        cluster_rows.append(
            {
                "audio": m["filename"],
                "audio_id": m["audio_id"],
                "cluster_id": "UNRESOLVED" if cid < 0 else f"speaker_{cid+1:03d}",
                "confidence": next(
                    (s["confidence"] for s in stats if s["cluster_id"] == f"speaker_{cid+1:03d}"),
                    "LOW",
                )
                if cid >= 0
                else "UNRESOLVED",
                "nearest_neighbor": nn_rows[i]["nearest_neighbor"],
                "nearest_similarity": nn_rows[i]["nearest_similarity"],
            }
        )
    write_csv(out / "clusters.csv", cluster_rows)
    unresolved = [r for r in cluster_rows if r["cluster_id"] == "UNRESOLVED"]
    write_csv(out / "unresolved.csv", unresolved)

    # clusters.md
    md = [
        "# 추정 가수 그룹",
        "",
        f"총 음원: **{len(meta_rows)}**",
        f"추정 화자 cluster: **{clustering['n_clusters']}**",
        f"UNRESOLVED: **{len(unresolved)}**",
        f"Model: `{model_info['encoder_name']}` / `{model_info['model_version']}`",
        "",
        "> Singer Identity = WHO · VAgent = HOW (축 분리)",
        "",
    ]
    for s in stats:
        md.append(f"## {s['cluster_id']}")
        md.append("")
        md.append(f"Confidence: **{s['confidence']}**")
        md.append(f"- members: {s['member_count']}")
        md.append(f"- mean within similarity: {s['mean_within_similarity']:.4f}")
        md.append(f"- min within similarity: {s['min_within_similarity']:.4f}")
        md.append(f"- nearest external similarity: {s['nearest_external_similarity']:.4f}")
        md.append(f"- separation margin: {s['separation_margin']:.4f}")
        md.append("")
        for name in s["members"]:
            md.append(f"- {name}")
        md.append("")
    if unresolved:
        md.append("## UNRESOLVED")
        md.append("")
        for r in unresolved:
            md.append(f"- {r['audio']} (`{r['audio_id']}`)")
        md.append("")
    (out / "clusters.md").write_text("\n".join(md), encoding="utf-8")

    # --- Known same-singer / identification eval from labels ---
    known_groups = labels.get("same_singer_groups") or {}
    labeled_recs = []
    for m in meta_rows:
        sha = m["sha256"]
        short = m["audio_id"]
        info = rec_labels.get(sha) or rec_labels.get(short)
        if info:
            labeled_recs.append(
                {
                    **m,
                    "singer_id": info["singer_id"],
                    "display_name": info.get("display_name") or info["singer_id"],
                    "split": info.get("split") or "ENROLLMENT",
                    "recording_id": m["audio_id"],
                    "embedding": X[meta_rows.index(m)],
                }
            )

    # If same_singer_groups maps A/B/C/D styles to one person, use that
    same_sims = []
    diff_sims = []
    same_report = {}
    emb_by_sha = {m["sha256"]: X[i] for i, m in enumerate(meta_rows)}
    emb_by_id = {m["audio_id"]: X[i] for i, m in enumerate(meta_rows)}

    group_members = {}
    for gid, members in known_groups.items():
        embs = []
        for key in members:
            e = emb_by_sha.get(key)
            if e is None:
                e = emb_by_id.get(key[:12])
            if e is not None:
                embs.append((key, e))
        group_members[gid] = embs
        for i in range(len(embs)):
            for j in range(i + 1, len(embs)):
                s = cosine_similarity(embs[i][1], embs[j][1])
                same_sims.append(s)
                same_report[f"{embs[i][0][:8]}↔{embs[j][0][:8]}"] = s

    # different: across different known groups or labeled singers
    singer_embs: dict[str, list[np.ndarray]] = {}
    for r in labeled_recs:
        singer_embs.setdefault(r["singer_id"], []).append(r["embedding"])
    sids = list(singer_embs.keys())
    for i in range(len(sids)):
        for j in range(i + 1, len(sids)):
            for a in singer_embs[sids[i]]:
                for b in singer_embs[sids[j]]:
                    diff_sims.append(cosine_similarity(a, b))

    # If only one singer labeled, sample different from random other audios not in group
    if labeled_recs and not diff_sims:
        known_ids = {r["audio_id"] for r in labeled_recs}
        others = [X[i] for i, m in enumerate(meta_rows) if m["audio_id"] not in known_ids]
        for r in labeled_recs:
            for o in others[:20]:
                diff_sims.append(cosine_similarity(r["embedding"], o))

    same_pairs: list[tuple[np.ndarray, np.ndarray]] = []
    for embs in singer_embs.values():
        for i in range(len(embs)):
            for j in range(i + 1, len(embs)):
                same_pairs.append((embs[i], embs[j]))
    if not same_pairs:
        for embs in group_members.values():
            for i in range(len(embs)):
                for j in range(i + 1, len(embs)):
                    same_pairs.append((embs[i][1], embs[j][1]))

    diff_pairs: list[tuple[np.ndarray, np.ndarray]] = []
    if len(sids) >= 2:
        for i in range(len(sids)):
            for j in range(i + 1, len(sids)):
                for a in singer_embs[sids[i]]:
                    for b in singer_embs[sids[j]]:
                        diff_pairs.append((a, b))
    elif same_pairs:
        known_ids = {r["audio_id"] for r in labeled_recs} if labeled_recs else set()
        for embs in group_members.values():
            known_ids |= {k[:12] for k, _ in embs}
            for k, _ in embs:
                if len(k) > 12:
                    # full sha also in emb_by_sha; audio_id is short
                    pass
        for m in meta_rows:
            if m["sha256"] in (known_groups.get("person_controlled_v1") or []):
                known_ids.add(m["audio_id"])
        others = [(m["audio_id"], X[i]) for i, m in enumerate(meta_rows) if m["audio_id"] not in known_ids]
        for a, _b in same_pairs[:4]:
            for _oid, o in others[:15]:
                diff_pairs.append((a, o))
        for i in range(min(25, len(others))):
            for j in range(i + 1, min(25, len(others))):
                diff_pairs.append((others[i][1], others[j][1]))

    verif = verification_metrics(same_pairs, diff_pairs)

    # Enrollment / identification held-out
    ident = {"status": "INSUFFICIENT_DATA"}
    unknown = {"status": "INSUFFICIENT_DATA"}
    n_singers = len({r["singer_id"] for r in labeled_recs}) if labeled_recs else len(known_groups)
    min_rec = 0
    if labeled_recs:
        counts = {}
        for r in labeled_recs:
            counts[r["singer_id"]] = counts.get(r["singer_id"], 0) + 1
        min_rec = min(counts.values()) if counts else 0
        if n_singers >= 2 and min_rec >= 2:
            split = song_level_split(labeled_recs)
            assert_no_segment_leakage(split)
            gallery = {}
            for r in split["ENROLLMENT"]:
                # mean per singer from enroll
                gallery.setdefault(r["singer_id"], []).append(r["embedding"])
            gallery = {k: np.mean(np.stack(v), axis=0) for k, v in gallery.items()}
            probes = [(r["singer_id"], r["embedding"]) for r in split["TEST"]]
            # optionally use validation for threshold only — not for reporting test
            ident = identification_metrics(gallery, probes)
            write_csv(
                out / "enrollment_eval" / "identification.csv",
                [
                    {
                        "true": r["true"],
                        "pred": r["pred"],
                        "score": r["score"],
                        "top3": "|".join(r["top3"]),
                    }
                    for r in ident.get("rows") or []
                ],
            )
            # unknown: audios not in labeled set
            known = {r["audio_id"] for r in labeled_recs}
            unk = [X[i] for i, m in enumerate(meta_rows) if m["audio_id"] not in known][:25]
            unknown = unknown_rejection_metrics(gallery, unk)
        else:
            ident = {
                "status": "INSUFFICIENT_SPEAKER_LABELS",
                "n_singers": n_singers,
                "min_recordings": min_rec,
            }

    # enroll labeled into a temp registry for demo counts
    reg = SingerRegistry(args.runtime)
    enrolled = 0
    if labeled_recs:
        by_s = {}
        for r in labeled_recs:
            by_s.setdefault(r["singer_id"], []).append(r)
        for sid, rows in by_s.items():
            if not reg.get_singer(sid):
                reg.create_singer(
                    rows[0].get("display_name") or sid,
                    consented_enrollment=True,
                    singer_id=sid,
                    model_version=MODEL_VERSION,
                )
            for r in rows:
                if (r.get("split") or "ENROLLMENT") != "TEST":
                    reg.add_recording(
                        sid,
                        embedding=r["embedding"],
                        audio_sha256=r["sha256"],
                        filename=r["filename"],
                        split=r.get("split") or "ENROLLMENT",
                        quality=r.get("quality") or "FAIR",
                        model_version=MODEL_VERSION,
                    )
                    enrolled += 1

    gate = load_gate(args.gate) if args.gate.exists() else {}
    gate_result = evaluate_integration_gate(
        gate or {
            "min_speakers": 5,
            "min_recordings_per_speaker": 3,
            "require_heldout_test": True,
        },
        n_singers=n_singers,
        min_recordings=min_rec,
        has_heldout=bool(ident.get("status") == "OK" and ident.get("n")),
        ident=ident if ident.get("status") == "OK" else {"status": "INSUFFICIENT_DATA"},
        verif=verif,
        unknown=unknown if unknown.get("status") == "OK" else {"status": "INSUFFICIENT_DATA"},
    )

    eval_summary = {
        "model": model_info,
        "audio": {
            "qualifying": len(audios),
            "embedded": len(meta_rows),
            "failures": len(failures),
            "segment_count_total": total_segments,
            "used_segment_count_total": used_segments,
        },
        "clustering": {
            "method": "agglomerative_cosine_distance",
            "n_clusters": clustering["n_clusters"],
            "unresolved": len(unresolved),
            "stats": stats,
        },
        "known_same_singer": {
            "groups": list(known_groups.keys()),
            "pair_similarities": same_report,
            "same_mean": float(np.mean(same_sims)) if same_sims else None,
            "diff_mean": float(np.mean(diff_sims)) if diff_sims else None,
        },
        "labels": {
            "n_singers": n_singers,
            "n_labeled_recordings": len(labeled_recs),
            "min_recordings": min_rec,
        },
        "identification": ident,
        "verification": verif,
        "unknown_rejection": unknown,
        "enrollment": {"singers": n_singers, "recordings": enrolled},
        "integration_gate": gate_result,
        "fine_tune": {"ran": False, "reason": "SKIPPED_INSUFFICIENT_DATA_OR_BASELINE_ONLY"},
    }
    (out / "enrollment_eval" / "summary.json").write_text(
        json.dumps(eval_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "enrollment_eval" / "verification.csv").write_text(
        "metric,value\n"
        + "\n".join(f"{k},{v}" for k, v in verif.items() if not isinstance(v, (list, dict))),
        encoding="utf-8",
    )

    # report.md
    within_means = [s["mean_within_similarity"] for s in stats] or [0]
    between = [s["nearest_external_similarity"] for s in stats] or [0]
    report = f"""# Singer Identity Engine — Batch Report

## Overview

- Qualifying audio: {len(audios)}
- Embedding success: {len(meta_rows)}
- Failures: {len(failures)}
- Usable segments (used/total): {used_segments}/{total_segments}
- Encoder: `{model_info['encoder_name']}`
- Model version: `{model_info['model_version']}`
- Embedding dim: {model_info['embedding_dim']}

## Architecture

- Singer Identity = **WHO is singing**
- VAgent Vocal Analyzer = **HOW they are singing**
- Production VAgent integration: **NOT connected**
- Integration gate: **{gate_result['overall']}** ({', '.join(gate_result.get('reasons') or []) or 'ok'})

## Clustering

- Method: agglomerative (cosine distance), no fixed K
- Estimated singer clusters: **{clustering['n_clusters']}**
- Unresolved: **{len(unresolved)}**
- Largest cluster: {max((s['member_count'] for s in stats), default=0)}
- Smallest cluster: {min((s['member_count'] for s in stats), default=0)}
- Mean within-cluster similarity: {float(np.mean(within_means)):.4f}
- Mean nearest between-cluster similarity: {float(np.mean(between)):.4f}
- Mean separation: {float(np.mean([s['separation_margin'] for s in stats] or [0])):.4f}

## Known same-singer

- Groups: {list(known_groups.keys()) or 'none'}
- Same-singer mean similarity: {eval_summary['known_same_singer']['same_mean']}
- Different reference mean: {eval_summary['known_same_singer']['diff_mean']}
- Pair scores: {json.dumps(same_report, ensure_ascii=False)}

## Identification

- Status: {ident.get('status')}
- Top-1: {ident.get('top1')}
- Top-3: {ident.get('top3')}

## Verification

- Status: {verif.get('status')}
- EER: {verif.get('eer')}
- ROC-AUC: {verif.get('roc_auc')}
- Same mean: {verif.get('same_singer_mean')}
- Diff mean: {verif.get('different_singer_mean')}

## Unknown rejection

- Status: {unknown.get('status')}
- {json.dumps(unknown, ensure_ascii=False)}

## Fine-tuning

- Ran: NO
- Reason: baseline Stage-0 only; labels insufficient for safe fine-tune / or deferred

## Privacy

- Named enrollment requires `consented_enrollment=true`
- Raw embeddings not exposed on public GET singer endpoints
"""
    (out / "report.md").write_text(report, encoding="utf-8")
    print(report)
    print("OUTPUT:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
