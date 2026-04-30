import json
from typing import Any

from app.domain.models import GroundTruthFields


def extract_ground_truth(pdf_bytes: bytes) -> GroundTruthFields:
    payload = _parse_payload(pdf_bytes)
    return GroundTruthFields(
        brand_name=_as_optional_text(payload.get("brand_name")),
        class_type=_as_optional_text(payload.get("class_type")),
        alcohol_content=_as_optional_text(payload.get("alcohol_content")),
        net_contents=_as_optional_text(payload.get("net_contents")),
        government_warning=_as_optional_text(payload.get("government_warning")),
    )


def _parse_payload(raw_bytes: bytes) -> dict[str, Any]:
    parsed = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Form PDF payload must be a JSON object")
    return parsed


def _as_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
