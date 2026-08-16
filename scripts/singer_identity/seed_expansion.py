# -*- coding: utf-8 -*-
"""CLI: drowning/movie seed expansion using cached ECAPA audio embeddings."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from services.singer_identity.inference.encoder import cosine_similarity, get_default_encoder, l2_normalize  # noqa: E402
from services.singer_identity.seed_expansion.core import (  # noqa: E402
    CandidateScore,
    SeedInfo,
    apply_human_confirmed,
    build_prototype,
    build_review_html,
    classify_candidate,
    controlled_within_sims,
    cross_segment_stats,
    dedupe_by_sha,
    load_audio_embedding,
    load_or_compute_segments,
    merge_seed_labels,
    resolve_named_audios,
    robust_score,
    write_csv,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=REPO / "audit_output_final_v2" / "audio_manifest.json")
    ap.add_argument("--embeddings-dir", type=Path, default=REPO / "singer_identity_output" / "audio_embeddings")
    ap.add_argument("--segments-dir", type=Path, default=REPO / "singer_identity_output" / "segment_embeddings")
    ap.add_argument("--clusters-csv", type=Path, default=REPO / "singer_identity_output" / "clusters.csv")
    ap.add_argument("--labels", type=Path, default=REPO / "singer_identity_labels" / "singers.json")
    ap.add_argument(
        "--output",
        type=Path,
        default=REPO / "singer_identity_output" / "seed_expansion" / "drowning_movie",
    )
    ap.add_argument("--singer", default="person_drowning_movie")
    ap.add_argument("--use-human-confirmed", action="store_true")
    ap.add_argument("--skip-segments", action="store_true", help="audio-level only (faster)")
    ap.add_argument("--segment-top-n", type=int, default=0, help="0=all candidates")
    args = ap.parse_args()

    if args.use_human_confirmed:
        review = REPO / "singer_identity_labels" / "reviews" / "drowning_movie_review.json"
        n = apply_human_confirmed(args.labels, review, singer_id=args.singer)
        print(f"Applied HUMAN_REVIEW SAME labels: {n}")
        # continue to rebuild profile ranking with expanded confirmed set

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    audios = list(manifest.get("audios") or [])
    hits = resolve_named_audios(audios, ["drowning", "movie"])
    d_hits, d_notes = dedupe_by_sha(hits["drowning"])
    m_hits, m_notes = dedupe_by_sha(hits["movie"])
    if len(d_hits) != 1 or len(m_hits) != 1:
        print("SEED AMBIGUITY", d_notes, m_notes, d_hits, m_hits)
        return 2
    d_raw, m_raw = d_hits[0], m_hits[0]

    # clusters
    import csv

    cluster_by_id = {}
    if args.clusters_csv.exists():
        with args.clusters_csv.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                cluster_by_id[row["audio_id"]] = row

    emb_dir = args.embeddings_dir
    e_d = load_audio_embedding(emb_dir, d_raw["audio_id"])
    e_m = load_audio_embedding(emb_dir, m_raw["audio_id"])
    # optionally include human-confirmed embeddings in prototype
    confirmed_embs = [e_d, e_m]
    labels = merge_seed_labels(
        args.labels,
        drowning_sha=d_raw["sha256"],
        movie_sha=m_raw["sha256"],
        singer_id=args.singer,
    )
    if args.use_human_confirmed:
        for sha, meta in (labels.get("recordings") or {}).items():
            if meta.get("singer_id") != args.singer:
                continue
            if meta.get("label_source") != "HUMAN_REVIEW":
                continue
            # find audio_id
            aid = next((a["audio_id"] for a in audios if a.get("sha256") == sha), sha[:12])
            try:
                confirmed_embs.append(load_audio_embedding(emb_dir, aid))
            except FileNotFoundError:
                pass

    # MODEL_CANDIDATE never expands prototype
    prototype = build_prototype(confirmed_embs)
    seed_pair = cosine_similarity(e_d, e_m)

    drowning = SeedInfo(
        key="drowning",
        audio_id=d_raw["audio_id"],
        sha256=d_raw["sha256"],
        path=str(d_raw["path"]),
        filename=Path(d_raw["path"]).name,
        cluster_id=(cluster_by_id.get(d_raw["audio_id"]) or {}).get("cluster_id", ""),
        embedding=e_d,
    )
    movie = SeedInfo(
        key="movie",
        audio_id=m_raw["audio_id"],
        sha256=m_raw["sha256"],
        path=str(m_raw["path"]),
        filename=Path(m_raw["path"]).name,
        cluster_id=(cluster_by_id.get(m_raw["audio_id"]) or {}).get("cluster_id", ""),
        embedding=e_m,
    )

    encoder = None
    seg_d = seg_m = np.zeros((0, 192), dtype=np.float32)
    if not args.skip_segments:
        encoder = get_default_encoder()
        seg_d = load_or_compute_segments(
            audio_id=drowning.audio_id, path=drowning.path, seg_dir=args.segments_dir, encoder=encoder
        )
        seg_m = load_or_compute_segments(
            audio_id=movie.audio_id, path=movie.path, seg_dir=args.segments_dir, encoder=encoder
        )

    seed_seg_cross = cross_segment_stats(seg_d, seg_m) if seg_d.size and seg_m.size else {}

    # map embeddings
    meta_by_id = {a["audio_id"]: a for a in audios}
    quality_by_id = {}
    for a in audios:
        jp = emb_dir / f"{a['audio_id']}.json"
        if jp.exists():
            quality_by_id[a["audio_id"]] = json.loads(jp.read_text(encoding="utf-8")).get("quality", "")

    candidates: list[CandidateScore] = []
    seed_ids = {drowning.audio_id, movie.audio_id}
    for a in audios:
        aid = a["audio_id"]
        if aid in seed_ids:
            continue
        try:
            emb = load_audio_embedding(emb_dir, aid)
        except FileNotFoundError:
            continue
        sd = cosine_similarity(emb, e_d)
        sm = cosine_similarity(emb, e_m)
        sp = cosine_similarity(emb, prototype)
        mn = min(sd, sm)
        mx = max(sd, sm)
        mean = 0.5 * (sd + sm)
        gap = abs(sd - sm)
        rs = robust_score(mn, mean, sp)
        fname = Path(a.get("path") or "").name or aid
        try:
            from scripts.vocal_behavioral_audit.report_labels import display_audio_name

            fname = display_audio_name(path=str(a.get("path") or ""), audio_id=aid)
        except Exception:
            pass
        candidates.append(
            CandidateScore(
                filename=fname,
                audio_id=aid,
                sha256=str(a.get("sha256") or ""),
                path=str(a.get("path") or ""),
                current_cluster=(cluster_by_id.get(aid) or {}).get("cluster_id", ""),
                robust_score=rs,
                sim_drowning=sd,
                sim_movie=sm,
                sim_prototype=sp,
                min_seed_similarity=mn,
                max_seed_similarity=mx,
                mean_seed_similarity=mean,
                seed_similarity_gap=gap,
                quality=quality_by_id.get(aid, ""),
            )
        )

    # rank by robust score then min_seed
    candidates.sort(key=lambda c: (-c.robust_score, -c.min_seed_similarity))
    for i, c in enumerate(candidates, start=1):
        c.rank = i

    # segment support: all or top-n
    seg_targets = candidates if args.segment_top_n <= 0 else candidates[: args.segment_top_n]
    # also ensure seed cluster mates get segments
    for c in candidates:
        if c.current_cluster in (drowning.cluster_id, movie.cluster_id) and c not in seg_targets:
            seg_targets.append(c)

    if encoder is not None:
        for c in seg_targets:
            try:
                seg_c = load_or_compute_segments(
                    audio_id=c.audio_id, path=c.path, seg_dir=args.segments_dir, encoder=encoder
                )
                st_d = cross_segment_stats(seg_c, seg_d)
                st_m = cross_segment_stats(seg_c, seg_m)
                c.segment_median_drowning = st_d.get("median", float("nan"))
                c.segment_median_movie = st_m.get("median", float("nan"))
                # support = mean of support ratios / medians consistency
                supports = [st_d.get("support_ratio", float("nan")), st_m.get("support_ratio", float("nan"))]
                meds = [st_d.get("median", float("nan")), st_m.get("median", float("nan"))]
                c.segment_support = float(np.nanmean(supports))
                c.segment_top_q = float(np.nanmean([st_d.get("q75", float("nan")), st_m.get("q75", float("nan"))]))
                # conflict if audio min high but segment medians diverge a lot
                if (
                    not math.isnan(c.segment_median_drowning)
                    and not math.isnan(c.segment_median_movie)
                    and abs(c.segment_median_drowning - c.segment_median_movie) >= 0.25
                    and c.min_seed_similarity >= seed_pair * 0.75
                ):
                    c.notes = "audio/segment seed inconsistency"
            except Exception as e:
                c.notes = f"segment_error:{e}"

    for c in candidates:
        status, note = classify_candidate(
            min_s=c.min_seed_similarity,
            mean_s=c.mean_seed_similarity,
            gap=c.seed_similarity_gap,
            max_s=c.max_seed_similarity,
            seg_support=c.segment_support,
            seed_pair_sim=seed_pair,
            quality=c.quality or "FAIR",
        )
        if c.notes.startswith("audio/segment") and status == "HIGH_CANDIDATE":
            status = "CONFLICT"
        if c.notes and note:
            c.notes = c.notes + "; " + note
        else:
            c.notes = c.notes or note
        c.status = status
        c.review_required = status in ("HIGH_CANDIDATE", "MEDIUM_CANDIDATE", "CONFLICT")

    # nearest neighbors
    def top_nn(seed_emb, k=15):
        scored = [
            (cosine_similarity(load_audio_embedding(emb_dir, a["audio_id"]), seed_emb), a)
            for a in audios
            if a["audio_id"] not in seed_ids and (emb_dir / f"{a['audio_id']}.npy").exists()
        ]
        scored.sort(key=lambda x: -x[0])
        return scored[:k]

    nn_d = top_nn(e_d, 15)
    nn_m = top_nn(e_m, 15)
    nn_p = top_nn(prototype, 20)
    set_d = {a["audio_id"] for _, a in nn_d}
    set_m = {a["audio_id"] for _, a in nn_m}
    consensus = set_d & set_m
    one_d = set_d - set_m
    one_m = set_m - set_d

    # controlled reference
    sha_to_emb = {}
    for a in audios:
        p = emb_dir / f"{a['audio_id']}.npy"
        if p.exists():
            sha_to_emb[a["sha256"]] = load_audio_embedding(emb_dir, a["audio_id"])
            sha_to_emb[a["audio_id"]] = sha_to_emb[a["sha256"]]
    controlled = (labels.get("same_singer_groups") or {}).get("person_controlled_v1") or []
    ctrl_sims = controlled_within_sims(controlled, sha_to_emb)

    out = args.output
    out.mkdir(parents=True, exist_ok=True)

    seed_profile = {
        "singer_id": args.singer,
        "display_name": "Drowning/Movie Singer",
        "confirmed_recordings": [
            {
                "role": "SEED",
                "filename": drowning.filename,
                "audio_id": drowning.audio_id,
                "sha256": drowning.sha256,
                "path": drowning.path,
                "cluster": drowning.cluster_id,
                "label_source": "USER_CONFIRMED",
            },
            {
                "role": "SEED",
                "filename": movie.filename,
                "audio_id": movie.audio_id,
                "sha256": movie.sha256,
                "path": movie.path,
                "cluster": movie.cluster_id,
                "label_source": "USER_CONFIRMED",
            },
        ],
        "prototype_method": "normalize(sum(L2(confirmed embeddings)))",
        "confirmed_embedding_count": len(confirmed_embs),
        "seed_pair_similarity": seed_pair,
        "segment_seed_cross": seed_seg_cross,
        "model_candidates_do_not_expand_profile": True,
        "ambiguity_notes": d_notes + m_notes,
    }
    (out / "seed_profile.json").write_text(json.dumps(seed_profile, ensure_ascii=False, indent=2), encoding="utf-8")

    cand_rows = []
    for c in candidates:
        cand_rows.append(
            {
                "rank": c.rank,
                "filename": c.filename,
                "audio_id": c.audio_id,
                "sha256": c.sha256,
                "path": c.path,
                "current_cluster": c.current_cluster,
                "status": c.status,
                "robust_score": f"{c.robust_score:.6f}",
                "sim_drowning": f"{c.sim_drowning:.6f}",
                "sim_movie": f"{c.sim_movie:.6f}",
                "sim_prototype": f"{c.sim_prototype:.6f}",
                "min_seed_similarity": f"{c.min_seed_similarity:.6f}",
                "mean_seed_similarity": f"{c.mean_seed_similarity:.6f}",
                "seed_similarity_gap": f"{c.seed_similarity_gap:.6f}",
                "segment_median_drowning": ""
                if math.isnan(c.segment_median_drowning)
                else f"{c.segment_median_drowning:.6f}",
                "segment_median_movie": ""
                if math.isnan(c.segment_median_movie)
                else f"{c.segment_median_movie:.6f}",
                "segment_support": "" if math.isnan(c.segment_support) else f"{c.segment_support:.6f}",
                "quality": c.quality,
                "review_required": c.review_required,
                "notes": c.notes,
            }
        )
    write_csv(out / "candidates.csv", cand_rows)
    (out / "candidates.json").write_text(
        json.dumps([{**r, "review_required": bool(r["review_required"])} for r in cand_rows], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    seg_rows = [
        {
            "filename": c.filename,
            "audio_id": c.audio_id,
            "segment_median_drowning": c.segment_median_drowning,
            "segment_median_movie": c.segment_median_movie,
            "segment_support": c.segment_support,
            "segment_top_q": c.segment_top_q,
            "status": c.status,
        }
        for c in candidates
        if not math.isnan(c.segment_support)
    ]
    write_csv(out / "segment_support.csv", seg_rows)

    breakdown = []
    for c in candidates:
        breakdown.append(
            {
                "filename": c.filename,
                "sim_drowning": c.sim_drowning,
                "sim_movie": c.sim_movie,
                "sim_prototype": c.sim_prototype,
                "min_seed": c.min_seed_similarity,
                "gap": c.seed_similarity_gap,
                "robust": c.robust_score,
                "status": c.status,
            }
        )
    write_csv(out / "similarity_breakdown.csv", breakdown)

    same_cluster = drowning.cluster_id == movie.cluster_id and bool(drowning.cluster_id)
    counts = {s: 0 for s in ("HIGH_CANDIDATE", "MEDIUM_CANDIDATE", "LOW_CANDIDATE", "CONFLICT", "UNRESOLVED")}
    for c in candidates:
        counts[c.status] = counts.get(c.status, 0) + 1

    # cluster comparison md
    d_members = [r for r in cluster_by_id.values() if r.get("cluster_id") == drowning.cluster_id]
    m_members = [r for r in cluster_by_id.values() if r.get("cluster_id") == movie.cluster_id]
    cluster_md = [
        "# Cluster Comparison — Drowning / Movie",
        "",
        f"- drowning → **{drowning.cluster_id}**",
        f"- movie → **{movie.cluster_id}**",
        f"- Same cluster: **{'YES' if same_cluster else 'NO'}**",
        "",
    ]
    if not same_cluster:
        cluster_md.append("## KNOWN SAME SINGER SPLIT BY CLUSTERING")
        cluster_md.append("")
        cluster_md.append("drowning and movie are confirmed same singer but unsupervised clustering separated them.")
        cluster_md.append("")
    cluster_md.append(f"## Members of {drowning.cluster_id} (drowning cluster)")
    cluster_md.append("")
    for r in d_members:
        cluster_md.append(f"- {r.get('audio')} (`{r.get('audio_id')}`)")
    cluster_md.append("")
    if drowning.cluster_id != movie.cluster_id:
        cluster_md.append(f"## Members of {movie.cluster_id} (movie cluster)")
        cluster_md.append("")
        for r in m_members:
            cluster_md.append(f"- {r.get('audio')} (`{r.get('audio_id')}`)")
        cluster_md.append("")
    (out / "cluster_comparison.md").write_text("\n".join(cluster_md), encoding="utf-8")

    def fmt_cand(c: CandidateScore) -> str:
        seg = "n/a" if math.isnan(c.segment_support) else f"{c.segment_support:.3f}"
        return (
            f"| {c.filename} | {c.sim_drowning:.3f} | {c.sim_movie:.3f} | {c.sim_prototype:.3f} | "
            f"{c.min_seed_similarity:.3f} | {seg} | {c.current_cluster} | {c.status} |"
        )

    high = [c for c in candidates if c.status == "HIGH_CANDIDATE"]
    med = [c for c in candidates if c.status == "MEDIUM_CANDIDATE"]
    conf = [c for c in candidates if c.status == "CONFLICT"]
    top15 = candidates[:15]

    report = [
        "# Drowning / Movie Singer Expansion",
        "",
        "Confirmed same-singer seeds:",
        f"- {drowning.filename} (`{drowning.audio_id}`)",
        f"- {movie.filename} (`{movie.audio_id}`)",
        "",
        f"Seed pair similarity (audio-level): **{seed_pair:.4f}**",
        f"Seed segment-level median: **{seed_seg_cross.get('median', float('nan'))}**",
        f"Known-control same-singer mean (person_controlled_v1): **{(float(np.mean(ctrl_sims)) if ctrl_sims else float('nan')):.4f}**",
        "",
        "Current clusters:",
        f"- drowning → `{drowning.cluster_id}`",
        f"- movie → `{movie.cluster_id}`",
        f"- Same cluster: **{'YES' if same_cluster else 'NO'}**",
        "",
        f"Total searched: **{len(candidates)}**",
        f"- HIGH: {counts['HIGH_CANDIDATE']}",
        f"- MEDIUM: {counts['MEDIUM_CANDIDATE']}",
        f"- CONFLICT: {counts['CONFLICT']}",
        f"- LOW: {counts['LOW_CANDIDATE']}",
        f"- UNRESOLVED: {counts['UNRESOLVED']}",
        "",
        "> HIGH_CANDIDATE is **MODEL_CANDIDATE only** until human confirmation.",
        "",
        "## 같은 사람일 가능성이 높은 음원 (HIGH)",
        "",
        "| 음원 | Drowning | Movie | Prototype | min_seed | Segment Support | 현재 Cluster | status |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for c in high[:30]:
        report.append(fmt_cand(c))
    if not high:
        report.append("| _(none)_ | | | | | | | |")
    report += ["", "## MEDIUM", "", "| 음원 | Drowning | Movie | Prototype | min_seed | Segment Support | Cluster | status |", "|---|---:|---:|---:|---:|---:|---|---|"]
    for c in med[:30]:
        report.append(fmt_cand(c))
    if not med:
        report.append("| _(none)_ | | | | | | | |")
    report += ["", "## CONFLICT", "", "| 음원 | Drowning | Movie | Prototype | min_seed | Segment Support | Cluster | status |", "|---|---:|---:|---:|---:|---:|---|---|"]
    for c in conf[:30]:
        report.append(fmt_cand(c))
    if not conf:
        report.append("| _(none)_ | | | | | | | |")

    report += ["", "## Top 15 by robust score", ""]
    for c in top15:
        report.append(
            f"{c.rank}. **{c.filename}** · cluster `{c.current_cluster}` · "
            f"drowning={c.sim_drowning:.3f} movie={c.sim_movie:.3f} proto={c.sim_prototype:.3f} "
            f"min={c.min_seed_similarity:.3f} gap={c.seed_similarity_gap:.3f} "
            f"seg={('n/a' if math.isnan(c.segment_support) else f'{c.segment_support:.3f}')} · **{c.status}**"
        )

    report += ["", "## Consensus nearest neighbors (NN15 drowning ∩ NN15 movie)", ""]
    id_to_name = {c.audio_id: c.filename for c in candidates}
    for aid in sorted(consensus):
        report.append(f"- {id_to_name.get(aid, aid)}")

    report += ["", "## One-sided matches", "", "Stronger in drowning NN only:", ""]
    for aid in list(one_d)[:10]:
        report.append(f"- {id_to_name.get(aid, aid)}")
    report += ["", "Stronger in movie NN only:", ""]
    for aid in list(one_m)[:10]:
        report.append(f"- {id_to_name.get(aid, aid)}")

    report += [
        "",
        "## Tuning / Integration",
        "",
        "- ECAPA fine-tuned: **NO**",
        "- Cluster threshold changed: **NO**",
        "- VAgent production connected: **NO**",
        "",
    ]
    (out / "report.md").write_text("\n".join(report), encoding="utf-8")

    # review queue
    review_cands = [c for c in candidates if c.review_required]
    rq = ["# Review Queue — Drowning/Movie", "", "Priority: P0 HIGH → P1 CONFLICT(one-sided high) → P2 MEDIUM", ""]
    for c in review_cands:
        prio = "P0" if c.status == "HIGH_CANDIDATE" else ("P1" if c.status == "CONFLICT" else "P2")
        rq.append(f"- [{prio}] {c.filename} · {c.status} · d={c.sim_drowning:.3f} m={c.sim_movie:.3f}")
    (out / "review_queue.md").write_text("\n".join(rq), encoding="utf-8")
    build_review_html(out_path=out / "review_queue.html", drowning=drowning, movie=movie, candidates=candidates)

    # empty review json scaffold
    review_dir = REPO / "singer_identity_labels" / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    review_path = review_dir / "drowning_movie_review.json"
    if not review_path.exists():
        review_path.write_text(
            json.dumps(
                {
                    "singer_id": args.singer,
                    "seeds": {"drowning": drowning.sha256, "movie": movie.sha256},
                    "reviews": {},
                    "note": "Fill via review_queue.html localStorage export. MODEL_CANDIDATE must not expand profile.",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    summary = {
        "seed_pair_similarity": seed_pair,
        "same_cluster": same_cluster,
        "counts": counts,
        "top15": [
            {
                "rank": c.rank,
                "filename": c.filename,
                "cluster": c.current_cluster,
                "drowning": c.sim_drowning,
                "movie": c.sim_movie,
                "prototype": c.sim_prototype,
                "min_seed": c.min_seed_similarity,
                "segment_support": c.segment_support,
                "status": c.status,
            }
            for c in top15
        ],
        "consensus_nn": list(consensus),
        "output": str(out),
    }
    (out / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("REPORT:", out / "report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
