import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.models import FieldResult, MatchStatus
from app.services.extractor import extract_fields
from app.services.image_preprocess import preprocess_image
from app.services.matcher import match_fields
from app.services.ocr.tesseract_engine import TesseractEngine
from app.services.pdf_parser import extract_ground_truth
from app.services.retention_guard import (
    clear_all_batch_artifacts,
    clear_batch_artifacts,
    clear_single_artifacts,
    forbid_disk_writes,
)

_MAX_ATTEMPTS_PER_ITEM = 2
_COMPLETED_JOB_STATUSES = {"completed", "completed_with_failures"}
_COMPLETED_JOB_TTL_SECONDS = 600
_current_time = time.time


@dataclass(slots=True)
class BatchItemState:
    item_id: str
    status: str = "queued"
    attempts: int = 0
    overall_status: MatchStatus | None = None
    field_results: dict[str, dict[str, str | None]] = field(default_factory=dict)
    error: str | None = None


@dataclass(slots=True)
class BatchJobRecord:
    job_id: str
    status: str
    total: int
    processed: int
    items: list[BatchItemState]
    completed_at: float | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


_jobs: dict[str, BatchJobRecord] = {}
_jobs_lock = threading.Lock()


def create_batch_job(items: list[dict[str, Any]]) -> str:
    job_id = str(uuid.uuid4())
    item_states = [BatchItemState(item_id=_resolve_item_id(item, index)) for index, item in enumerate(items, start=1)]
    record = BatchJobRecord(
        job_id=job_id,
        status="queued",
        total=len(items),
        processed=0,
        items=item_states,
    )

    with _jobs_lock:
        _purge_expired_jobs_locked()
        _jobs[job_id] = record

    _emit_event(record, event_type="job_created")
    worker = threading.Thread(target=_process_job, args=(job_id, items), daemon=True)
    worker.start()
    return job_id


def get_job_snapshot(job_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        _purge_expired_jobs_locked()
        record = _jobs.get(job_id)
    if record is None:
        return None
    with record.lock:
        return {
            "job_id": record.job_id,
            "status": record.status,
            "summary": {"processed": record.processed, "total": record.total},
            "items": [
                {
                    "item_id": item.item_id,
                    "status": item.status,
                    "attempts": item.attempts,
                    "overall_status": item.overall_status,
                    "field_results": item.field_results,
                    "error": item.error,
                }
                for item in record.items
            ],
            "events": [event.copy() for event in record.events],
        }


def get_events_since(job_id: str, cursor: int) -> tuple[list[dict[str, Any]], int]:
    snapshot = get_job_snapshot(job_id)
    if snapshot is None:
        return [], cursor
    events = snapshot["events"]
    if cursor >= len(events):
        return [], cursor
    return events[cursor:], len(events)


def is_job_finished(job_id: str) -> bool:
    snapshot = get_job_snapshot(job_id)
    if snapshot is None:
        return True
    return snapshot["status"] in _COMPLETED_JOB_STATUSES


def clear_job(job_id: str) -> bool:
    with _jobs_lock:
        return clear_batch_artifacts(_jobs, job_id)


def clear_all_jobs() -> int:
    with _jobs_lock:
        return clear_all_batch_artifacts(_jobs)


def _process_job(job_id: str, items: list[dict[str, Any]]) -> None:
    record = _get_required_job(job_id)
    with record.lock:
        record.status = "running"
        record.completed_at = None
    _emit_event(record, event_type="job_started")

    for index, item_payload in enumerate(items):
        item_state = record.items[index]
        _process_item(record, item_state, item_payload)

    with record.lock:
        has_failure_outcome = any(item.overall_status in {"fail", "review_required"} for item in record.items)
        record.status = "completed_with_failures" if has_failure_outcome else "completed"
        record.completed_at = _current_time()
        processed = record.processed
        total = record.total
        status = record.status

    _emit_event(
        record,
        event_type="job_completed",
        item_id=None,
        processed=processed,
        total=total,
        status=status,
    )


def _process_item(record: BatchJobRecord, item_state: BatchItemState, item_payload: dict[str, Any]) -> None:
    for attempt in range(1, _MAX_ATTEMPTS_PER_ITEM + 1):
        with record.lock:
            item_state.attempts = attempt
            item_state.status = "processing" if attempt == 1 else "retrying"
            item_state.error = None

        if attempt > 1:
            _emit_event(
                record,
                event_type="item_retrying",
                item_id=item_state.item_id,
                processed=record.processed,
                total=record.total,
            )

        try:
            result = _verify_item_payload(item_payload)
        except Exception as error:  # noqa: BLE001
            if attempt == _MAX_ATTEMPTS_PER_ITEM:
                with record.lock:
                    item_state.status = "review_required"
                    item_state.overall_status = "review_required"
                    item_state.error = str(error)
                    record.processed += 1
                    processed = record.processed
                    total = record.total
                _emit_event(
                    record,
                    event_type="item_processed",
                    item_id=item_state.item_id,
                    processed=processed,
                    total=total,
                    status=item_state.status,
                    overall_status=item_state.overall_status,
                )
                return
            continue

        with record.lock:
            item_state.overall_status = result["status"]
            item_state.status = "completed"
            item_state.field_results = result["field_results"]
            item_state.error = None
            record.processed += 1
            processed = record.processed
            total = record.total

        _emit_event(
            record,
            event_type="item_processed",
            item_id=item_state.item_id,
            processed=processed,
            total=total,
            status=item_state.status,
            overall_status=item_state.overall_status,
        )
        return


def _verify_item_payload(item_payload: dict[str, Any]) -> dict[str, Any]:
    form_payload = item_payload.get("form_payload")
    label_payload = item_payload.get("label_payload")
    form_bytes = bytearray(json.dumps(form_payload).encode("utf-8"))
    label_bytes = bytearray(json.dumps(label_payload).encode("utf-8"))
    extracted_payloads: list[Any] = []

    try:
        with forbid_disk_writes():
            ground_truth = extract_ground_truth(bytes(form_bytes))
            preprocessed_image = preprocess_image(bytes(label_bytes))
            ocr_text = TesseractEngine().extract_text(preprocessed_image)
            extracted_fields = extract_fields(ocr_text)
            field_results = match_fields(ground_truth, extracted_fields)

        extracted_payloads.extend([preprocessed_image, ocr_text, extracted_fields, field_results])
        return {
            "status": _compute_overall_status(field_results),
            "field_results": _serialize_field_results(field_results),
        }
    finally:
        clear_single_artifacts(form_bytes, label_bytes, extracted_payloads)


def _compute_overall_status(field_results: dict[str, FieldResult]) -> MatchStatus:
    statuses = {result.status for result in field_results.values()}
    if "fail" in statuses:
        return "fail"
    if "review_required" in statuses:
        return "review_required"
    return "pass"


def _serialize_field_results(field_results: dict[str, FieldResult]) -> dict[str, dict[str, str | None]]:
    return {
        field_name: {
            "expected_value": result.expected_value,
            "extracted_value": result.extracted_value,
            "status": result.status,
        }
        for field_name, result in field_results.items()
    }


def _emit_event(
    record: BatchJobRecord,
    *,
    event_type: str,
    item_id: str | None = None,
    processed: int | None = None,
    total: int | None = None,
    status: str | None = None,
    overall_status: MatchStatus | None = None,
) -> None:
    with record.lock:
        event: dict[str, Any] = {
            "job_id": record.job_id,
            "event_type": event_type,
            "processed": record.processed if processed is None else processed,
            "total": record.total if total is None else total,
            "status": record.status if status is None else status,
        }
        if item_id is not None:
            event["item_id"] = item_id
        if overall_status is not None:
            event["overall_status"] = overall_status
        record.events.append(event)


def _resolve_item_id(item: dict[str, Any], index: int) -> str:
    item_id = item.get("item_id")
    if isinstance(item_id, str) and item_id.strip():
        return item_id
    return f"item-{index}"


def _purge_expired_jobs_locked() -> int:
    now = _current_time()
    expired_ids = [
        job_id
        for job_id, record in _jobs.items()
        if record.status in _COMPLETED_JOB_STATUSES
        and record.completed_at is not None
        and now - record.completed_at >= _COMPLETED_JOB_TTL_SECONDS
    ]
    for job_id in expired_ids:
        del _jobs[job_id]
    return len(expired_ids)


def _get_required_job(job_id: str) -> BatchJobRecord:
    with _jobs_lock:
        record = _jobs.get(job_id)
    if record is None:
        raise KeyError(f"Unknown job_id: {job_id}")
    return record
