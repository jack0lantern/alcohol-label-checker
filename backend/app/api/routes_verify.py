from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.domain.models import FieldResult, MatchStatus
from app.services.batch_manager import create_batch_job, get_job_snapshot
from app.services.extractor import extract_fields
from app.services.image_preprocess import preprocess_image
from app.services.matcher import match_fields
from app.services.ocr.tesseract_engine import TesseractEngine
from app.services.pdf_parser import extract_ground_truth
from app.services.report_builder import build_batch_report

router = APIRouter()


class BatchItemPayload(BaseModel):
    item_id: str | None = None
    form_payload: Any
    label_payload: Any


class BatchVerifyRequest(BaseModel):
    items: list[BatchItemPayload]


@router.post("/verify/single")
async def verify_single(form_pdf: UploadFile = File(...), label_image: UploadFile = File(...)) -> dict[str, object]:
    ground_truth_pdf = await form_pdf.read()
    label_image_bytes = await label_image.read()

    ground_truth = extract_ground_truth(ground_truth_pdf)
    preprocessed_image = preprocess_image(label_image_bytes)
    ocr_text = TesseractEngine().extract_text(preprocessed_image)
    extracted_fields = extract_fields(ocr_text)
    field_results = match_fields(ground_truth, extracted_fields)

    return {
        "status": _compute_overall_status(field_results),
        "field_results": _serialize_field_results(field_results),
    }


@router.post("/verify/batch", status_code=202)
async def verify_batch(payload: BatchVerifyRequest) -> dict[str, str]:
    job_id = create_batch_job([item.model_dump() for item in payload.items])
    return {"job_id": job_id}


@router.get("/verify/batch/{job_id}/report")
async def get_batch_report(job_id: str) -> JSONResponse:
    snapshot = get_job_snapshot(job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Batch job not found")

    report = build_batch_report(snapshot)
    status_code = 202 if snapshot["status"] in {"queued", "running"} else 200
    return JSONResponse(status_code=status_code, content=report)


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
