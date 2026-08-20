"""
SQS analysis job queue.

Standard Queue only — no FIFO MessageDeduplicationId.
Importing this module must not connect to AWS and must not require queue env vars.
Worker / heartbeat loops are STEP 3+; this file is the primitive API.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from .runner import validate_analysis_id
from ..storage.s3 import parse_analysis_audio_key

logger = logging.getLogger("vagent.jobs.queue")

SCHEMA_VERSION = 1
ALLOWED_ANALYSIS_MODES = frozenset({"QUICK", "FUNCTIONAL", "DIAGNOSTIC"})
ALLOWED_INPUT_MODES = frozenset({"AUTO", "MIXED", "VOCAL_ONLY"})
MESSAGE_FIELDS = (
    "schema_version",
    "analysis_id",
    "audio_key",
    "analysis_mode",
    "input_mode",
    "created_at",
    "include_feedback",
)
FORBIDDEN_BODY_KEYS = frozenset(
    {
        "access_token",
        "authorization_code",
        "toss_auth_token",
        "authorization",
        "user_key",
        "raw_user_key",
        "userkey",
        "password",
        "db_password",
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        "secret_access_key",
        "session_token",
        "audio_base64",
        "audio_binary",
        "audio_bytes",
    }
)


class QueueUnavailableError(Exception):
    """SQS could not complete the operation."""


class InvalidAnalysisJobError(Exception):
    """Queue payload is missing, malformed, or contains forbidden fields."""

    def __init__(
        self,
        message: str,
        *,
        receipt_handle: str | None = None,
        message_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.receipt_handle = receipt_handle
        self.message_id = message_id


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class AnalysisJobMessage:
    schema_version: int
    analysis_id: str
    audio_key: str
    analysis_mode: str
    input_mode: str
    created_at: str
    include_feedback: bool = False

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=False)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: payload[key] for key in MESSAGE_FIELDS}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AnalysisJobMessage":
        if not isinstance(raw, dict):
            raise InvalidAnalysisJobError("job body must be an object")
        lowered = {str(key).lower() for key in raw}
        forbidden = lowered & FORBIDDEN_BODY_KEYS
        if forbidden:
            raise InvalidAnalysisJobError("job body contains forbidden fields")
        missing = [key for key in MESSAGE_FIELDS if key != "include_feedback" and key not in raw]
        if missing:
            raise InvalidAnalysisJobError(f"missing fields: {','.join(missing)}")
        try:
            schema_version = int(raw["schema_version"])
        except (TypeError, ValueError) as exc:
            raise InvalidAnalysisJobError("invalid schema_version") from exc
        if schema_version != SCHEMA_VERSION:
            raise InvalidAnalysisJobError("unsupported schema_version")
        analysis_id = str(raw.get("analysis_id") or "").strip()
        if not validate_analysis_id(analysis_id):
            raise InvalidAnalysisJobError("invalid analysis_id")
        audio_key = str(raw.get("audio_key") or "").strip()
        try:
            key_analysis_id, _ext = parse_analysis_audio_key(audio_key)
        except ValueError as exc:
            raise InvalidAnalysisJobError("invalid audio_key") from exc
        if key_analysis_id != analysis_id:
            raise InvalidAnalysisJobError("audio_key analysis_id mismatch")
        analysis_mode = str(raw.get("analysis_mode") or "").strip().upper()
        input_mode = str(raw.get("input_mode") or "").strip().upper()
        if analysis_mode not in ALLOWED_ANALYSIS_MODES:
            raise InvalidAnalysisJobError("invalid analysis_mode")
        if input_mode not in ALLOWED_INPUT_MODES:
            raise InvalidAnalysisJobError("invalid input_mode")
        created_at = str(raw.get("created_at") or "").strip()
        if not created_at:
            raise InvalidAnalysisJobError("missing created_at")
        include_feedback = bool(raw.get("include_feedback", False))
        return cls(
            schema_version=schema_version,
            analysis_id=analysis_id,
            audio_key=audio_key,
            analysis_mode=analysis_mode,
            input_mode=input_mode,
            created_at=created_at,
            include_feedback=include_feedback,
        )

    @classmethod
    def from_json(cls, body: str) -> "AnalysisJobMessage":
        try:
            raw = json.loads(body)
        except json.JSONDecodeError as exc:
            raise InvalidAnalysisJobError("invalid json") from exc
        if not isinstance(raw, dict):
            raise InvalidAnalysisJobError("job body must be an object")
        return cls.from_dict(raw)


@dataclass(frozen=True)
class ReceivedAnalysisJob:
    job: AnalysisJobMessage
    receipt_handle: str
    message_id: str
    approximate_receive_count: int


def _aws_error_code(exc: BaseException) -> str | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    error = response.get("Error") or {}
    code = error.get("Code")
    if code is None:
        return None
    return str(code)


def _new_sqs_client(region: str) -> Any:
    import boto3

    return boto3.client("sqs", region_name=region)


def build_queue_service(*, sqs_client: Any | None = None) -> "AnalysisQueueService":
    from ..config import (
        analysis_dlq_url,
        analysis_queue_url,
        aws_region,
        sqs_visibility_timeout_seconds,
        sqs_wait_time_seconds,
    )

    queue_url = analysis_queue_url()
    if not queue_url:
        raise RuntimeError("VAGENT_ANALYSIS_QUEUE_URL is required when SQS queue is enabled")
    region = aws_region()
    if not region:
        raise RuntimeError("AWS_REGION is required when SQS queue is enabled")
    return AnalysisQueueService(
        queue_url=queue_url,
        region=region,
        sqs_client=sqs_client,
        visibility_timeout=sqs_visibility_timeout_seconds(),
        wait_time_seconds=sqs_wait_time_seconds(),
        dlq_url=analysis_dlq_url(),
    )


class AnalysisQueueService:
    def __init__(
        self,
        queue_url: str,
        sqs_client: Any | None = None,
        *,
        region: str | None = None,
        visibility_timeout: int | None = None,
        wait_time_seconds: int | None = None,
        dlq_url: str | None = None,
    ) -> None:
        url = (queue_url or "").strip()
        if not url:
            raise RuntimeError("VAGENT_ANALYSIS_QUEUE_URL is required when SQS queue is enabled")
        self.queue_url = url
        self.dlq_url = (dlq_url or "").strip() or None
        self.region = (region or "").strip() or None
        if visibility_timeout is None:
            from ..config import sqs_visibility_timeout_seconds

            visibility_timeout = sqs_visibility_timeout_seconds()
        if wait_time_seconds is None:
            from ..config import sqs_wait_time_seconds

            wait_time_seconds = sqs_wait_time_seconds()
        self.visibility_timeout = max(1, int(visibility_timeout))
        self.wait_time_seconds = max(0, min(int(wait_time_seconds), 20))
        if sqs_client is not None:
            self._client = sqs_client
        else:
            if not self.region:
                raise RuntimeError("AWS_REGION is required when SQS queue is enabled")
            self._client = _new_sqs_client(self.region)

    def enqueue_analysis(self, job: AnalysisJobMessage) -> str:
        parsed = AnalysisJobMessage.from_dict(job.to_dict())
        body = parsed.to_json()
        logger.info("[SQS] enqueue started analysis_id=%s", parsed.analysis_id)
        try:
            response = self._client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=body,
            )
        except Exception as exc:  # noqa: BLE001
            self._raise_queue(exc, operation="enqueue", analysis_id=parsed.analysis_id)
        message_id = str((response or {}).get("MessageId") or "")
        logger.info("[SQS] enqueue complete analysis_id=%s", parsed.analysis_id)
        return message_id

    def receive_analysis_jobs(
        self,
        max_messages: int = 1,
        wait_time_seconds: int | None = None,
        visibility_timeout: int | None = None,
    ) -> list[ReceivedAnalysisJob]:
        wait = self.wait_time_seconds if wait_time_seconds is None else max(0, min(int(wait_time_seconds), 20))
        visibility = self.visibility_timeout if visibility_timeout is None else max(1, int(visibility_timeout))
        n = max(1, min(int(max_messages), 10))
        try:
            response = self._client.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=n,
                WaitTimeSeconds=wait,
                VisibilityTimeout=visibility,
                AttributeNames=["ApproximateReceiveCount"],
            )
        except Exception as exc:  # noqa: BLE001
            self._raise_queue(exc, operation="receive", analysis_id=None)
        jobs: list[ReceivedAnalysisJob] = []
        for raw in response.get("Messages") or []:
            jobs.append(self._parse_received(raw))
        return jobs

    def delete_message(self, receipt_handle: str) -> None:
        handle = (receipt_handle or "").strip()
        if not handle:
            raise InvalidAnalysisJobError("missing receipt_handle")
        try:
            self._client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=handle)
        except Exception as exc:  # noqa: BLE001
            self._raise_queue(exc, operation="delete", analysis_id=None)

    def change_visibility(self, receipt_handle: str, timeout_seconds: int) -> None:
        handle = (receipt_handle or "").strip()
        if not handle:
            raise InvalidAnalysisJobError("missing receipt_handle")
        timeout = max(0, int(timeout_seconds))
        try:
            self._client.change_message_visibility(
                QueueUrl=self.queue_url,
                ReceiptHandle=handle,
                VisibilityTimeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001
            self._raise_queue(exc, operation="change_visibility", analysis_id=None)

    def _parse_received(self, raw: dict[str, Any]) -> ReceivedAnalysisJob:
        message_id = str(raw.get("MessageId") or "")
        receipt_handle = str(raw.get("ReceiptHandle") or "")
        body = raw.get("Body") or ""
        attrs = raw.get("Attributes") or {}
        try:
            receive_count = int(attrs.get("ApproximateReceiveCount") or 1)
        except (TypeError, ValueError):
            receive_count = 1
        try:
            job = AnalysisJobMessage.from_json(str(body))
        except InvalidAnalysisJobError as exc:
            raise InvalidAnalysisJobError(
                str(exc),
                receipt_handle=receipt_handle or None,
                message_id=message_id or None,
            ) from exc
        return ReceivedAnalysisJob(
            job=job,
            receipt_handle=receipt_handle,
            message_id=message_id,
            approximate_receive_count=receive_count,
        )

    def _raise_queue(
        self,
        exc: BaseException,
        *,
        operation: str,
        analysis_id: Optional[str],
    ) -> None:
        if isinstance(exc, (QueueUnavailableError, InvalidAnalysisJobError)):
            raise exc
        code = _aws_error_code(exc)
        logger.warning(
            "[SQS] %s failed analysis_id=%s error_code=%s",
            operation,
            analysis_id or "-",
            code or type(exc).__name__,
        )
        raise QueueUnavailableError(f"{operation} failed") from exc
