import json
from typing import Any

from app.domain.models import LabelExtractedFields


def extract_fields(ocr_text: str) -> LabelExtractedFields:
    payload = _parse_payload(ocr_text)
    return LabelExtractedFields(
        brand_name=_as_optional_text(payload.get("brand_name")),
        class_type=_as_optional_text(payload.get("class_type")),
        alcohol_content=_as_optional_text(payload.get("alcohol_content")),
        net_contents=_as_optional_text(payload.get("net_contents")),
        government_warning=_as_optional_text(payload.get("government_warning")),
    )


def _parse_payload(ocr_text: str) -> dict[str, Any]:
    parsed = json.loads(ocr_text)
    if not isinstance(parsed, dict):
        raise ValueError("OCR output must be a JSON object")
    return parsed


def _as_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
