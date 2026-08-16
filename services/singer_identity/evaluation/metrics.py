# -*- coding: utf-8 -*-
"""Held-out evaluation helpers (song-level split, no segment leakage)."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from services.singer_identity.inference.encoder import cosine_similarity


def song_level_split(
    recordings: list[dict[str, Any]],
    *,
    seed: int = 42,
) -> dict[str, list[dict[str, Any]]]:
    """Split by recording/song id — never by segment."""
    by_singer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in recordings:
        by_singer[str(r["singer_id"])].append(r)
    enroll, val, test = [], [], []
    rng = np.random.default_rng(seed)
    for sid, rows in by_singer.items():
        rows = list(rows)
        rng.shuffle(rows)
        if len(rows) == 1:
            enroll.append(rows[0])
        elif len(rows) == 2:
            enroll.append(rows[0])
            test.append(rows[1])
        elif len(rows) == 3:
            enroll.extend(rows[:2])
            test.append(rows[2])
        else:
            n_enroll = max(2, len(rows) - 2)
            enroll.extend(rows[:n_enroll])
            val.append(rows[n_enroll])
            test.extend(rows[n_enroll + 1 :])
    return {"ENROLLMENT": enroll, "VALIDATION": val, "TEST": test}


def assert_no_segment_leakage(split: dict[str, list[dict[str, Any]]]) -> None:
    """Each recording_id / sha appears in at most one split."""
    seen: dict[str, str] = {}
    for name, rows in split.items():
        for r in rows:
            key = str(r.get("recording_id") or r.get("audio_sha256") or r.get("audio_id"))
            if key in seen and seen[key] != name:
                raise AssertionError(f"leakage: {key} in {seen[key]} and {name}")
            seen[key] = name


def identification_metrics(
    gallery: dict[str, np.ndarray],
    probes: list[tuple[str, np.ndarray]],
) -> dict[str, Any]:
    """probes: list of (true_singer_id, embedding)."""
    if not gallery or not probes:
        return {"status": "INSUFFICIENT_DATA", "top1": None, "top3": None}
    singer_ids = list(gallery.keys())
    correct1 = 0
    correct3 = 0
    rows = []
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for true_id, emb in probes:
        scores = [(sid, cosine_similarity(emb, gallery[sid])) for sid in singer_ids]
        scores.sort(key=lambda x: -x[1])
        top = [s[0] for s in scores[:3]]
        pred = top[0]
        correct1 += int(pred == true_id)
        correct3 += int(true_id in top)
        confusion[true_id][pred] += 1
        rows.append({"true": true_id, "pred": pred, "top3": top, "score": scores[0][1]})
    n = len(probes)
    per = defaultdict(lambda: {"n": 0, "hit": 0})
    for r in rows:
        per[r["true"]]["n"] += 1
        per[r["true"]]["hit"] += int(r["true"] == r["pred"])
    return {
        "status": "OK",
        "n": n,
        "top1": correct1 / n,
        "top3": correct3 / n,
        "per_singer": {k: (v["hit"] / v["n"] if v["n"] else 0) for k, v in per.items()},
        "rows": rows,
        "confusion": {k: dict(v) for k, v in confusion.items()},
    }


def verification_metrics(
    same_pairs: list[tuple[np.ndarray, np.ndarray]],
    diff_pairs: list[tuple[np.ndarray, np.ndarray]],
) -> dict[str, Any]:
    if len(same_pairs) < 1 or len(diff_pairs) < 1:
        return {"status": "INSUFFICIENT_DATA", "eer": None, "roc_auc": None}
    same = np.array([cosine_similarity(a, b) for a, b in same_pairs], dtype=np.float64)
    diff = np.array([cosine_similarity(a, b) for a, b in diff_pairs], dtype=np.float64)
    # Sweep thresholds for EER
    scores = np.concatenate([same, diff])
    labels = np.concatenate([np.ones(len(same)), np.zeros(len(diff))])
    thr_candidates = np.unique(scores)
    best_eer = 1.0
    for thr in thr_candidates:
        pred = (scores >= thr).astype(np.float64)
        # FAR among negatives, FRR among positives
        neg = labels == 0
        pos = labels == 1
        far = float(np.mean(pred[neg] == 1)) if neg.any() else 0.0
        frr = float(np.mean(pred[pos] == 0)) if pos.any() else 0.0
        eer = 0.5 * (far + frr)
        if abs(far - frr) < abs(best_eer * 2) or eer < best_eer:
            # prefer balanced
            if abs(far - frr) <= 0.15:
                best_eer = min(best_eer, eer)
            best_eer = min(best_eer, max(far, frr))
    # ROC-AUC Mann-Whitney
    try:
        from sklearn.metrics import roc_auc_score

        auc = float(roc_auc_score(labels, scores))
    except Exception:
        # rank AUC
        order = np.argsort(scores)
        ranks = np.empty_like(order, dtype=float)
        ranks[order] = np.arange(1, len(scores) + 1)
        n_pos = float(labels.sum())
        n_neg = float(len(labels) - n_pos)
        auc = (ranks[labels == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg + 1e-12)
        auc = float(auc)
    return {
        "status": "OK",
        "eer": float(best_eer),
        "roc_auc": auc,
        "same_singer_mean": float(same.mean()),
        "same_singer_std": float(same.std()),
        "different_singer_mean": float(diff.mean()),
        "different_singer_std": float(diff.std()),
        "n_same": len(same),
        "n_diff": len(diff),
    }


def unknown_rejection_metrics(
    gallery: dict[str, np.ndarray],
    unknown_embs: list[np.ndarray],
    *,
    match_thr: float = 0.72,
) -> dict[str, Any]:
    if not gallery or not unknown_embs:
        return {"status": "INSUFFICIENT_DATA"}
    false_accept = 0
    for emb in unknown_embs:
        best = max(cosine_similarity(emb, c) for c in gallery.values())
        if best >= match_thr:
            false_accept += 1
    n = len(unknown_embs)
    return {
        "status": "OK",
        "n_unknown": n,
        "false_accepts": false_accept,
        "false_accept_rate": false_accept / n,
        "unknown_recall": (n - false_accept) / n,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)


def load_gate(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except Exception:
        # minimal YAML subset: key: value lines
        out: dict[str, Any] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if v.lower() in ("true", "false"):
                out[k] = v.lower() == "true"
            else:
                try:
                    out[k] = int(v)
                except ValueError:
                    try:
                        out[k] = float(v)
                    except ValueError:
                        out[k] = v
        return out


def evaluate_integration_gate(
    gate: dict[str, Any],
    *,
    n_singers: int,
    min_recordings: int,
    has_heldout: bool,
    ident: dict[str, Any],
    verif: dict[str, Any],
    unknown: dict[str, Any],
) -> dict[str, Any]:
    reasons = []
    if n_singers < int(gate.get("min_speakers", 5)):
        reasons.append("min_speakers")
    if min_recordings < int(gate.get("min_recordings_per_speaker", 3)):
        reasons.append("min_recordings_per_speaker")
    if gate.get("require_heldout_test", True) and not has_heldout:
        reasons.append("heldout")
    if ident.get("status") != "OK":
        reasons.append("identification")
    if verif.get("status") != "OK":
        reasons.append("verification")
    if unknown.get("status") != "OK":
        reasons.append("unknown_rejection")
    # metric thresholds only applied when present and status OK
    if ident.get("status") == "OK" and gate.get("min_top1") is not None:
        if float(ident.get("top1") or 0) < float(gate["min_top1"]):
            reasons.append("top1_threshold")
    if not reasons:
        overall = "ELIGIBLE"
    elif "min_speakers" in reasons or ident.get("status") == "INSUFFICIENT_DATA":
        overall = "INSUFFICIENT_DATA"
    else:
        overall = "BLOCKED"
    return {"overall": overall, "reasons": reasons, "gate": gate}
