#!/usr/bin/env python3
"""Generate PDF forms + label PNGs for manual-test-pairs/.

Each pair folder gets two files named after the scenario (unique across all pairs):
  <slug>-form.pdf   – filled TTB F 5100.31 form; parsed by pdf_parser
  <slug>-label.png  – synthetic label; read by OCR

Why unique names: the batch upload API de-dups files by filename, so all forms
must have distinct names when dragged together for a batch run.

Why key:value block in Item 15 (not checkbox alone): _parse_key_value_text extracts
the specific class_type (e.g. BOURBON WHISKY) from the key:value block.  The TTB
checkbox only encodes the high-level category (DISTILLED SPIRITS), so it is used
only for visual correctness.  The merge priority in pdf_parser gives key:value
lines precedence over the TTB checkbox extraction.

Run from repo root:
  python3 scripts/generate_manual_test_pdfs.py
"""

from __future__ import annotations

import io
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from pypdf.constants import CatalogDictionary

REPO_ROOT = Path(__file__).resolve().parents[1]
PAIRS_DIR = REPO_ROOT / "manual-test-pairs"
SOURCE_PDF = REPO_ROOT / "tests" / "fixtures" / "labels" / "forms" / "f510031.pdf"

ITEM15 = (
    "15.  SHOW ANY INFORMATION THAT IS BLOWN, BRANDED, OR EMBOSSED ON THE "
    "CONTAINER (e.g., net contents) ONLY IF IT DOES NOT APPEAR ON THE LABELS"
)

WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)
WARNING_TYPO = (
    "GOVERNMET WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

# Check Box22 kid on-states: /Wine (kid 0), /Spirits (kid 1), /Malt (kid 2)
_CLASS_TO_CHECKBOX: dict[str, str] = {
    "BEER": "/Malt",
    "MALT BEVERAGE": "/Malt",
    "TABLE WINE": "/Wine",
    "BOURBON WHISKY": "/Spirits",
}

# (folder, slug, brand, class_type, alcohol, net, form_warning, label_warning)
# form_warning = what the PDF form declares (ground truth)
# label_warning = what appears on the label image (may differ for adversarial pairs)
PAIRS: list[tuple[str, str, str, str, str, str, str, str]] = [
    (
        "01-beer-pass",
        "beer-pass",
        "GOOD PEOPLE BREWING CO",
        "BEER",
        "5.0% ALC/VOL",
        "12 FL OZ",
        WARNING,
        WARNING,
    ),
    (
        "02-wine-pass",
        "wine-pass",
        "CHARLES SHAW WINERY",
        "TABLE WINE",
        "12.5% ALC/VOL",
        "750 ML",
        WARNING,
        WARNING,
    ),
    (
        "03-spirits-pass",
        "spirits-pass",
        "BUFFALO TRACE DISTILLERY",
        "BOURBON WHISKY",
        "45% ALC/VOL (90 PROOF)",
        "750 ML",
        WARNING,
        WARNING,
    ),
    (
        "04-ipa-pass",
        "ipa-pass",
        "CITRUS IPA BREWING CO",
        "MALT BEVERAGE",
        "6.5% ALC/VOL",
        "16 FL OZ",
        WARNING,
        WARNING,
    ),
    (
        "05-beer-fail-wrong-abv",
        "beer-fail-wrong-abv",
        "GOOD PEOPLE BREWING CO",
        "BEER",
        "5.0% ALC/VOL",  # form declares 5%
        "12 FL OZ",
        WARNING,
        WARNING,
        # label image will show 7.0% (generated separately below)
    ),
    (
        "06-beer-review-warning-typo",
        "beer-review-warning-typo",
        "CITRUS IPA BREWING CO",
        "MALT BEVERAGE",
        "6.5% ALC/VOL",
        "16 FL OZ",
        WARNING,        # form has correct warning
        WARNING_TYPO,   # label has "GOVERNMET" typo
    ),
    (
        "07-realistic-lager-pass",
        "realistic-lager-pass",
        "NORTH COAST LAGER",
        "MALT BEVERAGE",
        "5.0% ALC/VOL",
        "12 FL OZ",
        WARNING,
        WARNING,
    ),
]

# Pair 05 has a different ABV on the label vs the form
_LABEL_OVERRIDES: dict[str, dict[str, str]] = {
    "beer-fail-wrong-abv": {"alcohol": "7.0% ALC/VOL"},
}

_BG_TINTS: list[tuple[int, int, int]] = [
    (226, 198, 160),  # amber   – beer
    (210, 190, 220),  # mauve   – wine
    (230, 218, 170),  # gold    – spirits
    (200, 230, 200),  # green   – IPA
    (205, 210, 235),  # blue    – wrong ABV
    (230, 205, 205),  # rose    – warning typo
    (220, 220, 210),  # stone   – lager
]


# ---------------------------------------------------------------------------
# PDF generation (filled TTB F 5100.31)
# ---------------------------------------------------------------------------

def _item15_block(brand: str, class_type: str, alcohol: str, net: str, warning: str) -> str:
    """Key:value lines in Item 15 so pdf_parser._parse_key_value_text extracts all fields."""
    return (
        f"Brand name: {brand}\n"
        f"Class / type: {class_type}\n"
        f"Alcohol content: {alcohol}\n"
        f"Net contents: {net}\n"
        f"Government warning: {warning}"
    )


def _build_fields(slug: str, brand: str, class_type: str, alcohol: str,
                  net: str, warning: str) -> dict[str, str]:
    suffix = "".join(c for c in slug if c.isalnum())[-6:].upper() or "FIXTURE"
    checkbox = _CLASS_TO_CHECKBOX.get(class_type, "/Malt")
    return {
        "Check Box22": checkbox,
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
        "6. BRAND NAME (Required)": brand,
        "7. FANCIFUL NAME (If any)": f"{brand.split()[0]} Series",
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
        "13.  EMAIL ADDRESS": f"ttb+{slug}@fixtures.example",
        "14 b (Fill in State abbreviation)": "OR",
        "14c.  TOTAL BOTTLE CAPACITY BEFORE CLOSURE (Fill in amount)": net,
        "TTB ID": f"TTB-COLA-{suffix}",
        ITEM15: _item15_block(brand, class_type, alcohol, net, warning),
        "16.  DATE OF APPLICATION": "04/30/2026",
        "18.  PRINT NAME OF APPLICANT OR AUTHORIZED AGENT": "Jordan Example",
        "19. DATE ISSUED": "",
        "FOR TTB USE ONLY - QUALIFICATIONS": "",
        "FOR TTB USE ONLY - EXPIRATION DATE (If any)": "",
    }


def _make_pdf(slug: str, brand: str, class_type: str, alcohol: str,
              net: str, warning: str) -> bytes:
    fields = _build_fields(slug, brand, class_type, alcohol, net, warning)
    reader = PdfReader(SOURCE_PDF.open("rb"))
    writer = PdfWriter()
    writer.append(reader)
    writer.set_need_appearances_writer(True)
    writer.update_page_form_field_values(None, fields, flatten=True)
    writer.remove_annotations(["/Widget"])
    if CatalogDictionary.ACRO_FORM in writer.root_object:
        del writer.root_object[CatalogDictionary.ACRO_FORM]
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Label image generation
# ---------------------------------------------------------------------------

_FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
# 32 px gives reliable Tesseract reads; 6000 px wide fits the full
# government warning (~303 chars) on one line at ~18 px/char average.
_FONT_SIZE = 32
_LINE_H = 46
_IMG_W = 6000


def _make_label(
    brand: str,
    class_type: str,
    alcohol: str,
    net: str,
    warning: str,
    tint: tuple[int, int, int],
) -> bytes:
    """Render each field as a single 'Key: value' line.

    The extractor's key:value patterns require key and value on the same line,
    so the entire field must fit in one line.  We use a 32 px font on a 6000 px
    wide image so even the full government warning (~303 chars) fits.
    """
    font = ImageFont.truetype(_FONT_PATH, _FONT_SIZE)

    lines = [
        f"Brand Name: {brand}",
        f"Class/Type: {class_type}",
        f"Alcohol Content: {alcohol}",
        f"Net Contents: {net}",
        f"Government Warning: {warning}",
    ]

    img_h = len(lines) * _LINE_H + 60
    img = Image.new("RGB", (_IMG_W, img_h), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Colour stripe for visual pair identification
    draw.rectangle([0, 0, _IMG_W, 4], fill=tint)

    y = 20
    for line in lines:
        draw.text((20, y), line, font=font, fill=(0, 0, 0))
        y += _LINE_H

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not SOURCE_PDF.is_file():
        raise FileNotFoundError(f"Missing TTB template: {SOURCE_PDF}")

    for (folder, slug, brand, class_type, alcohol, net, form_warning, label_warning), tint in zip(
        PAIRS, _BG_TINTS
    ):
        dest = PAIRS_DIR / folder
        dest.mkdir(parents=True, exist_ok=True)

        label_alcohol = _LABEL_OVERRIDES.get(slug, {}).get("alcohol", alcohol)

        pdf_path = dest / f"{slug}-form.pdf"
        png_path = dest / f"{slug}-label.png"

        pdf_path.write_bytes(_make_pdf(slug, brand, class_type, alcohol, net, form_warning))
        png_path.write_bytes(
            _make_label(brand, class_type, label_alcohol, net, label_warning, tint)
        )

        print(f"  {folder}/{slug}-form.pdf   ({pdf_path.stat().st_size} B)")
        print(f"  {folder}/{slug}-label.png  ({png_path.stat().st_size} B)")


if __name__ == "__main__":
    main()
