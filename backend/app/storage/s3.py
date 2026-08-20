"""
S3 analysis-audio storage.

This module is idle until STEP 3. Importing it must not connect to AWS
and must not require VAGENT_S3_BUCKET / AWS_REGION.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

from ..jobs.runner import validate_analysis_id

logger = logging.getLogger("vagent.storage.s3")

_SAFE_EXT_RE = re.compile(r"^\.[a-z0-9]{1,8}$")
_OBJECT_KEY_RE = re.compile(
    r"^analyses/(?P<analysis_id>[a-fA-F0-9]{16,64})/input(?P<ext>\.[a-z0-9]{1,8})$"
)

_CONTENT_TYPES = {
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
    ".webm": "audio/webm",
    ".mp4": "audio/mp4",
    ".m4v": "video/mp4",
}

_NOT_FOUND_CODES = frozenset({"404", "NoSuchKey", "NotFound", "NoSuchBucket"})


class StorageUnavailableError(Exception):
    """S3 could not complete the operation."""


class StorageObjectNotFoundError(Exception):
    """Requested object is missing."""


def analysis_audio_object_key(analysis_id: str, extension: str) -> str:
    analysis_id = _require_analysis_id(analysis_id)
    ext = _safe_extension(extension)
    return f"analyses/{analysis_id}/input{ext}"


def parse_analysis_audio_key(object_key: str) -> tuple[str, str]:
    key = (object_key or "").strip()
    if not key or ".." in key or "\\" in key or key.startswith("/"):
        raise ValueError("invalid object key")
    match = _OBJECT_KEY_RE.fullmatch(key)
    if not match:
        raise ValueError("invalid object key")
    analysis_id = match.group("analysis_id")
    if not validate_analysis_id(analysis_id):
        raise ValueError("invalid analysis_id")
    return analysis_id, match.group("ext")


def is_analysis_audio_object_key(object_key: str, analysis_id: str) -> bool:
    try:
        parsed_id, _ext = parse_analysis_audio_key(object_key)
    except ValueError:
        return False
    return parsed_id == analysis_id


def _require_analysis_id(analysis_id: str) -> str:
    value = (analysis_id or "").strip()
    if not validate_analysis_id(value):
        raise ValueError("invalid analysis_id")
    if ".." in value or "/" in value or "\\" in value:
        raise ValueError("invalid analysis_id")
    return value


def _safe_extension(extension: str) -> str:
    ext = (extension or "").strip().lower()
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    if not _SAFE_EXT_RE.fullmatch(ext):
        raise ValueError("invalid audio extension")
    if ext not in _CONTENT_TYPES:
        raise ValueError("unsupported audio extension")
    return ext


def _content_type_for(extension: str, override: str | None) -> str | None:
    if override:
        return override
    return _CONTENT_TYPES.get(extension)


def _aws_error_code(exc: BaseException) -> str | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    error = response.get("Error") or {}
    code = error.get("Code")
    if code is None:
        return None
    return str(code)


def _new_s3_client(region: str) -> Any:
    import boto3

    return boto3.client("s3", region_name=region)


def build_storage_service(*, s3_client: Any | None = None) -> "StorageService":
    from ..config import aws_region, s3_bucket

    bucket = s3_bucket()
    if not bucket:
        raise RuntimeError("VAGENT_S3_BUCKET is required when S3 storage is enabled")
    region = aws_region()
    if not region:
        raise RuntimeError("AWS_REGION is required when S3 storage is enabled")
    return StorageService(bucket_name=bucket, region=region, s3_client=s3_client)


class StorageService:
    def __init__(
        self,
        bucket_name: str,
        s3_client: Any | None = None,
        *,
        region: str | None = None,
    ) -> None:
        bucket = (bucket_name or "").strip()
        if not bucket:
            raise RuntimeError("VAGENT_S3_BUCKET is required when S3 storage is enabled")
        self.bucket_name = bucket
        self.region = (region or "").strip() or None
        if s3_client is not None:
            self._client = s3_client
        else:
            if not self.region:
                raise RuntimeError("AWS_REGION is required when S3 storage is enabled")
            self._client = _new_s3_client(self.region)

    def upload_analysis_audio(
        self,
        analysis_id: str,
        local_path: Path,
        content_type: str | None = None,
    ) -> str:
        analysis_id = _require_analysis_id(analysis_id)
        path = Path(local_path)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        ext = _safe_extension(path.suffix)
        key = analysis_audio_object_key(analysis_id, ext)
        extra: dict[str, str] = {}
        resolved_type = _content_type_for(ext, content_type)
        if resolved_type:
            extra["ContentType"] = resolved_type
        logger.info("[S3] upload started analysis_id=%s", analysis_id)
        try:
            kwargs: dict[str, Any] = {
                "Filename": str(path),
                "Bucket": self.bucket_name,
                "Key": key,
            }
            if extra:
                kwargs["ExtraArgs"] = extra
            self._client.upload_file(**kwargs)
        except Exception as exc:  # noqa: BLE001
            self._raise_storage(exc, operation="upload", analysis_id=analysis_id)
        logger.info("[S3] upload complete analysis_id=%s key=%s", analysis_id, key)
        return key

    def download_analysis_audio(self, object_key: str, destination: Path) -> Path:
        analysis_id, _ext = parse_analysis_audio_key(object_key)
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._client.download_file(
                Bucket=self.bucket_name,
                Key=object_key,
                Filename=str(dest),
            )
        except Exception as exc:  # noqa: BLE001
            code = _aws_error_code(exc)
            if code in _NOT_FOUND_CODES:
                logger.warning(
                    "[S3] download missing analysis_id=%s error_code=%s",
                    analysis_id,
                    code,
                )
                raise StorageObjectNotFoundError(object_key) from exc
            self._raise_storage(exc, operation="download", analysis_id=analysis_id)
        logger.info("[S3] download complete analysis_id=%s", analysis_id)
        return dest

    def delete_analysis_audio(self, object_key: str) -> None:
        analysis_id, _ext = parse_analysis_audio_key(object_key)
        try:
            self._client.delete_object(Bucket=self.bucket_name, Key=object_key)
        except Exception as exc:  # noqa: BLE001
            self._raise_storage(exc, operation="delete", analysis_id=analysis_id)

    def object_exists(self, object_key: str) -> bool:
        analysis_id, _ext = parse_analysis_audio_key(object_key)
        try:
            self._client.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except Exception as exc:  # noqa: BLE001
            code = _aws_error_code(exc)
            if code in _NOT_FOUND_CODES:
                return False
            self._raise_storage(exc, operation="head", analysis_id=analysis_id)

    def _raise_storage(
        self,
        exc: BaseException,
        *,
        operation: str,
        analysis_id: Optional[str],
    ) -> None:
        code = _aws_error_code(exc)
        logger.warning(
            "[S3] %s failed analysis_id=%s error_code=%s",
            operation,
            analysis_id or "-",
            code or type(exc).__name__,
        )
        if code in _NOT_FOUND_CODES:
            raise StorageObjectNotFoundError(str(analysis_id or "")) from exc
        raise StorageUnavailableError(f"{operation} failed") from exc
