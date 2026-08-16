# -*- coding: utf-8 -*-
"""Confirmed Singer Profile v3 — 11-song LOO, hard positives, strategy comparison (experimental)."""

from __future__ import annotations

import itertools
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.decomposition import PCA

from services.singer_identity.config import DEFAULT_VERIFY_MATCH, DEFAULT_VERIFY_NONMATCH, MODEL_VERSION
from services.singer_identity.confirmed_profile.core import (
    RecordingRef,
    classify_remaining,
    compute_medoid,
    load_clusters,
    load_frozen_2seed_ranks,
    mean_centroid,
    resolve_exact_stems,
    sim_stats,
    support_ratio_vs_confirmed,
    verify_decision,
    _norm_stem,
)
from services.singer_identity.inference.encoder import cosine_similarity, l2_normalize
from services.singer_identity.personal_baseline.schema import (
    build_experimental_baseline_preview,
    write_baseline_preview_artifacts,
)
from services.singer_identity.seed_expansion.core import (
    cross_segment_stats,
    load_audio_embedding,
    write_csv,
)

SINGER_ID = "person_drowning_movie"
PROFILE_VERSION = 3
PROFILE_ID = "person_drowning_movie_profile_v3"
DEFAULT_STRATEGY = "SINGLE_CENTROID"
MULTI_PROTOTYPE_PRODUCTION_ENABLED = False

CONFIRMED_STEMS_V3 = [
    "drowning",
    "movie",
    "거의동115",
    "거의동116",
    "거의동117",
    "좋은사람",
    "요즘 바쁜가봐",
    "bluemoon",
    "I'llneverloveagain",
    "love again",
    "옥탑방",
]

FROZEN_V2_REMAINING = Path(
    "singer_identity_output/confirmed_profile_v2/person_drowning_movie/remaining_candidates.csv"
)
FROZEN_V2_SUMMARY = Path(
    "singer_identity_output/confirmed_profile_v2/person_drowning_movie/run_summary.json"
)
FROZEN_V2_CURVE = Path(
    "singer_identity_output/confirmed_profile_v2/person_drowning_movie/enrollment_size_curve.csv"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_csv_by_id(path: Path, key: str = "audio_id") -> dict[str, dict[str, Any]]:
    import csv

    out: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row[key]] = row
    return out


def promote_confirmed_labels_v3(
    labels_path: Path,
    recordings: list[RecordingRef],
    *,
    singer_id: str = SINGER_ID,
    v2_meta_by_id: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, Any]:
    data = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.exists() else {}
    data.setdefault("version", "singer-identity-labels-v1")
    data.setdefault("same_singer_groups", {})
    data.setdefault("recordings", {})
    group = data["same_singer_groups"].setdefault(singer_id, [])
    confirmed_shas = {r.sha256 for r in recordings}
    v2_meta_by_id = v2_meta_by_id or {}

    for r in recordings:
        prev = data["recordings"].get(r.sha256) or {}
        if prev.get("singer_id") == "person_controlled_v1":
            raise ValueError(f"refusing to overwrite controlled label: {r.sha256}")
        previous_source = prev.get("label_source")
        role = "SEED" if r.stem in ("drowning", "movie") else "CONFIRMED"
        entry: dict[str, Any] = {
            "singer_id": singer_id,
            "display_name": "Drowning/Movie Singer",
            "label_source": "USER_CONFIRMED",
            "confidence": "CONFIRMED",
            "role": role,
            "filename": r.filename,
            "audio_id": r.audio_id,
            "confirmed_at": _now(),
            "confirmation_source": "USER",
            "profile_version": PROFILE_VERSION,
        }
        if previous_source == "USER_CONFIRMED" and prev.get("role") == "SEED":
            entry["role"] = "SEED"
            entry["seed_name"] = prev.get("seed_name") or r.stem
        if previous_source and previous_source != "USER_CONFIRMED":
            entry["previous_label_source"] = previous_source
        elif r.previous_model_status and previous_source != "USER_CONFIRMED":
            entry["previous_label_source"] = "MODEL_CANDIDATE"
        # Preserve earlier USER_CONFIRMED provenance fields
        if prev.get("previous_label_source"):
            entry.setdefault("previous_label_source", prev["previous_label_source"])
        if prev.get("previous_model_status"):
            entry["previous_model_status"] = prev["previous_model_status"]
        if r.previous_model_status:
            entry["previous_model_status"] = r.previous_model_status
        meta = v2_meta_by_id.get(r.audio_id) or {}
        if meta.get("status"):
            entry["previous_model_status"] = meta["status"]
            if meta["status"] == "CONFLICT" or _norm_stem(r.filename) == "love again":
                entry["previous_v2_status"] = meta["status"]
        if meta.get("rank"):
            entry["previous_rank"] = int(meta["rank"])
        for key in (
            "sim_centroid",
            "min_similarity_to_confirmed",
            "median_similarity_to_confirmed",
            "mean_similarity_to_confirmed",
        ):
            if meta.get(key) not in (None, ""):
                entry[f"previous_{key}"] = float(meta[key])
        if previous_source == "USER_CONFIRMED" and prev.get("confirmed_at"):
            entry["confirmed_at"] = prev["confirmed_at"]
            entry["confirmation_source"] = prev.get("confirmation_source") or "USER"
        data["recordings"][r.sha256] = entry
        if r.sha256 not in group:
            group.append(r.sha256)

    ordered = []
    seen = set()
    for s in list(group) + list(confirmed_shas):
        if s in confirmed_shas and s not in seen:
            seen.add(s)
            ordered.append(s)
    data["same_singer_groups"][singer_id] = ordered
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def build_multi_prototypes(
    ids: list[str],
    embs: list[np.ndarray],
    *,
    k: int,
) -> dict[str, Any]:
    """Agglomerative clustering on enrollment only. Returns prototypes + membership."""
    n = len(embs)
    if n == 0:
        return {"k": k, "prototypes": [], "members": {}, "degenerate": True, "warnings": ["empty"]}
    k_eff = min(k, n)
    stacked = np.stack([l2_normalize(e) for e in embs], axis=0)
    warnings: list[str] = []
    if k_eff == 1:
        labels = np.zeros(n, dtype=int)
    else:
        # cosine distance via affinity
        sim = stacked @ stacked.T
        dist = np.clip(1.0 - sim, 0.0, 2.0)
        np.fill_diagonal(dist, 0.0)
        model = AgglomerativeClustering(
            n_clusters=k_eff,
            metric="precomputed",
            linkage="average",
        )
        labels = model.fit_predict(dist)

    prototypes = []
    members: dict[str, list[str]] = {}
    for c in range(k_eff):
        idxs = [i for i in range(n) if int(labels[i]) == c]
        member_ids = [ids[i] for i in idxs]
        members[f"p{c}"] = member_ids
        if len(idxs) < 2 and n >= 2 * k_eff:
            warnings.append(f"DEGENERATE_PROTOTYPE p{c} size={len(idxs)}")
        elif len(idxs) < 2:
            warnings.append(f"SINGLE_MEMBER_PROTOTYPE p{c} size={len(idxs)}")
        cent = mean_centroid([embs[i] for i in idxs])
        prototypes.append(
            {
                "prototype_id": f"p{c}",
                "member_ids": member_ids,
                "member_count": len(member_ids),
                "embedding": cent,
            }
        )
    return {
        "k": k,
        "k_effective": k_eff,
        "prototypes": prototypes,
        "members": members,
        "degenerate": any("DEGENERATE" in w or "SINGLE_MEMBER" in w for w in warnings),
        "warnings": warnings,
        "method": "agglomerative_average_cosine",
    }


def max_prototype_similarity(query: np.ndarray, proto_info: dict[str, Any]) -> float:
    protos = proto_info.get("prototypes") or []
    if not protos:
        return float("nan")
    return float(max(cosine_similarity(query, p["embedding"]) for p in protos))


def top2_prototype_mean(query: np.ndarray, proto_info: dict[str, Any]) -> float:
    sims = [cosine_similarity(query, p["embedding"]) for p in (proto_info.get("prototypes") or [])]
    if not sims:
        return float("nan")
    sims = sorted(sims, reverse=True)
    if len(sims) == 1:
        return float(sims[0])
    return float(0.5 * (sims[0] + sims[1]))


def pca_2d(ids: list[str], embs: list[np.ndarray], filenames: list[str]) -> dict[str, Any]:
    stacked = np.stack([l2_normalize(e) for e in embs], axis=0)
    if stacked.shape[0] < 2:
        return {"points": [], "note": "insufficient points"}
    n_comp = min(2, stacked.shape[0], stacked.shape[1])
    coords = PCA(n_components=n_comp, random_state=0).fit_transform(stacked)
    points = []
    for i, aid in enumerate(ids):
        pt = {"audio_id": aid, "filename": filenames[i], "x": float(coords[i, 0])}
        pt["y"] = float(coords[i, 1]) if n_comp > 1 else 0.0
        points.append(pt)
    return {
        "method": "PCA",
        "dimensions": n_comp,
        "points": points,
        "caption": (
            "PCA 2D is a visualization aid only; it does not fully represent "
            "192-D cosine relationships."
        ),
    }


def build_review_html_v3(
    *,
    out_path: Path,
    confirmed: list[RecordingRef],
    medoid_id: str,
    hardest_id: str,
    love_again_id: Optional[str],
    candidates: list[dict[str, Any]],
) -> None:
    by_id = {r.audio_id: r for r in confirmed}
    medoid = by_id[medoid_id]
    hardest = by_id.get(hardest_id) or confirmed[0]
    love = by_id.get(love_again_id) if love_again_id else None
    refs = [
        {
            "audio_id": r.audio_id,
            "sha256": r.sha256,
            "filename": r.filename,
            "path": r.path.replace("\\", "/"),
            "is_medoid": r.audio_id == medoid_id,
            "is_hardest": r.audio_id == hardest_id,
            "is_love_again": love_again_id is not None and r.audio_id == love_again_id,
        }
        for r in confirmed
    ]
    reviewable = [
        c
        for c in candidates
        if c.get("status")
        in ("CONSISTENT_HIGH", "STYLE_SPECIFIC", "BORDERLINE", "CONFLICT", "MULTI_PROTOTYPE_ONLY")
        or c.get("rank", 999) <= 20
    ]
    payload = {
        "singer_id": SINGER_ID,
        "profile_version": PROFILE_VERSION,
        "default_strategy": DEFAULT_STRATEGY,
        "multi_prototype_production_enabled": False,
        "medoid": {
            "filename": medoid.filename,
            "path": medoid.path.replace("\\", "/"),
            "sha256": medoid.sha256,
            "audio_id": medoid.audio_id,
        },
        "hardest": {
            "filename": hardest.filename,
            "path": hardest.path.replace("\\", "/"),
            "sha256": hardest.sha256,
            "audio_id": hardest.audio_id,
        },
        "love_again": None
        if love is None
        else {
            "filename": love.filename,
            "path": love.path.replace("\\", "/"),
            "sha256": love.sha256,
            "audio_id": love.audio_id,
        },
        "confirmed": refs,
        "candidates": [
            {
                "audio_id": c["audio_id"],
                "sha256": c["sha256"],
                "filename": c["filename"],
                "path": str(c.get("path") or "").replace("\\", "/"),
                "status": c["status"],
                "sim_centroid": round(float(c["sim_centroid"]), 4),
                "sim_medoid": round(float(c["sim_medoid"]), 4),
                "sim_k2": round(float(c["sim_k2"]), 4),
                "sim_k3": round(float(c["sim_k3"]), 4),
                "mean_confirmed": round(float(c["mean_similarity_to_confirmed"]), 4),
                "min_confirmed": round(float(c["min_similarity_to_confirmed"]), 4),
                "segment_support": None
                if c.get("segment_support") is None
                or (isinstance(c.get("segment_support"), float) and math.isnan(float(c["segment_support"])))
                else round(float(c["segment_support"]), 4),
                "cluster": c.get("current_cluster", ""),
                "rank": c.get("rank"),
            }
            for c in reviewable
        ],
    }
    data_json = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<title>Confirmed Profile v3 Review (local)</title>
<style>
body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; background:#0f1216; color:#e8eaed; }}
h1,h2 {{ color:#fff; }}
.card {{ background:#1a1f27; border:1px solid #2a3340; border-radius:10px; padding:14px; margin:12px 0; }}
.muted {{ color:#9aa3af; }}
button {{ margin:4px; padding:8px 12px; border-radius:8px; border:1px solid #2a3340; background:#11151b; color:#e8eaed; cursor:pointer; }}
button.same {{ border-color:#3fb950; }}
button.diff {{ border-color:#ff7b72; }}
button.unk {{ border-color:#e3b341; }}
.nums.hidden,.refs.hidden {{ display:none; }}
audio {{ width:100%; margin-top:8px; }}
.row {{ display:grid; grid-template-columns: 1fr 1fr 1fr; gap:12px; }}
@media (max-width:900px) {{ .row {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<h1>Confirmed Singer Profile v3 — Human Review</h1>
<p class="muted">Local-only. MODEL candidates are not ground truth. Blind mode ON by default. Multi-prototype is EXPERIMENTAL ONLY.</p>
<label><input type="checkbox" id="blind" checked/> Blind Review Mode</label>
<div class="card">
  <h2>Confirmed singer references: 11</h2>
  <div class="row">
    <div><b>대표(medoid)</b><br/><span id="medName"></span><audio id="medAud" controls></audio></div>
    <div><b>hard positive (love again)</b><br/><span id="loveName"></span><audio id="loveAud" controls></audio></div>
    <div><b>가장 다른 confirmed</b><br/><span id="hardName"></span><audio id="hardAud" controls></audio></div>
  </div>
  <button id="toggleRefs">전체 11개 펼치기</button>
  <div id="allRefs" class="refs hidden"></div>
</div>
<div id="list"></div>
<script>
const DATA = {data_json};
function fileUrl(p) {{
  if (!p) return "";
  if (p.startsWith("file:")) return p;
  if (/^[A-Za-z]:/.test(p)) return "file:///" + p.replace(/\\\\/g,"/");
  return "file://" + p;
}}
function loadLocal() {{
  try {{ return JSON.parse(localStorage.getItem("confirmed_profile_v3_review")||"{{}}"); }}
  catch {{ return {{}}; }}
}}
function saveLocal(obj) {{
  localStorage.setItem("confirmed_profile_v3_review", JSON.stringify(obj, null, 2));
  document.getElementById("export").textContent = JSON.stringify(obj, null, 2);
}}
document.getElementById("medName").textContent = DATA.medoid.filename;
document.getElementById("medAud").src = fileUrl(DATA.medoid.path);
document.getElementById("hardName").textContent = DATA.hardest.filename;
document.getElementById("hardAud").src = fileUrl(DATA.hardest.path);
if (DATA.love_again) {{
  document.getElementById("loveName").textContent = DATA.love_again.filename;
  document.getElementById("loveAud").src = fileUrl(DATA.love_again.path);
}} else {{
  document.getElementById("loveName").textContent = "(n/a)";
}}
const refBox = document.getElementById("allRefs");
DATA.confirmed.forEach(r => {{
  const d = document.createElement("div");
  d.innerHTML = `<div class="muted">${{r.filename}}${{r.is_medoid?" (medoid)":""}}${{r.is_love_again?" (hard+)":""}}${{r.is_hardest?" (atypical)":""}}</div><audio controls src="${{fileUrl(r.path)}}"></audio>`;
  refBox.appendChild(d);
}});
document.getElementById("toggleRefs").onclick = () => refBox.classList.toggle("hidden");
const decisions = loadLocal();
decisions.singer_id = DATA.singer_id;
decisions.profile_version = DATA.profile_version;
decisions.reviews = decisions.reviews || {{}};
function render() {{
  const blind = document.getElementById("blind").checked;
  const root = document.getElementById("list");
  root.innerHTML = "";
  DATA.candidates.forEach((c, i) => {{
    const div = document.createElement("div");
    div.className = "card";
    const prev = (decisions.reviews[c.sha256]||{{}}).decision || "";
    div.innerHTML = `
      <h2>#${{i+1}} ${{c.filename}} <span class="muted">${{c.status}}</span></h2>
      <div class="muted">cluster: ${{c.cluster}} · rank: ${{c.rank}}</div>
      <audio controls src="${{fileUrl(c.path)}}"></audio>
      <div class="nums ${{blind ? "hidden" : ""}}">
        Centroid: ${{c.sim_centroid}} · Medoid: ${{c.sim_medoid}} · K2: ${{c.sim_k2}} · K3: ${{c.sim_k3}} ·
        mean: ${{c.mean_confirmed}} · min: ${{c.min_confirmed}} · segment: ${{c.segment_support}}
      </div>
      <div>
        <button class="same" data-d="SAME">같은 사람</button>
        <button class="diff" data-d="DIFFERENT">다른 사람</button>
        <button class="unk" data-d="UNKNOWN">모르겠음</button>
        <button data-d="REVEAL">분석값 보기</button>
        <span class="muted" id="dec-${{c.sha256}}">${{prev}}</span>
      </div>`;
    div.querySelectorAll("button").forEach(btn => {{
      btn.onclick = () => {{
        const d = btn.getAttribute("data-d");
        if (d === "REVEAL") {{ div.querySelector(".nums").classList.remove("hidden"); return; }}
        decisions.reviews[c.sha256] = {{
          decision: d, filename: c.filename, audio_id: c.audio_id, sha256: c.sha256,
          model_status: c.status, label_source: "HUMAN_REVIEW",
          scores: {{centroid:c.sim_centroid, medoid:c.sim_medoid, k2:c.sim_k2, k3:c.sim_k3}},
          note: "Does not auto-expand profile; explicit rebuild required",
        }};
        document.getElementById("dec-"+c.sha256).textContent = d;
        saveLocal(decisions);
      }};
    }});
    root.appendChild(div);
  }});
}}
document.getElementById("blind").onchange = render;
render();
</script>
<div class="card">
  <h2>Export → singer_identity_labels/reviews/confirmed_profile_v3_review.json</h2>
  <pre id="export" style="white-space:pre-wrap;background:#11151b;padding:12px;border-radius:8px;"></pre>
</div>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")


def run_confirmed_profile_v3(
    *,
    repo: Path,
    singer_id: str = SINGER_ID,
    manifest_path: Optional[Path] = None,
    embeddings_dir: Optional[Path] = None,
    segments_dir: Optional[Path] = None,
    clusters_csv: Optional[Path] = None,
    labels_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    skip_segments: bool = False,
) -> dict[str, Any]:
    manifest_path = manifest_path or (repo / "audit_output_final_v2" / "audio_manifest.json")
    embeddings_dir = embeddings_dir or (repo / "singer_identity_output" / "audio_embeddings")
    segments_dir = segments_dir or (repo / "singer_identity_output" / "segment_embeddings")
    clusters_csv = clusters_csv or (repo / "singer_identity_output" / "clusters.csv")
    labels_path = labels_path or (repo / "singer_identity_labels" / "singers.json")
    output_dir = output_dir or (repo / "singer_identity_output" / "confirmed_profile_v3" / singer_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audios = list(manifest.get("audios") or [])
    cluster_by_id = load_clusters(clusters_csv)
    v2_remaining = load_csv_by_id(repo / FROZEN_V2_REMAINING)
    frozen_2seed = load_frozen_2seed_ranks(repo)
    v2_summary = {}
    if (repo / FROZEN_V2_SUMMARY).exists():
        v2_summary = json.loads((repo / FROZEN_V2_SUMMARY).read_text(encoding="utf-8"))

    hits = resolve_exact_stems(audios, CONFIRMED_STEMS_V3)
    confirmed: list[RecordingRef] = []
    for stem in CONFIRMED_STEMS_V3:
        raw = hits[stem]
        by_sha = {str(h.get("sha256") or ""): h for h in raw}
        if len(by_sha) != 1:
            raise ValueError(f"AMBIGUITY/missing for {stem}: {list(by_sha)}")
        h = next(iter(by_sha.values()))
        aid = h["audio_id"]
        prev_status = None
        if aid in v2_remaining:
            prev_status = v2_remaining[aid].get("status")
        elif aid in frozen_2seed:
            prev_status = frozen_2seed[aid].get("status")
        confirmed.append(
            RecordingRef(
                stem=stem,
                filename=Path(h["path"]).name,
                path=str(h["path"]),
                audio_id=aid,
                sha256=str(h["sha256"]),
                cluster_id=(cluster_by_id.get(aid) or {}).get("cluster_id", ""),
                embedding=load_audio_embedding(embeddings_dir, aid),
                previous_model_status=prev_status,
            )
        )
    if len({r.sha256 for r in confirmed}) != 11:
        raise ValueError("expected 11 unique SHAs")

    promote_confirmed_labels_v3(
        labels_path, confirmed, singer_id=singer_id, v2_meta_by_id=v2_remaining
    )

    conf_ids = [r.audio_id for r in confirmed]
    conf_embs = [r.embedding for r in confirmed]
    assert all(e is not None for e in conf_embs)
    centroid = mean_centroid(conf_embs)  # type: ignore[arg-type]
    medoid_id, medoid_mean = compute_medoid(conf_ids, conf_embs)  # type: ignore[arg-type]
    medoid_rec = next(r for r in confirmed if r.audio_id == medoid_id)

    # centrality
    centrality_rows = []
    for r in confirmed:
        sims = [
            float(cosine_similarity(r.embedding, o.embedding))
            for o in confirmed
            if o.audio_id != r.audio_id
        ]
        centrality_rows.append(
            {
                "filename": r.filename,
                "audio_id": r.audio_id,
                "mean_similarity_to_others": float(np.mean(sims)),
                "median_similarity_to_others": float(np.median(sims)),
                "min_similarity_to_others": float(np.min(sims)),
                "max_similarity_to_others": float(np.max(sims)),
            }
        )
    centrality_rows.sort(key=lambda x: -x["mean_similarity_to_others"])
    for i, row in enumerate(centrality_rows, start=1):
        row["centrality_rank"] = i
    write_csv(output_dir / "centrality.csv", centrality_rows)
    most_central = centrality_rows[0]
    most_atypical = centrality_rows[-1]

    # within matrix
    pair_list = []
    matrix_rows = []
    for i, a in enumerate(confirmed):
        row = {"filename": a.filename, "audio_id": a.audio_id}
        for j, b in enumerate(confirmed):
            s = float(cosine_similarity(a.embedding, b.embedding))
            row[b.filename] = f"{s:.6f}"
            if i < j:
                pair_list.append((s, a.audio_id, b.audio_id, a.filename, b.filename))
        matrix_rows.append(row)
    write_csv(output_dir / "within_singer_similarity.csv", matrix_rows)
    pair_list.sort(key=lambda x: x[0])
    hardest = pair_list[0]
    easiest = pair_list[-1]
    within_sims = [p[0] for p in pair_list]
    within_stats = sim_stats(within_sims)
    within_stats["p10"] = float(np.percentile(within_sims, 10))
    within_stats["p90"] = float(np.percentile(within_sims, 90))

    # love again vs others
    love = next(r for r in confirmed if _norm_stem(r.filename) == "love again")
    love_sims = [
        (float(cosine_similarity(love.embedding, o.embedding)), o.filename, o.audio_id)
        for o in confirmed
        if o.audio_id != love.audio_id
    ]
    love_sims.sort(key=lambda x: x[0])
    love_vals = [s for s, _, _ in love_sims]
    love_stats = {
        "mean": float(np.mean(love_vals)),
        "median": float(np.median(love_vals)),
        "min": float(np.min(love_vals)),
        "max": float(np.max(love_vals)),
        "nearest": love_sims[-1][1],
        "furthest": love_sims[0][1],
        "pairwise": [{"filename": fn, "similarity": s} for s, fn, _ in love_sims],
    }

    # hard positives: bottom quartile centrality + previous CONFLICT + love again
    means = [r["mean_similarity_to_others"] for r in centrality_rows]
    q25 = float(np.percentile(means, 25))
    hard_ids = set()
    hard_rows = []
    for row in centrality_rows:
        reasons = []
        if row["audio_id"] == love.audio_id:
            reasons.append("previous_CONFLICT_now_USER_CONFIRMED")
            reasons.append("named_hard_positive")
        if row["mean_similarity_to_others"] <= q25 + 1e-12:
            reasons.append("bottom_quartile_centrality")
        meta = v2_remaining.get(row["audio_id"]) or {}
        if meta.get("status") == "CONFLICT":
            reasons.append("previous_v2_CONFLICT")
        if reasons:
            hard_ids.add(row["audio_id"])
            hard_rows.append({**row, "reasons": ";".join(reasons), "hard_positive": True})
    # Sort atypical-first for report readability
    hard_rows.sort(key=lambda r: r["mean_similarity_to_others"])
    write_csv(output_dir / "hard_positives.csv", hard_rows)

    seg_cache: dict[str, np.ndarray] = {}
    if not skip_segments:
        for r in confirmed:
            npy = segments_dir / f"{r.audio_id}.npy"
            if npy.exists():
                seg_cache[r.audio_id] = np.load(npy)

    hard_md = [
        "# Hard Positive Report",
        "",
        "USER_CONFIRMED recordings with atypical identity embedding placement.",
        "These remain valid same-singer variation — not label errors.",
        "",
        f"Bottom-quartile centrality threshold (distribution): **{q25:.4f}**",
        "",
        "## love again",
        "",
        f"- Confirmed same singer: **YES**",
        f"- Mean/median/min/max to other 10: "
        f"{love_stats['mean']:.4f} / {love_stats['median']:.4f} / "
        f"{love_stats['min']:.4f} / {love_stats['max']:.4f}",
        f"- Nearest: {love_stats['nearest']} · Furthest: {love_stats['furthest']}",
        f"- Previous v2 status: **{(v2_remaining.get(love.audio_id) or {}).get('status', 'n/a')}**",
        f"- Current interpretation: **HARD SAME-SINGER VARIATION**",
        f"- Usable segments: {len(seg_cache.get(love.audio_id, []))}",
        f"- Cluster: `{love.cluster_id}` · format: {Path(love.path).suffix}",
        "",
        "### Pairwise vs other confirmed",
        "",
    ]
    for item in love_stats["pairwise"]:
        hard_md.append(f"- {item['filename']}: {item['similarity']:.4f}")
    hard_md += ["", "## Other hard positives", ""]
    for h in hard_rows:
        if h["audio_id"] == love.audio_id:
            continue
        hard_md.append(
            f"- {h['filename']}: mean={h['mean_similarity_to_others']:.4f} "
            f"min={h['min_similarity_to_others']:.4f} · {h['reasons']}"
        )
    hard_md += [
        "",
        "> Identity explanation does **not** use VAgent effort/contact/register/brightness as features.",
        "",
    ]
    (output_dir / "hard_positive_report.md").write_text("\n".join(hard_md), encoding="utf-8")

    # Full-profile prototypes (for remaining search + artifacts; LOO rebuilds separately)
    proto_k2_full = build_multi_prototypes(conf_ids, conf_embs, k=2)  # type: ignore[arg-type]
    proto_k3_full = build_multi_prototypes(conf_ids, conf_embs, k=3)  # type: ignore[arg-type]

    def _proto_json(info: dict[str, Any]) -> dict[str, Any]:
        return {
            "k": info["k"],
            "k_effective": info["k_effective"],
            "method": info["method"],
            "degenerate": info["degenerate"],
            "warnings": info["warnings"],
            "members": info["members"],
            "note": "EXPERIMENTAL ONLY — not production default",
            "production_enabled": False,
        }

    (output_dir / "prototype_k2.json").write_text(
        json.dumps(_proto_json(proto_k2_full), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "prototype_k3.json").write_text(
        json.dumps(_proto_json(proto_k3_full), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Gallery
    all_gallery = []
    for a in audios:
        aid = a["audio_id"]
        if not (embeddings_dir / f"{aid}.npy").exists():
            continue
        all_gallery.append(
            {
                "audio_id": aid,
                "filename": Path(a.get("path") or "").name,
                "path": str(a.get("path") or ""),
                "sha256": str(a.get("sha256") or ""),
                "embedding": load_audio_embedding(embeddings_dir, aid),
                "cluster": (cluster_by_id.get(aid) or {}).get("cluster_id", ""),
            }
        )
    conf_set = set(conf_ids)

    # 11-way LOO with strategies
    loo_rows = []
    strategy_accum: dict[str, list[float]] = {
        "centroid": [],
        "medoid": [],
        "k2": [],
        "k3": [],
    }
    strategy_match: dict[str, int] = {k: 0 for k in strategy_accum}
    love_loo = None

    for held in confirmed:
        enroll = [r for r in confirmed if r.audio_id != held.audio_id]
        e_ids = [r.audio_id for r in enroll]
        e_embs = [r.embedding for r in enroll]
        assert held.embedding is not None
        # leakage guards
        assert held.audio_id not in e_ids
        fold_cent = mean_centroid(e_embs)  # type: ignore[arg-type]
        fold_medoid_id, _ = compute_medoid(e_ids, e_embs)  # type: ignore[arg-type]
        fold_medoid_emb = next(r.embedding for r in enroll if r.audio_id == fold_medoid_id)
        fold_k2 = build_multi_prototypes(e_ids, e_embs, k=2)  # type: ignore[arg-type]
        fold_k3 = build_multi_prototypes(e_ids, e_embs, k=3)  # type: ignore[arg-type]
        assert all(held.audio_id not in mems for mems in fold_k2["members"].values())
        assert all(held.audio_id not in mems for mems in fold_k3["members"].values())

        sim_c = float(cosine_similarity(held.embedding, fold_cent))
        sim_m = float(cosine_similarity(held.embedding, fold_medoid_emb))
        sim_k2 = max_prototype_similarity(held.embedding, fold_k2)
        sim_k3 = max_prototype_similarity(held.embedding, fold_k3)
        nearest = max(
            enroll, key=lambda r: float(cosine_similarity(held.embedding, r.embedding))
        )
        furthest = min(
            enroll, key=lambda r: float(cosine_similarity(held.embedding, r.embedding))
        )
        nearest_sim = float(cosine_similarity(held.embedding, nearest.embedding))
        decision = verify_decision(sim_c)
        margin = sim_c - DEFAULT_VERIFY_MATCH

        enroll_ids = set(e_ids)
        scored = sorted(
            [
                (float(cosine_similarity(g["embedding"], fold_cent)), g["audio_id"])
                for g in all_gallery
                if g["audio_id"] not in enroll_ids
            ],
            key=lambda x: -x[0],
        )
        rank = next(i for i, (_, aid) in enumerate(scored, start=1) if aid == held.audio_id)

        for key, sim in (("centroid", sim_c), ("medoid", sim_m), ("k2", sim_k2), ("k3", sim_k3)):
            strategy_accum[key].append(sim)
            if verify_decision(sim) == "MATCH":
                strategy_match[key] += 1

        row = {
            "heldout_filename": held.filename,
            "heldout_audio_id": held.audio_id,
            "enrollment_count": 10,
            "centroid_similarity": sim_c,
            "medoid_similarity": sim_m,
            "k2_similarity": sim_k2,
            "k3_similarity": sim_k3,
            "k2_top2_mean": top2_prototype_mean(held.embedding, fold_k2),
            "k3_top2_mean": top2_prototype_mean(held.embedding, fold_k3),
            "nearest_enrollment_recording": nearest.filename,
            "nearest_similarity": nearest_sim,
            "furthest_enrollment_recording": furthest.filename,
            "verification_decision": decision,
            "threshold": DEFAULT_VERIFY_MATCH,
            "margin_to_threshold": margin,
            "rank_against_all_non_enrollment_audio": rank,
            "k2_warnings": ";".join(fold_k2["warnings"]),
            "k3_warnings": ";".join(fold_k3["warnings"]),
            "is_hard_positive": held.audio_id in hard_ids,
        }
        loo_rows.append(row)
        if held.audio_id == love.audio_id:
            love_loo = row

    write_csv(output_dir / "leave_one_out.csv", loo_rows)

    # Enrollment curve 2→10 — all combinations
    curve_rows = []
    indexed = list(enumerate(confirmed))
    for size in range(2, 11):
        agg = []
        for combo in itertools.combinations(indexed, size):
            enroll_idx = {i for i, _ in combo}
            enroll = [r for i, r in indexed if i in enroll_idx]
            held_list = [r for i, r in indexed if i not in enroll_idx]
            e_embs = [r.embedding for r in enroll]
            cent = mean_centroid(e_embs)  # type: ignore[arg-type]
            enroll_ids = {r.audio_id for r in enroll}
            for held in held_list:
                assert held.audio_id not in enroll_ids
                sim = float(cosine_similarity(held.embedding, cent))
                decision = verify_decision(sim)
                scored = sorted(
                    [
                        (float(cosine_similarity(g["embedding"], cent)), g["audio_id"])
                        for g in all_gallery
                        if g["audio_id"] not in enroll_ids
                    ],
                    key=lambda x: -x[0],
                )
                rank = next(i for i, (_, aid) in enumerate(scored, start=1) if aid == held.audio_id)
                agg.append(
                    {
                        "sim": sim,
                        "decision": decision,
                        "margin": sim - DEFAULT_VERIFY_MATCH,
                        "top1": rank == 1,
                        "top3": rank <= 3,
                        "top5": rank <= 5,
                    }
                )
        sims = [x["sim"] for x in agg]
        n = max(1, len(agg))
        curve_rows.append(
            {
                "enrollment_size": size,
                "n_evaluations": len(agg),
                "n_combinations": math.comb(11, size),
                "sampling": "ALL_COMBINATIONS",
                "mean_heldout_similarity": float(np.mean(sims)),
                "median_heldout_similarity": float(np.median(sims)),
                "min_heldout_similarity": float(np.min(sims)),
                "p10_heldout_similarity": float(np.percentile(sims, 10)),
                "verification_match_rate": sum(1 for x in agg if x["decision"] == "MATCH") / n,
                "uncertain_rate": sum(1 for x in agg if x["decision"] == "UNCERTAIN") / n,
                "nonmatch_rate": sum(1 for x in agg if x["decision"] == "NON_MATCH") / n,
                "mean_margin_to_threshold": float(np.mean([x["margin"] for x in agg])),
                "worst_case_margin": float(np.min([x["margin"] for x in agg])),
                "global_retrieval_top1_rate": sum(1 for x in agg if x["top1"]) / n,
                "global_retrieval_top3_rate": sum(1 for x in agg if x["top3"]) / n,
                "global_retrieval_top5_rate": sum(1 for x in agg if x["top5"]) / n,
            }
        )
    write_csv(output_dir / "enrollment_size_curve.csv", curve_rows)

    mean2 = curve_rows[0]["mean_heldout_similarity"]
    mean10 = curve_rows[-1]["mean_heldout_similarity"]
    match2 = curve_rows[0]["verification_match_rate"]
    match10 = curve_rows[-1]["verification_match_rate"]
    if mean10 > mean2 + 0.01 and match10 >= match2 - 0.02:
        curve_trend = "IMPROVED"
    elif mean10 < mean2 - 0.01 and match10 <= match2 + 0.02:
        curve_trend = "DEGRADED"
    elif abs(mean10 - mean2) <= 0.01 and abs(match10 - match2) <= 0.02:
        curve_trend = "FLAT"
    else:
        curve_trend = "MIXED"

    # Strategy comparison summary
    hard_loo = [r for r in loo_rows if r["is_hard_positive"]]
    strategy_rows = []
    for name, key in (
        ("SINGLE_CENTROID", "centroid"),
        ("MEDOID", "medoid"),
        ("MULTI_PROTOTYPE_K2", "k2"),
        ("MULTI_PROTOTYPE_K3", "k3"),
    ):
        sims = strategy_accum[key]
        hard_sims = [
            r[{"centroid": "centroid_similarity", "medoid": "medoid_similarity", "k2": "k2_similarity", "k3": "k3_similarity"}[key]]
            for r in hard_loo
        ]
        love_score = love_loo[
            {"centroid": "centroid_similarity", "medoid": "medoid_similarity", "k2": "k2_similarity", "k3": "k3_similarity"}[key]
        ] if love_loo else float("nan")
        strategy_rows.append(
            {
                "strategy": name,
                "loo_match_rate": strategy_match[key] / 11,
                "loo_match_count": strategy_match[key],
                "mean_similarity": float(np.mean(sims)),
                "min_similarity": float(np.min(sims)),
                "hard_positive_mean": float(np.mean(hard_sims)) if hard_sims else float("nan"),
                "love_again_score": love_score,
                "production_default": name == "SINGLE_CENTROID",
                "experimental_only": name != "SINGLE_CENTROID",
            }
        )
    write_csv(output_dir / "strategy_comparison.csv", strategy_rows)

    # Does multi-prototype help hard positives?
    cent_love = love_loo["centroid_similarity"] if love_loo else 0
    k2_love = love_loo["k2_similarity"] if love_loo else 0
    k3_love = love_loo["k3_similarity"] if love_loo else 0
    if max(k2_love, k3_love) > cent_love + 0.02:
        multi_helps = "YES"
    elif max(k2_love, k3_love) < cent_love - 0.02:
        multi_helps = "NO"
    else:
        multi_helps = "MIXED"

    best_pos = max(strategy_rows, key=lambda r: (r["loo_match_rate"], r["min_similarity"], r["hard_positive_mean"]))
    strategy_verdict = "CENTROID_REMAINS_DEFAULT"
    if best_pos["strategy"] != "SINGLE_CENTROID" and best_pos["min_similarity"] > strategy_rows[0]["min_similarity"] + 0.01:
        strategy_verdict = "MULTI_PROTOTYPE_PROMISING_BUT_UNVALIDATED"
    elif strategy_rows[1]["min_similarity"] > strategy_rows[0]["min_similarity"] + 0.01:
        strategy_verdict = "MEDOID_PROMISING"

    # Remaining 62 — default strategy = centroid for rediscovery primary status
    remaining = []
    support_thr = within_stats["p25"] if not math.isnan(within_stats["p25"]) else 0.50
    for g in all_gallery:
        if g["audio_id"] in conf_set:
            continue
        sims = [float(cosine_similarity(g["embedding"], r.embedding)) for r in confirmed]
        arr = np.asarray(sims, dtype=np.float64)
        sim_c = float(cosine_similarity(g["embedding"], centroid))
        sim_m = float(cosine_similarity(g["embedding"], medoid_rec.embedding))
        sim_k2 = max_prototype_similarity(g["embedding"], proto_k2_full)
        sim_k3 = max_prototype_similarity(g["embedding"], proto_k3_full)
        status = classify_remaining(
            min_s=float(np.min(arr)),
            median_s=float(np.median(arr)),
            mean_s=float(np.mean(arr)),
            max_s=float(np.max(arr)),
            std_s=float(np.std(arr)),
            support_ratio=support_ratio_vs_confirmed(sims, support_thr),
            within_mean=within_stats["mean"],
            within_min=within_stats["min"],
        )
        # multi-prototype-only uplift
        multi_only = False
        if status in ("LOW", "BORDERLINE") and max(sim_k2, sim_k3) >= sim_c + 0.08 and max(sim_k2, sim_k3) >= 0.70:
            multi_only = True
            status = "MULTI_PROTOTYPE_ONLY"
        remaining.append(
            {
                "filename": g["filename"],
                "audio_id": g["audio_id"],
                "sha256": g["sha256"],
                "path": g["path"],
                "current_cluster": g["cluster"],
                "sim_centroid": sim_c,
                "sim_medoid": sim_m,
                "sim_k2": sim_k2,
                "sim_k3": sim_k3,
                "mean_similarity_to_confirmed": float(np.mean(arr)),
                "median_similarity_to_confirmed": float(np.median(arr)),
                "min_similarity_to_confirmed": float(np.min(arr)),
                "max_similarity_to_confirmed": float(np.max(arr)),
                "std_similarity_to_confirmed": float(np.std(arr)),
                "support_ratio": support_ratio_vs_confirmed(sims, support_thr),
                "status": status,
                "multi_prototype_only": multi_only,
                "segment_support": float("nan"),
                "old_v2_rank": int(v2_remaining[g["audio_id"]]["rank"])
                if g["audio_id"] in v2_remaining and v2_remaining[g["audio_id"]].get("rank")
                else None,
                "old_v2_status": (v2_remaining.get(g["audio_id"]) or {}).get("status", ""),
            }
        )

    remaining.sort(
        key=lambda c: (-c["sim_centroid"], -c["min_similarity_to_confirmed"], -c["sim_k2"])
    )
    for i, c in enumerate(remaining, start=1):
        c["rank"] = i

    if not skip_segments:
        for c in remaining[:25]:
            npy = segments_dir / f"{c['audio_id']}.npy"
            if not npy.exists():
                continue
            seg_c = np.load(npy)
            supports = []
            for r in confirmed:
                cs = seg_cache.get(r.audio_id)
                if cs is None or cs.size == 0:
                    continue
                supports.append(cross_segment_stats(seg_c, cs).get("support_ratio", float("nan")))
            if supports:
                c["segment_support"] = float(np.nanmean(supports))

    write_csv(output_dir / "remaining_candidates.csv", remaining)

    counts = Counter(c["status"] for c in remaining)
    multi_only_list = [c for c in remaining if c["multi_prototype_only"]]

    # Compare unlabeled score uplift under multi-proto (not true negatives)
    unlabeled_cent = [c["sim_centroid"] for c in remaining]
    unlabeled_k2 = [c["sim_k2"] for c in remaining]
    unlabeled_k3 = [c["sim_k3"] for c in remaining]

    # Cluster validation
    clusters = sorted({r.cluster_id for r in confirmed})
    same_cluster = len(clusters) == 1 and bool(clusters[0])
    member_ids = [
        aid for aid, row in cluster_by_id.items() if row.get("cluster_id") == clusters[0]
    ] if same_cluster else []
    member_set = set(member_ids)
    reviewed_purity = None
    first_fully_reviewed = False
    if same_cluster and member_set == conf_set and len(member_ids) == 11:
        reviewed_purity = 1.0
        first_fully_reviewed = True
    cluster_md = [
        "# Cluster Validation — speaker membership vs USER_CONFIRMED",
        "",
        f"Confirmed cluster IDs: {', '.join(f'`{c}`' for c in clusters)}",
        f"All 11 confirmed in same cluster: **{'YES' if same_cluster else 'NO'}**",
        "",
    ]
    if same_cluster:
        cluster_md += [
            f"`{clusters[0]}` total members: **{len(member_ids)}**",
            f"Confirmed members: **{len(conf_set & member_set)}**",
            f"Different-person confirmed members: **0** (none labeled)",
            "",
        ]
        if first_fully_reviewed:
            cluster_md += [
                "Tag: **FIRST_FULLY_HUMAN_REVIEWED_SINGER_CLUSTER**",
                "",
                "Reviewed members: 11",
                "Confirmed same singer: 11",
                "Confirmed other singer: 0",
                "Reviewed purity: **1.000**",
                "",
                f"`{clusters[0]}` reviewed purity = **100%**",
                "",
                "> This does **not** mean ECAPA clustering accuracy = 100%.",
                "> Do **not** generalize to all 25 clusters.",
                "",
            ]
        else:
            cluster_md += [
                f"Unreviewed in cluster: **{len(member_set - conf_set)}**",
                "Reviewed purity: **NOT_YET_FULLY_REVIEWED**",
                "",
            ]
    (output_dir / "cluster_validation.md").write_text("\n".join(cluster_md), encoding="utf-8")

    # PCA
    pca = pca_2d(conf_ids, conf_embs, [r.filename for r in confirmed])  # type: ignore[arg-type]
    (output_dir / "pca_2d.json").write_text(json.dumps(pca, ensure_ascii=False, indent=2), encoding="utf-8")

    # Profile JSON
    profile = {
        "singer_id": singer_id,
        "profile_id": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "confirmed_recording_count": 11,
        "model_name": "ECAPA-TDNN",
        "model_version": MODEL_VERSION,
        "embedding_dim": int(centroid.shape[0]),
        "mean_centroid_method": "L2-normalize(mean(L2-normalized embeddings))",
        "medoid_audio_id": medoid_id,
        "medoid_filename": medoid_rec.filename,
        "medoid_mean_similarity_to_others": medoid_mean,
        "most_central_recording": most_central["filename"],
        "most_atypical_recording": most_atypical["filename"],
        "within_similarity_statistics": within_stats,
        "hard_positive_cases": [h["filename"] for h in hard_rows],
        "default_strategy": DEFAULT_STRATEGY,
        "multi_prototype_production_enabled": MULTI_PROTOTYPE_PRODUCTION_ENABLED,
        "strategy_verdict": strategy_verdict,
        "false_accept_evaluation": "INSUFFICIENT_MULTI_SINGER_NEGATIVES",
        "model_candidates_excluded_from_profile": True,
        "created_at": _now(),
        "confirmed_recordings": [
            {
                "filename": r.filename,
                "audio_id": r.audio_id,
                "sha256": r.sha256,
                "cluster": r.cluster_id,
                "label_source": "USER_CONFIRMED",
            }
            for r in confirmed
        ],
    }
    np.save(output_dir / "centroid.npy", centroid)
    (output_dir / "profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    write_csv(
        output_dir / "confirmed_recordings.csv",
        [
            {
                "filename": r.filename,
                "audio_id": r.audio_id,
                "sha256": r.sha256,
                "path": r.path,
                "cluster": r.cluster_id,
                "label_source": "USER_CONFIRMED",
                "previous_model_status": r.previous_model_status or "",
            }
            for r in confirmed
        ],
    )

    # old vs new growth
    old_vs = [
        {
            "stage": "2_seed",
            "confirmed": 2,
            "loo_match": "",
            "loo_mean_sim": "",
            "enrollment_note": "frozen seed expansion",
            "seed_pair": 0.6488,
            "curve_trend": "",
            "hard_positives": "",
        },
        {
            "stage": "8_song_v2",
            "confirmed": 8,
            "loo_match": (v2_summary.get("loo") or {}).get("match", ""),
            "loo_mean_sim": (v2_summary.get("loo") or {}).get("mean_sim", ""),
            "enrollment_note": v2_summary.get("enrollment_improves", ""),
            "seed_pair": "",
            "curve_trend": "",
            "hard_positives": "",
        },
        {
            "stage": "11_song_v3",
            "confirmed": 11,
            "loo_match": strategy_match["centroid"],
            "loo_mean_sim": float(np.mean(strategy_accum["centroid"])),
            "enrollment_note": curve_trend,
            "seed_pair": "",
            "curve_trend": curve_trend,
            "hard_positives": len(hard_rows),
        },
    ]
    write_csv(output_dir / "old_vs_new.csv", old_vs)

    # Baseline preview
    baseline = build_experimental_baseline_preview(
        singer_id=singer_id,
        recordings=confirmed,
        reviews_path=repo / "audit_output_final_v2" / "audio_reviews.json",
    )
    available = sum(1 for s in baseline.get("snapshots") or [] if s.get("canonical"))
    baseline["confirmed_recordings"] = 11
    baseline["canonical_analyses_available"] = available
    write_baseline_preview_artifacts(output_dir, baseline)

    # Markdown reports
    loo_pass = sum(1 for r in loo_rows if r["verification_decision"] == "MATCH")
    loo_unc = sum(1 for r in loo_rows if r["verification_decision"] == "UNCERTAIN")
    loo_fail = sum(1 for r in loo_rows if r["verification_decision"] == "NON_MATCH")
    worst = min(loo_rows, key=lambda r: r["centroid_similarity"])

    loo_md = [
        "# 11-way Leave-One-Song-Out",
        "",
        f"MATCH: {loo_pass}/11 · UNCERTAIN: {loo_unc}/11 · NON_MATCH: {loo_fail}/11",
        f"Threshold (frozen): {DEFAULT_VERIFY_MATCH}",
        "",
        "> Rank among non-enrollment is descriptive; unlabeled pool may contain same singer.",
        "",
        "| Held-out | Centroid | Medoid | K2 | K3 | Decision | Rank |",
        "|---|---:|---:|---:|---:|---|---:|",
    ]
    for r in loo_rows:
        loo_md.append(
            f"| {r['heldout_filename']} | {r['centroid_similarity']:.4f} | {r['medoid_similarity']:.4f} | "
            f"{r['k2_similarity']:.4f} | {r['k3_similarity']:.4f} | {r['verification_decision']} | "
            f"{r['rank_against_all_non_enrollment_audio']} |"
        )
    if love_loo:
        loo_md += [
            "",
            "## love again fold (emphasized)",
            "",
            f"- Centroid: {love_loo['centroid_similarity']:.4f}",
            f"- Medoid: {love_loo['medoid_similarity']:.4f}",
            f"- K2: {love_loo['k2_similarity']:.4f}",
            f"- K3: {love_loo['k3_similarity']:.4f}",
            f"- Decision: {love_loo['verification_decision']}",
            f"- Rank: {love_loo['rank_against_all_non_enrollment_audio']}",
            f"- Nearest: {love_loo['nearest_enrollment_recording']}",
            f"- Furthest: {love_loo['furthest_enrollment_recording']}",
            "",
        ]
    (output_dir / "leave_one_out.md").write_text("\n".join(loo_md), encoding="utf-8")

    curve_md = [
        "# Enrollment Size Curve 2→10 (11 confirmed)",
        "",
        "Sampling: **ALL_COMBINATIONS**",
        "",
        "| Size | N | Mean | Min | P10 | MATCH | UNCERTAIN | Top1 retrieval* |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in curve_rows:
        curve_md.append(
            f"| {r['enrollment_size']} | {r['n_evaluations']} | {r['mean_heldout_similarity']:.4f} | "
            f"{r['min_heldout_similarity']:.4f} | {r['p10_heldout_similarity']:.4f} | "
            f"{r['verification_match_rate']:.4f} | {r['uncertain_rate']:.4f} | "
            f"{r['global_retrieval_top1_rate']:.4f} |"
        )
    curve_md += [
        "",
        f"Trend: **{curve_trend}**",
        f"Mean sim 2→10: {mean2:.4f} → {mean10:.4f}",
        f"MATCH rate 2→10: {match2:.4f} → {match10:.4f}",
        f"Worst-case margin 2→10: {curve_rows[0]['worst_case_margin']:.4f} → {curve_rows[-1]['worst_case_margin']:.4f}",
        "",
        "*global retrieval rank rate — not identification accuracy (unlabeled may include same singer).",
        "",
        "v2 frozen curve (8 songs, sizes 2→7) preserved at confirmed_profile_v2/ — reference only.",
        "",
    ]
    (output_dir / "enrollment_size_curve.md").write_text("\n".join(curve_md), encoding="utf-8")

    strat_md = [
        "# Representation Strategy Comparison (EXPERIMENTAL)",
        "",
        "Production default remains **SINGLE_CENTROID**.",
        "Multi-prototype is **not** auto-promoted.",
        "False-accept evaluation: **INSUFFICIENT_MULTI_SINGER_NEGATIVES**",
        "",
        "| Strategy | LOO MATCH | Mean | Min | Hard+ mean | love again |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in strategy_rows:
        strat_md.append(
            f"| {r['strategy']} | {r['loo_match_count']}/11 | {r['mean_similarity']:.4f} | "
            f"{r['min_similarity']:.4f} | {r['hard_positive_mean']:.4f} | {r['love_again_score']:.4f} |"
        )
    strat_md += [
        "",
        f"Does multi-prototype help hard positives: **{multi_helps}**",
        f"Verdict: **{strategy_verdict}**",
        f"Can production winner be selected now: **NO**",
        "",
        f"Unlabeled remaining mean centroid/k2/k3: "
        f"{float(np.mean(unlabeled_cent)):.4f} / {float(np.mean(unlabeled_k2)):.4f} / {float(np.mean(unlabeled_k3)):.4f}",
        "(Not true negatives — do not interpret as false-accept rate.)",
        "",
    ]
    (output_dir / "strategy_comparison.md").write_text("\n".join(strat_md), encoding="utf-8")

    rem_md = [
        "# Remaining Candidates (62)",
        "",
        f"CONSISTENT_HIGH: {counts.get('CONSISTENT_HIGH', 0)}",
        f"STYLE_SPECIFIC: {counts.get('STYLE_SPECIFIC', 0)}",
        f"MULTI_PROTOTYPE_ONLY: {counts.get('MULTI_PROTOTYPE_ONLY', 0)}",
        f"BORDERLINE: {counts.get('BORDERLINE', 0)}",
        f"CONFLICT: {counts.get('CONFLICT', 0)}",
        f"LOW: {counts.get('LOW', 0)}",
        f"UNRESOLVED: {counts.get('UNRESOLVED', 0)}",
        "",
        "## Top 15",
        "",
    ]
    for c in remaining[:15]:
        rem_md.append(
            f"{c['rank']}. **{c['filename']}** · {c['current_cluster']} · "
            f"c={c['sim_centroid']:.3f} m={c['sim_medoid']:.3f} k2={c['sim_k2']:.3f} k3={c['sim_k3']:.3f} "
            f"· **{c['status']}**"
        )
    rem_md += ["", "## MULTI_PROTOTYPE_ONLY candidates", ""]
    if multi_only_list:
        for c in multi_only_list[:20]:
            rem_md.append(
                f"- {c['filename']}: centroid={c['sim_centroid']:.3f} k2={c['sim_k2']:.3f} k3={c['sim_k3']:.3f}"
            )
    else:
        rem_md.append("- _(none)_")
    rem_md += ["", "Automatically confirmed: **NO**", ""]
    (output_dir / "remaining_candidates.md").write_text("\n".join(rem_md), encoding="utf-8")

    report = [
        "# Confirmed Singer Profile v3",
        "",
        f"Singer: **{singer_id}**",
        "Human-confirmed recordings: **11**",
        "",
    ]
    for i, r in enumerate(confirmed, 1):
        report.append(f"{i}. {r.filename} (`{r.audio_id}`) · `{r.cluster_id}`")
    report += [
        "",
        f"Medoid: **{medoid_rec.filename}** · Most atypical: **{most_atypical['filename']}**",
        f"Within mean/min/max: {within_stats['mean']:.4f} / {within_stats['min']:.4f} / {within_stats['max']:.4f}",
        f"Hardest pair: {hardest[3]} ↔ {hardest[4]} ({hardest[0]:.4f})",
        "",
        f"LOO MATCH: {loo_pass}/11 · love again held-out decision: "
        f"{love_loo['verification_decision'] if love_loo else 'n/a'}",
        f"Enrollment curve 2→10: **{curve_trend}**",
        f"Strategy verdict: **{strategy_verdict}** (production default: SINGLE_CENTROID)",
        f"speaker_009 reviewed purity: "
        f"{'1.000' if reviewed_purity == 1.0 else 'see cluster_validation.md'}",
        "",
        "ECAPA fine-tuned: NO · threshold retuned: NO · multi-prototype production: NO · VAgent: NO",
        "",
    ]
    (output_dir / "report.md").write_text("\n".join(report), encoding="utf-8")

    build_review_html_v3(
        out_path=output_dir / "review_queue.html",
        confirmed=confirmed,
        medoid_id=medoid_id,
        hardest_id=most_atypical["audio_id"],
        love_again_id=love.audio_id,
        candidates=remaining,
    )

    review_path = repo / "singer_identity_labels" / "reviews" / "confirmed_profile_v3_review.json"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    if not review_path.exists():
        review_path.write_text(
            json.dumps(
                {
                    "singer_id": singer_id,
                    "profile_version": 3,
                    "reviews": {},
                    "note": "HUMAN_REVIEW does not auto-expand profile.",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    summary = {
        "singer_id": singer_id,
        "confirmed": [
            {
                "filename": r.filename,
                "audio_id": r.audio_id,
                "sha256": r.sha256,
                "cluster": r.cluster_id,
            }
            for r in confirmed
        ],
        "within_singer": within_stats,
        "medoid": medoid_rec.filename,
        "most_central": most_central["filename"],
        "most_atypical": most_atypical["filename"],
        "hardest_pair": {"a": hardest[3], "b": hardest[4], "sim": hardest[0]},
        "easiest_pair": {"a": easiest[3], "b": easiest[4], "sim": easiest[0]},
        "love_again": love_stats,
        "love_loo": love_loo,
        "hard_positives": hard_rows,
        "loo": {
            "match": loo_pass,
            "uncertain": loo_unc,
            "non_match": loo_fail,
            "mean_sim": float(np.mean(strategy_accum["centroid"])),
            "min_sim": float(np.min(strategy_accum["centroid"])),
            "worst": worst["heldout_filename"],
            "folds": loo_rows,
        },
        "enrollment_curve": curve_rows,
        "curve_trend": curve_trend,
        "strategy_rows": strategy_rows,
        "strategy_verdict": strategy_verdict,
        "multi_helps_hard_positives": multi_helps,
        "remaining_counts": dict(counts),
        "remaining_top15": remaining[:15],
        "multi_prototype_only": multi_only_list,
        "cluster": {
            "ids": clusters,
            "same": same_cluster,
            "members": len(member_ids),
            "reviewed_purity": reviewed_purity,
            "first_fully_reviewed": first_fully_reviewed,
        },
        "baseline_canonical_available": available,
        "false_accept": "INSUFFICIENT_MULTI_SINGER_NEGATIVES",
        "output": str(output_dir),
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return summary
