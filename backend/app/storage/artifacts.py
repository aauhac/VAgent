"""Artifact storage abstraction — files outside PostgreSQL."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Optional, Union

from ..config import get_runtime_dir

BytesLike = Union[bytes, bytearray, memoryview]


class ArtifactStore(ABC):
    @abstractmethod
    def save_upload(self, analysis_id: str, filename: str, data: BytesLike) -> str:
        """Return storage_key."""

    @abstractmethod
    def save_preview(self, analysis_id: str, data: BytesLike) -> str: ...

    @abstractmethod
    def save_analysis_result(self, analysis_id: str, name: str, data: BytesLike) -> str: ...

    @abstractmethod
    def open(self, storage_key: str) -> Path: ...

    @abstractmethod
    def delete(self, storage_key: str) -> bool: ...

    @abstractmethod
    def delete_analysis(self, analysis_id: str) -> bool: ...


class LocalArtifactStore(ArtifactStore):
    """Development / private deploy: absolute persistent directory under runtime."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or get_runtime_dir()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _analysis_dir(self, analysis_id: str) -> Path:
        d = self.root / analysis_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_upload(self, analysis_id: str, filename: str, data: BytesLike) -> str:
        path = self._analysis_dir(analysis_id) / filename
        path.write_bytes(bytes(data))
        return f"{analysis_id}/{filename}"

    def save_preview(self, analysis_id: str, data: BytesLike) -> str:
        path = self._analysis_dir(analysis_id) / "preview.wav"
        path.write_bytes(bytes(data))
        return f"{analysis_id}/preview.wav"

    def save_analysis_result(self, analysis_id: str, name: str, data: BytesLike) -> str:
        safe = Path(name).name
        path = self._analysis_dir(analysis_id) / safe
        path.write_bytes(bytes(data))
        return f"{analysis_id}/{safe}"

    def open(self, storage_key: str) -> Path:
        path = (self.root / storage_key).resolve()
        path.relative_to(self.root)
        if not path.is_file():
            raise FileNotFoundError(storage_key)
        return path

    def delete(self, storage_key: str) -> bool:
        try:
            path = self.open(storage_key)
        except (FileNotFoundError, ValueError):
            return False
        path.unlink(missing_ok=True)
        return True

    def delete_analysis(self, analysis_id: str) -> bool:
        import shutil

        path = (self.root / analysis_id).resolve()
        try:
            path.relative_to(self.root)
        except ValueError:
            return False
        if not path.exists():
            return False
        shutil.rmtree(path, ignore_errors=True)
        return True


class ObjectStorageArtifactStore(ArtifactStore):
    """Production stub — wire S3/GCS later; same interface."""

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        raise NotImplementedError("Object storage not configured yet")

    def save_upload(self, analysis_id: str, filename: str, data: BytesLike) -> str:
        raise NotImplementedError

    def save_preview(self, analysis_id: str, data: BytesLike) -> str:
        raise NotImplementedError

    def save_analysis_result(self, analysis_id: str, name: str, data: BytesLike) -> str:
        raise NotImplementedError

    def open(self, storage_key: str) -> Path:
        raise NotImplementedError

    def delete(self, storage_key: str) -> bool:
        raise NotImplementedError

    def delete_analysis(self, analysis_id: str) -> bool:
        raise NotImplementedError


def get_artifact_store() -> ArtifactStore:
    return LocalArtifactStore()
