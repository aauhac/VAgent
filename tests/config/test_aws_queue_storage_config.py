"""S3/SQS config is lazy: import and boot must not require AWS env."""

from __future__ import annotations

import pytest

from backend.app.config import (
    analysis_dlq_url,
    analysis_execution_mode,
    analysis_queue_url,
    aws_region,
    parse_analysis_execution_mode,
    s3_bucket,
    sqs_heartbeat_seconds,
    sqs_retry_visibility_seconds,
    sqs_visibility_timeout_seconds,
    sqs_wait_time_seconds,
    validate_analysis_execution_config,
    validate_worker_config,
)


def test_aws_config_getters_are_none_when_unset(monkeypatch):
    monkeypatch.delenv("VAGENT_S3_BUCKET", raising=False)
    monkeypatch.delenv("VAGENT_ANALYSIS_QUEUE_URL", raising=False)
    monkeypatch.delenv("VAGENT_ANALYSIS_DLQ_URL", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    assert s3_bucket() is None
    assert analysis_queue_url() is None
    assert analysis_dlq_url() is None
    assert aws_region() is None


def test_sqs_timeouts_have_overridable_defaults(monkeypatch):
    monkeypatch.delenv("VAGENT_SQS_VISIBILITY_TIMEOUT", raising=False)
    monkeypatch.delenv("VAGENT_SQS_WAIT_TIME_SECONDS", raising=False)
    assert sqs_visibility_timeout_seconds() == 600
    assert sqs_wait_time_seconds() == 20
    monkeypatch.setenv("VAGENT_SQS_VISIBILITY_TIMEOUT", "900")
    monkeypatch.setenv("VAGENT_SQS_WAIT_TIME_SECONDS", "5")
    assert sqs_visibility_timeout_seconds() == 900
    assert sqs_wait_time_seconds() == 5


def test_wait_time_capped_at_sqs_maximum(monkeypatch):
    monkeypatch.setenv("VAGENT_SQS_WAIT_TIME_SECONDS", "99")
    assert sqs_wait_time_seconds() == 20


def test_backend_main_import_without_s3_env(monkeypatch):
    monkeypatch.delenv("VAGENT_S3_BUCKET", raising=False)
    monkeypatch.delenv("VAGENT_ANALYSIS_QUEUE_URL", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    from backend.app.main import app

    assert app.title == "Vocal Skill Test API"


def test_execution_mode_defaults_to_local(monkeypatch):
    monkeypatch.delenv("VAGENT_ANALYSIS_EXECUTION_MODE", raising=False)
    assert analysis_execution_mode() == "local"
    assert validate_analysis_execution_config() == []


def test_queue_mode_missing_env_is_blocked(monkeypatch):
    monkeypatch.setenv("VAGENT_ANALYSIS_EXECUTION_MODE", "queue")
    monkeypatch.delenv("VAGENT_S3_BUCKET", raising=False)
    monkeypatch.delenv("VAGENT_ANALYSIS_QUEUE_URL", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    blockers = validate_analysis_execution_config()
    assert "VAGENT_S3_BUCKET_MISSING" in blockers
    assert "VAGENT_ANALYSIS_QUEUE_URL_MISSING" in blockers
    assert "AWS_REGION_MISSING" in blockers
    assert "DATABASE_URL_MISSING" in blockers


def test_execution_mode_local_explicit(monkeypatch):
    monkeypatch.setenv("VAGENT_ANALYSIS_EXECUTION_MODE", "local")
    assert parse_analysis_execution_mode() == ("local", None)
    assert analysis_execution_mode() == "local"
    assert validate_analysis_execution_config() == []


def test_execution_mode_queue_explicit(monkeypatch):
    monkeypatch.setenv("VAGENT_ANALYSIS_EXECUTION_MODE", "queue")
    monkeypatch.setenv("VAGENT_S3_BUCKET", "bucket")
    monkeypatch.setenv("VAGENT_ANALYSIS_QUEUE_URL", "https://sqs.test/queue")
    monkeypatch.setenv("AWS_REGION", "ap-northeast-2")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    assert parse_analysis_execution_mode() == ("queue", None)
    assert analysis_execution_mode() == "queue"
    assert validate_analysis_execution_config() == []


@pytest.mark.parametrize("raw", ["queu", "LOCAL1", "foobar"])
def test_invalid_execution_mode_fail_fast(monkeypatch, raw):
    monkeypatch.setenv("VAGENT_ANALYSIS_EXECUTION_MODE", raw)
    mode, err = parse_analysis_execution_mode()
    assert mode is None
    assert err == "VAGENT_ANALYSIS_EXECUTION_MODE_INVALID"
    assert "VAGENT_ANALYSIS_EXECUTION_MODE_INVALID" in validate_analysis_execution_config()
    with pytest.raises(RuntimeError, match="invalid"):
        analysis_execution_mode()


def test_heartbeat_must_be_less_than_visibility(monkeypatch):
    monkeypatch.setenv("VAGENT_S3_BUCKET", "bucket")
    monkeypatch.setenv("VAGENT_ANALYSIS_QUEUE_URL", "https://sqs.test/queue")
    monkeypatch.setenv("AWS_REGION", "ap-northeast-2")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("VAGENT_SQS_VISIBILITY_TIMEOUT", "600")
    monkeypatch.delenv("VAGENT_SQS_HEARTBEAT_SECONDS", raising=False)
    assert sqs_heartbeat_seconds() == 120
    assert sqs_heartbeat_seconds() < sqs_visibility_timeout_seconds()
    assert validate_worker_config() == []
    monkeypatch.setenv("VAGENT_SQS_HEARTBEAT_SECONDS", "600")
    assert "VAGENT_SQS_HEARTBEAT_INVALID" in validate_worker_config()


def test_retry_visibility_default_and_range(monkeypatch):
    monkeypatch.setenv("VAGENT_S3_BUCKET", "bucket")
    monkeypatch.setenv("VAGENT_ANALYSIS_QUEUE_URL", "https://sqs.test/queue")
    monkeypatch.setenv("AWS_REGION", "ap-northeast-2")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.delenv("VAGENT_SQS_RETRY_VISIBILITY_SECONDS", raising=False)
    monkeypatch.delenv("VAGENT_SQS_HEARTBEAT_SECONDS", raising=False)
    monkeypatch.setenv("VAGENT_SQS_VISIBILITY_TIMEOUT", "600")
    assert sqs_retry_visibility_seconds() == 60
    monkeypatch.setenv("VAGENT_SQS_RETRY_VISIBILITY_SECONDS", "0")
    assert sqs_retry_visibility_seconds() == 0
    monkeypatch.setenv("VAGENT_SQS_RETRY_VISIBILITY_SECONDS", "43200")
    assert sqs_retry_visibility_seconds() == 43200
    monkeypatch.setenv("VAGENT_SQS_RETRY_VISIBILITY_SECONDS", "-1")
    assert "VAGENT_SQS_RETRY_VISIBILITY_INVALID" in validate_worker_config()
    monkeypatch.setenv("VAGENT_SQS_RETRY_VISIBILITY_SECONDS", "43201")
    assert "VAGENT_SQS_RETRY_VISIBILITY_INVALID" in validate_worker_config()
