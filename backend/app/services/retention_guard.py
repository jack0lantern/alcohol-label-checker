from collections.abc import MutableMapping
from contextlib import ExitStack, contextmanager
from typing import Any
import builtins
import tempfile
from unittest.mock import patch


class DiskWriteViolation(RuntimeError):
    pass


def clear_batch_artifacts(job_store: MutableMapping[str, Any], job_id: str) -> bool:
    try:
        del job_store[job_id]
    except KeyError:
        return False
    return True


def clear_all_batch_artifacts(job_store: MutableMapping[str, Any]) -> int:
    removed_count = len(job_store)
    job_store.clear()
    return removed_count


def clear_single_artifacts(*artifacts: Any) -> None:
    for artifact in artifacts:
        if isinstance(artifact, bytearray):
            artifact[:] = b"\x00" * len(artifact)
            continue
        if isinstance(artifact, list):
            artifact.clear()
            continue
        if isinstance(artifact, set):
            artifact.clear()
            continue
        if isinstance(artifact, dict):
            artifact.clear()


@contextmanager
def forbid_disk_writes():
    original_open = builtins.open
    original_named_temporary_file = tempfile.NamedTemporaryFile

    def _guarded_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any):
        if _is_write_mode(mode):
            raise DiskWriteViolation(f"Disk write attempted through open() for: {file}")
        return original_open(file, mode, *args, **kwargs)

    def _blocked_named_temporary_file(*args: Any, **kwargs: Any):
        mode = kwargs.get("mode")
        if mode is None and len(args) > 0 and isinstance(args[0], str):
            mode = args[0]
        if mode is None:
            mode = "w+b"
        if _is_write_mode(mode):
            raise DiskWriteViolation("Disk write attempted through tempfile.NamedTemporaryFile()")
        return original_named_temporary_file(*args, **kwargs)

    def _blocked_mkstemp(*args: Any, **kwargs: Any):
        raise DiskWriteViolation("Disk write attempted through tempfile.mkstemp()")

    with ExitStack() as stack:
        stack.enter_context(patch("builtins.open", _guarded_open))
        stack.enter_context(patch("tempfile.NamedTemporaryFile", _blocked_named_temporary_file))
        stack.enter_context(patch("tempfile.mkstemp", _blocked_mkstemp))
        yield


def _is_write_mode(mode: str) -> bool:
    return any(flag in mode for flag in ("w", "a", "x", "+"))
