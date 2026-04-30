import os
import io
from pathlib import Path

import pytest

from app.services.retention_guard import (
    DiskWriteViolation,
    clear_batch_artifacts,
    clear_single_artifacts,
    forbid_disk_writes,
)


def test_clear_batch_artifacts_removes_existing_job() -> None:
    jobs = {"job-1": {"status": "completed"}}

    was_removed = clear_batch_artifacts(jobs, "job-1")

    assert was_removed is True
    assert jobs == {}


def test_clear_batch_artifacts_returns_false_when_job_missing() -> None:
    jobs: dict[str, object] = {}

    was_removed = clear_batch_artifacts(jobs, "missing-job")

    assert was_removed is False


def test_clear_single_artifacts_clears_mutables_in_place() -> None:
    dict_payload = {"field": "value"}
    list_payload = ["value-1", "value-2"]
    byte_payload = bytearray(b"secret")

    clear_single_artifacts(dict_payload, list_payload, byte_payload)

    assert dict_payload == {}
    assert list_payload == []
    assert byte_payload == bytearray(b"\x00\x00\x00\x00\x00\x00")


def test_forbid_disk_writes_blocks_open_write_modes() -> None:
    with forbid_disk_writes():
        with pytest.raises(DiskWriteViolation):
            with open("blocked-write.txt", "w", encoding="utf-8"):
                pass


def test_forbid_disk_writes_blocks_pathlib_write_text() -> None:
    with forbid_disk_writes():
        with pytest.raises(DiskWriteViolation):
            Path("blocked-pathlib-write.txt").write_text("forbidden", encoding="utf-8")


def test_forbid_disk_writes_blocks_io_open_write_modes() -> None:
    with forbid_disk_writes():
        with pytest.raises(DiskWriteViolation):
            with io.open("blocked-io-open-write.txt", "w", encoding="utf-8"):
                pass


def test_forbid_disk_writes_blocks_os_open_write_flags() -> None:
    with forbid_disk_writes():
        with pytest.raises(DiskWriteViolation):
            os.open("blocked-os-open-write.txt", os.O_WRONLY | os.O_CREAT)
