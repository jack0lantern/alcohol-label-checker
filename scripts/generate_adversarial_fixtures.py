#!/usr/bin/env python3
"""Create generated and adversarial fixture images and metadata.

Three fixtures:
  generated_citrus_ipa      – clean label, all fields pass
  adversarial_warning_typo  – one-char typo in government warning → review_required
  adversarial_wrong_abv     – label shows 7.0% but form declares 5.0% → alcohol_content fail

Run once, inspect images, then commit:
  uv run python scripts/generate_adversarial_fixtures.py
"""

from __future__ import annotations

import io
import json
from hashlib import sha256
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests/fixtures/labels"

_WARNING_CORRECT = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

# One-char typo: GOVERNMENT → GOVERNMET
_WARNING_TYPO = (
    "GOVERNMET WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

# Each entry: form = what the TTB form declares; truth = what the label actually shows.
# For clean fixtures truth == form; for adversarial they differ.
FIXTURES: list[dict] = [
    {
        "fixture_id": "generated_citrus_ipa",
        "sample_type": "generated",
        "source": "synthetic",
        "scenario": "single_pass",
        "notes": "Synthetic generated IPA label (MALT BEVERAGE, 6.5% ABV, 16 fl oz). All fields pass.",
        "form": {
            "brand_name": "CITRUS IPA BREWING CO",
            "class_type": "MALT BEVERAGE",
            "alcohol_content": "6.5% ALC/VOL",
            "net_contents": "16 FL OZ",
            "government_warning": _WARNING_CORRECT,
        },
        "truth": None,  # same as form
    },
    {
        "fixture_id": "adversarial_warning_typo",
        "sample_type": "adversarial",
        "source": "synthetic",
        "scenario": "review_required",
        "notes": (
            "Adversarial label: government warning has a one-character typo "
            "('GOVERNMET' vs 'GOVERNMENT'). High similarity triggers review_required."
        ),
        "form": {
            "brand_name": "CITRUS IPA BREWING CO",
            "class_type": "MALT BEVERAGE",
            "alcohol_content": "6.5% ALC/VOL",
            "net_contents": "16 FL OZ",
            "government_warning": _WARNING_CORRECT,
        },
        "truth": {
            "brand_name": "CITRUS IPA BREWING CO",
            "class_type": "MALT BEVERAGE",
            "alcohol_content": "6.5% ALC/VOL",
            "net_contents": "16 FL OZ",
            "government_warning": _WARNING_TYPO,
        },
    },
    {
        "fixture_id": "adversarial_wrong_abv",
        "sample_type": "adversarial",
        "source": "synthetic",
        "scenario": "fail",
        "notes": (
            "Adversarial label: alcohol content is 7.0% on the label but form declares 5.0%. "
            "alcohol_content field must fail."
        ),
        "form": {
            "brand_name": "GOOD PEOPLE BREWING CO",
            "class_type": "BEER",
            "alcohol_content": "5.0% ALC/VOL",
            "net_contents": "12 FL OZ",
            "government_warning": _WARNING_CORRECT,
        },
        "truth": {
            "brand_name": "GOOD PEOPLE BREWING CO",
            "class_type": "BEER",
            "alcohol_content": "7.0% ALC/VOL",
            "net_contents": "12 FL OZ",
            "government_warning": _WARNING_CORRECT,
        },
    },
]

_BG_TINTS = [
    (200, 230, 200),  # pale green  (citrus IPA)
    (230, 205, 205),  # pale rose   (warning typo)
    (205, 210, 235),  # pale blue   (wrong ABV)
]


def _make_image(label_content: dict, tint: tuple[int, int, int], fixture_id: str) -> bytes:
    w, h = 1400, 900
    img = Image.new("RGB", (w, h), color=tint)
    draw = ImageDraw.Draw(img)

    lines = [
        f"Brand Name: {label_content['brand_name']}",
        f"Class/Type: {label_content['class_type']}",
        f"Alcohol Content: {label_content['alcohol_content']}",
        f"Net Contents: {label_content['net_contents']}",
        f"Government Warning: {label_content['government_warning']}",
    ]

    y = 40
    for line in lines:
        draw.text((40, y), line, fill=(15, 15, 15))
        y += 60

    # Decorative lines confined below text rows to avoid OCR interference.
    bottom = y + 20
    seed = sum(ord(c) for c in fixture_id)
    for i in range(3):
        row = bottom + (seed + i * 31) % (h - bottom - 10)
        draw.line((0, row, w, row), fill=(100, 100, 100), width=1)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _build_expected(scenario: str) -> dict:
    all_pass = {"brand_name": "pass", "class_type": "pass", "alcohol_content": "pass",
                "net_contents": "pass", "government_warning": "pass"}
    if scenario == "single_pass":
        return {"overall_status": "pass", "field_statuses": all_pass}
    if scenario == "review_required":
        return {
            "overall_status": "review_required",
            "field_statuses": {**all_pass, "government_warning": "review_required"},
        }
    if scenario == "fail":
        return {
            "overall_status": "fail",
            "field_statuses": {**all_pass, "alcohol_content": "fail"},
        }
    raise ValueError(f"Unknown scenario: {scenario}")


def main() -> None:
    images_dir = FIXTURES_DIR / "images"
    forms_dir = FIXTURES_DIR / "forms"
    truth_dir = FIXTURES_DIR / "truth"
    expected_dir = FIXTURES_DIR / "expected"
    for d in (images_dir, forms_dir, truth_dir, expected_dir):
        d.mkdir(parents=True, exist_ok=True)

    manifest_path = FIXTURES_DIR / "fixtures_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for fixture, tint in zip(FIXTURES, _BG_TINTS):
        fid = fixture["fixture_id"]
        form_data = fixture["form"]
        truth_data = fixture["truth"] if fixture["truth"] is not None else form_data

        image_path = images_dir / f"{fid}.png"
        form_path = forms_dir / f"{fid}.json"
        truth_path = truth_dir / f"{fid}.json"
        expected_path = expected_dir / f"{fid}.json"

        # Image renders the label content (truth — adversarial version for adversarial fixtures).
        image_path.write_bytes(_make_image(truth_data, tint, fid))
        _write_json(form_path, form_data)
        _write_json(truth_path, truth_data)
        _write_json(expected_path, _build_expected(fixture["scenario"]))

        entry = {
            "fixture_id": fid,
            "sample_type": fixture["sample_type"],
            "source": fixture["source"],
            "scenario": fixture["scenario"],
            "notes": fixture["notes"],
            "image": f"tests/fixtures/labels/images/{fid}.png",
            "image_sha256": _sha256(image_path),
            "form": f"tests/fixtures/labels/forms/{fid}.json",
            "form_sha256": _sha256(form_path),
            "truth": f"tests/fixtures/labels/truth/{fid}.json",
            "truth_sha256": _sha256(truth_path),
            "expected": f"tests/fixtures/labels/expected/{fid}.json",
            "expected_sha256": _sha256(expected_path),
        }

        existing = [e for e in manifest["fixtures"] if e["fixture_id"] == fid]
        if existing:
            idx = manifest["fixtures"].index(existing[0])
            manifest["fixtures"][idx] = entry
        else:
            manifest["fixtures"].append(entry)

        print(f"  {fid}: {image_path.stat().st_size} bytes")

    _write_json(manifest_path, manifest)
    print(f"Manifest updated: {manifest_path}")


if __name__ == "__main__":
    main()
