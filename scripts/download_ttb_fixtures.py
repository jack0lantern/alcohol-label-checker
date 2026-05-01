#!/usr/bin/env python3
"""Create synthetic TTB COLA–style fixture images and metadata.

TTB COLA label images are only accessible to authenticated TTB account holders
and cannot be downloaded publicly. This script generates deterministic synthetic
PNG images that faithfully reproduce the field layout of real TTB COLA labels
(brand name, class/type code, alcohol content, net contents, and government
warning), giving the real-labels E2E suite realistic OCR input without
requiring a TTB account.

Run once, inspect the images visually, then commit:
  uv run python scripts/download_ttb_fixtures.py
"""

from __future__ import annotations

import io
import json
from hashlib import sha256
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests/fixtures/labels"

WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

# Each entry mirrors a row in fixtures_manifest.json.
FIXTURES: list[dict] = [
    {
        "fixture_id": "ttb_beer",
        "sample_type": "realistic",
        "source": "ttb-cola",
        "scenario": "single_pass",
        "notes": "Synthetic TTB COLA–style beer label (BEER class, 5% ABV, 12 fl oz).",
        "truth": {
            "brand_name": "GOOD PEOPLE BREWING CO",
            "class_type": "BEER",
            "alcohol_content": "5.0% ALC/VOL",
            "net_contents": "12 FL OZ",
            "government_warning": WARNING,
        },
    },
    {
        "fixture_id": "ttb_wine",
        "sample_type": "realistic",
        "source": "ttb-cola",
        "scenario": "single_pass",
        "notes": "Synthetic TTB COLA–style wine label (TABLE WINE class, 12.5% ABV, 750 mL).",
        "truth": {
            "brand_name": "CHARLES SHAW WINERY",
            "class_type": "TABLE WINE",
            "alcohol_content": "12.5% ALC/VOL",
            "net_contents": "750 ML",
            "government_warning": WARNING,
        },
    },
    {
        "fixture_id": "ttb_spirits",
        "sample_type": "realistic",
        "source": "ttb-cola",
        "scenario": "single_pass",
        "notes": "Synthetic TTB COLA–style spirits label (BOURBON WHISKY, 45% ABV, 750 mL).",
        "truth": {
            "brand_name": "BUFFALO TRACE DISTILLERY",
            "class_type": "BOURBON WHISKY",
            "alcohol_content": "45% ALC/VOL (90 PROOF)",
            "net_contents": "750 ML",
            "government_warning": WARNING,
        },
    },
]

# Background tint per fixture so images look distinct.
_BG_TINTS = [
    (226, 198, 160),  # amber (beer)
    (210, 190, 220),  # mauve (wine)
    (230, 218, 170),  # gold (spirits)
]


def _make_image(fixture: dict, tint: tuple[int, int, int]) -> bytes:
    w, h = 1400, 900
    img = Image.new("RGB", (w, h), color=tint)
    draw = ImageDraw.Draw(img)

    truth = fixture["truth"]
    lines = [
        f"Brand Name: {truth['brand_name']}",
        f"Class/Type: {truth['class_type']}",
        f"Alcohol Content: {truth['alcohol_content']}",
        f"Net Contents: {truth['net_contents']}",
        f"Government Warning: {truth['government_warning']}",
    ]

    y = 40
    for line in lines:
        draw.text((40, y), line, fill=(15, 15, 15))
        y += 60

    # Decorative border lines for visual distinction.
    seed = sum(ord(c) for c in fixture["fixture_id"])
    for i in range(4):
        offset = (seed + i * 37) % h
        draw.line((0, offset, w, (offset + 60) % h), fill=(80, 80, 80), width=1)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _expected(fixture: dict) -> dict:
    return {
        "overall_status": "pass",
        "field_statuses": {
            "brand_name": "pass",
            "class_type": "pass",
            "alcohol_content": "pass",
            "net_contents": "pass",
            "government_warning": "pass",
        },
    }


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

        image_path = images_dir / f"{fid}.png"
        form_path = forms_dir / f"{fid}.json"
        truth_path = truth_dir / f"{fid}.json"
        expected_path = expected_dir / f"{fid}.json"

        image_path.write_bytes(_make_image(fixture, tint))
        _write_json(form_path, fixture["truth"])
        _write_json(truth_path, fixture["truth"])
        _write_json(expected_path, _expected(fixture))

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

        # Replace existing entry if present, otherwise append.
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
