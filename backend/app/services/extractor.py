import json
import re
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
    try:
        parsed = json.loads(ocr_text)
    except json.JSONDecodeError:
        return _parse_key_value_text(ocr_text)
    if not isinstance(parsed, dict):
        raise ValueError("OCR output must be a JSON object")
    return parsed


def _parse_key_value_text(ocr_text: str) -> dict[str, str]:
    normalized_text = ocr_text.replace("’", "").replace("‘", "")
    patterns = {
        "brand_name": re.compile(r"^\s*brand\s*name\s*[:\-]\s*(.+?)\s*$", re.IGNORECASE),
        "class_type": re.compile(r"^\s*class\s*/?\s*type\s*[:\-]?\s*(.+?)\s*$", re.IGNORECASE),
        "alcohol_content": re.compile(r"^\s*(?:alcohol|cohol)\s*content\s*[:\-]?\s*(.+?)\s*$", re.IGNORECASE),
        "net_contents": re.compile(r"^\s*net\s*contents?\s*[:\-]?\s*(.+?)\s*$", re.IGNORECASE),
        "government_warning": re.compile(r"^\s*government\s*warning\s*[:\-]\s*(.+?)\s*$", re.IGNORECASE),
    }
    payload: dict[str, str] = {}
    for line in normalized_text.splitlines():
        for field_name, pattern in patterns.items():
            match = pattern.match(line)
            if match is None:
                continue
            payload[field_name] = match.group(1).strip()
            break
    return payload


def _as_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
