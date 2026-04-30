import json
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.domain.models import FieldResult, MatchStatus
from app.services.batch_manager import clear_all_jobs, clear_job, create_batch_job, get_job_snapshot
from app.services.extractor import extract_fields
from app.services.image_preprocess import preprocess_image
from app.services.matcher import match_fields
from app.services.ocr.tesseract_engine import TesseractEngine
from app.services.pdf_parser import extract_ground_truth
from app.services.report_builder import build_batch_report
from app.services.retention_guard import clear_single_artifacts, forbid_disk_writes

router = APIRouter()
_SINGLE_FALLBACK_FIELDS = ("brand_name", "class_type", "alcohol_content", "net_contents", "government_warning")


class BatchItemPayload(BaseModel):
    item_id: str | None = None
    form_payload: Any
    label_payloads: list[Any] = Field(min_length=1, max_length=10)


class BatchVerifyRequest(BaseModel):
    items: list[BatchItemPayload]


@router.post("/verify/single")
async def verify_single(form_pdf: UploadFile = File(...), label_images: list[UploadFile] = File(...)) -> dict[str, object]:
    if not 1 <= len(label_images) <= 10:
        raise HTTPException(status_code=400, detail="label_images must include between 1 and 10 files")

    ground_truth_pdf = bytearray(await form_pdf.read())
    label_image_bytes_list = [bytearray(await label_image.read()) for label_image in label_images]
    extracted_payloads: list[Any] = []

    try:
        with forbid_disk_writes():
            ground_truth = extract_ground_truth(bytes(ground_truth_pdf))
            image_results: list[dict[str, object]] = []
            for label_image_bytes in label_image_bytes_list:
                try:
                    preprocessed_image = preprocess_image(bytes(label_image_bytes))
                    ocr_text = TesseractEngine().extract_text(preprocessed_image)
                    extracted_fields = extract_fields(ocr_text)
                    field_results = match_fields(ground_truth, extracted_fields)
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    image_results.append(_build_single_image_fallback_result())
                    continue

                extracted_payloads.extend([preprocessed_image, ocr_text, extracted_fields, field_results])
                image_results.append(
                    {
                        "status": _compute_overall_status(field_results),
                        "field_results": _serialize_field_results(field_results),
                    }
                )

        aggregate_field_results = _aggregate_field_results(image_results)
        return {
            "status": _compute_overall_status_from_serialized(aggregate_field_results),
            "field_results": aggregate_field_results,
            "image_results": image_results,
        }
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return _build_single_upload_fallback_response()
    finally:
        clear_single_artifacts(ground_truth_pdf, *label_image_bytes_list, extracted_payloads)


@router.post("/verify/batch", status_code=202)
async def verify_batch(payload: BatchVerifyRequest) -> dict[str, str]:
    job_id = create_batch_job([item.model_dump() for item in payload.items])
    return {"job_id": job_id}


@router.get("/verify/batch/{job_id}/report")
async def get_batch_report(job_id: str, purge: bool = Query(default=False)) -> JSONResponse:
    snapshot = get_job_snapshot(job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Batch job not found")

    report = build_batch_report(snapshot)
    status_code = 202 if snapshot["status"] in {"queued", "running"} else 200
    if purge and status_code == 200:
        clear_job(job_id)
    return JSONResponse(status_code=status_code, content=report)


@router.delete("/verify/batch/{job_id}", status_code=204)
async def clear_batch_job(job_id: str) -> Response:
    if not clear_job(job_id):
        raise HTTPException(status_code=404, detail="Batch job not found")
    return Response(status_code=204)


@router.delete("/verify/batch")
async def clear_batch_jobs() -> dict[str, int]:
    return {"removed_jobs": clear_all_jobs()}


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


def _build_single_upload_fallback_response() -> dict[str, object]:
    fallback_result = _build_single_image_fallback_result()
    return {
        "status": fallback_result["status"],
        "field_results": fallback_result["field_results"],
        "image_results": [fallback_result],
    }


def _build_single_image_fallback_result() -> dict[str, object]:
    return {
        "status": "review_required",
        "field_results": {
            field_name: {
                "expected_value": None,
                "extracted_value": None,
                "status": "review_required",
            }
            for field_name in _SINGLE_FALLBACK_FIELDS
        },
    }


def _aggregate_field_results(
    image_results: list[dict[str, object]],
) -> dict[str, dict[str, str | None]]:
    status_rank = {"pass": 2, "review_required": 1, "fail": 0}
    aggregate: dict[str, dict[str, str | None]] = {}
    for field_name in _SINGLE_FALLBACK_FIELDS:
        best_result: dict[str, str | None] | None = None
        best_rank = -1
        for image_result in image_results:
            field_results = image_result.get("field_results")
            if not isinstance(field_results, dict):
                continue
            field_result = field_results.get(field_name)
            if not isinstance(field_result, dict):
                continue
            status = field_result.get("status")
            if not isinstance(status, str):
                continue
            current_rank = status_rank.get(status, -1)
            if current_rank > best_rank:
                best_rank = current_rank
                best_result = {
                    "expected_value": field_result.get("expected_value"),
                    "extracted_value": field_result.get("extracted_value"),
                    "status": status,
                }
                continue
            if current_rank == best_rank and best_result is not None:
                if best_result.get("extracted_value") is None and field_result.get("extracted_value") is not None:
                    best_result = {
                        "expected_value": field_result.get("expected_value"),
                        "extracted_value": field_result.get("extracted_value"),
                        "status": status,
                    }

        if best_result is not None:
            aggregate[field_name] = best_result
        else:
            aggregate[field_name] = {
                "expected_value": None,
                "extracted_value": None,
                "status": "review_required",
            }
    return aggregate


def _compute_overall_status_from_serialized(field_results: dict[str, dict[str, str | None]]) -> MatchStatus:
    statuses = {
        result["status"]
        for result in field_results.values()
        if isinstance(result.get("status"), str)
    }
    if "fail" in statuses:
        return "fail"
    if "review_required" in statuses:
        return "review_required"
    return "pass"
