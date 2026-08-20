"""Fake-client tests for SQS AnalysisQueueService. No live AWS calls."""

from __future__ import annotations

import json

import pytest

from backend.app.jobs.queue import (
    FORBIDDEN_BODY_KEYS,
    MESSAGE_FIELDS,
    AnalysisJobMessage,
    AnalysisQueueService,
    InvalidAnalysisJobError,
    QueueUnavailableError,
    ReceivedAnalysisJob,
    build_queue_service,
    utc_now_iso,
)

ANALYSIS_ID = "c7045e107d714b64880a468748b1f8b7"
AUDIO_KEY = f"analyses/{ANALYSIS_ID}/input.m4a"
QUEUE_URL = "https://sqs.test.amazonaws.com/123/analysis"


class FakeAWSError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeSQSClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.messages: list[dict] = []
        self.deleted: list[str] = []
        self.visibility: list[tuple[str, int]] = []
        self.fail_code: str | None = None

    def send_message(self, **kwargs):
        self.calls.append(("send_message", kwargs))
        if self.fail_code:
            raise FakeAWSError(self.fail_code)
        assert "MessageDeduplicationId" not in kwargs
        body = kwargs["MessageBody"]
        msg = {
            "MessageId": "msg-1",
            "ReceiptHandle": "rh-1",
            "Body": body,
            "Attributes": {"ApproximateReceiveCount": "1"},
        }
        self.messages.append(msg)
        return {"MessageId": "msg-1"}

    def receive_message(self, **kwargs):
        self.calls.append(("receive_message", kwargs))
        if self.fail_code:
            raise FakeAWSError(self.fail_code)
        batch = list(self.messages[: kwargs.get("MaxNumberOfMessages", 1)])
        return {"Messages": batch} if batch else {}

    def delete_message(self, **kwargs):
        self.calls.append(("delete_message", kwargs))
        if self.fail_code:
            raise FakeAWSError(self.fail_code)
        self.deleted.append(kwargs["ReceiptHandle"])

    def change_message_visibility(self, **kwargs):
        self.calls.append(("change_message_visibility", kwargs))
        if self.fail_code:
            raise FakeAWSError(self.fail_code)
        self.visibility.append((kwargs["ReceiptHandle"], kwargs["VisibilityTimeout"]))


def _job(**overrides) -> AnalysisJobMessage:
    payload = dict(
        schema_version=1,
        analysis_id=ANALYSIS_ID,
        audio_key=AUDIO_KEY,
        analysis_mode="FUNCTIONAL",
        input_mode="MIXED",
        created_at="2026-08-19T02:00:00Z",
        include_feedback=False,
    )
    payload.update(overrides)
    return AnalysisJobMessage(**payload)


def _service(fake: FakeSQSClient | None = None) -> tuple[AnalysisQueueService, FakeSQSClient]:
    client = fake or FakeSQSClient()
    return (
        AnalysisQueueService(
            QUEUE_URL,
            client,
            region="test-region",
            visibility_timeout=600,
            wait_time_seconds=20,
        ),
        client,
    )


def test_importing_queue_module_does_not_require_env(monkeypatch):
    monkeypatch.delenv("VAGENT_ANALYSIS_QUEUE_URL", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    from backend.app.jobs.queue import AnalysisQueueService as cls

    assert cls is AnalysisQueueService


def test_build_queue_service_requires_url(monkeypatch):
    monkeypatch.delenv("VAGENT_ANALYSIS_QUEUE_URL", raising=False)
    monkeypatch.setenv("AWS_REGION", "ap-northeast-2")
    with pytest.raises(RuntimeError, match="VAGENT_ANALYSIS_QUEUE_URL"):
        build_queue_service(sqs_client=FakeSQSClient())


def test_job_serialization_round_trip():
    job = _job()
    body = job.to_json()
    parsed = AnalysisJobMessage.from_json(body)
    assert parsed == job
    raw = json.loads(body)
    assert set(raw) == set(MESSAGE_FIELDS)
    assert raw["analysis_id"] == ANALYSIS_ID
    assert raw["audio_key"] == AUDIO_KEY
    for key in FORBIDDEN_BODY_KEYS:
        assert key not in raw


def test_enqueue_sends_json_body_without_secrets():
    service, client = _service()
    message_id = service.enqueue_analysis(_job())
    assert message_id == "msg-1"
    kwargs = client.calls[0][1]
    assert kwargs["QueueUrl"] == QUEUE_URL
    body = json.loads(kwargs["MessageBody"])
    assert body["schema_version"] == 1
    assert body["analysis_id"] == ANALYSIS_ID
    assert body["audio_key"] == AUDIO_KEY
    assert body["analysis_mode"] == "FUNCTIONAL"
    assert body["input_mode"] == "MIXED"
    assert "created_at" in body
    for key in FORBIDDEN_BODY_KEYS:
        assert key not in body
    assert "MessageDeduplicationId" not in kwargs


def test_receive_parses_message_and_preserves_receipt_handle():
    service, client = _service()
    service.enqueue_analysis(_job())
    client.messages[0]["Attributes"]["ApproximateReceiveCount"] = "3"
    received = service.receive_analysis_jobs()
    assert len(received) == 1
    item = received[0]
    assert isinstance(item, ReceivedAnalysisJob)
    assert item.receipt_handle == "rh-1"
    assert item.message_id == "msg-1"
    assert item.approximate_receive_count == 3
    assert item.job.analysis_id == ANALYSIS_ID
    recv_kwargs = [c[1] for c in client.calls if c[0] == "receive_message"][0]
    assert recv_kwargs["MaxNumberOfMessages"] == 1
    assert recv_kwargs["WaitTimeSeconds"] == 20
    assert recv_kwargs["VisibilityTimeout"] == 600


def test_delete_message_uses_receipt_handle():
    service, client = _service()
    service.delete_message("rh-keep")
    assert client.deleted == ["rh-keep"]
    assert client.calls[-1][1]["QueueUrl"] == QUEUE_URL
    assert client.calls[-1][1]["ReceiptHandle"] == "rh-keep"


def test_change_visibility_uses_timeout_argument():
    service, client = _service()
    service.change_visibility("rh-keep", 90)
    assert client.visibility == [("rh-keep", 90)]


def test_invalid_json_message_raises():
    fake = FakeSQSClient()
    fake.messages.append(
        {
            "MessageId": "msg-bad",
            "ReceiptHandle": "rh-bad",
            "Body": "{not-json",
            "Attributes": {"ApproximateReceiveCount": "1"},
        }
    )
    service, _client = _service(fake)
    with pytest.raises(InvalidAnalysisJobError, match="invalid json") as err:
        service.receive_analysis_jobs()
    assert err.value.receipt_handle == "rh-bad"
    assert err.value.message_id == "msg-bad"


def test_missing_required_field_raises():
    with pytest.raises(InvalidAnalysisJobError, match="missing fields"):
        AnalysisJobMessage.from_dict(
            {
                "schema_version": 1,
                "analysis_id": ANALYSIS_ID,
                "audio_key": AUDIO_KEY,
                "analysis_mode": "FUNCTIONAL",
                "input_mode": "MIXED",
            }
        )


def test_forbidden_secret_fields_rejected():
    raw = _job().to_dict()
    raw["aws_secret_access_key"] = "should-never-be-here"
    with pytest.raises(InvalidAnalysisJobError, match="forbidden"):
        AnalysisJobMessage.from_dict(raw)


def test_aws_error_on_enqueue_is_wrapped():
    fake = FakeSQSClient()
    fake.fail_code = "ServiceUnavailable"
    service, _client = _service(fake)
    with pytest.raises(QueueUnavailableError):
        service.enqueue_analysis(_job())


def test_created_at_helper_is_utc():
    stamp = utc_now_iso()
    assert stamp.endswith("Z")
    assert "T" in stamp
