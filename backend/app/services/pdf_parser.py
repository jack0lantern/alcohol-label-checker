import io
import json
import re
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.domain.models import GroundTruthFields


def extract_ground_truth(raw_bytes: bytes) -> GroundTruthFields:
    """Load ground truth from a UTF-8 JSON blob (dev/MVP) or a real TTB PDF form."""
    if _is_pdf_magic(raw_bytes):
        text = _extract_pdf_text(raw_bytes)
        payload = _parse_ground_truth_from_form_text(text)
        return _build_ground_truth_fields(payload)
    return _ground_truth_from_json_bytes(raw_bytes)


def _is_pdf_magic(raw_bytes: bytes) -> bool:
    return len(raw_bytes) >= 5 and raw_bytes[:5] == b"%PDF-"


def _ground_truth_from_json_bytes(raw_bytes: bytes) -> GroundTruthFields:
    parsed = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Form PDF payload must be a JSON object")
    return _build_ground_truth_fields(parsed)


def _build_ground_truth_fields(payload: dict[str, Any]) -> GroundTruthFields:
    return GroundTruthFields(
        brand_name=_as_optional_text(payload.get("brand_name")),
        class_type=_as_optional_text(payload.get("class_type")),
        alcohol_content=_as_optional_text(payload.get("alcohol_content")),
        net_contents=_as_optional_text(payload.get("net_contents")),
        government_warning=_as_optional_text(payload.get("government_warning")),
    )


def _extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
    except PdfReadError as exc:
        raise ValueError("Could not read PDF form") from exc
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _parse_ground_truth_from_form_text(text: str) -> dict[str, Any]:
    """Merge generic label-style key:value lines with TTB F 5100.31 layout heuristics."""
    from app.services.extractor import _parse_key_value_text

    merged: dict[str, Any] = dict(_parse_key_value_text(text))
    for key, value in _extract_ttb_f510031_fields(text).items():
        if value is not None and str(value).strip() != "":
            merged[key] = value
    return merged


def _extract_ttb_f510031_fields(text: str) -> dict[str, str]:
    """Pull known fields when they appear in fillable TTB F 5100.31 text."""
    out: dict[str, str] = {}

    brand = _match_brand_name_item_6(text)
    if brand is not None:
        out["brand_name"] = brand

    class_type = _match_product_class_item_5(text)
    if class_type is not None:
        out["class_type"] = class_type

    warning = _match_government_warning_block(text)
    if warning is not None:
        out["government_warning"] = warning

    return out


def _match_brand_name_item_6(text: str) -> str | None:
    m = re.search(
        r"(?ms)6\.\s*BRAND NAME[^\n]*\n\s*(.+?)\s*\n\s*7\.\s*FANCIFUL",
        text,
        re.IGNORECASE,
    )
    if m is None:
        return None
    candidate = m.group(1).strip()
    return candidate if candidate != "" else None


def _match_product_class_item_5(text: str) -> str | None:
    window = _slice_after_heading(text, r"5\.\s*TYPE OF PRODUCT")
    if window is None:
        return None
    head = window[:1200]
    for label, normalized in (
        (r"MALT\s+BEVERAGES?\b", "MALT BEVERAGE"),
        (r"DISTILLED\s+SPIRITS?\b", "DISTILLED SPIRITS"),
        (r"\bWINE\b", "WINE"),
    ):
        if re.search(rf"(?i)[x✓√☒]\s{{0,20}}{label}", head):
            return normalized
        if re.search(rf"(?i){label}.{{0,20}}[x✓√☒]", head):
            return normalized
    return None


def _slice_after_heading(text: str, heading_pattern: str) -> str | None:
    m = re.search(heading_pattern, text, re.IGNORECASE)
    if m is None:
        return None
    return text[m.end() : m.end() + 2500]


def _match_government_warning_block(text: str) -> str | None:
    m = re.search(
        r"(GOVERNMENT WARNING:\s*.+?)(?=\n\s*(?:\d+\.|PART |TTB F|--- |\Z))",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m is None:
        return None
    collapsed = re.sub(r"\s+", " ", m.group(1)).strip()
    return collapsed if len(collapsed) > 40 else None


def _as_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
