# -*- coding: utf-8 -*-
"""Confirmed Singer Profile v2 — analysis only; no VAgent production integration."""

from __future__ import annotations

import csv
import itertools
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from services.singer_identity.config import DEFAULT_VERIFY_MATCH, DEFAULT_VERIFY_NONMATCH
from services.singer_identity.inference.encoder import cosine_similarity, l2_normalize
from services.singer_identity.seed_expansion.core import (
    cross_segment_stats,
    load_audio_embedding,
    write_csv,
)

SINGER_ID = "person_drowning_movie"
PROFILE_VERSION = 2
PROFILE_ID = "person_drowning_movie_profile_v2"

# Exact stem matches (case-insensitive); Unicode NFC-safe via Path.name
CONFIRMED_STEMS = [
    "drowning",
    "movie",
    "거의동115",
    "거의동116",
    "거의동117",
    "좋은사람",
    "요즘 바쁜가봐",
    "bluemoon",
]

# Still MODEL_CANDIDATE — never auto-promote
UNCONFIRMED_HIGH_STEMS = [
    "i'llneverloveagain",
    "love again",
    "옥탑방",
]

# Frozen 2-seed baseline path (do not overwrite)
FROZEN_2SEED_CANDIDATES = Path("singer_identity_output/seed_expansion/drowning_movie/candidates.csv")
FROZEN_2SEED_SUMMARY = Path("singer_identity_output/seed_expansion/drowning_movie/run_summary.json")


@dataclass
class RecordingRef:
    stem: str
    filename: str
    path: str
    audio_id: str
    sha256: str
    cluster_id: str = ""
    embedding: Optional[np.ndarray] = None
    previous_label_source: Optional[str] = None
    previous_model_status: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_stem(name: str) -> str:
    return Path(name).stem.lower().strip()


def resolve_exact_stems(
    manifest_audios: list[dict[str, Any]],
    stems: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Match by exact filename stem (case-insensitive), not substring-in-path."""
    wanted = {s.lower(): s for s in stems}
    out: dict[str, list[dict[str, Any]]] = {s: [] for s in stems}
    for a in manifest_audios:
        path = str(a.get("path") or "")
        stem = _norm_stem(Path(path).name)
        for key, orig in wanted.items():
            if stem == key:
                out[orig].append(a)
    return out


def load_clusters(clusters_csv: Path) -> dict[str, dict[str, str]]:
    by_id: dict[str, dict[str, str]] = {}
    if not clusters_csv.exists():
        return by_id
    with clusters_csv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_id[row["audio_id"]] = row
    return by_id


def promote_confirmed_labels(
    labels_path: Path,
    recordings: list[RecordingRef],
    *,
    singer_id: str = SINGER_ID,
) -> dict[str, Any]:
    """Promote confirmed SHAs to USER_CONFIRMED; never touch other singers or auto-promote unconfirmed."""
    data = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.exists() else {}
    data.setdefault("version", "singer-identity-labels-v1")
    data.setdefault("same_singer_groups", {})
    data.setdefault("recordings", {})
    group = data["same_singer_groups"].setdefault(singer_id, [])
    confirmed_shas = {r.sha256 for r in recordings}

    for r in recordings:
        prev = data["recordings"].get(r.sha256) or {}
        if prev.get("singer_id") == "person_controlled_v1":
            raise ValueError(f"refusing to overwrite controlled label: {r.sha256}")
        previous_source = prev.get("label_source")
        role = "SEED" if r.stem in ("drowning", "movie") else "CONFIRMED"
        entry = {
            "singer_id": singer_id,
            "display_name": "Drowning/Movie Singer",
            "label_source": "USER_CONFIRMED",
            "confidence": "CONFIRMED",
            "role": role,
            "filename": r.filename,
            "audio_id": r.audio_id,
            "confirmed_at": _now(),
            "confirmation_source": "USER_CONFIRMED_PROFILE_V2",
            "profile_version": PROFILE_VERSION,
        }
        if previous_source and previous_source != "USER_CONFIRMED":
            entry["previous_label_source"] = previous_source
        elif r.previous_model_status and not previous_source:
            entry["previous_label_source"] = "MODEL_CANDIDATE"
        if previous_source == "USER_CONFIRMED" and prev.get("role") == "SEED":
            entry["role"] = "SEED"
            entry["seed_name"] = prev.get("seed_name") or r.stem
        if r.previous_model_status:
            entry["previous_model_status"] = r.previous_model_status
        data["recordings"][r.sha256] = entry
        if r.sha256 not in group:
            group.append(r.sha256)

    # Ensure group equals exactly confirmed set (append-only for other singers already preserved)
    data["same_singer_groups"][singer_id] = [s for s in group if s in confirmed_shas] + [
        s for s in confirmed_shas if s not in group
    ]
    # Deduplicate preserving order
    seen = set()
    ordered = []
    for s in data["same_singer_groups"][singer_id]:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    data["same_singer_groups"][singer_id] = ordered

    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def mean_centroid(embs: list[np.ndarray]) -> np.ndarray:
    stacked = np.stack([l2_normalize(e) for e in embs], axis=0)
    return l2_normalize(np.mean(stacked, axis=0))


def compute_medoid(ids: list[str], embs: list[np.ndarray]) -> tuple[str, float]:
    """Recording with highest mean similarity to the other members."""
    best_i = 0
    best_mean = -1.0
    for i in range(len(embs)):
        sims = [cosine_similarity(embs[i], embs[j]) for j in range(len(embs)) if j != i]
        m = float(np.mean(sims)) if sims else 0.0
        if m > best_mean:
            best_mean = m
            best_i = i
    return ids[best_i], best_mean


def pairwise_sims(embs: list[np.ndarray]) -> list[float]:
    out = []
    for i in range(len(embs)):
        for j in range(i + 1, len(embs)):
            out.append(float(cosine_similarity(embs[i], embs[j])))
    return out


def sim_stats(sims: list[float]) -> dict[str, float]:
    if not sims:
        return {
            "mean": float("nan"),
            "median": float("nan"),
            "min": float("nan"),
            "max": float("nan"),
            "std": float("nan"),
            "p25": float("nan"),
            "p75": float("nan"),
            "n_pairs": 0,
        }
    arr = np.asarray(sims, dtype=np.float64)
    return {
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "std": float(np.std(arr)),
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75)),
        "n_pairs": int(len(arr)),
    }


def verify_decision(sim: float, *, match_thr: float = DEFAULT_VERIFY_MATCH, nonmatch_thr: float = DEFAULT_VERIFY_NONMATCH) -> str:
    if sim >= match_thr:
        return "MATCH"
    if sim <= nonmatch_thr:
        return "NON_MATCH"
    return "UNCERTAIN"


def load_frozen_2seed_ranks(repo: Path) -> dict[str, dict[str, Any]]:
    """Frozen baseline ranks from seed expansion CSV — never recomputed."""
    path = repo / FROZEN_2SEED_CANDIDATES
    by_id: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return by_id
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_id[row["audio_id"]] = row
    return by_id


def load_frozen_2seed_summary(repo: Path) -> dict[str, Any]:
    path = repo / FROZEN_2SEED_SUMMARY
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def two_seed_recall_at_k(
    frozen_ranks: dict[str, dict[str, Any]],
    confirmed_ids: set[str],
    seed_ids: set[str],
    ks: tuple[int, ...] = (1, 3, 5, 10, 15),
) -> dict[str, float]:
    """
    Enrollment = drowning+movie. Gallery ranking among non-seed audios.
    How many of the other confirmed songs appear in top-k of frozen 2-seed ranking.
    """
    targets = confirmed_ids - seed_ids
    ranked = sorted(
        [r for aid, r in frozen_ranks.items() if aid not in seed_ids],
        key=lambda r: int(r.get("rank") or 9999),
    )
    ranked_ids = [r["audio_id"] for r in ranked]
    out: dict[str, float] = {}
    n = max(1, len(targets))
    for k in ks:
        top = set(ranked_ids[:k])
        hit = len(targets & top)
        out[f"recall@{k}"] = hit / n
        out[f"hits@{k}"] = float(hit)
    out["n_targets"] = float(len(targets))
    return out


def classify_remaining(
    *,
    min_s: float,
    median_s: float,
    mean_s: float,
    max_s: float,
    std_s: float,
    support_ratio: float,
    within_mean: float,
    within_min: float,
) -> str:
    """Relative to within-singer distribution — not tuned to force a count."""
    if math.isnan(min_s) or math.isnan(median_s):
        return "UNRESOLVED"
    high_floor = within_min * 0.92 if not math.isnan(within_min) else 0.55
    mid_floor = within_mean * 0.75 if not math.isnan(within_mean) else 0.45
    gap = max_s - min_s
    if gap >= 0.28 and max_s >= (within_mean * 0.95 if not math.isnan(within_mean) else 0.60):
        if min_s < mid_floor:
            return "CONFLICT"
        return "STYLE_SPECIFIC"
    if min_s >= high_floor and median_s >= (within_mean * 0.90 if not math.isnan(within_mean) else 0.55):
        if not math.isnan(support_ratio) and support_ratio < 0.35:
            return "STYLE_SPECIFIC"
        return "CONSISTENT_HIGH"
    if max_s >= (within_mean * 0.95 if not math.isnan(within_mean) else 0.60) and min_s < mid_floor:
        return "STYLE_SPECIFIC"
    if median_s >= mid_floor or mean_s >= mid_floor:
        return "BORDERLINE"
    return "LOW"


def support_ratio_vs_confirmed(sims: list[float], thr: float) -> float:
    if not sims:
        return float("nan")
    return float(np.mean(np.asarray(sims) >= thr))


def build_review_html_v2(
    *,
    out_path: Path,
    confirmed: list[RecordingRef],
    medoid_id: str,
    hardest_pair: tuple[str, str],
    candidates: list[dict[str, Any]],
) -> None:
    by_id = {r.audio_id: r for r in confirmed}
    medoid = by_id[medoid_id]
    hard_a = by_id.get(hardest_pair[0]) or confirmed[0]
    hard_b = by_id.get(hardest_pair[1]) or confirmed[1]
    # use the harder recording vs medoid as "most different" reference
    def mean_to_others(r: RecordingRef) -> float:
        sims = [
            cosine_similarity(r.embedding, o.embedding)
            for o in confirmed
            if o.audio_id != r.audio_id and r.embedding is not None and o.embedding is not None
        ]
        return float(np.mean(sims)) if sims else 0.0

    farthest = min(confirmed, key=mean_to_others)
    refs = [
        {
            "audio_id": r.audio_id,
            "sha256": r.sha256,
            "filename": r.filename,
            "path": r.path.replace("\\", "/"),
            "is_medoid": r.audio_id == medoid_id,
        }
        for r in confirmed
    ]
    reviewable = [
        c
        for c in candidates
        if c.get("status") in ("CONSISTENT_HIGH", "STYLE_SPECIFIC", "BORDERLINE", "CONFLICT")
    ]
    payload = {
        "singer_id": SINGER_ID,
        "profile_version": PROFILE_VERSION,
        "medoid": {
            "filename": medoid.filename,
            "path": medoid.path.replace("\\", "/"),
            "sha256": medoid.sha256,
            "audio_id": medoid.audio_id,
        },
        "farthest": {
            "filename": farthest.filename,
            "path": farthest.path.replace("\\", "/"),
            "sha256": farthest.sha256,
            "audio_id": farthest.audio_id,
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
                "median_confirmed": round(float(c["median_similarity_to_confirmed"]), 4),
                "min_confirmed": round(float(c["min_similarity_to_confirmed"]), 4),
                "support_ratio": None
                if c.get("support_ratio") is None or (isinstance(c.get("support_ratio"), float) and math.isnan(c["support_ratio"]))
                else round(float(c["support_ratio"]), 4),
                "segment_support": None
                if c.get("segment_support") is None
                or (isinstance(c.get("segment_support"), float) and math.isnan(float(c.get("segment_support"))))
                else round(float(c["segment_support"]), 4),
                "cluster": c.get("current_cluster", ""),
                "old_rank": c.get("old_rank"),
                "new_rank": c.get("rank"),
            }
            for c in reviewable
        ],
    }
    data_json = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<title>Confirmed Profile v2 Review (local)</title>
<style>
body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; background:#0f1216; color:#e8eaed; }}
h1,h2 {{ color:#fff; }}
.card {{ background:#1a1f27; border:1px solid #2a3340; border-radius:10px; padding:14px; margin:12px 0; }}
.muted {{ color:#9aa3af; }}
button {{ margin:4px; padding:8px 12px; border-radius:8px; border:1px solid #2a3340; background:#11151b; color:#e8eaed; cursor:pointer; }}
button.same {{ border-color:#3fb950; }}
button.diff {{ border-color:#ff7b72; }}
button.unk {{ border-color:#e3b341; }}
.nums.hidden {{ display:none; }}
.refs.hidden {{ display:none; }}
audio {{ width:100%; margin-top:8px; }}
.row {{ display:grid; grid-template-columns: 1fr 1fr; gap:12px; }}
@media (max-width:900px) {{ .row {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<h1>Confirmed Singer Profile v2 — Human Review</h1>
<p class="muted">Local-only. MODEL_CANDIDATE는 사람 확인 전까지 ground truth가 아닙니다. Blind mode 기본 ON.</p>
<label><input type="checkbox" id="blind" checked/> Blind Review Mode (숫자 숨김)</label>
<div class="card">
  <h2>Confirmed Singer References (8)</h2>
  <div class="row">
    <div><b>대표(medoid):</b> <span id="medName"></span><audio id="medAud" controls></audio></div>
    <div><b>가장 다른 확정 음원:</b> <span id="farName"></span><audio id="farAud" controls></audio></div>
  </div>
  <button id="toggleRefs">확정 8곡 전체 보기</button>
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
  try {{ return JSON.parse(localStorage.getItem("confirmed_profile_v2_review")||"{{}}"); }}
  catch {{ return {{}}; }}
}}
function saveLocal(obj) {{
  localStorage.setItem("confirmed_profile_v2_review", JSON.stringify(obj, null, 2));
  document.getElementById("export").textContent = JSON.stringify(obj, null, 2);
}}
document.getElementById("medName").textContent = DATA.medoid.filename;
document.getElementById("farName").textContent = DATA.farthest.filename;
document.getElementById("medAud").src = fileUrl(DATA.medoid.path);
document.getElementById("farAud").src = fileUrl(DATA.farthest.path);
const refBox = document.getElementById("allRefs");
DATA.confirmed.forEach(r => {{
  const d = document.createElement("div");
  d.innerHTML = `<div class="muted">${{r.filename}}${{r.is_medoid ? " (medoid)" : ""}}</div><audio controls src="${{fileUrl(r.path)}}"></audio>`;
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
      <div class="muted">cluster: ${{c.cluster}} · old_rank: ${{c.old_rank}} · new_rank: ${{c.new_rank}}</div>
      <audio controls src="${{fileUrl(c.path)}}"></audio>
      <div class="nums ${{blind ? "hidden" : ""}}">
        centroid: ${{c.sim_centroid}} · medoid: ${{c.sim_medoid}} · median_confirmed: ${{c.median_confirmed}} ·
        min_confirmed: ${{c.min_confirmed}} · support: ${{c.support_ratio}} · segment: ${{c.segment_support}}
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
        if (d === "REVEAL") {{
          div.querySelector(".nums").classList.remove("hidden");
          return;
        }}
        decisions.reviews[c.sha256] = {{
          decision: d,
          filename: c.filename,
          audio_id: c.audio_id,
          sha256: c.sha256,
          model_status: c.status,
          label_source: "HUMAN_REVIEW",
          relationship: d === "SAME" ? "person_drowning_movie" : (d === "DIFFERENT" ? "NOT_person_drowning_movie" : "UNCERTAIN"),
          note: "Does not auto-expand profile; explicit rebuild required for profile v3",
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
  <h2>Export → singer_identity_labels/reviews/confirmed_profile_v2_review.json</h2>
  <pre id="export" style="white-space:pre-wrap;background:#11151b;padding:12px;border-radius:8px;"></pre>
</div>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")


def run_confirmed_profile_v2(
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
    output_dir = output_dir or (
        repo / "singer_identity_output" / "confirmed_profile_v2" / singer_id
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audios = list(manifest.get("audios") or [])
    cluster_by_id = load_clusters(clusters_csv)
    frozen_ranks = load_frozen_2seed_ranks(repo)
    frozen_summary = load_frozen_2seed_summary(repo)

    hits = resolve_exact_stems(audios, CONFIRMED_STEMS)
    confirmed: list[RecordingRef] = []
    ambiguity: list[str] = []
    for stem in CONFIRMED_STEMS:
        raw_hits = hits[stem]
        by_sha: dict[str, dict[str, Any]] = {}
        for h in raw_hits:
            by_sha[str(h.get("sha256") or "")] = h
        if len(by_sha) == 0:
            raise FileNotFoundError(f"confirmed stem not found: {stem}")
        if len(by_sha) > 1:
            ambiguity.append(f"{stem}: multiple SHAs {list(by_sha)}")
            raise ValueError(f"AMBIGUITY for {stem}: {list(by_sha.keys())}")
        h = next(iter(by_sha.values()))
        aid = h["audio_id"]
        emb = load_audio_embedding(embeddings_dir, aid)
        prev_status = None
        if aid in frozen_ranks:
            prev_status = frozen_ranks[aid].get("status")
        confirmed.append(
            RecordingRef(
                stem=stem,
                filename=Path(h["path"]).name,
                path=str(h["path"]),
                audio_id=aid,
                sha256=str(h["sha256"]),
                cluster_id=(cluster_by_id.get(aid) or {}).get("cluster_id", ""),
                embedding=emb,
                previous_model_status=prev_status,
            )
        )

    shas = [r.sha256 for r in confirmed]
    if len(set(shas)) != 8:
        raise ValueError(f"expected 8 unique SHAs, got {len(set(shas))}")

    # provenance from existing labels before promote
    if labels_path.exists():
        old_labels = json.loads(labels_path.read_text(encoding="utf-8"))
        for r in confirmed:
            prev = (old_labels.get("recordings") or {}).get(r.sha256) or {}
            r.previous_label_source = prev.get("label_source")

    promote_confirmed_labels(labels_path, confirmed, singer_id=singer_id)

    # Ensure unconfirmed HIGH remain unconfirmed
    unconf_hits = resolve_exact_stems(audios, UNCONFIRMED_HIGH_STEMS)
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    for stem, lst in unconf_hits.items():
        for h in lst:
            sha = h["sha256"]
            rec = (labels.get("recordings") or {}).get(sha)
            if rec and rec.get("label_source") == "USER_CONFIRMED" and rec.get("singer_id") == singer_id:
                # should not happen unless previously wrongly set — strip only if not in confirmed
                if sha not in shas:
                    raise AssertionError(f"unconfirmed high was USER_CONFIRMED: {stem}")

    conf_ids = [r.audio_id for r in confirmed]
    conf_embs = [r.embedding for r in confirmed]
    centroid = mean_centroid(conf_embs)
    medoid_id, medoid_mean = compute_medoid(conf_ids, conf_embs)
    within = pairwise_sims(conf_embs)
    within_stats = sim_stats(within)

    # pairwise matrix + hardest/easiest
    name_by_id = {r.audio_id: r.filename for r in confirmed}
    matrix_rows = []
    pair_list = []
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

    # segment cross among confirmed (optional summary)
    seg_cache: dict[str, np.ndarray] = {}
    if not skip_segments:
        for r in confirmed:
            npy = segments_dir / f"{r.audio_id}.npy"
            if npy.exists():
                seg_cache[r.audio_id] = np.load(npy)

    segment_pair_medians = []
    for i, a in enumerate(confirmed):
        for j, b in enumerate(confirmed):
            if i >= j:
                continue
            sa, sb = seg_cache.get(a.audio_id), seg_cache.get(b.audio_id)
            if sa is None or sb is None or sa.size == 0 or sb.size == 0:
                continue
            st = cross_segment_stats(sa, sb)
            segment_pair_medians.append(st.get("median", float("nan")))

    # Leave-one-out
    conf_set = set(conf_ids)
    all_gallery = []
    for a in audios:
        aid = a["audio_id"]
        p = embeddings_dir / f"{aid}.npy"
        if not p.exists():
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

    loo_rows = []
    for held in confirmed:
        enroll = [r for r in confirmed if r.audio_id != held.audio_id]
        enroll_embs = [r.embedding for r in enroll]
        assert held.embedding is not None
        assert all(e is not None for e in enroll_embs)
        # leakage guard: held embedding not in enroll
        fold_cent = mean_centroid(enroll_embs)
        fold_medoid_id, _ = compute_medoid([r.audio_id for r in enroll], enroll_embs)
        fold_medoid_emb = next(r.embedding for r in enroll if r.audio_id == fold_medoid_id)
        sim_cent = float(cosine_similarity(held.embedding, fold_cent))
        sim_med = float(cosine_similarity(held.embedding, fold_medoid_emb))
        nearest = None
        nearest_sim = -1.0
        for r in enroll:
            s = float(cosine_similarity(held.embedding, r.embedding))
            if s > nearest_sim:
                nearest_sim = s
                nearest = r
        # rank among all non-enrollment (includes held-out + 65 others)
        enroll_ids = {r.audio_id for r in enroll}
        scored = []
        for g in all_gallery:
            if g["audio_id"] in enroll_ids:
                continue
            scored.append((float(cosine_similarity(g["embedding"], fold_cent)), g["audio_id"]))
        scored.sort(key=lambda x: -x[0])
        rank = next(i for i, (s, aid) in enumerate(scored, start=1) if aid == held.audio_id)
        # margin: held sim - best non-target (non-confirmed) competitor
        best_non_target = -1.0
        for s, aid in scored:
            if aid == held.audio_id:
                continue
            if aid not in conf_set:
                best_non_target = s
                break
        margin = sim_cent - best_non_target if best_non_target >= 0 else float("nan")
        decision = verify_decision(sim_cent)
        loo_rows.append(
            {
                "heldout_filename": held.filename,
                "heldout_audio_id": held.audio_id,
                "enrollment_count": 7,
                "enrollment_filenames": ";".join(r.filename for r in enroll),
                "similarity_to_7song_centroid": sim_cent,
                "similarity_to_medoid": sim_med,
                "nearest_confirmed_recording": nearest.filename if nearest else "",
                "nearest_similarity": nearest_sim,
                "rank_among_non_enrollment": rank,
                "margin_vs_nearest_non_target": margin,
                "verification_decision": decision,
                "match_threshold": DEFAULT_VERIFY_MATCH,
                "nonmatch_threshold": DEFAULT_VERIFY_NONMATCH,
            }
        )
    write_csv(output_dir / "leave_one_out.csv", loo_rows)

    # Enrollment size curve — all combinations
    curve_rows = []
    curve_agg: dict[int, list[dict[str, Any]]] = {k: [] for k in range(2, 8)}
    indexed = list(enumerate(confirmed))
    for size in range(2, 8):
        for combo in itertools.combinations(indexed, size):
            enroll_idx = [i for i, _ in combo]
            enroll = [r for _, r in combo]
            held_list = [r for i, r in indexed if i not in enroll_idx]
            e_embs = [r.embedding for r in enroll]
            cent = mean_centroid(e_embs)
            for held in held_list:
                sim = float(cosine_similarity(held.embedding, cent))
                decision = verify_decision(sim)
                # top1 among held-outs + all non-confirmed? Use: among all non-enrollment, is held rank 1 among confirmed-heldouts relative to centroid
                enroll_ids = {r.audio_id for r in enroll}
                scored = [
                    (float(cosine_similarity(g["embedding"], cent)), g["audio_id"])
                    for g in all_gallery
                    if g["audio_id"] not in enroll_ids
                ]
                scored.sort(key=lambda x: -x[0])
                top1_id = scored[0][1] if scored else ""
                # Top1 rate for this held-out: is this held-out the nearest non-enrollment?
                is_top1 = top1_id == held.audio_id
                # also: rank among confirmed held-outs only
                held_sims = sorted(
                    [(float(cosine_similarity(h.embedding, cent)), h.audio_id) for h in held_list],
                    key=lambda x: -x[0],
                )
                held_top1 = held_sims[0][1] == held.audio_id if held_sims else False
                curve_agg[size].append(
                    {
                        "sim": sim,
                        "decision": decision,
                        "is_top1_global": is_top1,
                        "is_top1_among_heldouts": held_top1,
                    }
                )
        sims = [x["sim"] for x in curve_agg[size]]
        match_n = sum(1 for x in curve_agg[size] if x["decision"] == "MATCH")
        unc_n = sum(1 for x in curve_agg[size] if x["decision"] == "UNCERTAIN")
        top1_global = sum(1 for x in curve_agg[size] if x["is_top1_global"])
        n = max(1, len(curve_agg[size]))
        curve_rows.append(
            {
                "enrollment_size": size,
                "n_evaluations": len(curve_agg[size]),
                "mean_heldout_similarity": float(np.mean(sims)),
                "min_heldout_similarity": float(np.min(sims)),
                "median_heldout_similarity": float(np.median(sims)),
                "top1_global_rate": top1_global / n,
                "verification_match_rate": match_n / n,
                "uncertain_rate": unc_n / n,
                "nonmatch_rate": sum(1 for x in curve_agg[size] if x["decision"] == "NON_MATCH") / n,
            }
        )
    write_csv(output_dir / "enrollment_size_curve.csv", curve_rows)

    # Remaining 65 search
    conf_id_set = set(conf_ids)
    conf_sha_set = set(shas)
    seed_ids = {r.audio_id for r in confirmed if r.stem in ("drowning", "movie")}
    recall = two_seed_recall_at_k(frozen_ranks, conf_id_set, seed_ids)

    support_thr = within_stats["p25"] if not math.isnan(within_stats["p25"]) else 0.50
    remaining = []
    for g in all_gallery:
        if g["audio_id"] in conf_id_set:
            continue
        sims = [float(cosine_similarity(g["embedding"], r.embedding)) for r in confirmed]
        arr = np.asarray(sims, dtype=np.float64)
        sim_cent = float(cosine_similarity(g["embedding"], centroid))
        medoid_emb = next(r.embedding for r in confirmed if r.audio_id == medoid_id)
        sim_med = float(cosine_similarity(g["embedding"], medoid_emb))
        support = support_ratio_vs_confirmed(sims, support_thr)
        status = classify_remaining(
            min_s=float(np.min(arr)),
            median_s=float(np.median(arr)),
            mean_s=float(np.mean(arr)),
            max_s=float(np.max(arr)),
            std_s=float(np.std(arr)),
            support_ratio=support,
            within_mean=within_stats["mean"],
            within_min=within_stats["min"],
        )
        old = frozen_ranks.get(g["audio_id"]) or {}
        old_rank = int(old["rank"]) if old.get("rank") else None
        old_status = old.get("status", "")
        remaining.append(
            {
                "filename": g["filename"],
                "audio_id": g["audio_id"],
                "sha256": g["sha256"],
                "path": g["path"],
                "current_cluster": g["cluster"],
                "sim_centroid": sim_cent,
                "sim_medoid": sim_med,
                "mean_similarity_to_confirmed": float(np.mean(arr)),
                "median_similarity_to_confirmed": float(np.median(arr)),
                "min_similarity_to_confirmed": float(np.min(arr)),
                "max_similarity_to_confirmed": float(np.max(arr)),
                "p25_similarity": float(np.percentile(arr, 25)),
                "p75_similarity": float(np.percentile(arr, 75)),
                "similarity_std": float(np.std(arr)),
                "support_ratio": support,
                "status": status,
                "old_rank": old_rank,
                "old_status": old_status,
                "segment_support": float("nan"),
                "newly_discovered": False,
            }
        )

    # rank by min then median (consistency-first)
    remaining.sort(
        key=lambda c: (
            -c["min_similarity_to_confirmed"],
            -c["median_similarity_to_confirmed"],
            -c["sim_centroid"],
        )
    )
    for i, c in enumerate(remaining, start=1):
        c["rank"] = i
        c["rank_delta"] = (c["old_rank"] - i) if c["old_rank"] is not None else None
        # newly discovered: was LOW/MEDIUM/absent in old, now CONSISTENT_HIGH or strong STYLE
        if c["status"] in ("CONSISTENT_HIGH",) and c["old_status"] in (
            "LOW_CANDIDATE",
            "MEDIUM_CANDIDATE",
            "UNRESOLVED",
            "",
        ):
            c["newly_discovered"] = True
        if c["status"] == "CONSISTENT_HIGH" and c["old_rank"] is not None and c["old_rank"] > 15:
            c["newly_discovered"] = True

    # segment support for interesting candidates
    if not skip_segments:
        interesting = [
            c
            for c in remaining
            if c["status"] in ("CONSISTENT_HIGH", "STYLE_SPECIFIC", "CONFLICT")
            or c["rank"] <= 20
        ]
        # aggregate confirmed segments
        conf_segs = [seg_cache[r.audio_id] for r in confirmed if r.audio_id in seg_cache]
        for c in interesting:
            npy = segments_dir / f"{c['audio_id']}.npy"
            if not npy.exists() or not conf_segs:
                continue
            seg_c = np.load(npy)
            supports = []
            meds = []
            for cs in conf_segs:
                st = cross_segment_stats(seg_c, cs)
                supports.append(st.get("support_ratio", float("nan")))
                meds.append(st.get("median", float("nan")))
            c["segment_support"] = float(np.nanmean(supports)) if supports else float("nan")
            c["segment_median_vs_confirmed"] = float(np.nanmean(meds)) if meds else float("nan")

    rem_csv = []
    for c in remaining:
        rem_csv.append(
            {
                **{k: c[k] for k in c if k != "path"},
                "path": c["path"],
                "review_required": c["status"]
                in ("CONSISTENT_HIGH", "STYLE_SPECIFIC", "BORDERLINE", "CONFLICT"),
            }
        )
    write_csv(output_dir / "remaining_candidates.csv", rem_csv)

    old_vs_new = [
        {
            "filename": c["filename"],
            "audio_id": c["audio_id"],
            "old_rank": c["old_rank"],
            "new_rank": c["rank"],
            "rank_delta": c["rank_delta"],
            "old_status": c["old_status"],
            "new_status": c["status"],
            "newly_discovered": c["newly_discovered"],
        }
        for c in remaining
    ]
    write_csv(output_dir / "old_vs_new_ranking.csv", old_vs_new)

    # confirmed recordings csv
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
                "previous_label_source": r.previous_label_source or "",
                "previous_model_status": r.previous_model_status or "",
            }
            for r in confirmed
        ],
    )

    # profile.json
    medoid_rec = next(r for r in confirmed if r.audio_id == medoid_id)
    profile = {
        "singer_id": singer_id,
        "profile_id": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "display_name": "Drowning/Movie Singer",
        "encoder": "ECAPA-TDNN (cached audio embeddings)",
        "embedding_dim": int(centroid.shape[0]),
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
        "confirmed_count": 8,
        "centroid_method": "L2-normalize(mean(L2-normalized embeddings))",
        "medoid_audio_id": medoid_id,
        "medoid_filename": medoid_rec.filename,
        "medoid_mean_similarity_to_others": medoid_mean,
        "within_singer": within_stats,
        "hardest_pair": {
            "a": hardest[3],
            "b": hardest[4],
            "similarity": hardest[0],
            "audio_ids": [hardest[1], hardest[2]],
        },
        "easiest_pair": {
            "a": easiest[3],
            "b": easiest[4],
            "similarity": easiest[0],
            "audio_ids": [easiest[1], easiest[2]],
        },
        "segment_pair_median_mean": float(np.nanmean(segment_pair_medians))
        if segment_pair_medians
        else None,
        "model_candidates_excluded_from_profile": True,
        "ambiguity": ambiguity,
        "created_at": _now(),
    }
    np.save(output_dir / "centroid.npy", centroid)
    (output_dir / "profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # cluster GT
    clusters = sorted({r.cluster_id for r in confirmed})
    same_cluster = len(clusters) == 1 and bool(clusters[0])
    member_ids = [
        aid for aid, row in cluster_by_id.items() if row.get("cluster_id") == clusters[0]
    ] if same_cluster else []
    unreviewed = [aid for aid in member_ids if aid not in conf_id_set]

    cluster_md = [
        "# Cluster Ground Truth — person_drowning_movie",
        "",
        f"Confirmed recordings: **8**",
        f"Cluster IDs: {', '.join(f'`{c}`' for c in clusters) or '(none)'}",
        f"All same cluster: **{'YES' if same_cluster else 'NO'}**",
        "",
    ]
    if same_cluster:
        cluster_md += [
            f"`{clusters[0]}` total members: **{len(member_ids)}**",
            f"Confirmed: **8**",
            f"Unreviewed: **{len(unreviewed)}**",
            "",
            "Cluster precision: **NOT_YET_MEASURABLE** (unreviewed ≠ different singer)",
            "",
        ]
    (output_dir / "cluster_ground_truth.md").write_text("\n".join(cluster_md), encoding="utf-8")

    # personal vocal baseline preview (separate module)
    from services.singer_identity.personal_baseline.schema import (
        build_experimental_baseline_preview,
        write_baseline_preview_artifacts,
    )

    baseline_preview = build_experimental_baseline_preview(
        singer_id=singer_id,
        recordings=confirmed,
        reviews_path=repo / "audit_output_final_v2" / "audio_reviews.json",
    )
    write_baseline_preview_artifacts(output_dir, baseline_preview)

    # reports
    loo_pass = sum(1 for r in loo_rows if r["verification_decision"] == "MATCH")
    loo_fail = sum(1 for r in loo_rows if r["verification_decision"] == "NON_MATCH")
    loo_unc = sum(1 for r in loo_rows if r["verification_decision"] == "UNCERTAIN")
    # Recognition for reporting: rank==1 among non-enrollment OR MATCH decision
    loo_recognized = sum(1 for r in loo_rows if r["rank_among_non_enrollment"] == 1)

    counts: dict[str, int] = {}
    for c in remaining:
        counts[c["status"]] = counts.get(c["status"], 0) + 1

    # previous high candidates detail
    prev_high_detail = {}
    for stem in UNCONFIRMED_HIGH_STEMS:
        for c in remaining:
            if _norm_stem(c["filename"]) == stem:
                prev_high_detail[stem] = c
                break

    # markdown reports
    within_md = [
        "# Within-Singer Similarity",
        "",
        f"Mean: **{within_stats['mean']:.4f}**",
        f"Median: **{within_stats['median']:.4f}**",
        f"Min: **{within_stats['min']:.4f}**",
        f"Max: **{within_stats['max']:.4f}**",
        f"Std: **{within_stats['std']:.4f}**",
        f"P25/P75: **{within_stats['p25']:.4f}** / **{within_stats['p75']:.4f}**",
        "",
        f"Hardest pair: **{hardest[3]}** ↔ **{hardest[4]}** ({hardest[0]:.4f})",
        f"Easiest pair: **{easiest[3]}** ↔ **{easiest[4]}** ({easiest[0]:.4f})",
        f"Medoid: **{medoid_rec.filename}** (mean sim to others {medoid_mean:.4f})",
        "",
    ]
    (output_dir / "within_singer_report.md").write_text("\n".join(within_md), encoding="utf-8")

    loo_md = ["# Leave-One-Song-Out (8-way)", "", f"MATCH: {loo_pass}/8 · UNCERTAIN: {loo_unc}/8 · NON_MATCH: {loo_fail}/8", f"Rank-1 among non-enrollment: **{loo_recognized}/8**", "", "| Held-out | Sim(centroid) | Nearest | Rank | Margin | Decision |", "|---|---:|---|---:|---:|---|"]
    for r in loo_rows:
        loo_md.append(
            f"| {r['heldout_filename']} | {r['similarity_to_7song_centroid']:.4f} | "
            f"{r['nearest_confirmed_recording']} ({r['nearest_similarity']:.4f}) | "
            f"{r['rank_among_non_enrollment']} | {r['margin_vs_nearest_non_target']:.4f} | {r['verification_decision']} |"
        )
    (output_dir / "leave_one_out.md").write_text("\n".join(loo_md), encoding="utf-8")

    curve_md = [
        "# Enrollment Size Robustness Curve",
        "",
        "| Size | N evals | Mean held-out sim | Min | Top1 global rate | MATCH rate | UNCERTAIN rate |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in curve_rows:
        curve_md.append(
            f"| {r['enrollment_size']} | {r['n_evaluations']} | {r['mean_heldout_similarity']:.4f} | "
            f"{r['min_heldout_similarity']:.4f} | {r['top1_global_rate']:.4f} | "
            f"{r['verification_match_rate']:.4f} | {r['uncertain_rate']:.4f} |"
        )
    # improvement interpretation
    if len(curve_rows) >= 2:
        mean2 = curve_rows[0]["mean_heldout_similarity"]
        mean7 = curve_rows[-1]["mean_heldout_similarity"]
        top2 = curve_rows[0]["top1_global_rate"]
        top7 = curve_rows[-1]["top1_global_rate"]
        if mean7 > mean2 + 0.01 and top7 >= top2 - 0.02:
            improve = "YES"
        elif mean7 < mean2 - 0.01 and top7 <= top2 + 0.02:
            improve = "NO"
        else:
            improve = "MIXED"
        curve_md += ["", f"Does more enrollment improve robustness: **{improve}**", f"Evidence: mean sim {mean2:.4f} (size=2) → {mean7:.4f} (size=7); top1 {top2:.4f} → {top7:.4f}", ""]
    else:
        improve = "MIXED"
    (output_dir / "enrollment_size_curve.md").write_text("\n".join(curve_md), encoding="utf-8")

    rem_md = [
        "# Remaining Candidates (65)",
        "",
        f"CONSISTENT_HIGH: {counts.get('CONSISTENT_HIGH', 0)}",
        f"STYLE_SPECIFIC: {counts.get('STYLE_SPECIFIC', 0)}",
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
            f"{c['rank']}. **{c['filename']}** · old={c['old_rank']} new={c['rank']} · "
            f"cent={c['sim_centroid']:.3f} med={c['median_similarity_to_confirmed']:.3f} "
            f"min={c['min_similarity_to_confirmed']:.3f} · **{c['status']}**"
            + (" · NEWLY_DISCOVERED" if c["newly_discovered"] else "")
        )
    rem_md += ["", "## Previous unconfirmed HIGH", ""]
    for stem, c in prev_high_detail.items():
        rem_md.append(
            f"- {c['filename']}: old_rank={c['old_rank']} new_rank={c['rank']} "
            f"status={c['status']} min={c['min_similarity_to_confirmed']:.3f} "
            f"(still UNCONFIRMED / MODEL_CANDIDATE)"
        )
    (output_dir / "remaining_candidates.md").write_text("\n".join(rem_md), encoding="utf-8")

    seed_pair = float(frozen_summary.get("seed_pair_similarity") or 0.6488)
    report = [
        "# Confirmed Singer Profile v2",
        "",
        f"Singer: **{singer_id}**",
        "",
        "Human-confirmed recordings: **8**",
        "",
    ]
    for i, r in enumerate(confirmed, 1):
        report.append(f"{i}. {r.filename} (`{r.audio_id}`) · cluster `{r.cluster_id}`")
    report += [
        "",
        "## Identity profile",
        "",
        f"- Centroid: L2-normalized mean of 8 cached ECAPA embeddings (dim={centroid.shape[0]})",
        f"- Medoid: **{medoid_rec.filename}**",
        f"- Within-singer mean/median/min/max: "
        f"{within_stats['mean']:.4f} / {within_stats['median']:.4f} / "
        f"{within_stats['min']:.4f} / {within_stats['max']:.4f}",
        f"- Hardest pair: {hardest[3]} ↔ {hardest[4]} ({hardest[0]:.4f})",
        "",
        "## Leave-One-Song-Out",
        "",
        f"- MATCH: {loo_pass}/8 · UNCERTAIN: {loo_unc}/8 · NON_MATCH: {loo_fail}/8",
        f"- Rank-1 recognition: {loo_recognized}/8",
        f"- LOO mean similarity: {float(np.mean([r['similarity_to_7song_centroid'] for r in loo_rows])):.4f}",
        f"- LOO min similarity: {float(np.min([r['similarity_to_7song_centroid'] for r in loo_rows])):.4f}",
        "",
        "## 2-seed frozen baseline retrieval (known 6 confirmed)",
        "",
        f"- Seed pair: {seed_pair:.4f}",
        f"- Recall@3: {recall.get('recall@3', float('nan')):.3f}",
        f"- Recall@5: {recall.get('recall@5', float('nan')):.3f}",
        f"- Recall@10: {recall.get('recall@10', float('nan')):.3f}",
        f"- Recall@15: {recall.get('recall@15', float('nan')):.3f}",
        "",
        "## Enrollment-size robustness",
        "",
        f"- More enrollment improves robustness: **{improve}**",
        "",
        "> Do not claim absolute improvement beyond comparable metrics (LOO / enrollment curve).",
        "",
        "## Remaining 65 rediscovery",
        "",
        f"- CONSISTENT_HIGH: {counts.get('CONSISTENT_HIGH', 0)}",
        f"- STYLE_SPECIFIC: {counts.get('STYLE_SPECIFIC', 0)}",
        f"- BORDERLINE: {counts.get('BORDERLINE', 0)}",
        f"- CONFLICT: {counts.get('CONFLICT', 0)}",
        f"- LOW: {counts.get('LOW', 0)}",
        "",
        "## Safety",
        "",
        "- Profile contains only USER_CONFIRMED recordings",
        "- I'llneverloveagain / love again / 옥탑방 remain unconfirmed",
        "- ECAPA fine-tuned: NO · thresholds retuned: NO · VAgent production: NO",
        "",
    ]
    (output_dir / "report.md").write_text("\n".join(report), encoding="utf-8")

    build_review_html_v2(
        out_path=output_dir / "review_queue.html",
        confirmed=confirmed,
        medoid_id=medoid_id,
        hardest_pair=(hardest[1], hardest[2]),
        candidates=remaining,
    )

    review_scaffold = repo / "singer_identity_labels" / "reviews" / "confirmed_profile_v2_review.json"
    review_scaffold.parent.mkdir(parents=True, exist_ok=True)
    if not review_scaffold.exists():
        review_scaffold.write_text(
            json.dumps(
                {
                    "singer_id": singer_id,
                    "profile_version": PROFILE_VERSION,
                    "reviews": {},
                    "note": "HUMAN_REVIEW SAME does not auto-expand profile; rebuild explicitly for v3.",
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
        "hardest_pair": {"a": hardest[3], "b": hardest[4], "sim": hardest[0]},
        "easiest_pair": {"a": easiest[3], "b": easiest[4], "sim": easiest[0]},
        "loo": {
            "match": loo_pass,
            "uncertain": loo_unc,
            "non_match": loo_fail,
            "rank1": loo_recognized,
            "mean_sim": float(np.mean([r["similarity_to_7song_centroid"] for r in loo_rows])),
            "min_sim": float(np.min([r["similarity_to_7song_centroid"] for r in loo_rows])),
            "folds": loo_rows,
        },
        "enrollment_curve": curve_rows,
        "enrollment_improves": improve,
        "two_seed_recall": recall,
        "frozen_seed_pair": seed_pair,
        "remaining_counts": counts,
        "remaining_top15": remaining[:15],
        "previous_high": prev_high_detail,
        "cluster": {
            "ids": clusters,
            "same": same_cluster,
            "members": len(member_ids),
            "unreviewed": len(unreviewed),
        },
        "output": str(output_dir),
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return summary
