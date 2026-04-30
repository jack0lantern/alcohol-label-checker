from fastapi import APIRouter, File, UploadFile

from app.domain.models import FieldResult, MatchStatus
from app.services.extractor import extract_fields
from app.services.image_preprocess import preprocess_image
from app.services.matcher import match_fields
from app.services.ocr.tesseract_engine import TesseractEngine
from app.services.pdf_parser import extract_ground_truth

router = APIRouter()


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
