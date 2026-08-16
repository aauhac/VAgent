# -*- coding: utf-8 -*-
"""Drowning+Movie same-singer seed expansion (analysis only; no VAgent integration)."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from services.singer_identity.inference.encoder import cosine_similarity, get_default_encoder, l2_normalize
from services.singer_identity.preprocessing.segments import load_mono, prefer_vocal_stem, select_vocal_segments


STATUSES = (
    "CONFIRMED_SEED",
    "HIGH_CANDIDATE",
    "MEDIUM_CANDIDATE",
    "LOW_CANDIDATE",
    "CONFLICT",
    "UNRESOLVED",
)


@dataclass
class SeedInfo:
    key: str
    audio_id: str
    sha256: str
    path: str
    filename: str
    cluster_id: str
    embedding: np.ndarray


@dataclass
class CandidateScore:
    rank: int = 0
    filename: str = ""
    audio_id: str = ""
    sha256: str = ""
    path: str = ""
    current_cluster: str = ""
    status: str = "LOW_CANDIDATE"
    robust_score: float = 0.0
    sim_drowning: float = 0.0
    sim_movie: float = 0.0
    sim_prototype: float = 0.0
    min_seed_similarity: float = 0.0
    max_seed_similarity: float = 0.0
    mean_seed_similarity: float = 0.0
    seed_similarity_gap: float = 0.0
    segment_median_drowning: float = float("nan")
    segment_median_movie: float = float("nan")
    segment_support: float = float("nan")
    segment_top_q: float = float("nan")
    quality: str = ""
    review_required: bool = False
    notes: str = ""


def resolve_named_audios(
    manifest_audios: list[dict[str, Any]],
    names: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Case-insensitive filename/path match. Returns all hits per name (ambiguity-safe)."""
    out: dict[str, list[dict[str, Any]]] = {n: [] for n in names}
    for a in manifest_audios:
        path = str(a.get("path") or "")
        fname = Path(path).name.lower() if path else ""
        blob = " ".join(
            [fname, path.lower(), " ".join(str(x).lower() for x in (a.get("aliases") or []))]
        )
        for n in names:
            if n.lower() in blob:
                out[n].append(a)
    return out


def dedupe_by_sha(hits: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    by_sha: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    for h in hits:
        sha = str(h.get("sha256") or "")
        if sha in by_sha:
            notes.append(f"duplicate path same SHA {sha[:12]}: {h.get('path')}")
            continue
        by_sha[sha] = h
    if len(by_sha) > 1:
        notes.append(
            "AMBIGUITY: multiple distinct SHAs matched name — "
            + ", ".join(f"{Path(v.get('path') or '').name}:{k[:12]}" for k, v in by_sha.items())
        )
    return list(by_sha.values()), notes


def load_audio_embedding(emb_dir: Path, audio_id: str) -> np.ndarray:
    p = emb_dir / f"{audio_id}.npy"
    if not p.exists():
        raise FileNotFoundError(f"cached embedding missing: {p}")
    return l2_normalize(np.load(p))


def build_prototype(embs: list[np.ndarray]) -> np.ndarray:
    stacked = np.stack([l2_normalize(e) for e in embs], axis=0)
    return l2_normalize(stacked.sum(axis=0))


def robust_score(min_s: float, mean_s: float, proto: float) -> float:
    """Fixed weights — not tuned to include a target N."""
    return float(0.5 * min_s + 0.3 * mean_s + 0.2 * proto)


def load_or_compute_segments(
    *,
    audio_id: str,
    path: str,
    seg_dir: Path,
    encoder,
    recompute: bool = False,
) -> np.ndarray:
    """Return (N, D) L2-normalized segment embeddings. Cache to seg_dir."""
    seg_dir.mkdir(parents=True, exist_ok=True)
    npy = seg_dir / f"{audio_id}.npy"
    meta = seg_dir / f"{audio_id}.json"
    if npy.exists() and not recompute:
        return np.load(npy)
    p = prefer_vocal_stem(path)
    y, sr = load_mono(p)
    segs = select_vocal_segments(y, sr)
    if not segs and y.size >= int(0.5 * sr):
        from services.singer_identity.preprocessing.segments import VocalSegment

        segs = [
            VocalSegment(0.0, len(y) / sr, y.astype(np.float32, copy=False), sr, 0.3)
        ]
    rows = []
    embs = []
    for s in segs:
        e = l2_normalize(encoder.encode_segment(s.audio, s.sr))
        embs.append(e)
        rows.append({"start_sec": s.start_sec, "end_sec": s.end_sec, "quality": s.quality})
    if not embs:
        arr = np.zeros((0, encoder.embedding_dim), dtype=np.float32)
    else:
        arr = np.stack(embs).astype(np.float32)
    np.save(npy, arr)
    meta.write_text(json.dumps({"audio_id": audio_id, "segments": rows}, indent=2), encoding="utf-8")
    return arr


def cross_segment_stats(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    if a.size == 0 or b.size == 0 or a.ndim != 2 or b.ndim != 2:
        return {
            "median": float("nan"),
            "q75": float("nan"),
            "top_k_mean": float("nan"),
            "support_ratio": float("nan"),
        }
    # cosine matrix
    a_n = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-12)
    b_n = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-12)
    mat = a_n @ b_n.T
    # per-candidate-segment: best match to any seed segment
    best = mat.max(axis=1)
    med = float(np.median(best))
    q75 = float(np.percentile(best, 75))
    k = max(1, min(3, len(best)))
    top_k = float(np.mean(np.sort(best)[-k:]))
    # support: fraction of candidate segments with best >= median of bests
    thr = float(np.median(best))
    support = float(np.mean(best >= thr)) if len(best) else float("nan")
    # stronger support vs absolute: fraction above 0.5 if possible
    support_abs = float(np.mean(best >= 0.50)) if len(best) else float("nan")
    return {
        "median": med,
        "q75": q75,
        "top_k_mean": top_k,
        "support_ratio": support_abs if not math.isnan(support_abs) else support,
        "best_mean": float(np.mean(best)),
    }


def classify_candidate(
    *,
    min_s: float,
    mean_s: float,
    gap: float,
    max_s: float,
    seg_support: float,
    seed_pair_sim: float,
    quality: str,
) -> tuple[str, str]:
    """Relative to seed-pair reference — not tuned to force a candidate count."""
    if quality in ("FAILED",) or (math.isnan(min_s)):
        return "UNRESOLVED", "quality/evidence insufficient"
    # Conflict: one-sided match
    if gap >= 0.25 and max_s >= max(0.55, seed_pair_sim * 0.85):
        return "CONFLICT", "large seed gap with strong one-sided similarity"
    # HIGH: both seeds near seed-pair range + segment support
    high_min = seed_pair_sim * 0.85
    if min_s >= high_min and gap <= 0.18:
        if not math.isnan(seg_support) and seg_support < 0.25:
            return "MEDIUM_CANDIDATE", "audio strong but weak segment support"
        return "HIGH_CANDIDATE", "consistent with both seeds"
    # MEDIUM
    if min_s >= seed_pair_sim * 0.70 and gap <= 0.25:
        return "MEDIUM_CANDIDATE", "moderate both-seed similarity"
    if max_s >= seed_pair_sim * 0.90 and gap > 0.18:
        return "CONFLICT", "strong max but inconsistent across seeds"
    return "LOW_CANDIDATE", "weak similarity"


def controlled_within_sims(
    controlled_shas: list[str],
    sha_to_emb: dict[str, np.ndarray],
) -> list[float]:
    embs = []
    for sha in controlled_shas:
        e = sha_to_emb.get(sha)
        if e is None:
            e = sha_to_emb.get(sha[:12])
        if e is not None:
            embs.append(e)
    sims = []
    for i in range(len(embs)):
        for j in range(i + 1, len(embs)):
            sims.append(cosine_similarity(embs[i], embs[j]))
    return sims


def merge_seed_labels(
    labels_path: Path,
    *,
    drowning_sha: str,
    movie_sha: str,
    singer_id: str = "person_drowning_movie",
) -> dict[str, Any]:
    data = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.exists() else {}
    data.setdefault("version", "singer-identity-labels-v1")
    data.setdefault("same_singer_groups", {})
    data.setdefault("recordings", {})
    # preserve controlled
    group = data["same_singer_groups"].setdefault(singer_id, [])
    for sha in (drowning_sha, movie_sha):
        if sha not in group:
            group.append(sha)
    for sha, role_file in ((drowning_sha, "drowning"), (movie_sha, "movie")):
        prev = data["recordings"].get(sha)
        if prev and prev.get("label_source") in ("USER_CONFIRMED", "HUMAN_REVIEW") and prev.get(
            "singer_id"
        ) not in (None, singer_id):
            # do not overwrite unrelated confirmed
            continue
        if prev and prev.get("singer_id") == "person_controlled_v1":
            # should not happen for drowning/movie
            continue
        data["recordings"][sha] = {
            "singer_id": singer_id,
            "display_name": "Drowning/Movie Singer",
            "label_source": "USER_CONFIRMED",
            "confidence": "CONFIRMED",
            "role": "SEED",
            "seed_name": role_file,
        }
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def build_review_html(
    *,
    out_path: Path,
    drowning: SeedInfo,
    movie: SeedInfo,
    candidates: list[CandidateScore],
) -> None:
    reviewable = [c for c in candidates if c.status in ("HIGH_CANDIDATE", "MEDIUM_CANDIDATE", "CONFLICT")]
    items = []
    for c in reviewable:
        items.append(
            {
                "audio_id": c.audio_id,
                "sha256": c.sha256,
                "filename": c.filename,
                "path": c.path.replace("\\", "/"),
                "status": c.status,
                "sim_drowning": round(c.sim_drowning, 4),
                "sim_movie": round(c.sim_movie, 4),
                "sim_prototype": round(c.sim_prototype, 4),
                "min_seed": round(c.min_seed_similarity, 4),
                "segment_support": None
                if math.isnan(c.segment_support)
                else round(c.segment_support, 4),
                "cluster": c.current_cluster,
            }
        )
    payload = {
        "singer_id": "person_drowning_movie",
        "drowning": {
            "filename": drowning.filename,
            "path": drowning.path.replace("\\", "/"),
            "sha256": drowning.sha256,
            "audio_id": drowning.audio_id,
        },
        "movie": {
            "filename": movie.filename,
            "path": movie.path.replace("\\", "/"),
            "sha256": movie.sha256,
            "audio_id": movie.audio_id,
        },
        "candidates": items,
    }
    data_json = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<title>Drowning/Movie Singer Review (local)</title>
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
audio {{ width:100%; margin-top:8px; }}
.row {{ display:grid; grid-template-columns: 1fr 1fr 1fr; gap:12px; }}
@media (max-width:900px) {{ .row {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<h1>Drowning / Movie — Human Review</h1>
<p class="muted">Local-only. HIGH/MEDIUM/CONFLICT는 사람 확인 전까지 ground truth가 아닙니다. Blind mode: 숫자 숨김 → 청취 → 판단.</p>
<label><input type="checkbox" id="blind" checked/> Blind Review Mode (숫자 숨김)</label>
<div class="card">
  <h2>Confirmed Seeds</h2>
  <div class="row">
    <div><b id="dName"></b><audio id="dAud" controls></audio></div>
    <div><b id="mName"></b><audio id="mAud" controls></audio></div>
  </div>
</div>
<div id="list"></div>
<script>
const DATA = {data_json};
const SAVE_HINT = "singer_identity_labels/reviews/drowning_movie_review.json";
function fileUrl(p) {{
  if (!p) return "";
  if (p.startsWith("file:")) return p;
  // Windows path → file URL
  if (/^[A-Za-z]:/.test(p)) return "file:///" + p.replace(/\\\\/g,"/");
  return "file://" + p;
}}
function loadLocal() {{
  try {{ return JSON.parse(localStorage.getItem("drowning_movie_review")||"{{}}"); }}
  catch {{ return {{}}; }}
}}
function saveLocal(obj) {{
  localStorage.setItem("drowning_movie_review", JSON.stringify(obj, null, 2));
  document.getElementById("export").textContent = JSON.stringify(obj, null, 2);
}}
document.getElementById("dName").textContent = DATA.drowning.filename;
document.getElementById("mName").textContent = DATA.movie.filename;
document.getElementById("dAud").src = fileUrl(DATA.drowning.path);
document.getElementById("mAud").src = fileUrl(DATA.movie.path);
const decisions = loadLocal();
decisions.singer_id = DATA.singer_id;
decisions.seeds = {{ drowning: DATA.drowning.sha256, movie: DATA.movie.sha256 }};
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
      <div class="muted">cluster: ${{c.cluster}} · id: ${{c.audio_id}}</div>
      <audio controls src="${{fileUrl(c.path)}}"></audio>
      <div class="nums ${{blind ? "hidden" : ""}}">
        Drowning: ${{c.sim_drowning}} · Movie: ${{c.sim_movie}} · Prototype: ${{c.sim_prototype}} ·
        min: ${{c.min_seed}} · segment_support: ${{c.segment_support}}
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
  <h2>Export (copy into singer_identity_labels/reviews/drowning_movie_review.json)</h2>
  <pre id="export" style="white-space:pre-wrap;background:#11151b;padding:12px;border-radius:8px;"></pre>
</div>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")


def apply_human_confirmed(
    labels_path: Path,
    review_path: Path,
    singer_id: str = "person_drowning_movie",
) -> int:
    """Only HUMAN_REVIEW SAME expands profile. Never overwrite USER_CONFIRMED of other singers."""
    if not review_path.exists():
        return 0
    review = json.loads(review_path.read_text(encoding="utf-8"))
    data = json.loads(labels_path.read_text(encoding="utf-8"))
    data.setdefault("recordings", {})
    data.setdefault("same_singer_groups", {})
    group = data["same_singer_groups"].setdefault(singer_id, [])
    n = 0
    for sha, row in (review.get("reviews") or {}).items():
        if row.get("decision") != "SAME":
            continue
        prev = data["recordings"].get(sha)
        if prev and prev.get("label_source") == "USER_CONFIRMED" and prev.get("singer_id") != singer_id:
            continue
        if prev and prev.get("label_source") == "USER_CONFIRMED" and prev.get("role") == "SEED":
            continue
        data["recordings"][sha] = {
            "singer_id": singer_id,
            "display_name": "Drowning/Movie Singer",
            "label_source": "HUMAN_REVIEW",
            "confidence": "CONFIRMED",
            "role": "HUMAN_CONFIRMED",
            "filename": row.get("filename"),
        }
        if sha not in group:
            group.append(sha)
        n += 1
    labels_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return n
