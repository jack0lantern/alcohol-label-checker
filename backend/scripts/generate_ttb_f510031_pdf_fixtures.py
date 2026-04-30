#!/usr/bin/env python3
"""Fill TTB F 5100.31 template PDFs for each JSON form fixture (same stem as tests)."""

from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.constants import CatalogDictionary

REPO_ROOT = Path(__file__).resolve().parents[2]
FORMS_DIR = REPO_ROOT / "tests" / "fixtures" / "labels" / "forms"
SOURCE_PDF = FORMS_DIR / "f510031.pdf"

ITEM15 = (
    "15.  SHOW ANY INFORMATION THAT IS BLOWN, BRANDED, OR EMBOSSED ON THE "
    "CONTAINER (e.g., net contents) ONLY IF IT DOES NOT APPEAR ON THE LABELS"
)


def _item15_block(data: dict[str, str]) -> str:
    """Key:value lines so `extract_ground_truth` can parse the same fields as JSON."""
    return (
        f"Brand name: {data['brand_name']}\n"
        f"Class / type: {data['class_type']}\n"
        f"Alcohol content: {data['alcohol_content']}\n"
        f"Net contents: {data['net_contents']}\n"
        f"Government warning: {data['government_warning']}"
    )


def build_fields(stem: str, data: dict[str, str]) -> dict[str, str]:
    suffix = "".join(c if c.isalnum() else "" for c in stem)[-6:].upper() or "FIXTURE"
    return {
        "Check Box22": "/Malt",
        "Check Box34": "/Domes",
        "14a. CERTIFICATE OF LABEL APPROVAL": "/yes",
        "1. REP. ID. NO. (If any)": "COLA-2026-0142",
        "2.  PLANT REGISTRY/BASIC PERMIT/BREWER'S NO. (Required)": "OR-BREW-2018-00042",
        "YEAR 1": "20",
        "YEAR 2": "26",
        "Text24.0": "2",
        "Text24.1": "0",
        "Text25.0": "O",
        "Text25.1": "R",
        "SERIAL NUMBER 1": "0",
        "SERIAL NUMBER 2": "0",
        "SERIAL NUMBER 3": "0",
        "SERIAL NUMBER 4": "1",
        "6. BRAND NAME (Required)": data["brand_name"],
        "7. FANCIFUL NAME (If any)": f"{data['brand_name'].split()[0]} Series",
        "8. NAME AND ADDRESS OF APPLICANT AS SHOWN ON PLANT REGISTRY, BASIC": (
            "Fixture Brewing Company LLC\n"
            "Attn: Label Compliance\n"
            "1200 NW Front Avenue, Suite 400\n"
            "Portland, OR 97209"
        ),
        "8a. MAILING ADDRESS, IF DIFFERENT": "PO Box 1000, Portland OR 97210",
        "9.  FORMULA": f"FL-{suffix}-A",
        "10. GRAPE VARIETAL(S) Wine only": "N/A",
        "11.  WINE APPELLATION (If on label)": "N/A",
        "12.  PHONE NUMBER": "503-555-0100",
        "13.  EMAIL ADDRESS": f"ttb+{stem}@fixtures.example",
        "14 b (Fill in State abbreviation)": "OR",
        "14c.  TOTAL BOTTLE CAPACITY BEFORE CLOSURE (Fill in amount)": data["net_contents"],
        "TTB ID": f"TTB-COLA-{suffix}",
        ITEM15: _item15_block(data),
        "16.  DATE OF APPLICATION": "04/30/2026",
        "18.  PRINT NAME OF APPLICANT OR AUTHORIZED AGENT": "Jordan Example",
        "19. DATE ISSUED": "",
        "FOR TTB USE ONLY - QUALIFICATIONS": "",
        "FOR TTB USE ONLY - EXPIRATION DATE (If any)": "",
    }


def write_filled_pdf(dest: Path, fields: dict[str, str]) -> None:
    reader = PdfReader(SOURCE_PDF.open("rb"))
    writer = PdfWriter()
    writer.append(reader)
    writer.set_need_appearances_writer(True)
    # Flatten merges field appearances into page /Contents via XObjects. Without the
    # next steps, viewers also paint the living AcroForm widgets on top → double text / blur.
    writer.update_page_form_field_values(None, fields, flatten=True)
    writer.remove_annotations(["/Widget"])
    if CatalogDictionary.ACRO_FORM in writer.root_object:
        del writer.root_object[CatalogDictionary.ACRO_FORM]
    buf = BytesIO()
    writer.write(buf)
    dest.write_bytes(buf.getvalue())


def main() -> int:
    if not SOURCE_PDF.is_file():
        print(f"Missing template: {SOURCE_PDF}", file=sys.stderr)
        return 1
    json_files = sorted(
        p
        for p in FORMS_DIR.glob("*.json")
        if p.is_file() and p.stem not in ("", "f510031")
    )
    if not json_files:
        print(f"No JSON form fixtures under {FORMS_DIR}", file=sys.stderr)
        return 1
    for path in json_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            print(f"Skip non-object JSON: {path}", file=sys.stderr)
            continue
        stem = path.stem
        dest = FORMS_DIR / f"{stem}_f510031.pdf"
        fields = build_fields(stem, {k: str(v) for k, v in data.items()})
        write_filled_pdf(dest, fields)
        print(f"Wrote {dest.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
