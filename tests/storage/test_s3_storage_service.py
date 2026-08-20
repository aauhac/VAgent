"""Fake-client tests for S3 StorageService. No live AWS calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.storage.s3 import (
    StorageObjectNotFoundError,
    StorageService,
    StorageUnavailableError,
    analysis_audio_object_key,
    build_storage_service,
)


class FakeAWSError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail_code: str | None = None

    def upload_file(self, Filename, Bucket, Key, ExtraArgs=None, **kwargs):
        self.calls.append(
            ("upload_file", {"Filename": Filename, "Bucket": Bucket, "Key": Key, "ExtraArgs": ExtraArgs})
        )
        if self.fail_code:
            raise FakeAWSError(self.fail_code)
        self.objects[(Bucket, Key)] = {
            "body": Path(Filename).read_bytes(),
            "extra": ExtraArgs or {},
        }

    def download_file(self, Bucket, Key, Filename, **kwargs):
        self.calls.append(("download_file", {"Bucket": Bucket, "Key": Key, "Filename": Filename}))
        if self.fail_code:
            raise FakeAWSError(self.fail_code)
        obj = self.objects.get((Bucket, Key))
        if obj is None:
            raise FakeAWSError("NoSuchKey")
        dest = Path(Filename)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(obj["body"])

    def delete_object(self, Bucket, Key, **kwargs):
        self.calls.append(("delete_object", {"Bucket": Bucket, "Key": Key}))
        if self.fail_code:
            raise FakeAWSError(self.fail_code)
        self.objects.pop((Bucket, Key), None)

    def head_object(self, Bucket, Key, **kwargs):
        self.calls.append(("head_object", {"Bucket": Bucket, "Key": Key}))
        if self.fail_code:
            raise FakeAWSError(self.fail_code)
        if (Bucket, Key) not in self.objects:
            raise FakeAWSError("404")
        return {"ContentLength": len(self.objects[(Bucket, Key)]["body"])}


ANALYSIS_ID = "c7045e107d714b64880a468748b1f8b7"


def _service(fake: FakeS3Client | None = None) -> tuple[StorageService, FakeS3Client]:
    client = fake or FakeS3Client()
    return StorageService("test-bucket", client, region="test-region"), client


def test_importing_storage_module_does_not_require_env(monkeypatch):
    monkeypatch.delenv("VAGENT_S3_BUCKET", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    import backend.app.storage.s3 as mod

    assert hasattr(mod, "StorageService")


def test_build_storage_service_requires_bucket(monkeypatch):
    monkeypatch.delenv("VAGENT_S3_BUCKET", raising=False)
    monkeypatch.setenv("AWS_REGION", "ap-northeast-2")
    with pytest.raises(RuntimeError, match="VAGENT_S3_BUCKET"):
        build_storage_service(s3_client=FakeS3Client())


def test_build_storage_service_requires_region(monkeypatch):
    monkeypatch.setenv("VAGENT_S3_BUCKET", "test-bucket")
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    with pytest.raises(RuntimeError, match="AWS_REGION"):
        build_storage_service(s3_client=FakeS3Client())


def test_upload_builds_object_key_and_preserves_extension(tmp_path):
    local = tmp_path / "song.m4a"
    local.write_bytes(b"fake-audio")
    service, client = _service()
    key = service.upload_analysis_audio(ANALYSIS_ID, local)
    assert key == f"analyses/{ANALYSIS_ID}/input.m4a"
    assert analysis_audio_object_key(ANALYSIS_ID, ".m4a") == key
    call = client.calls[0]
    assert call[0] == "upload_file"
    assert call[1]["Bucket"] == "test-bucket"
    assert call[1]["Key"] == key
    assert call[1]["Filename"] == str(local)
    assert call[1]["ExtraArgs"]["ContentType"] == "audio/mp4"
    assert "ACL" not in (call[1]["ExtraArgs"] or {})


def test_upload_wav_keeps_wav_extension(tmp_path):
    local = tmp_path / "clip.wav"
    local.write_bytes(b"RIFF")
    service, client = _service()
    key = service.upload_analysis_audio(ANALYSIS_ID, local, content_type="audio/wav")
    assert key.endswith(".wav")
    assert client.calls[0][1]["ExtraArgs"]["ContentType"] == "audio/wav"


def test_download_writes_destination(tmp_path):
    local = tmp_path / "song.m4a"
    local.write_bytes(b"abc123")
    service, client = _service()
    key = service.upload_analysis_audio(ANALYSIS_ID, local)
    dest = tmp_path / "work" / "input.m4a"
    out = service.download_analysis_audio(key, dest)
    assert out.read_bytes() == b"abc123"
    assert client.calls[-1][0] == "download_file"
    assert client.calls[-1][1]["Bucket"] == "test-bucket"
    assert client.calls[-1][1]["Key"] == key


def test_object_exists_true_and_false(tmp_path):
    local = tmp_path / "song.mp3"
    local.write_bytes(b"mp3")
    service, _client = _service()
    key = service.upload_analysis_audio(ANALYSIS_ID, local)
    assert service.object_exists(key) is True
    assert service.object_exists(f"analyses/{ANALYSIS_ID}/input.wav") is False


def test_delete_removes_object(tmp_path):
    local = tmp_path / "song.flac"
    local.write_bytes(b"flac")
    service, client = _service()
    key = service.upload_analysis_audio(ANALYSIS_ID, local)
    service.delete_analysis_audio(key)
    assert client.calls[-1] == ("delete_object", {"Bucket": "test-bucket", "Key": key})
    assert service.object_exists(key) is False


def test_rejects_path_traversal_analysis_id(tmp_path):
    local = tmp_path / "song.m4a"
    local.write_bytes(b"x")
    service, _client = _service()
    with pytest.raises(ValueError):
        service.upload_analysis_audio("../etc/passwd", local)
    with pytest.raises(ValueError):
        service.upload_analysis_audio("abc/../../secret", local)
    with pytest.raises(ValueError):
        service.download_analysis_audio("analyses/../input.m4a", tmp_path / "out.m4a")
    with pytest.raises(ValueError):
        service.object_exists("analyses/not-hex/input.m4a")


def test_rejects_invalid_analysis_id(tmp_path):
    local = tmp_path / "song.m4a"
    local.write_bytes(b"x")
    service, _client = _service()
    with pytest.raises(ValueError):
        service.upload_analysis_audio("short", local)
    with pytest.raises(ValueError):
        service.upload_analysis_audio("", local)


def test_aws_error_on_upload_is_wrapped(tmp_path):
    local = tmp_path / "song.m4a"
    local.write_bytes(b"x")
    fake = FakeS3Client()
    fake.fail_code = "InternalError"
    service, _client = _service(fake)
    with pytest.raises(StorageUnavailableError):
        service.upload_analysis_audio(ANALYSIS_ID, local)


def test_download_missing_object_raises_not_found(tmp_path):
    service, _client = _service()
    with pytest.raises(StorageObjectNotFoundError):
        service.download_analysis_audio(
            f"analyses/{ANALYSIS_ID}/input.m4a",
            tmp_path / "missing.m4a",
        )


def test_head_unexpected_error_is_unavailable():
    fake = FakeS3Client()
    fake.fail_code = "SlowDown"
    service, _client = _service(fake)
    with pytest.raises(StorageUnavailableError):
        service.object_exists(f"analyses/{ANALYSIS_ID}/input.m4a")
