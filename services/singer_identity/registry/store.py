# -*- coding: utf-8 -*-
"""File-backed singer registry (isolated from VAgent DB)."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from services.singer_identity.inference.encoder import cosine_similarity, l2_normalize


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SingerRegistry:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.singers_dir = self.root / "singers"
        self.singers_dir.mkdir(exist_ok=True)
        self.index_path = self.root / "index.json"
        if not self.index_path.exists():
            self._write_index({"singers": {}})

    def _write_index(self, payload: dict[str, Any]) -> None:
        self.index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_index(self) -> dict[str, Any]:
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def list_singers(self) -> list[dict[str, Any]]:
        idx = self._read_index()
        return list(idx.get("singers", {}).values())

    def get_singer(self, singer_id: str) -> Optional[dict[str, Any]]:
        return self._read_index().get("singers", {}).get(singer_id)

    def create_singer(
        self,
        display_name: str,
        *,
        consented_enrollment: bool,
        singer_id: Optional[str] = None,
        model_version: str = "",
    ) -> dict[str, Any]:
        if not consented_enrollment:
            raise ValueError("consented_enrollment must be true for named enrollment")
        sid = singer_id or f"singer_{uuid.uuid4().hex[:10]}"
        meta = {
            "singer_id": sid,
            "display_name": display_name,
            "created_at": _now(),
            "consented_enrollment": True,
            "recording_count": 0,
            "model_version": model_version,
        }
        sdir = self.singers_dir / sid
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "recordings").mkdir(exist_ok=True)
        (sdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        idx = self._read_index()
        idx.setdefault("singers", {})[sid] = meta
        self._write_index(idx)
        return meta

    def delete_singer(self, singer_id: str) -> bool:
        idx = self._read_index()
        if singer_id not in idx.get("singers", {}):
            return False
        sdir = self.singers_dir / singer_id
        if sdir.exists():
            shutil.rmtree(sdir)
        del idx["singers"][singer_id]
        self._write_index(idx)
        return True

    def add_recording(
        self,
        singer_id: str,
        *,
        embedding: np.ndarray,
        audio_sha256: str,
        filename: str,
        split: str = "ENROLLMENT",
        quality: str = "FAIR",
        model_version: str = "",
    ) -> dict[str, Any]:
        meta = self.get_singer(singer_id)
        if not meta:
            raise KeyError(singer_id)
        rid = f"rec_{uuid.uuid4().hex[:12]}"
        emb = l2_normalize(embedding)
        rec = {
            "recording_id": rid,
            "singer_id": singer_id,
            "audio_sha256": audio_sha256,
            "filename": filename,
            "split": split,
            "quality": quality,
            "model_version": model_version,
            "created_at": _now(),
        }
        sdir = self.singers_dir / singer_id
        np.save(sdir / "recordings" / f"{rid}.npy", emb)
        (sdir / "recordings" / f"{rid}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._rebuild_profile(singer_id)
        return rec

    def _list_recording_embeddings(self, singer_id: str) -> list[tuple[dict[str, Any], np.ndarray]]:
        sdir = self.singers_dir / singer_id / "recordings"
        out = []
        if not sdir.exists():
            return out
        for jp in sorted(sdir.glob("*.json")):
            rec = json.loads(jp.read_text(encoding="utf-8"))
            npy = sdir / f"{rec['recording_id']}.npy"
            if npy.exists():
                out.append((rec, np.load(npy)))
        return out

    def _rebuild_profile(self, singer_id: str) -> dict[str, Any]:
        pairs = self._list_recording_embeddings(singer_id)
        embs = [e for _, e in pairs]
        within: dict[str, float] = {}
        if len(embs) >= 2:
            sims = []
            for i in range(len(embs)):
                for j in range(i + 1, len(embs)):
                    sims.append(cosine_similarity(embs[i], embs[j]))
            within = {
                "mean": float(np.mean(sims)),
                "min": float(np.min(sims)),
                "max": float(np.max(sims)),
                "n_pairs": len(sims),
            }
        centroid = None
        if embs:
            centroid = l2_normalize(np.mean(np.stack(embs), axis=0))
            np.save(self.singers_dir / singer_id / "centroid.npy", centroid)
        profile = {
            "singer_id": singer_id,
            "recording_count": len(embs),
            "within_singer_similarity": within,
            "prototypes": {},  # multi-prototype ready, empty in v1
            "updated_at": _now(),
        }
        (self.singers_dir / singer_id / "profile.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        idx = self._read_index()
        if singer_id in idx.get("singers", {}):
            idx["singers"][singer_id]["recording_count"] = len(embs)
            self._write_index(idx)
            meta_path = self.singers_dir / singer_id / "meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["recording_count"] = len(embs)
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return profile

    def get_profile(self, singer_id: str) -> Optional[dict[str, Any]]:
        p = self.singers_dir / singer_id / "profile.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def get_centroid(self, singer_id: str) -> Optional[np.ndarray]:
        p = self.singers_dir / singer_id / "centroid.npy"
        if not p.exists():
            return None
        return np.load(p)
