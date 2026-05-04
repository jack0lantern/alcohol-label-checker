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
        reader = _open_pdf(raw_bytes)
        # AcroForm fields (filled form values) take priority over text-layer parsing.
        acroform = _extract_acroform_fields(reader)
        text = _extract_pdf_text_from_reader(reader)
        text_payload = _parse_ground_truth_from_form_text(text)
        # Merge: acroform values win over text-layer heuristics.
        merged: dict[str, Any] = {**text_payload, **acroform}
        return _build_ground_truth_fields(merged)
    return _ground_truth_from_json_bytes(raw_bytes)


def _is_pdf_magic(raw_bytes: bytes) -> bool:
    return len(raw_bytes) >= 5 and raw_bytes[:5] == b"%PDF-"


def _open_pdf(raw_bytes: bytes) -> PdfReader:
    try:
        return PdfReader(io.BytesIO(raw_bytes))
    except PdfReadError as exc:
        raise ValueError("Could not read PDF form") from exc


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


def _extract_acroform_fields(reader: PdfReader) -> dict[str, Any]:
    """Read filled AcroForm widget values from a TTB F 5100.31 PDF.

    Real COLA submissions store applicant-entered data (brand name, product type,
    net contents, government warning) in PDF form fields, not in the static text
    layer.  pypdf.get_fields() returns these filled values.
    """
    try:
        fields = reader.get_fields() or {}
    except Exception:
        return {}

    out: dict[str, Any] = {}

    # Item 6 — Brand Name
    # Try the canonical full name first, then fall back to the short key "6"
    for brand_key in ("6. BRAND NAME (Required)", "6"):
        brand_field = fields.get(brand_key)
        if brand_field is not None:
            val = _field_value(brand_field)
            if val:
                out["brand_name"] = val
                break

    # Item 5 — Type of product (checkbox group; value is the selected option name)
    _PRODUCT_TYPE_CHECKBOX_NAMES = (
        "Check Box22",   # typical field name on TTB F 5100.31 (04/2023)
        "5. TYPE OF PRODUCT",
    )
    _PRODUCT_TYPE_MAP = {
        "wine": "WINE",
        "distilledspirits": "DISTILLED SPIRITS",
        "maltbev": "MALT BEVERAGE",
        "malt": "MALT BEVERAGE",
    }
    for cb_name in _PRODUCT_TYPE_CHECKBOX_NAMES:
        cb = fields.get(cb_name)
        if cb is not None:
            val = _field_value(cb)
            if val:
                normalized = _PRODUCT_TYPE_MAP.get(val.lower().replace(" ", "").replace("_", ""))
                if normalized:
                    out["class_type"] = normalized
                    break

    # Item 15 — Blown/branded/embossed info (net contents, alcohol content, government warning)
    #
    # TTB guidance directs applicants to list net contents and the government warning here
    # when they do not appear separately on affixed labels.  Many real COLAs place all
    # mandatory information in this single free-text field.
    #
    # PDFs sometimes truncate long field names, producing multiple keys with the same
    # prefix (e.g. "15.  SHOW...CONTAINER (e", "15.  SHOW...CONTAINER (e.g",
    # "15.  SHOW...CONTAINER (e.g., net contents)...LABELS").  We pick the longest
    # matching key because that is the leaf field that actually holds the /V value.
    f15_candidates = [k for k in fields if k.startswith("15.") and "BLOWN" in k.upper()]
    if f15_candidates:
        f15_key = max(f15_candidates, key=len)
        f15_field = fields[f15_key]
        val = _field_value(f15_field)
        if val:
            _parse_field15_into(val, out)

    return out


def _field_value(field: Any) -> str | None:
    """Return the string value of a pypdf Field, stripping leading '/' from PDF name objects."""
    if field is None:
        return None
    raw = field.get("/V") if hasattr(field, "get") else field
    if raw is None or raw == "/Off":
        return None
    text = str(raw).strip()
    # PDF name objects for checkboxes arrive as e.g. '/Wine' — strip the slash
    if text.startswith("/"):
        text = text[1:]
    return text if text else None


def _parse_field15_into(text: str, out: dict[str, Any]) -> None:
    """Parse net contents, alcohol content, and government warning from field 15 free text."""
    normalised = text.replace("\r", " ")

    if "government_warning" not in out:
        gw_m = re.search(r"(GOVERNMENT WARNING:.+)", normalised, re.IGNORECASE | re.DOTALL)
        if gw_m:
            out["government_warning"] = re.sub(r"\s+", " ", gw_m.group(1)).strip()

    if "net_contents" not in out:
        nc_m = re.search(r"(\d[\d.,]*\s*(?:ML|L|OZ|fl\.?\s*oz\.?)\b)", normalised, re.IGNORECASE)
        if nc_m:
            out["net_contents"] = nc_m.group(1).strip()

    if "alcohol_content" not in out:
        alc_m = re.search(r"(ALC\.?\s*[\d.]+\s*%\s*BY\s*VOL\.?)", normalised, re.IGNORECASE)
        if alc_m:
            out["alcohol_content"] = alc_m.group(1).strip()


def _extract_pdf_text(raw_bytes: bytes) -> str:
    reader = _open_pdf(raw_bytes)
    return _extract_pdf_text_from_reader(reader)


def _extract_pdf_text_from_reader(reader: PdfReader) -> str:
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _parse_ground_truth_from_form_text(text: str) -> dict[str, Any]:
    """Merge generic label-style key:value lines with TTB F 5100.31 layout heuristics.

    Key:value lines take precedence: they are more specific (e.g. "BOURBON WHISKY"
    beats the high-level "DISTILLED SPIRITS" checkbox) and the TTB block extractor
    can over-capture when multi-page field text follows the government warning.
    TTB-specific fields serve as fallback when the key:value block is absent.
    """
    from app.services.extractor import _parse_key_value_text

    merged: dict[str, Any] = dict(_extract_ttb_f510031_fields(text))
    for key, value in _parse_key_value_text(text).items():
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
